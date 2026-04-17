"""
Nightly pipeline — unified orchestration of all Epic 4 steps.

Schedule: 3:00 AM CET (after sitemap sync at 00:00)

Pipeline:
  1. Crawl restaurants (all platforms, sitemap-powered)
  2. Match restaurants (entity resolution)
  3. Crawl menus (for cross-platform matched restaurants)
  4. Match menu items (cross-platform dish linking)
  5. Record prices (snapshots to price_history)

Usage:
    # Dramatiq
    nightly_pipeline.send("warszawa")

    # Standalone
    python -m app.jobs.nightly_pipeline
    python -m app.jobs.nightly_pipeline --city warszawa

    # Selective steps
    python -m app.jobs.nightly_pipeline --steps crawl,match_restaurants
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import dramatiq
from redis import Redis as SyncRedis

from app.config import get_settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# PIPELINE STATS
# ══════════════════════════════════════════════════════════════


@dataclass
class PipelineStats:
    """Aggregate stats for entire pipeline run."""
    city: str = ""
    started_at: float = 0.0
    elapsed_s: float = 0.0

    # Step 1: crawl
    crawl_restaurants: dict[str, int] = field(default_factory=dict)

    # Step 2: match restaurants
    restaurant_match_auto: int = 0
    restaurant_match_review: int = 0
    restaurant_match_new: int = 0
    restaurant_match_skipped: int = 0

    # Step 3: menu crawl
    menus_crawled: int = 0
    menus_failed: int = 0
    menu_items_total: int = 0

    # Step 4: match menu items
    menu_match_seed: int = 0
    menu_match_auto: int = 0
    menu_match_new: int = 0

    # Errors
    step_errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "city": self.city,
            "elapsed_s": round(self.elapsed_s, 1),
            "crawl": self.crawl_restaurants,
            "restaurant_matching": {
                "auto": self.restaurant_match_auto,
                "review": self.restaurant_match_review,
                "new": self.restaurant_match_new,
                "skipped": self.restaurant_match_skipped,
            },
            "menu_crawl": {
                "crawled": self.menus_crawled,
                "failed": self.menus_failed,
                "items": self.menu_items_total,
            },
            "menu_matching": {
                "seed": self.menu_match_seed,
                "auto": self.menu_match_auto,
                "new": self.menu_match_new,
            },
            "errors": self.step_errors,
        }


# ══════════════════════════════════════════════════════════════
# PIPELINE STEPS
# ══════════════════════════════════════════════════════════════


ALL_STEPS = [
    "crawl",
    "match_restaurants",
    "crawl_menus",
    "match_menus",
]


async def _step_crawl(
    city_slug: str, lat: float, lng: float, radius_km: float,
    stats: PipelineStats,
) -> None:
    """Step 1: Crawl restaurants from all platforms."""
    from app.jobs.crawl_restaurants import _crawl_city_async

    logger.info("pipeline [%s] step 1/4: crawl_restaurants", city_slug)
    result = await _crawl_city_async(
        city_slug, lat, lng, radius_km,
        get_settings().orchestrator_platforms,
    )

    for platform, data in result.get("platforms", {}).items():
        stats.crawl_restaurants[platform] = data.get("count", 0)

    persisted = result.get("persisted", {})
    for platform, p in persisted.items():
        if isinstance(p, dict) and "inserted" in p:
            logger.info(
                "  %s: %d restaurants (+%d new, ~%d updated)",
                platform, stats.crawl_restaurants.get(platform, 0),
                p["inserted"], p["updated"],
            )


async def _step_match_restaurants(
    city_slug: str, stats: PipelineStats,
) -> None:
    """Step 2: Match restaurants across platforms."""
    from app.jobs.db import get_async_session
    from app.entity_resolution.restaurant_matcher import RestaurantMatcher

    logger.info("pipeline [%s] step 2/4: match_restaurants", city_slug)

    async with get_async_session() as session:
        matcher = RestaurantMatcher(session)
        result = await matcher.match_all_platforms(city_slug)
        await session.commit()

    stats.restaurant_match_auto = result.auto_matched
    stats.restaurant_match_review = result.review_queue
    stats.restaurant_match_new = result.new_canonical
    stats.restaurant_match_skipped = result.skipped_no_coords

    logger.info(
        "  auto=%d, review=%d, new=%d, skipped=%d",
        result.auto_matched, result.review_queue,
        result.new_canonical, result.skipped_no_coords,
    )


async def _step_crawl_menus(
    city_slug: str, stats: PipelineStats,
    max_restaurants: int = 200,
) -> None:
    """Step 3: Crawl menus for cross-platform matched restaurants."""
    from app.jobs.db import get_async_session
    from app.jobs.crawl_menus import _crawl_menu_async
    from sqlalchemy import text

    logger.info("pipeline [%s] step 3/4: crawl_menus (max %d)", city_slug, max_restaurants)

    # Find restaurants on 2+ platforms (most valuable for comparison)
    async with get_async_session() as session:
        rows = await session.execute(text("""
            SELECT DISTINCT pr.platform, pr.platform_restaurant_id, pr.platform_slug
            FROM platform_restaurants pr
            WHERE pr.canonical_restaurant_id IN (
                SELECT canonical_restaurant_id
                FROM platform_restaurants
                WHERE canonical_restaurant_id IS NOT NULL
                GROUP BY canonical_restaurant_id
                HAVING COUNT(DISTINCT platform) >= 2
            )
            AND pr.canonical_restaurant_id IS NOT NULL
            ORDER BY pr.platform
            LIMIT :limit
        """), {"limit": max_restaurants})
        to_crawl = [(r[0], r[1], r[2]) for r in rows]

    if not to_crawl:
        logger.info("  no cross-platform restaurants to crawl menus for")
        return

    logger.info("  crawling menus for %d platform entries", len(to_crawl))

    for platform, pid, slug in to_crawl:
        menu_slug = slug or pid
        try:
            result = await _crawl_menu_async(platform, menu_slug)
            items = result.get("items_count", 0)
            if items > 0:
                stats.menus_crawled += 1
                stats.menu_items_total += items
            else:
                stats.menus_failed += 1
        except Exception:
            stats.menus_failed += 1

    logger.info(
        "  crawled=%d, failed=%d, total_items=%d",
        stats.menus_crawled, stats.menus_failed, stats.menu_items_total,
    )


async def _step_match_menus(
    city_slug: str, stats: PipelineStats,
) -> None:
    """Step 4: Match menu items across platforms."""
    from app.jobs.db import get_async_session
    from app.entity_resolution.menu_matcher import MenuMatcher

    logger.info("pipeline [%s] step 4/4: match_menus", city_slug)

    async with get_async_session() as session:
        matcher = MenuMatcher(session)
        result = await matcher.match_all()
        await session.commit()

    stats.menu_match_seed = result.seed_items_created
    stats.menu_match_auto = result.auto_matched
    stats.menu_match_new = result.new_canonical

    logger.info(
        "  seed=%d, auto_matched=%d, new=%d (across %d restaurants)",
        result.seed_items_created, result.auto_matched,
        result.new_canonical, result.restaurants_processed,
    )


# ══════════════════════════════════════════════════════════════
# PIPELINE RUNNER
# ══════════════════════════════════════════════════════════════


async def run_pipeline(
    city_slug: str | None = None,
    steps: list[str] | None = None,
) -> PipelineStats:
    """
    Run the full nightly pipeline for a city.

    Args:
        city_slug: City to process (default: from settings)
        steps: Subset of steps to run (default: all)
    """
    settings = get_settings()
    if city_slug is None:
        city_slug = settings.default_city_slug

    run_steps = steps or ALL_STEPS

    # Find city config
    city_config = None
    for c in settings.launch_cities:
        if c["slug"] == city_slug:
            city_config = c
            break
    if city_config is None:
        raise ValueError(f"City '{city_slug}' not in launch_cities config")

    lat = city_config["center_lat"]
    lng = city_config["center_lng"]
    radius = city_config.get("radius_km", 15)

    stats = PipelineStats(city=city_slug, started_at=time.time())
    start = time.monotonic()

    logger.info(
        "═══ NIGHTLY PIPELINE START city=%s steps=%s ═══",
        city_slug, run_steps,
    )

    step_map = {
        "crawl": lambda: _step_crawl(city_slug, lat, lng, radius, stats),
        "match_restaurants": lambda: _step_match_restaurants(city_slug, stats),
        "crawl_menus": lambda: _step_crawl_menus(city_slug, stats),
        "match_menus": lambda: _step_match_menus(city_slug, stats),
    }

    for step_name in ALL_STEPS:
        if step_name not in run_steps:
            continue

        step_fn = step_map.get(step_name)
        if step_fn is None:
            continue

        step_start = time.monotonic()
        try:
            await step_fn()
            step_elapsed = time.monotonic() - step_start
            logger.info(
                "  step '%s' completed in %.1fs", step_name, step_elapsed
            )
        except Exception as e:
            step_elapsed = time.monotonic() - step_start
            stats.step_errors[step_name] = str(e)
            logger.exception(
                "  step '%s' FAILED after %.1fs: %s",
                step_name, step_elapsed, e,
            )

    stats.elapsed_s = time.monotonic() - start

    logger.info(
        "═══ NIGHTLY PIPELINE DONE city=%s elapsed=%.1fs ═══",
        city_slug, stats.elapsed_s,
    )

    # Log to Redis for monitoring
    _log_pipeline_result(stats)

    return stats


def _log_pipeline_result(stats: PipelineStats) -> None:
    """Write pipeline result to Redis for health monitoring."""
    try:
        settings = get_settings()
        redis = SyncRedis.from_url(settings.redis_url, decode_responses=True)
        entry = json.dumps(stats.to_dict(), default=str)
        redis.set(
            f"pipeline:last_run:{stats.city}",
            entry,
            ex=86400 * 7,  # keep for 7 days
        )
        redis.rpush("pipeline:history", entry)
        redis.ltrim("pipeline:history", -100, -1)
        redis.close()
    except Exception:
        logger.debug("Failed to log pipeline result to Redis", exc_info=True)


# ══════════════════════════════════════════════════════════════
# DRAMATIQ ACTOR
# ══════════════════════════════════════════════════════════════


@dramatiq.actor(
    queue_name="background",
    max_retries=1,
    min_backoff=300_000,  # 5 min between retries
    max_backoff=600_000,
)
def nightly_pipeline(city_slug: str | None = None) -> None:
    """
    Dramatiq actor for nightly pipeline.

    Schedule: 3:00 AM CET via external scheduler.

    Usage:
        nightly_pipeline.send("warszawa")
        nightly_pipeline.send()  # uses default city
    """
    logger.info("nightly_pipeline actor START city=%s", city_slug)
    start = time.monotonic()

    try:
        stats = asyncio.run(run_pipeline(city_slug))
        elapsed = time.monotonic() - start
        logger.info(
            "nightly_pipeline actor DONE city=%s elapsed=%.1fs errors=%d",
            city_slug or "default",
            elapsed,
            len(stats.step_errors),
        )
    except Exception:
        elapsed = time.monotonic() - start
        logger.exception(
            "nightly_pipeline actor FAILED city=%s elapsed=%.1fs",
            city_slug, elapsed,
        )


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="TaniejJedz Nightly Pipeline")
    parser.add_argument("--city", default=None, help="City slug (default: from config)")
    parser.add_argument(
        "--steps",
        default=None,
        help=f"Comma-separated steps to run (default: all). Options: {','.join(ALL_STEPS)}",
    )
    args = parser.parse_args()

    steps = args.steps.split(",") if args.steps else None
    result = asyncio.run(run_pipeline(args.city, steps))

    print("\n" + "═" * 60)
    print("PIPELINE RESULT")
    print("═" * 60)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
