"""Cache service — Redis-backed with TTL per data type.

Cache-first, fetch-behind pattern. Multi-layer:
- L1: Python cachetools.TTLCache (60s, per-process) — future enhancement
- L2: Redis (per-type TTL) — this service
- L3: PostgreSQL (permanent)
"""

import json
from typing import Any

from redis.asyncio import Redis

from app.cache.keys import CacheKeys, CacheTTL


class CacheService:
    """Redis cache with typed key builders and per-type TTLs."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    # ── Generic get/set ─────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None on miss."""
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set a cached value with TTL in seconds."""
        serialized = json.dumps(value, default=str) if not isinstance(value, str) else value
        await self._redis.setex(key, ttl, serialized)

    async def delete(self, key: str) -> None:
        """Delete a cached key."""
        await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        return bool(await self._redis.exists(key))

    # ── Typed helpers ───────────────────────────────────────

    async def get_search(self, city_slug: str, query_hash: str) -> dict | None:
        key = CacheKeys.search(city_slug, query_hash)
        return await self.get(key)

    async def set_search(self, city_slug: str, query_hash: str, data: dict) -> None:
        key = CacheKeys.search(city_slug, query_hash)
        await self.set(key, data, CacheTTL.SEARCH)

    async def get_menu(self, restaurant_id: str) -> dict | None:
        key = CacheKeys.menu(restaurant_id)
        return await self.get(key)

    async def set_menu(self, restaurant_id: str, data: dict) -> None:
        key = CacheKeys.menu(restaurant_id)
        await self.set(key, data, CacheTTL.MENU)

    async def get_delivery_fee(
        self, platform_restaurant_id: str, geohash: str
    ) -> dict | None:
        key = CacheKeys.delivery_fee(platform_restaurant_id, geohash)
        return await self.get(key)

    async def set_delivery_fee(
        self, platform_restaurant_id: str, geohash: str, data: dict
    ) -> None:
        key = CacheKeys.delivery_fee(platform_restaurant_id, geohash)
        await self.set(key, data, CacheTTL.DELIVERY_FEES)

    async def get_promotions(self, platform_restaurant_id: str) -> list | None:
        key = CacheKeys.promotions(platform_restaurant_id)
        return await self.get(key)

    async def set_promotions(self, platform_restaurant_id: str, data: list) -> None:
        key = CacheKeys.promotions(platform_restaurant_id)
        await self.set(key, data, CacheTTL.PROMOTIONS)

    async def get_operating_hours(self, platform_restaurant_id: str) -> list | None:
        key = CacheKeys.operating_hours(platform_restaurant_id)
        return await self.get(key)

    async def set_operating_hours(
        self, platform_restaurant_id: str, data: list
    ) -> None:
        key = CacheKeys.operating_hours(platform_restaurant_id)
        await self.set(key, data, CacheTTL.OPERATING_HOURS)

    # ── Invalidation helpers ────────────────────────────────

    async def invalidate_restaurant(self, restaurant_id: str) -> int:
        """Invalidate all cache for a restaurant. Returns number of keys deleted."""
        pattern = f"cache:restaurant:{restaurant_id}:*"
        keys = []
        async for key in self._redis.scan_iter(match=pattern, count=100):
            keys.append(key)
        if keys:
            return await self._redis.delete(*keys)
        return 0

    async def invalidate_platform(self, platform_restaurant_id: str) -> int:
        """Invalidate all cache for a platform restaurant."""
        patterns = [
            f"cache:platform:{platform_restaurant_id}:*",
            f"cache:delivery:{platform_restaurant_id}:*",
            f"cache:promos:{platform_restaurant_id}",
            f"cache:hours:{platform_restaurant_id}",
        ]
        keys = []
        for pattern in patterns:
            async for key in self._redis.scan_iter(match=pattern, count=100):
                keys.append(key)
        if keys:
            return await self._redis.delete(*keys)
        return 0
