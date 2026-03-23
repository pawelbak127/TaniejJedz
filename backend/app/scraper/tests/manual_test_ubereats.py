"""
Manual test — real Uber Eats API.
Usage:
  cd backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python -m app.scraper.tests.manual_test_ubereats
"""

import asyncio
import sys

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.adapters.ubereats import UberEatsAdapter

# Known UUIDs (from DevTools)
BOLLYWOOD_UUID = "6aaa3cb9-03a0-5d35-a00a-500f982d2120"


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    adapter = UberEatsAdapter(redis)

    store_uuid = BOLLYWOOD_UUID

    # 0. Search via suggestions
    print("=" * 60)
    print("UBER EATS: search (via suggestions)")
    print("=" * 60)

    try:
        restaurants = await adapter.search_restaurants(52.2297, 21.0122, 5.0)
        print(f"\n  Found: {len(restaurants)} restaurants")
        online = sum(1 for r in restaurants if r.is_online)
        print(f"  Online: {online}")
        for r in restaurants[:10]:
            icon = "✓" if r.is_online else "✗"
            cuisines = ", ".join(r.cuisine_tags[:3]) if r.cuisine_tags else ""
            print(f"    {icon} {r.platform_name[:45]:45s} [{cuisines}]")
        if len(restaurants) > 10:
            print(f"    ... +{len(restaurants) - 10}")
    except Exception as exc:
        print(f"  ✗ Search failed: {exc}")

    print(f"\n{'=' * 60}")
    print(f"UBER EATS: store + menu for {store_uuid[:20]}...")
    print("=" * 60)

    # 1. Store info
    print("\n--- Store Info ---")
    try:
        store_info = await adapter.get_store_info(store_uuid)
        print(f"  Name: {store_info.name}")
        print(f"  Address: {store_info.address_street}, {store_info.address_city}")
        print(f"  Open: {store_info.is_online}")
        print(f"  Rating: {store_info.rating_score} ({store_info.rating_count} reviews)")
        print(f"  Cuisines: {store_info.cuisine_tags}")
        print(f"  Service fee: {store_info.delivery_fee.fee_grosz / 100:.2f} zł")
    except Exception as exc:
        print(f"  ✗ Store info failed: {exc}")
        await redis.aclose()
        sys.exit(1)

    # 2. Menu
    print("\n--- Menu ---")
    try:
        items = await adapter.get_menu(store_uuid)
        print(f"  Items: {len(items)}")

        cats: dict[str, list] = {}
        for item in items:
            cats.setdefault(item.category_name, []).append(item)

        for cat_name, cat_items in list(cats.items())[:8]:
            print(f"\n  [{cat_name}]")
            for item in cat_items[:4]:
                avail = "✓" if item.is_available else "✗"
                print(f"    {avail} {item.platform_name[:40]:40s} {item.price_grosz / 100:7.2f} zł")
            if len(cat_items) > 4:
                print(f"    ... +{len(cat_items) - 4}")

    except Exception as exc:
        print(f"  ✗ Menu failed: {exc}")

    # 3. Quality
    if items:
        from app.scraper.quality_scorer import score_menu
        report = score_menu(items, "ubereats", store_uuid[:12])
        print(f"\n--- Quality ---")
        print(f"  Score: {report.score:.3f} [{report.status.upper()}]")

    print("\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
