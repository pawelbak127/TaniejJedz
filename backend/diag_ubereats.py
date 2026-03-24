"""
Diagnostyka Uber Eats — testuje ile restauracji wyciągniemy
z różnych query terms via getSearchSuggestionsV1.

Uruchom:
  cd C:\Projects\TaniejJedz\backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python diag_ubereats_queries.py
"""

import asyncio
from collections import defaultdict

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.adapters.ubereats import UberEatsAdapter


# Current queries (10)
CURRENT_QUERIES = [
    "pizza", "burger", "sushi", "kebab", "kurczak",
    "KFC", "McDonald", "ramen", "indyjska", "poke",
]

# Extended queries — Polish food, cuisines, chains, popular terms
EXTRA_QUERIES = [
    # Polish food
    "pierogi", "schabowy", "żurek", "naleśniki", "zapiekanka",
    # Cuisine types
    "tajska", "chińska", "meksykańska", "włoska", "turecka",
    # Popular chains
    "Dominos", "Subway", "Starbucks", "Pizza Hut", "Burger King",
    # Food types
    "pad thai", "pho", "tacos", "pasta", "śniadanie",
    "bowl", "vegan", "fit", "zupa", "makaron",
    # Generic
    "jedzenie", "restauracja", "lunch", "obiad", "kolacja",
]


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    adapter = UberEatsAdapter(redis)

    all_discovered: dict[str, dict] = {}  # uuid → {title, slug, source_queries}
    query_yields: dict[str, int] = {}     # query → new unique count

    all_queries = CURRENT_QUERIES + EXTRA_QUERIES

    print(f"Testing {len(all_queries)} query terms...")
    print(f"{'='*60}")

    for i, query in enumerate(all_queries):
        try:
            stores = await adapter._search_suggestions(query)
            new_count = 0
            for s in stores:
                if s.uuid and s.uuid not in all_discovered:
                    all_discovered[s.uuid] = {
                        "title": s.title,
                        "slug": s.slug,
                        "cuisines": s.cuisine_tags,
                        "first_query": query,
                    }
                    new_count += 1
            query_yields[query] = new_count
            total = len(all_discovered)
            marker = f" +{new_count}" if new_count > 0 else ""
            print(f"  [{i+1:2d}/{len(all_queries)}] {query:20s} → {len(stores):2d} results, {new_count:2d} new (total: {total}){marker}")
        except Exception as exc:
            print(f"  [{i+1:2d}/{len(all_queries)}] {query:20s} → ERROR: {exc}")
            query_yields[query] = 0

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"  Total unique restaurants: {len(all_discovered)}")
    print(f"  From current 10 queries: {sum(query_yields.get(q, 0) for q in CURRENT_QUERIES)}")
    print(f"  From extra queries:      {sum(query_yields.get(q, 0) for q in EXTRA_QUERIES)}")

    # Top yielding queries
    print(f"\n  Top queries by new discoveries:")
    for q, count in sorted(query_yields.items(), key=lambda x: -x[1])[:15]:
        if count > 0:
            src = "CURRENT" if q in CURRENT_QUERIES else "NEW"
            print(f"    {q:20s} +{count:2d} [{src}]")

    # Zero-yield queries
    zero = [q for q, c in query_yields.items() if c == 0]
    if zero:
        print(f"\n  Zero-yield queries ({len(zero)}): {', '.join(zero[:20])}")

    # All restaurants
    print(f"\n  All discovered restaurants:")
    for uuid, info in sorted(all_discovered.items(), key=lambda x: x[1]["title"]):
        cuisines = ", ".join(info["cuisines"][:3]) if info["cuisines"] else ""
        print(f"    {info['title'][:40]:40s} [{cuisines}] (via '{info['first_query']}')")

    print(f"\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())