"""
Manual test — real Pyszne.pl API.
Usage:
  cd backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python -m app.scraper.tests.manual_test_pyszne

Requires: pip install curl_cffi beautifulsoup4 lxml
"""

import asyncio
import sys

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.adapters.pyszne import PyszneAdapter
from app.scraper.budget_manager import BudgetManager
from app.scraper.circuit_breaker import CircuitBreaker

LAT, LNG = 52.2297, 21.0122


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    adapter = PyszneAdapter(redis)

    print("=" * 60)
    print("SEARCH: Warszawa centrum (Pyszne.pl)")
    print("=" * 60)

    try:
        restaurants = await adapter.search_restaurants(LAT, LNG, 5.0)
    except Exception as exc:
        print(f"\n✗ Search error: {type(exc).__name__}: {exc}")
        await redis.aclose()
        sys.exit(1)

    print(f"Znaleziono: {len(restaurants)} restauracji\n")

    if not restaurants:
        print("Brak wyników.")
        await redis.aclose()
        return

    for i, r in enumerate(restaurants[:10], 1):
        fee = f"{r.delivery_fee.fee_grosz / 100:.2f} zł" if r.delivery_fee else "?"
        eta = f"{r.delivery_fee.estimated_minutes}min" if r.delivery_fee and r.delivery_fee.estimated_minutes else "?"
        rating = f"{r.rating_score:.1f} ({r.rating_count})" if r.rating_score else "?"
        status = "✓" if r.is_online else "✗"
        print(f"  {i:2d}. [{status}] {r.platform_name}")
        print(f"      slug: {r.platform_slug} | fee: {fee} | ETA: {eta} | rating: {rating}")

    # Menu
    open_rest = next((r for r in restaurants if r.is_online), None)
    if not open_rest:
        print("\nBrak otwartych restauracji.")
        await redis.aclose()
        return

    slug = open_rest.platform_slug
    print(f"\n{'=' * 60}")
    print(f"MENU: {open_rest.platform_name} ({slug})")
    print("=" * 60)

    try:
        menu_items = await adapter.get_menu(slug)
    except Exception as exc:
        print(f"\n✗ Menu error: {type(exc).__name__}: {exc}")
        print("  Jeśli 403 → pip install curl_cffi")
        await redis.aclose()
        return

    print(f"Pozycje: {len(menu_items)}\n")

    # Group by category
    cats: dict[str, list] = {}
    for item in menu_items:
        cats.setdefault(item.category_name, []).append(item)

    for cat_name, items in list(cats.items())[:5]:
        print(f"\n  [{cat_name}]")
        for item in items[:4]:
            avail = "✓" if item.is_available else "✗"
            mods = f" ({len(item.modifier_groups)} mod)" if item.modifier_groups else ""
            print(f"    {avail} {item.platform_name}: {item.price_grosz / 100:.2f} zł{mods}")
        if len(items) > 4:
            print(f"    ... +{len(items) - 4}")

    # Show modifiers
    item_with_mods = next((i for i in menu_items if i.modifier_groups), None)
    if item_with_mods:
        print(f"\n--- Modyfikatory: {item_with_mods.platform_name} ---")
        for mg in item_with_mods.modifier_groups[:3]:
            req = "WYMAGANY" if mg.group_type == "required" else "opcjonalny"
            print(f"  {mg.name} [{req}] (min={mg.min_selections}, max={mg.max_selections})")
            for opt in mg.options[:5]:
                d = " ★" if opt.is_default else ""
                a = " [niedostępny]" if not opt.is_available else ""
                print(f"    - {opt.name}: +{opt.price_grosz / 100:.2f} zł{d}{a}")

    # Infra
    print(f"\n{'=' * 60}")
    print("INFRASTRUKTURA")
    print("=" * 60)
    bm = BudgetManager(redis)
    s = await bm.get_status("pyszne")
    print(f"  Budget:  {s['used']}/{s['cap']} ({s['pct_used'] * 100:.1f}%)")
    cb = CircuitBreaker(redis)
    info = await cb.get_info("pyszne")
    print(f"  Circuit: {info['state']} (failures={info['failures']})")
    print(f"  Proxy:   {'ON' if settings.proxy_enabled else 'OFF (direct)'}")
    print("\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
