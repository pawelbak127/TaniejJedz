"""
Manual test — orchestrator parallel search on Wolt + Pyszne.

Usage:
  cd backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python -m app.scraper.tests.manual_test_orchestrator
"""

import asyncio
import sys

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.orchestrator import ScraperOrchestrator

LAT, LNG = 52.2297, 21.0122


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    orch = ScraperOrchestrator(redis)

    print("=" * 60)
    print("ORCHESTRATOR: parallel search Wolt + Pyszne")
    print(f"Location: {LAT}, {LNG} (Warszawa centrum)")
    print("=" * 60)

    result = await orch.search_all(LAT, LNG, 5.0)

    for platform in ["wolt", "pyszne"]:
        restaurants = result.restaurants.get(platform, [])
        error = result.errors.get(platform)
        cached = platform in result.from_cache
        elapsed = result.timings.get(platform, 0)

        status = "CACHE" if cached else f"{elapsed:.0f}ms"
        if error:
            status = f"ERROR: {error[:60]}"

        print(f"\n  [{platform.upper()}] {len(restaurants)} restaurants ({status})")
        for r in restaurants[:5]:
            online = "✓" if r.is_online else "✗"
            print(f"    {online} {r.platform_name} ({r.platform_slug})")
        if len(restaurants) > 5:
            print(f"    ... +{len(restaurants) - 5}")

    total = len(result.all_restaurants)
    print(f"\n  TOTAL: {total} restaurants across {len(result.restaurants)} platforms")
    print(f"  Errors: {len(result.errors)}")
    print(f"  From cache: {result.from_cache or 'none'}")

    # Try menu for first open restaurant per platform
    slugs = {}
    for platform, restaurants in result.restaurants.items():
        open_rest = next((r for r in restaurants if r.is_online), None)
        if open_rest:
            slugs[platform] = open_rest.platform_slug

    if slugs:
        print(f"\n{'=' * 60}")
        print(f"MENU: parallel fetch for {slugs}")
        print("=" * 60)

        menu_result = await orch.get_menu_all(slugs)

        for platform, items in menu_result.menus.items():
            cached = platform in menu_result.from_cache
            elapsed = menu_result.timings.get(platform, 0)
            error = menu_result.errors.get(platform)

            if error:
                print(f"\n  [{platform.upper()}] ERROR: {error[:80]}")
            else:
                status = "CACHE" if cached else f"{elapsed:.0f}ms"
                print(f"\n  [{platform.upper()}] {len(items)} items ({status})")
                for item in items[:5]:
                    mods = f" ({len(item.modifier_groups)} mod)" if item.modifier_groups else ""
                    print(f"    {item.platform_name}: {item.price_grosz / 100:.2f} zł{mods}")
                if len(items) > 5:
                    print(f"    ... +{len(items) - 5}")

    print("\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
