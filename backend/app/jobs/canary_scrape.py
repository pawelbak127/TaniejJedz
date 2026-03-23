"""
Dramatiq actor: canary scrape — validate scrapers are still working.

Runs every 2 hours. For each platform:
  1. Search sample (1 request, top results)
  2. Pick first open restaurant → fetch menu (1 request)
  3. Validate response through Pydantic schemas
  4. Score quality via quality_scorer
  5. On ValidationError → SCHEMA_DRIFT alert
  6. Log results to scraper_health (Redis → flushed to DB)

Total: 2 requests per platform per run = 4 requests/run × 12 runs/day = 48 requests/day.
Uses Priority.CRITICAL so budget never blocks canary.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import dramatiq
from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from app.config import get_settings
from app.scraper.quality_scorer import score_menu, QualityReport

logger = logging.getLogger(__name__)


@dataclass
class CanaryResult:
    platform: str
    status: str  # "ok" | "schema_drift" | "search_failed" | "menu_failed" | "quality_reject"
    search_count: int = 0
    menu_count: int = 0
    quality_score: float = 0.0
    error: str | None = None
    elapsed_ms: float = 0


async def _canary_platform(platform: str) -> CanaryResult:
    """Run canary check for a single platform."""
    from app.scraper.adapters.wolt import WoltAdapter
    from app.scraper.adapters.pyszne import PyszneAdapter
    from app.scraper.adapters.glovo import GlovoAdapter
    from app.scraper.adapters.ubereats import UberEatsAdapter
    from app.scraper.budget_manager import Priority

    settings = get_settings()
    redis = AsyncRedis.from_url(settings.redis_url, decode_responses=True)

    adapters = {"wolt": WoltAdapter, "pyszne": PyszneAdapter, "glovo": GlovoAdapter, "ubereats": UberEatsAdapter}
    adapter_cls = adapters.get(platform)
    if not adapter_cls:
        return CanaryResult(platform=platform, status="unknown_platform", error=f"Unknown: {platform}")

    start = time.monotonic()
    result = CanaryResult(platform=platform, status="ok")

    try:
        adapter = adapter_cls(redis)

        # Use Warszawa centrum as canary location
        city = settings.launch_cities[0] if settings.launch_cities else {
            "center_lat": 52.2297, "center_lng": 21.0122,
        }
        lat = city.get("center_lat", 52.2297)
        lng = city.get("center_lng", 21.0122)

        # 1. Search
        try:
            restaurants = await adapter.search_restaurants(
                lat, lng, 5.0, priority=Priority.CRITICAL,
            )
            result.search_count = len(restaurants)
        except Exception as exc:
            result.status = "search_failed"
            result.error = f"Search: {type(exc).__name__}: {exc}"
            return result

        if not restaurants:
            result.status = "search_failed"
            result.error = "Search returned 0 restaurants"
            return result

        # 2. Menu — pick first open restaurant
        open_rest = next((r for r in restaurants if r.is_online), restaurants[0])
        slug = open_rest.platform_slug

        try:
            menu_items = await adapter.get_menu(slug, priority=Priority.CRITICAL)
            result.menu_count = len(menu_items)
        except Exception as exc:
            exc_name = type(exc).__name__
            if "Schema" in exc_name or "Validation" in exc_name or "Parse" in exc_name:
                result.status = "schema_drift"
                result.error = f"SCHEMA_DRIFT on {slug}: {exc_name}: {str(exc)[:200]}"
            else:
                result.status = "menu_failed"
                result.error = f"Menu {slug}: {exc_name}: {exc}"
            return result

        # 3. Quality scoring
        if menu_items:
            report = score_menu(menu_items, platform=platform, slug=slug)
            result.quality_score = report.score

            if report.status == "reject":
                result.status = "quality_reject"
                result.error = f"Quality {report.score:.3f} < 0.6: {'; '.join(report.issues[:5])}"
        else:
            # Empty menu — might be nocturnal, not a failure
            result.quality_score = 0.0
            logger.info("canary %s/%s: empty menu (may be closed)", platform, slug)

    except Exception as exc:
        result.status = "search_failed"
        result.error = f"Unexpected: {type(exc).__name__}: {exc}"
    finally:
        result.elapsed_ms = (time.monotonic() - start) * 1000
        await redis.aclose()

    return result


async def _run_canary_all(platforms: list[str]) -> list[CanaryResult]:
    """Run canary on all platforms sequentially (to avoid budget spikes)."""
    results = []
    for platform in platforms:
        result = await _canary_platform(platform)
        results.append(result)
        logger.info(
            "canary %s: %s (search=%d menu=%d quality=%.3f elapsed=%.0fms)%s",
            platform, result.status, result.search_count, result.menu_count,
            result.quality_score, result.elapsed_ms,
            f" ERROR: {result.error}" if result.error else "",
        )
    return results


def _log_canary_health(results: list[CanaryResult]) -> None:
    """Write canary results to Redis for scraper_health tracking."""
    settings = get_settings()
    redis = SyncRedis.from_url(settings.redis_url, decode_responses=True)

    for r in results:
        entry = {
            "platform": r.platform,
            "job_type": "canary_scrape",
            "status": r.status,
            "records_fetched": r.search_count + r.menu_count,
            "quality_score": r.quality_score,
            "error_message": r.error,
            "duration_ms": int(r.elapsed_ms),
            "timestamp": time.time(),
        }
        redis.rpush("scraper:health:log", json.dumps(entry, default=str))

        # Set alert key if schema drift detected
        if r.status == "schema_drift":
            alert_key = f"scraper:alert:schema_drift:{r.platform}"
            redis.setex(alert_key, 86400, json.dumps({
                "platform": r.platform,
                "error": r.error,
                "timestamp": time.time(),
            }))
            logger.critical(
                "🚨 SCHEMA_DRIFT ALERT: %s — %s", r.platform, r.error,
            )

    redis.ltrim("scraper:health:log", -1000, -1)
    redis.close()


@dramatiq.actor(queue_name="background", max_retries=1)
def canary_scrape() -> None:
    """Run canary validation on all platforms.

    Schedule: every 2 hours via external scheduler.

    Usage:
        canary_scrape.send()
    """
    settings = get_settings()
    platforms = settings.orchestrator_platforms

    logger.info("canary_scrape START platforms=%s", platforms)
    start = time.monotonic()

    results = asyncio.run(_run_canary_all(platforms))

    _log_canary_health(results)

    elapsed = (time.monotonic() - start) * 1000
    ok_count = sum(1 for r in results if r.status == "ok")
    fail_count = len(results) - ok_count

    logger.info(
        "canary_scrape DONE ok=%d fail=%d elapsed=%.0fms",
        ok_count, fail_count, elapsed,
    )
