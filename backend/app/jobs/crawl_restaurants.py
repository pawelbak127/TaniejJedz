"""
Dramatiq actor: nightly full restaurant crawl per city.

Runs at ~3:00 AM CET. For each enabled city:
  1. For each platform: adapter.search_restaurants(city center)
  2. Cache results in Redis
  3. Persist to PostgreSQL via DataPersistor (platform_restaurants with canonical_id=NULL)
  4. Log to scraper_health

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
    """Async core — crawl all platforms for a city, persist to DB."""
    from app.scraper.orchestrator import ScraperOrchestrator

    settings = get_settings()
    redis = AsyncRedis.from_url(settings.redis_url, decode_responses=True)

    try:
        orch = ScraperOrchestrator(redis)
        result = await orch.search_all(lat, lng, radius_km)

        summary: dict = {
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

        # Persist to PostgreSQL
        if settings.persist_enabled:
            persisted_counts = await _persist_search_results(result, city_slug)
            summary["persisted"] = persisted_counts

        return summary
    finally:
        await redis.aclose()


async def _persist_search_results(result, city_slug: str) -> dict[str, dict]:
    """Persist search results from all platforms to PostgreSQL.

    Each platform_restaurant is saved with canonical_restaurant_id=NULL.
    Lat/lng go into dedicated columns on platform_restaurants.
    """
    from app.jobs.db import get_async_session
    from app.services.persistor import DataPersistor

    persisted: dict[str, dict] = {}

    try:
        async with get_async_session() as session:
            persistor = DataPersistor(session)

            for platform, restaurants in result.restaurants.items():
                if not restaurants:
                    continue

                try:
                    stats = await persistor.persist_restaurants(
                        restaurants, city_slug, platform
                    )

                    # Persist delivery fees for restaurants that have them
                    fee_count = 0
                    for nr in restaurants:
                        if nr.delivery_fee and nr.delivery_fee.fee_grosz > 0:
                            pr_id = await persistor.get_platform_restaurant_id(
                                platform, nr.platform_restaurant_id
                            )
                            if pr_id:
                                await persistor.persist_delivery_fee(
                                    nr.delivery_fee, pr_id
                                )
                                fee_count += 1

                    persisted[platform] = {
                        "inserted": stats.inserted,
                        "updated": stats.updated,
                        "errors": stats.errors,
                        "fees": fee_count,
                    }
                except Exception:
                    logger.exception(
                        "persist failed for platform=%s city=%s",
                        platform, city_slug,
                    )
                    persisted[platform] = {"error": "persist_failed"}

            await session.commit()

    except Exception:
        logger.exception("DB session failed during persist for city=%s", city_slug)

    return persisted


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

            # Log persist stats
            persist_info = summary.get("persisted", {})
            persist_str = ", ".join(
                f"{p}: +{s.get('inserted', 0)}/~{s.get('updated', 0)}"
                for p, s in persist_info.items()
                if isinstance(s, dict) and "inserted" in s
            )
            logger.info(
                "crawl_restaurants DONE city=%s total=%d status=%s "
                "persisted=[%s] elapsed=%.0fms",
                slug, total, status, persist_str, elapsed,
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
    redis.ltrim("scraper:health:log", -1000, -1)
