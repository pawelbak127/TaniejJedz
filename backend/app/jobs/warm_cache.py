"""
Dramatiq actor: warm cache for top N restaurants per city.

Runs every 30 minutes. For each city:
  1. Get cached search results (from last crawl_restaurants or user searches)
  2. Pick top N open restaurants
  3. Enqueue crawl_menu jobs for each (staggered — not all at once)

Staggering: if 3 cities, each city's batch runs with 10s offset to avoid
budget spikes.
"""

import asyncio
import json
import logging
import time

import dramatiq
from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_sync_redis() -> SyncRedis:
    return SyncRedis.from_url(get_settings().redis_url, decode_responses=True)


async def _get_top_slugs(
    city_lat: float,
    city_lng: float,
    platforms: list[str],
    top_n: int,
) -> list[tuple[str, str]]:
    """Get top N (platform, slug) pairs from cached search results.

    Falls back to live search if cache is empty.
    """
    settings = get_settings()
    redis = AsyncRedis.from_url(settings.redis_url, decode_responses=True)

    slugs: list[tuple[str, str]] = []

    try:
        for platform in platforms:
            # Try cached search first
            cache_key = f"scraper:search:{platform}:{city_lat:.3f}:{city_lng:.3f}"
            raw = await redis.get(cache_key)

            if raw:
                try:
                    restaurants = json.loads(raw)
                    # Filter to online restaurants, take top N per platform
                    online = [r for r in restaurants if r.get("is_online", False)]
                    for r in online[:top_n]:
                        slug = r.get("platform_slug", "")
                        if slug:
                            slugs.append((platform, slug))
                except (json.JSONDecodeError, KeyError):
                    pass

            if not any(p == platform for p, _ in slugs):
                # No cache — do live search
                logger.info("warm_cache: no cached search for %s, doing live search", platform)
                from app.scraper.orchestrator import ScraperOrchestrator
                orch = ScraperOrchestrator(redis)
                result = await orch.search_all(city_lat, city_lng, 10.0)
                for r in result.restaurants.get(platform, [])[:top_n]:
                    if r.is_online and r.platform_slug:
                        slugs.append((platform, r.platform_slug))

        return slugs[:top_n * len(platforms)]  # cap total
    finally:
        await redis.aclose()


@dramatiq.actor(queue_name="background", max_retries=1)
def warm_cache(city_slug: str | None = None) -> None:
    """Warm cache for top restaurants in a city.

    Schedule: every 30 minutes via external scheduler.

    Usage:
        warm_cache.send("warszawa")  # specific city
        warm_cache.send()            # all cities (staggered)
    """
    from app.jobs.crawl_menus import crawl_menu

    settings = get_settings()
    cities = settings.launch_cities
    platforms = settings.orchestrator_platforms
    top_n = settings.warm_cache_top_n

    if city_slug:
        cities = [c for c in cities if c["slug"] == city_slug]

    for city_idx, city in enumerate(cities):
        slug = city["slug"]
        lat = city["center_lat"]
        lng = city["center_lng"]

        logger.info("warm_cache START city=%s top_n=%d", slug, top_n)
        start = time.monotonic()

        try:
            top_slugs = asyncio.run(
                _get_top_slugs(lat, lng, platforms, top_n)
            )

            # Enqueue menu crawl jobs with staggered delays
            stagger_base_ms = city_idx * 10_000  # 10s offset per city
            for i, (platform, rest_slug) in enumerate(top_slugs):
                delay_ms = stagger_base_ms + (i * 500)  # 500ms between each
                crawl_menu.send_with_options(
                    args=(platform, rest_slug),
                    delay=delay_ms,
                )

            elapsed = (time.monotonic() - start) * 1000
            logger.info(
                "warm_cache DONE city=%s enqueued=%d elapsed=%.0fms",
                slug, len(top_slugs), elapsed,
            )

        except Exception:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("warm_cache FAILED city=%s elapsed=%.0fms", slug, elapsed)
