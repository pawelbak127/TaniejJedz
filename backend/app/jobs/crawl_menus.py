"""
Dramatiq actor: crawl menu for a specific restaurant.

Triggered by:
  - warm_cache job (top N restaurants)
  - API endpoint (on-demand refresh)
  - Nightly crawl (after crawl_restaurants discovers new slugs)

Writes results to:
  - Redis cache (scraper:menu:{platform}:{slug})
  - PostgreSQL via DataPersistor (platform_menu_items with canonical_menu_item_id=NULL)
  - price_history via PriceRecorder
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
    """Async core — fetch menu for a single restaurant, persist to DB."""
    from app.scraper.adapters.wolt import WoltAdapter
    from app.scraper.adapters.pyszne import PyszneAdapter
    from app.scraper.adapters.glovo import GlovoAdapter
    from app.scraper.adapters.ubereats import UberEatsAdapter
    from app.scraper.budget_manager import Priority

    settings = get_settings()
    redis = AsyncRedis.from_url(settings.redis_url, decode_responses=True)

    adapters = {
        "wolt": WoltAdapter,
        "pyszne": PyszneAdapter,
        "glovo": GlovoAdapter,
        "ubereats": UberEatsAdapter,
    }

    adapter_cls = adapters.get(platform)
    if not adapter_cls:
        raise ValueError(f"Unknown platform: {platform}")

    try:
        adapter = adapter_cls(redis)
        items = await adapter.get_menu(slug, priority=Priority.LOW)

        # Cache the result in Redis
        cache_key = f"scraper:menu:{platform}:{slug}"
        data = [i.model_dump(mode="json") for i in items]
        await redis.setex(cache_key, 3600, json.dumps(data, default=str))

        # Persist to PostgreSQL
        persist_result = {"persisted": 0, "prices_recorded": 0}
        if settings.persist_enabled:
            persist_result = await _persist_menu_items(platform, slug, items)

        return {
            "platform": platform,
            "slug": slug,
            "items_count": len(items),
            **persist_result,
        }
    finally:
        await redis.aclose()


async def _persist_menu_items(
    platform: str,
    slug: str,
    items: list,
) -> dict:
    """Persist menu items + record prices to PostgreSQL.

    Each platform_menu_item is saved with canonical_menu_item_id=NULL.
    MenuMatcher in Sprint 4.5 will link them to canonical entities.
    """
    from app.jobs.db import get_async_session
    from app.services.persistor import DataPersistor
    from app.services.price_recorder import PriceRecorder

    result = {"persisted": 0, "prices_recorded": 0}

    if not items:
        return result

    try:
        async with get_async_session() as session:
            persistor = DataPersistor(session)

            # Find the platform_restaurant by (platform, platform_restaurant_id)
            # For Wolt/Pyszne/Glovo: slug == platform_restaurant_id
            # For UberEats: slug == UUID == platform_restaurant_id
            pr_id = await persistor.get_platform_restaurant_id(platform, slug)

            if pr_id is None:
                # Fallback: try platform_slug lookup
                pr_id = await persistor.get_platform_restaurant_by_slug(platform, slug)

            if pr_id is None:
                logger.warning(
                    "persist_menu: platform_restaurant not found for %s/%s "
                    "(run crawl_restaurants first)",
                    platform, slug,
                )
                return result

            # Persist menu items (canonical_menu_item_id=NULL)
            stats = await persistor.persist_menu(items, pr_id)
            result["persisted"] = stats.total

            # Record price snapshots
            recorder = PriceRecorder(session)
            prices = await recorder.record_prices(pr_id)
            result["prices_recorded"] = prices

            await session.commit()

    except Exception:
        logger.exception(
            "persist_menu DB failed for %s/%s", platform, slug,
        )

    return result


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
            "crawl_menu DONE %s/%s items=%d persisted=%d prices=%d elapsed=%.0fms",
            platform, slug,
            result["items_count"],
            result.get("persisted", 0),
            result.get("prices_recorded", 0),
            elapsed,
        )
    except Exception:
        elapsed = (time.monotonic() - start) * 1000
        logger.exception("crawl_menu FAILED %s/%s elapsed=%.0fms", platform, slug, elapsed)
