"""
TaniejJedz.pl — End-to-end price comparison demo.

Searches for restaurants near Warsaw center on all 4 platforms,
finds KFC on each, fetches menus, and compares prices.

Usage (PowerShell, from backend/):
    python diag/diag_e2e_price_compare.py

Requires:
    - Redis running with sitemap data (run sync jobs first)
    - Internet access (for Wolt/Pyszne API + Glovo/UberEats menu fetch)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════
# Setup
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.WARNING,  # Quiet — only errors
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Warsaw center
LAT = 52.2297
LNG = 21.0122
RADIUS_KM = 5.0


def _get_redis_url() -> str:
    url = os.environ.get("REDIS_URL")
    if not url:
        try:
            from app.config import get_settings
            settings = get_settings()
            url = str(getattr(settings, "REDIS_URL", "") or getattr(settings, "redis_url", ""))
        except Exception:
            pass
    if not url:
        url = "redis://:localdevpassword@localhost:6379/0"
    url = re.sub(r"@redis:", "@localhost:", url)
    return url


# ═══════════════════════════════════════════════════════════════
# Adapter initialization
# ═══════════════════════════════════════════════════════════════

async def create_adapters(redis):
    """Try to create all 4 platform adapters."""
    adapters = {}

    # Glovo — sitemap-based (just needs Redis)
    try:
        from app.scraper.adapters.glovo import GlovoAdapter
        adapters["glovo"] = GlovoAdapter(redis)
        print("  ✓ GlovoAdapter")
    except Exception as e:
        print(f"  ✗ GlovoAdapter: {e}")

    # UberEats — sitemap-based (just needs Redis)
    try:
        from app.scraper.adapters.ubereats import UberEatsAdapter
        adapters["ubereats"] = UberEatsAdapter(redis)
        print("  ✓ UberEatsAdapter")
    except Exception as e:
        print(f"  ✗ UberEatsAdapter: {e}")

    # Wolt — live API
    try:
        from app.scraper.adapters.wolt import WoltAdapter
        adapters["wolt"] = WoltAdapter(redis)
        print("  ✓ WoltAdapter")
    except Exception as e:
        print(f"  ✗ WoltAdapter: {e}")

    # Pyszne — live API (needs curl_cffi)
    try:
        from app.scraper.adapters.pyszne import PyszneAdapter
        adapters["pyszne"] = PyszneAdapter(redis)
        print("  ✓ PyszneAdapter")
    except Exception as e:
        print(f"  ✗ PyszneAdapter: {e}")

    return adapters


# ═══════════════════════════════════════════════════════════════
# Search
# ═══════════════════════════════════════════════════════════════

async def search_platform(name: str, adapter, lat: float, lng: float) -> list:
    """Search one platform, return list of NormalizedRestaurant."""
    try:
        start = time.monotonic()
        results = await adapter.search_restaurants(lat, lng, RADIUS_KM)
        elapsed = time.monotonic() - start
        print(f"  {name:10s}: {len(results):>6d} restaurants ({elapsed:.1f}s)")
        return results
    except Exception as e:
        print(f"  {name:10s}: ERROR — {e}")
        return []


def find_kfc(restaurants: list, platform: str) -> list:
    """Find KFC restaurants in search results."""
    kfc = []
    for r in restaurants:
        name_lower = (r.platform_name or r.name or "").lower()
        slug_lower = (r.platform_slug or "").lower()
        if "kfc" in name_lower or "kfc" in slug_lower:
            kfc.append(r)
    return kfc


# ═══════════════════════════════════════════════════════════════
# Menu fetch + price comparison
# ═══════════════════════════════════════════════════════════════

async def fetch_menu(adapter, slug: str, platform: str) -> list:
    """Fetch menu for a restaurant."""
    try:
        start = time.monotonic()
        items = await adapter.get_menu(slug)
        elapsed = time.monotonic() - start
        print(f"  {platform:10s}: {len(items):>4d} items ({elapsed:.1f}s)")
        return items
    except Exception as e:
        print(f"  {platform:10s}: ERROR — {e}")
        return []


def compare_prices(menus: dict[str, list]):
    """Compare prices across platforms for matching items."""
    # Build index: normalized_name → {platform: price_grosz}
    item_prices: dict[str, dict[str, int]] = defaultdict(dict)

    for platform, items in menus.items():
        for item in items:
            # Normalize: lowercase, strip whitespace
            name = (item.platform_name or "").strip()
            name_lower = name.lower()
            # Skip items with price 0 (likely category headers)
            if item.price_grosz <= 0:
                continue
            # Use lowercase name as key (simple matching)
            if name_lower not in item_prices or platform not in item_prices[name_lower]:
                item_prices[name_lower] = item_prices.get(name_lower, {})
                item_prices[name_lower][platform] = item.price_grosz
                # Store display name
                item_prices[name_lower]["_name"] = name

    # Find items available on 2+ platforms
    multi_platform = {
        name: prices for name, prices in item_prices.items()
        if len([k for k in prices if k != "_name"]) >= 2
    }

    return multi_platform


def print_comparison(multi_platform: dict):
    """Pretty-print price comparison table."""
    if not multi_platform:
        print("  Brak pozycji dostępnych na 2+ platformach.")
        print("  (To normalne — nazwy różnią się między platformami)")
        print("  Sprint 4.5 (Menu Item Matching) rozwiąże ten problem.")
        return

    # Sort by number of platforms (most first), then by name
    sorted_items = sorted(
        multi_platform.items(),
        key=lambda x: (-len([k for k in x[1] if k != "_name"]), x[0]),
    )

    platforms = ["wolt", "pyszne", "glovo", "ubereats"]
    header = f"  {'POZYCJA':<40}"
    for p in platforms:
        header += f" {p:>10}"
    header += f" {'OSZCZĘD.':>10}"

    print(header)
    print(f"  {'─'*40}" + f" {'─'*10}" * 4 + f" {'─'*10}")

    total_savings = 0
    items_with_diff = 0

    for name, prices in sorted_items[:30]:  # Top 30
        display_name = prices.get("_name", name)[:38]
        line = f"  {display_name:<40}"

        price_values = []
        for p in platforms:
            if p in prices:
                pln = prices[p] / 100
                line += f" {pln:>9.2f}"
                price_values.append(prices[p])
            else:
                line += f" {'—':>10}"

        # Calculate savings
        if len(price_values) >= 2:
            savings = max(price_values) - min(price_values)
            if savings > 0:
                items_with_diff += 1
                total_savings += savings
                line += f" {savings/100:>9.2f}"
            else:
                line += f" {'=':>10}"

        print(line)

    if len(sorted_items) > 30:
        print(f"  ... i {len(sorted_items) - 30} więcej pozycji")

    print()
    print(f"  Pozycje na 2+ platformach: {len(sorted_items)}")
    print(f"  Z różnicą cen:            {items_with_diff}")
    if total_savings > 0:
        print(f"  Łączne potencjalne oszczędności: {total_savings/100:.2f} zł")


# ═══════════════════════════════════════════════════════════════
# Alternative: raw Redis check (no adapter infrastructure needed)
# ═══════════════════════════════════════════════════════════════

async def quick_redis_check(redis):
    """Quick check of what's in Redis — no adapter needed."""
    print("\n  SZYBKI PODGLĄD REDIS (bez adapterów):")
    print(f"  {'─'*50}")

    # Glovo — Warsaw slugs
    glovo_raw = await redis.get("scraper:glovo:known_slugs:warszawa")
    if glovo_raw:
        glovo_slugs = json.loads(glovo_raw)
        kfc_glovo = [s for s in glovo_slugs if "kfc" in s.lower()]
        print(f"  Glovo Warszawa: {len(glovo_slugs)} restauracji")
        print(f"    KFC slugi: {kfc_glovo[:5]}")
    else:
        print("  Glovo: brak danych (uruchom sync_glovo_slugs)")

    # UberEats — all stores
    ue_raw = await redis.get("scraper:ubereats:known_stores")
    if ue_raw:
        ue_stores = json.loads(ue_raw)
        kfc_ue = [s for s in ue_stores if "kfc" in s.get("slug", "").lower()]
        print(f"  UberEats (cała Polska): {len(ue_stores)} restauracji")
        print(f"    KFC: {len(kfc_ue)} lokali")
        for s in kfc_ue[:5]:
            print(f"      • {s['slug']} → {s['uuid']}")
    else:
        print("  UberEats: brak danych (uruchom sync_ubereats_slugs)")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 65)
    print("  TaniejJedz.pl — E2E PRICE COMPARISON DEMO")
    print(f"  Lokalizacja: Warszawa Centrum ({LAT}, {LNG})")
    print("=" * 65)
    print()

    # Connect Redis
    from redis.asyncio import Redis
    redis_url = _get_redis_url()
    safe_url = re.sub(r"://:[^@]+@", "://:*****@", redis_url)
    print(f"  Redis: {safe_url}")
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        await redis.ping()
        print("  ✓ Connected")
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return

    # Quick Redis check (always works)
    await quick_redis_check(redis)

    # Try to create adapters
    print(f"\n{'─'*65}")
    print("  INICJALIZACJA ADAPTERÓW")
    print(f"{'─'*65}")
    adapters = await create_adapters(redis)

    if not adapters:
        print("\n  Żaden adapter nie załadował się.")
        print("  Sprawdź czy jesteś w katalogu backend/ i masz zainstalowane zależności.")
        await redis.aclose()
        return

    # Search
    print(f"\n{'─'*65}")
    print(f"  SEARCH: restauracje w Warszawie ({LAT}, {LNG})")
    print(f"{'─'*65}")

    all_results: dict[str, list] = {}
    for name, adapter in adapters.items():
        results = await search_platform(name, adapter, LAT, LNG)
        all_results[name] = results

    total = sum(len(r) for r in all_results.values())
    print(f"\n  TOTAL: {total} restauracji na {len(adapters)} platformach")

    # Find KFC
    print(f"\n{'─'*65}")
    print("  SZUKAM KFC na każdej platformie...")
    print(f"{'─'*65}")

    kfc_matches: dict[str, list] = {}
    for name, results in all_results.items():
        kfc = find_kfc(results, name)
        kfc_matches[name] = kfc
        if kfc:
            print(f"  {name:10s}: {len(kfc)} KFC lokali")
            for r in kfc[:3]:
                print(f"    • {r.platform_name or r.name} (slug: {r.platform_slug[:30]}...)")
        else:
            print(f"  {name:10s}: nie znaleziono KFC")

    # Fetch KFC menus
    platforms_with_kfc = {
        name: matches[0] for name, matches in kfc_matches.items() if matches
    }

    if len(platforms_with_kfc) < 2:
        print(f"\n  KFC znalezione na {len(platforms_with_kfc)} platformach — za mało do porównania.")
        print("  Spróbuj innej sieci (McDonald's, Pizza Hut) lub uruchom sync joby.")
        await redis.aclose()
        return

    print(f"\n{'─'*65}")
    print(f"  FETCH MENU: KFC z {len(platforms_with_kfc)} platform")
    print(f"{'─'*65}")

    menus: dict[str, list] = {}
    for name, kfc_restaurant in platforms_with_kfc.items():
        adapter = adapters[name]
        slug = kfc_restaurant.platform_slug
        items = await fetch_menu(adapter, slug, name)
        if items:
            menus[name] = items

    # Compare prices
    if len(menus) >= 2:
        print(f"\n{'─'*65}")
        print(f"  PORÓWNANIE CEN: KFC na {len(menus)} platformach")
        print(f"{'─'*65}\n")

        multi = compare_prices(menus)
        print_comparison(multi)
    else:
        print(f"\n  Menu pobrane z {len(menus)} platform — za mało do porównania.")

    # Summary
    print(f"\n{'='*65}")
    print("  PODSUMOWANIE")
    print(f"{'='*65}")
    for name, items in menus.items():
        avg_price = sum(i.price_grosz for i in items if i.price_grosz > 0) / max(1, len([i for i in items if i.price_grosz > 0]))
        print(f"  {name:10s}: {len(items)} pozycji, śr. cena {avg_price/100:.2f} zł")

    print(f"\n  UWAGA: Porównanie po dokładnej nazwie jest uproszczone.")
    print(f"  Sprint 4.5 (rapidfuzz + spaCy matching) poprawi dopasowanie.")

    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
