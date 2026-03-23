"""
Scraper Orchestrator — parallel fetch across platforms with cache fallback.

Flow for a user-facing request:
  1. Fire asyncio.gather for all enabled platforms (8s timeout each)
  2. Per platform: try live fetch → on error → fallback to CacheService
  3. After success: write fresh data to CacheService
  4. Return merged results from all platforms

Used by:
  - API endpoints (real-time comparison)
  - Dramatiq jobs (background warm/crawl) call adapters directly

Integrates with:
  - EXISTING app/cache/cache_service.py (CacheService class)
  - EXISTING app/cache/keys.py (CacheKeys, CacheTTL)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from redis.asyncio import Redis

from app.config import get_settings
from app.scraper.adapters.wolt import WoltAdapter
from app.scraper.adapters.pyszne import PyszneAdapter
from app.scraper.adapters.glovo import GlovoAdapter
from app.scraper.adapters.ubereats import UberEatsAdapter
from app.scraper.base_adapter import BaseAdapter, ScraperError
from app.scraper.schemas.normalized import (
    NormalizedMenuItem,
    NormalizedRestaurant,
)

logger = logging.getLogger(__name__)

# Platform name → adapter class
ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "wolt": WoltAdapter,
    "pyszne": PyszneAdapter,
    "glovo": GlovoAdapter,
    "ubereats": UberEatsAdapter,
}


class OrchestratorResult:
    """Result from orchestrator — per platform status + merged data."""

    def __init__(self) -> None:
        self.restaurants: dict[str, list[NormalizedRestaurant]] = {}  # platform → list
        self.menus: dict[str, list[NormalizedMenuItem]] = {}          # platform → list
        self.errors: dict[str, str] = {}                              # platform → error msg
        self.from_cache: set[str] = set()                             # platforms served from cache
        self.timings: dict[str, float] = {}                           # platform → ms

    @property
    def all_restaurants(self) -> list[NormalizedRestaurant]:
        """Merged restaurants from all platforms."""
        result = []
        for platform_list in self.restaurants.values():
            result.extend(platform_list)
        return result

    @property
    def all_menu_items(self) -> list[NormalizedMenuItem]:
        """Merged menu items from all platforms."""
        result = []
        for platform_list in self.menus.values():
            result.extend(platform_list)
        return result


class ScraperOrchestrator:
    """
    Parallel multi-platform scraper with cache integration.

    Usage:
        orch = ScraperOrchestrator(redis)
        result = await orch.search_all(52.2297, 21.0122, 5.0)
        print(f"Found {len(result.all_restaurants)} restaurants")

        menu_result = await orch.get_menu_all("pizza-hut-slug", "pyszne-slug")
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._settings = get_settings()
        self._timeout = self._settings.orchestrator_timeout
        self._platforms = self._settings.orchestrator_platforms

        # Instantiate adapters
        self._adapters: dict[str, BaseAdapter] = {}
        for platform in self._platforms:
            cls = ADAPTER_REGISTRY.get(platform)
            if cls:
                self._adapters[platform] = cls(redis)

    # ── Search all platforms ────────────────────────────────

    async def search_all(
        self,
        lat: float,
        lng: float,
        radius_km: float,
    ) -> OrchestratorResult:
        """
        Search restaurants on all platforms in parallel.

        Per platform: live fetch with timeout → on failure → cache fallback.
        """
        result = OrchestratorResult()

        tasks = {
            platform: self._search_one(platform, adapter, lat, lng, radius_km)
            for platform, adapter in self._adapters.items()
        }

        gathered = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        for platform, outcome in zip(tasks.keys(), gathered):
            if isinstance(outcome, Exception):
                result.errors[platform] = str(outcome)
                logger.warning("search %s FAILED: %s", platform, outcome)
                # Try cache fallback
                cached = await self._get_cached_search(platform, lat, lng)
                if cached:
                    result.restaurants[platform] = cached
                    result.from_cache.add(platform)
                    logger.info("search %s CACHE HIT (%d restaurants)", platform, len(cached))
            else:
                restaurants, elapsed = outcome
                result.restaurants[platform] = restaurants
                result.timings[platform] = elapsed
                # Write to cache
                await self._cache_search(platform, lat, lng, restaurants)
                logger.info("search %s OK (%d restaurants, %.0fms)",
                            platform, len(restaurants), elapsed)

        return result

    # ── Menu for specific slugs ─────────────────────────────

    async def get_menu_all(
        self,
        platform_slugs: dict[str, str],
    ) -> OrchestratorResult:
        """
        Fetch menu from multiple platforms in parallel.

        Args:
            platform_slugs: {"wolt": "bella-ciao-solec", "pyszne": "bella-ciao"}
        """
        result = OrchestratorResult()

        tasks = {}
        for platform, slug in platform_slugs.items():
            adapter = self._adapters.get(platform)
            if adapter:
                tasks[platform] = self._get_menu_one(platform, adapter, slug)

        gathered = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        for platform, outcome in zip(tasks.keys(), gathered):
            slug = platform_slugs[platform]
            if isinstance(outcome, Exception):
                result.errors[platform] = str(outcome)
                logger.warning("menu %s/%s FAILED: %s", platform, slug, outcome)
                # Cache fallback
                cached = await self._get_cached_menu(platform, slug)
                if cached:
                    result.menus[platform] = cached
                    result.from_cache.add(platform)
                    logger.info("menu %s/%s CACHE HIT", platform, slug)
            else:
                items, elapsed = outcome
                result.menus[platform] = items
                result.timings[platform] = elapsed
                # Write to cache
                await self._cache_menu(platform, slug, items)
                logger.info("menu %s/%s OK (%d items, %.0fms)",
                            platform, slug, len(items), elapsed)

        return result

    # ── Single platform fetch with timeout ──────────────────

    async def _search_one(
        self,
        platform: str,
        adapter: BaseAdapter,
        lat: float,
        lng: float,
        radius_km: float,
    ) -> tuple[list[NormalizedRestaurant], float]:
        """Fetch with hard timeout. Returns (restaurants, elapsed_ms)."""
        start = time.monotonic()
        restaurants = await asyncio.wait_for(
            adapter.search_restaurants(lat, lng, radius_km),
            timeout=self._timeout,
        )
        elapsed = (time.monotonic() - start) * 1000
        return restaurants, elapsed

    async def _get_menu_one(
        self,
        platform: str,
        adapter: BaseAdapter,
        slug: str,
    ) -> tuple[list[NormalizedMenuItem], float]:
        start = time.monotonic()
        items = await asyncio.wait_for(
            adapter.get_menu(slug),
            timeout=self._timeout,
        )
        elapsed = (time.monotonic() - start) * 1000
        return items, elapsed

    # ── Cache integration ───────────────────────────────────
    # Uses raw Redis keys compatible with existing CacheService patterns

    _SEARCH_CACHE_TTL = 300       # 5 min
    _MENU_CACHE_TTL = 600         # 10 min
    _SEARCH_STALE_TTL = 3600      # 1h stale fallback
    _MENU_STALE_TTL = 3600

    def _search_cache_key(self, platform: str, lat: float, lng: float) -> str:
        # Round coordinates to 3 decimals (~110m) for cache hits
        return f"scraper:search:{platform}:{lat:.3f}:{lng:.3f}"

    def _menu_cache_key(self, platform: str, slug: str) -> str:
        return f"scraper:menu:{platform}:{slug}"

    async def _cache_search(
        self, platform: str, lat: float, lng: float,
        restaurants: list[NormalizedRestaurant],
    ) -> None:
        key = self._search_cache_key(platform, lat, lng)
        data = [r.model_dump(mode="json") for r in restaurants]
        await self._redis.setex(key, self._SEARCH_STALE_TTL, json.dumps(data, default=str))

    async def _get_cached_search(
        self, platform: str, lat: float, lng: float,
    ) -> list[NormalizedRestaurant] | None:
        key = self._search_cache_key(platform, lat, lng)
        raw = await self._redis.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return [NormalizedRestaurant.model_validate(d) for d in data]
        except Exception:
            logger.warning("corrupt search cache for %s", key)
            return None

    async def _cache_menu(
        self, platform: str, slug: str,
        items: list[NormalizedMenuItem],
    ) -> None:
        key = self._menu_cache_key(platform, slug)
        data = [i.model_dump(mode="json") for i in items]
        await self._redis.setex(key, self._MENU_STALE_TTL, json.dumps(data, default=str))

    async def _get_cached_menu(
        self, platform: str, slug: str,
    ) -> list[NormalizedMenuItem] | None:
        key = self._menu_cache_key(platform, slug)
        raw = await self._redis.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return [NormalizedMenuItem.model_validate(d) for d in data]
        except Exception:
            logger.warning("corrupt menu cache for %s", key)
            return None
