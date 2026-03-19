"""
Dramatiq actor: nightly full restaurant crawl per city.

Runs at ~3:00 AM CET. For each enabled city:
  1. For each platform: adapter.search_restaurants(city center)
  2. Cache results in Redis
  3. Log to scraper_health

Pattern: sync Dramatiq actor → asyncio.run() for async adapters.
Uses sync Redis for Dramatiq (same as compare_worker.py).
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


async def _crawl_city_async(
    city_slug: str,
    lat: float,
    lng: float,
    radius_km: float,
    platforms: list[str],
) -> dict:
    """Async core — crawl all platforms for a city."""
    from app.scraper.orchestrator import ScraperOrchestrator

    settings = get_settings()
    redis = AsyncRedis.from_url(settings.redis_url, decode_responses=True)

    try:
        orch = ScraperOrchestrator(redis)
        result = await orch.search_all(lat, lng, radius_km)

        summary = {
            "city": city_slug,
            "platforms": {},
        }
        for platform in platforms:
            restaurants = result.restaurants.get(platform, [])
            error = result.errors.get(platform)
            from_cache = platform in result.from_cache
            summary["platforms"][platform] = {
                "count": len(restaurants),
                "from_cache": from_cache,
                "error": error,
                "elapsed_ms": result.timings.get(platform, 0),
            }

        return summary
    finally:
        await redis.aclose()


@dramatiq.actor(queue_name="background", max_retries=2, min_backoff=60_000)
def crawl_restaurants(city_slug: str | None = None) -> None:
    """Crawl restaurants for a city (or all cities if city_slug is None).

    Schedule: nightly at 3:00 AM CET via external scheduler or crontab.

    Usage:
        crawl_restaurants.send("warszawa")   # single city
        crawl_restaurants.send()              # all cities
    """
    settings = get_settings()
    cities = settings.launch_cities
    platforms = settings.orchestrator_platforms

    if city_slug:
        cities = [c for c in cities if c["slug"] == city_slug]
        if not cities:
            logger.error("City %s not found in launch_cities", city_slug)
            return

    for city in cities:
        slug = city["slug"]
        lat = city["center_lat"]
        lng = city["center_lng"]
        radius = city.get("radius_km", 15)

        logger.info("crawl_restaurants START city=%s lat=%.4f lng=%.4f", slug, lat, lng)
        start = time.monotonic()

        try:
            summary = asyncio.run(
                _crawl_city_async(slug, lat, lng, radius, platforms)
            )
            elapsed = (time.monotonic() - start) * 1000

            # Log to Redis for scraper health tracking
            _log_health(_get_sync_redis(), slug, "crawl_restaurants", summary, elapsed)

            total = sum(p["count"] for p in summary["platforms"].values())
            errors = [p for p in summary["platforms"].values() if p.get("error")]
            status = "partial" if errors else "success"
            logger.info(
                "crawl_restaurants DONE city=%s total=%d status=%s elapsed=%.0fms",
                slug, total, status, elapsed,
            )

        except Exception:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("crawl_restaurants FAILED city=%s elapsed=%.0fms", slug, elapsed)


def _log_health(
    redis: SyncRedis,
    city: str,
    job_type: str,
    summary: dict,
    elapsed_ms: float,
) -> None:
    """Write scraper health entry to Redis list (flushed to DB by separate job)."""
    entry = {
        "city": city,
        "job_type": job_type,
        "summary": summary,
        "elapsed_ms": int(elapsed_ms),
        "timestamp": time.time(),
    }
    redis.rpush("scraper:health:log", json.dumps(entry, default=str))
    # Keep max 1000 entries
    redis.ltrim("scraper:health:log", -1000, -1)
