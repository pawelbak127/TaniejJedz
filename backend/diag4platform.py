"""
4-platform KFC comparison — Kraków Kazimierz via Orchestrator.

Uruchom:
  cd C:\Projects\TaniejJedz\backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python diag_4platform_kfc.py
"""

import asyncio
import time
from collections import defaultdict

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.orchestrator import ScraperOrchestrator
from app.scraper.quality_scorer import score_menu

# Kraków Kazimierz
LAT, LNG = 50.0490, 19.9455


def _find_kfc(result) -> dict[str, str]:
    """Find KFC slug/uuid on each platform from search results."""
    slugs = {}
    for platform, restaurants in result.restaurants.items():
        kfc = next(
            (r for r in restaurants if "kfc" in r.name.lower() and r.is_online),
            next((r for r in restaurants if "kfc" in r.name.lower()), None),
        )
        if kfc:
            slugs[platform] = kfc.platform_slug
            print(f"  [{platform.upper():9s}] {kfc.name[:40]:40s} slug={kfc.platform_slug[:50]}")
        else:
            print(f"  [{platform.upper():9s}] KFC not found")
    return slugs


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    orch = ScraperOrchestrator(redis)

    # ═══════════════════════════════════════════════════════
    # PART 1: Parallel search — all 4 platforms
    # ═══════════════════════════════════════════════════════

    print("=" * 70)
    print("KRAKÓW KAZIMIERZ — 4-PLATFORM SEARCH (via Orchestrator)")
    print(f"Location: {LAT}, {LNG}")
    print("=" * 70)

    start = time.monotonic()
    result = await orch.search_all(LAT, LNG, 5.0)
    total_ms = (time.monotonic() - start) * 1000

    for platform in ["wolt", "pyszne", "glovo", "ubereats"]:
        restaurants = result.restaurants.get(platform, [])
        error = result.errors.get(platform)
        elapsed = result.timings.get(platform, 0)
        cached = platform in result.from_cache

        if error:
            print(f"\n  [{platform.upper():9s}] ✗ ERROR: {str(error)[:80]}")
        else:
            status = "CACHE" if cached else f"{elapsed:.0f}ms"
            online = sum(1 for r in restaurants if r.is_online)
            print(f"\n  [{platform.upper():9s}] {len(restaurants):4d} restaurants ({online} online) [{status}]")

    total = len(result.all_restaurants)
    print(f"\n  {'─' * 55}")
    print(f"  TOTAL: {total} restaurants ({total_ms:.0f}ms)")

    # ═══════════════════════════════════════════════════════
    # PART 2: Find KFC on each platform
    # ═══════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print("KFC — SLUG DISCOVERY")
    print("=" * 70)

    kfc_slugs = _find_kfc(result)

    if len(kfc_slugs) < 2:
        print(f"\n  KFC found on only {len(kfc_slugs)} platform(s). Need 2+.")
        await redis.aclose()
        return

    # ═══════════════════════════════════════════════════════
    # PART 3: Fetch menus via orchestrator
    # ═══════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print(f"KFC — MENU FETCH via Orchestrator ({len(kfc_slugs)} platforms)")
    print("=" * 70)

    start = time.monotonic()
    menu_result = await orch.get_menu_all(kfc_slugs)
    menu_ms = (time.monotonic() - start) * 1000

    for platform in ["wolt", "pyszne", "glovo", "ubereats"]:
        items = menu_result.menus.get(platform, [])
        error = menu_result.errors.get(platform)
        elapsed = menu_result.timings.get(platform, 0)
        cached = platform in menu_result.from_cache

        if error:
            print(f"  [{platform.upper():9s}] ✗ {str(error)[:80]}")
            continue
        if not items:
            if platform in kfc_slugs:
                print(f"  [{platform.upper():9s}] ✗ empty menu")
            continue

        report = score_menu(items, platform, kfc_slugs.get(platform, ""))
        avail = sum(1 for i in items if i.is_available)
        mods = sum(1 for i in items if i.modifier_groups)
        status = "CACHE" if cached else f"{elapsed:.0f}ms"
        print(f"  [{platform.upper():9s}] {len(items):3d} items ({avail} avail, {mods} mods) "
              f"Quality: {report.score:.3f} [{report.status.upper()}] [{status}]")

    print(f"\n  Menu fetch: {menu_ms:.0f}ms total")

    # ═══════════════════════════════════════════════════════
    # PART 4: Price comparison
    # ═══════════════════════════════════════════════════════

    platform_items = {}
    for name, items in menu_result.menus.items():
        lookup = {}
        for item in items:
            norm = item.platform_name.lower().strip()
            if norm and item.price_grosz > 0:
                lookup[norm] = (item.platform_name, item.price_grosz)
        platform_items[name] = lookup

    if len(platform_items) < 2:
        print(f"\n  Need 2+ platform menus for comparison. Got: {list(platform_items.keys())}")
        await redis.aclose()
        return

    print(f"\n{'='*70}")
    print("KFC — PRICE COMPARISON")
    print("=" * 70)

    all_names = set()
    for lookup in platform_items.values():
        all_names.update(lookup.keys())

    comparisons = []
    for norm_name in sorted(all_names):
        prices = {}
        display_name = norm_name
        for platform, lookup in platform_items.items():
            if norm_name in lookup:
                orig_name, price = lookup[norm_name]
                prices[platform] = price
                display_name = orig_name

        if len(prices) >= 2:
            cheapest = min(prices, key=prices.get)
            most_exp = max(prices, key=prices.get)
            diff = prices[most_exp] - prices[cheapest]
            diff_pct = (diff / prices[cheapest] * 100) if prices[cheapest] > 0 else 0
            comparisons.append((display_name, prices, cheapest, diff_pct))

    comparisons.sort(key=lambda x: -x[3])

    if not comparisons:
        print("\n  No items matched across platforms by name.")
        await redis.aclose()
        return

    platforms_with_menu = sorted(platform_items.keys())
    items_on_all = sum(1 for _, prices, _, _ in comparisons if len(prices) == len(platforms_with_menu))
    items_with_diff = sum(1 for _, _, _, d in comparisons if d > 0)
    total_savings = sum(max(p.values()) - min(p.values()) for _, p, _, _ in comparisons)

    print(f"\n  Platforms with menu: {', '.join(platforms_with_menu)}")
    print(f"  Items matched on 2+: {len(comparisons)}")
    print(f"  Items on ALL platforms: {items_on_all}")
    print(f"  Items with price diff: {items_with_diff}")
    print(f"  Total potential savings: {total_savings / 100:.2f} zł\n")

    header = f"  {'Pozycja':40s}"
    for p in platforms_with_menu:
        header += f" {p:>10s}"
    header += "     diff"
    print(header)
    print(f"  {'─' * (42 + 11 * len(platforms_with_menu) + 10)}")

    shown = 0
    for display_name, prices, cheapest, diff_pct in comparisons:
        if shown >= 40:
            print(f"  ... +{len(comparisons) - 40} more items")
            break
        shown += 1

        row = f"  {display_name[:40]:40s}"
        for p in platforms_with_menu:
            if p in prices:
                price_str = f"{prices[p] / 100:.2f}"
                marker = "*" if p == cheapest and diff_pct > 0 else " "
                row += f" {price_str:>9s}{marker}"
            else:
                row += f" {'—':>10s}"

        if diff_pct > 10:
            row += f"  ⚠ {diff_pct:.0f}%"
        elif diff_pct > 0:
            row += f"    {diff_pct:.0f}%"

        print(row)

    # Platform ranking
    print(f"\n  {'─' * 55}")
    wins = defaultdict(int)
    for _, prices, cheapest, diff_pct in comparisons:
        if diff_pct > 0:
            wins[cheapest] += 1

    if wins:
        print(f"  PLATFORM RANKING (cheapest wins):")
        for platform, count in sorted(wins.items(), key=lambda x: -x[1]):
            pct = count / len(comparisons) * 100
            print(f"    {platform:10s}: cheapest on {count:3d}/{len(comparisons)} items ({pct:.0f}%)")
    else:
        print(f"  ALL PRICES IDENTICAL across platforms!")

    # ═══════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print("SUMMARY")
    print("=" * 70)
    for platform in ["wolt", "pyszne", "glovo", "ubereats"]:
        r_count = len(result.restaurants.get(platform, []))
        m_count = len(menu_result.menus.get(platform, []))
        slug = kfc_slugs.get(platform, "—")
        r_ok = "✓" if platform not in result.errors else "✗"
        m_ok = "✓" if m_count > 0 else "✗"
        print(f"  {platform:9s}: search {r_ok} ({r_count:4d}) | menu {m_ok} ({m_count:3d}) | slug: {slug[:50]}")

    print(f"\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())