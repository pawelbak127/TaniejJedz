"""
Diagnostyka — dlaczego Wolt KFC Kazimierz ma 12 items vs 185 Floriańska.

Uruchom:
  cd C:\Projects\TaniejJedz\backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python diag_wolt_kfc.py
"""

import asyncio
import json
import httpx

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.adapters.wolt import WoltAdapter

# KFC slugs from search results
KFC_SLUGS = [
    "kfc-krakw-kazimierz",           # from Kazimierz search (12 items)
    "kfc-krakow-kazimierz",          # possible correct spelling
    "kfc-krakow-florianska-103102",  # from Rynek search (185 items)
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://wolt.com",
    "Wolt-Language": "pl",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
}

MENU_URL = "https://consumer-api.wolt.com/consumer-api/venue-content-api/v3/web/venue-content/slug"


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    adapter = WoltAdapter(redis)

    # Step 1: Raw API call per slug
    print("=" * 60)
    print("STEP 1: Raw menu API per slug")
    print("=" * 60)

    for slug in KFC_SLUGS:
        url = f"{MENU_URL}/{slug}"
        print(f"\n  --- {slug} ---")
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15)
            print(f"  Status: {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                # Count sections and items
                sections = data.get("sections", [])
                if not sections:
                    # Try nested
                    for key in ("page", "content"):
                        nested = data.get(key, {})
                        if isinstance(nested, dict) and "sections" in nested:
                            sections = nested["sections"]
                            break

                total_items = 0
                total_options = 0
                print(f"  Sections: {len(sections)}")
                for s in sections:
                    items = s.get("items", [])
                    options = s.get("options", [])
                    total_items += len(items)
                    total_options += len(options)
                    print(f"    [{s.get('name', '?'):30s}] {len(items):3d} items, {len(options):3d} options")

                print(f"  Total: {total_items} items, {total_options} options")
            elif resp.status_code == 404:
                print(f"  NOT FOUND: {resp.text[:200]}")
            else:
                print(f"  Body: {resp.text[:200]}")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    # Step 2: Search Kazimierz, find all KFC variants
    print(f"\n{'='*60}")
    print("STEP 2: All KFC in Wolt search (Kazimierz)")
    print("=" * 60)

    restaurants = await adapter.search_restaurants(50.0490, 19.9455, 5.0)
    kfc_matches = [r for r in restaurants if "kfc" in r.name.lower()]
    print(f"  KFC matches: {len(kfc_matches)}")
    for r in kfc_matches:
        online = "✓" if r.is_online else "✗"
        print(f"    {online} {r.name[:45]:45s} slug={r.platform_slug}")

    # Step 3: Fetch menu via adapter for each KFC
    print(f"\n{'='*60}")
    print("STEP 3: Menu via adapter for each KFC slug")
    print("=" * 60)

    for r in kfc_matches[:5]:
        slug = r.platform_slug
        print(f"\n  --- {r.name} ({slug}) ---")
        try:
            items = await adapter.get_menu(slug)
            cats = {}
            for item in items:
                cats.setdefault(item.category_name, []).append(item)
            print(f"  Items: {len(items)}, Categories: {len(cats)}")
            for cat_name, cat_items in cats.items():
                print(f"    [{cat_name}]: {len(cat_items)} items")
        except Exception as exc:
            print(f"  ERROR: {type(exc).__name__}: {exc}")

    print("\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())