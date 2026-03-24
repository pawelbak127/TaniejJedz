"""
Diagnostyka Glovo v2 — HTML scraping + RSC parsing.
Testuje nowy adapter bez API probing.

Uruchom:
  cd C:\Projects\TaniejJedz\backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python diag_glovo_v2.py
"""

import asyncio
import traceback

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.adapters.glovo import GlovoAdapter


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    adapter = GlovoAdapter(redis)

    LAT, LNG = 50.0614, 19.9372  # Kraków
    adapter._set_city(LAT, LNG)
    print(f"City: {adapter._city_code} / {adapter._city_slug} / {adapter._city_short}")

    # ── Step 1: Search (HTML scraping) ──
    print(f"\n{'='*60}")
    print("STEP 1: search_restaurants (HTML scraping)")
    print("="*60)
    try:
        restaurants = await adapter.search_restaurants(LAT, LNG, 5.0)
        print(f"  Found: {len(restaurants)} restaurants")
        for r in restaurants[:10]:
            print(f"    {r.name[:40]:40s} slug={r.platform_slug}")
        if len(restaurants) > 10:
            print(f"    ... +{len(restaurants) - 10} more")
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        restaurants = []

    # ── Step 2: Menu for KFC (RSC parsing) ──
    print(f"\n{'='*60}")
    print("STEP 2: get_menu('kfc-kra') — RSC parsing")
    print("="*60)
    try:
        items = await adapter.get_menu("kfc-kra")
        print(f"  Items: {len(items)}")

        cats: dict[str, list] = {}
        for item in items:
            cats.setdefault(item.category_name, []).append(item)

        for cat_name, cat_items in list(cats.items())[:5]:
            print(f"\n  [{cat_name}]")
            for item in cat_items[:3]:
                avail = "✓" if item.is_available else "✗"
                mods = f" ({len(item.modifier_groups)} mod)" if item.modifier_groups else ""
                print(f"    {avail} {item.platform_name[:40]:40s} {item.price_grosz/100:7.2f} zł{mods}")
            if len(cat_items) > 3:
                print(f"    ... +{len(cat_items) - 3}")

        # Quality check
        from app.scraper.quality_scorer import score_menu
        report = score_menu(items, "glovo", "kfc-kra")
        print(f"\n  Quality: {report.score:.3f} [{report.status.upper()}]")

    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc()

    # ── Step 3: Store detail from RSC ──
    print(f"\n{'='*60}")
    print("STEP 3: Store detail from RSC (delivery fee etc.)")
    print("="*60)
    try:
        store_data, _ = await adapter._fetch_store_page("kfc-kra")
        if store_data:
            print(f"  id: {store_data.get('id')}")
            print(f"  name: {store_data.get('name')}")
            print(f"  slug: {store_data.get('slug')}")
            print(f"  open: {store_data.get('open')}")
            print(f"  cityCode: {store_data.get('cityCode')}")
            print(f"  addressId: {store_data.get('addressId')}")
            fee_info = store_data.get('deliveryFeeInfo', {})
            print(f"  deliveryFee: {fee_info.get('fee')} PLN")
            print(f"  serviceFee: {store_data.get('serviceFee')} PLN")
            print(f"  filters: {[f.get('displayName') for f in store_data.get('filters', [])]}")
        else:
            print("  Store data not found in RSC")
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc()

    print("\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
