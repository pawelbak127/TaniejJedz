"""
Diagnostyka UberEats — timing każdego kroku search_restaurants().
Uruchom:
  cd C:\Projects\TaniejJedz\backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python diag_ubereats_timing.py
"""

import asyncio
import time
import traceback

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.adapters.ubereats import UberEatsAdapter, _SEARCH_QUERIES, _SUGGESTION_CONCURRENCY


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    adapter = UberEatsAdapter(redis)

    print(f"Queries: {len(_SEARCH_QUERIES)}")
    print(f"Concurrency: {_SUGGESTION_CONCURRENCY}")
    print(f"Orchestrator timeout: {settings.orchestrator_timeout}s")
    print(f"Scraper timeout: {settings.scraper_timeout_realtime}s")

    # Step 1: Time individual query
    print(f"\n{'='*60}")
    print("STEP 1: Single query timing (3 queries)")
    print("="*60)
    for q in _SEARCH_QUERIES[:3]:
        start = time.monotonic()
        try:
            stores = await adapter._search_suggestions(q)
            elapsed = (time.monotonic() - start) * 1000
            print(f"  '{q}': {len(stores)} stores, {elapsed:.0f}ms")
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            print(f"  '{q}': ERROR {exc}, {elapsed:.0f}ms")

    # Step 2: Time full search
    print(f"\n{'='*60}")
    print("STEP 2: Full search_restaurants() timing")
    print("="*60)
    start = time.monotonic()
    try:
        restaurants = await adapter.search_restaurants(50.0614, 19.9372, 5.0)
        elapsed = (time.monotonic() - start) * 1000
        print(f"  Result: {len(restaurants)} restaurants in {elapsed:.0f}ms")
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        print(f"  ERROR: {type(exc).__name__}: {exc} in {elapsed:.0f}ms")
        traceback.print_exc()

    # Step 3: Time with asyncio.wait_for (simulating orchestrator)
    print(f"\n{'='*60}")
    print("STEP 3: With orchestrator timeout (8s)")
    print("="*60)
    # Flush cache first
    keys = []
    async for key in redis.scan_iter("scraper:ubereats:*"):
        keys.append(key)
    if keys:
        await redis.delete(*keys)
        print(f"  Flushed {len(keys)} cache keys")

    start = time.monotonic()
    try:
        restaurants = await asyncio.wait_for(
            adapter.search_restaurants(50.0614, 19.9372, 5.0),
            timeout=8.0,
        )
        elapsed = (time.monotonic() - start) * 1000
        print(f"  OK: {len(restaurants)} restaurants in {elapsed:.0f}ms")
    except asyncio.TimeoutError:
        elapsed = (time.monotonic() - start) * 1000
        print(f"  TIMEOUT after {elapsed:.0f}ms")
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        print(f"  ERROR: {type(exc).__name__}: {exc} in {elapsed:.0f}ms")

    # Step 4: Budget check (how many requests consumed)
    print(f"\n{'='*60}")
    print("STEP 4: Budget status")
    print("="*60)
    from app.scraper.budget_manager import BudgetManager
    bm = BudgetManager(redis)
    status = await bm.get_status("ubereats")
    print(f"  Used: {status['used']}/{status['cap']}")

    print("\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())