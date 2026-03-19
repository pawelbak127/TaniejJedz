"""
Dramatiq actor: crawl menu for a specific restaurant.

Triggered by:
  - warm_cache job (top N restaurants)
  - API endpoint (on-demand refresh)
  - Nightly crawl (after crawl_restaurants discovers new slugs)

Writes results to Redis cache (scraper:menu:{platform}:{slug}).
"""

import asyncio
import json
import logging
import time

import dramatiq
from redis.asyncio import Redis as AsyncRedis

from app.config import get_settings

logger = logging.getLogger(__name__)


async def _crawl_menu_async(platform: str, slug: str) -> dict:
    """Async core — fetch menu for a single restaurant."""
    from app.scraper.adapters.wolt import WoltAdapter
    from app.scraper.adapters.pyszne import PyszneAdapter
    from app.scraper.budget_manager import Priority

    settings = get_settings()
    redis = AsyncRedis.from_url(settings.redis_url, decode_responses=True)

    adapters = {
        "wolt": WoltAdapter,
        "pyszne": PyszneAdapter,
    }

    adapter_cls = adapters.get(platform)
    if not adapter_cls:
        raise ValueError(f"Unknown platform: {platform}")

    try:
        adapter = adapter_cls(redis)
        items = await adapter.get_menu(slug, priority=Priority.LOW)

        # Cache the result
        cache_key = f"scraper:menu:{platform}:{slug}"
        data = [i.model_dump(mode="json") for i in items]
        await redis.setex(cache_key, 3600, json.dumps(data, default=str))

        return {
            "platform": platform,
            "slug": slug,
            "items_count": len(items),
        }
    finally:
        await redis.aclose()


@dramatiq.actor(queue_name="background", max_retries=2, min_backoff=30_000)
def crawl_menu(platform: str, slug: str) -> None:
    """Crawl menu for a specific restaurant.

    Usage:
        crawl_menu.send("wolt", "bella-ciao-solec")
        crawl_menu.send("pyszne", "nocny-szafran-warszawa")
    """
    logger.info("crawl_menu START %s/%s", platform, slug)
    start = time.monotonic()

    try:
        result = asyncio.run(_crawl_menu_async(platform, slug))
        elapsed = (time.monotonic() - start) * 1000
        logger.info(
            "crawl_menu DONE %s/%s items=%d elapsed=%.0fms",
            platform, slug, result["items_count"], elapsed,
        )
    except Exception:
        elapsed = (time.monotonic() - start) * 1000
        logger.exception("crawl_menu FAILED %s/%s elapsed=%.0fms", platform, slug, elapsed)
