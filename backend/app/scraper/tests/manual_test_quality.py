"""
Manual test — quality scorer + canary on real data.

Usage:
  cd backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python -m app.scraper.tests.manual_test_quality
"""

import asyncio
import sys

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.adapters.wolt import WoltAdapter
from app.scraper.adapters.pyszne import PyszneAdapter
from app.scraper.quality_scorer import score_menu

LAT, LNG = 52.2297, 21.0122


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    for platform, adapter_cls in [("wolt", WoltAdapter), ("pyszne", PyszneAdapter)]:
        print(f"\n{'=' * 60}")
        print(f"QUALITY CHECK: {platform.upper()}")
        print("=" * 60)

        adapter = adapter_cls(redis)

        try:
            restaurants = await adapter.search_restaurants(LAT, LNG, 5.0)
        except Exception as exc:
            print(f"  ✗ Search failed: {exc}")
            continue

        open_rest = next((r for r in restaurants if r.is_online), None)
        if not open_rest:
            print(f"  No open restaurants on {platform}")
            continue

        slug = open_rest.platform_slug
        print(f"  Restaurant: {open_rest.platform_name} ({slug})")

        try:
            items = await adapter.get_menu(slug)
        except Exception as exc:
            print(f"  ✗ Menu failed: {exc}")
            continue

        if not items:
            print(f"  Empty menu (may be closed)")
            continue

        report = score_menu(items, platform=platform, slug=slug)

        status_icon = {"accept": "✓", "warning": "⚠", "reject": "✗"}
        print(f"\n  Score: {report.score:.3f} [{status_icon.get(report.status, '?')} {report.status.upper()}]")
        print(f"  Items: {report.total_items}")
        print(f"  Completeness: {report.completeness:.2f}")
        print(f"  Price range:  {report.price_range:.2f}")
        print(f"  Modifiers:    {report.modifier_quality:.2f}")
        print(f"  Availability: {report.availability:.2f}")

        if report.issues:
            print(f"\n  Issues ({len(report.issues)}):")
            for issue in report.issues[:10]:
                print(f"    - {issue}")

    await redis.aclose()
    print("\n✓ Done!")


if __name__ == "__main__":
    asyncio.run(main())
