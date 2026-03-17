"""Feature flags — Redis-backed with DB fallback.

Simple key-value flags stored in Redis hash. Loaded from PG feature_flags
table on startup/refresh. Zero cost, city-level overrides supported.
"""

import json

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.keys import CacheKeys
from app.models.feature_flag import FeatureFlag

FLAGS_HASH_KEY = "feature_flags:all"
FLAGS_CACHE_TTL = 300  # 5 min


class FeatureFlagService:
    """Async feature flag service."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_flag(self, key: str) -> bool:
        """Check if a flag is active. Returns False if flag doesn't exist."""
        raw = await self._redis.hget(FLAGS_HASH_KEY, key)
        if raw is None:
            return False
        try:
            data = json.loads(raw)
            return bool(data.get("is_active", False))
        except (json.JSONDecodeError, TypeError):
            return False

    async def get_flag_config(self, key: str) -> dict | None:
        """Get full flag config (is_active + config dict). Returns None if not found."""
        raw = await self._redis.hget(FLAGS_HASH_KEY, key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def get_all_flags(self) -> dict[str, dict]:
        """Get all flags as {key: {is_active, config}}."""
        raw_all = await self._redis.hgetall(FLAGS_HASH_KEY)
        result = {}
        for key, raw in raw_all.items():
            try:
                result[key] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
        return result

    async def set_flag(self, key: str, is_active: bool, config: dict | None = None) -> None:
        """Set a flag value in Redis."""
        data = {"is_active": is_active, "config": config or {}}
        await self._redis.hset(FLAGS_HASH_KEY, key, json.dumps(data))

    async def delete_flag(self, key: str) -> None:
        """Remove a flag from Redis."""
        await self._redis.hdel(FLAGS_HASH_KEY, key)

    async def sync_from_db(self, db: AsyncSession) -> int:
        """Load all flags from PG into Redis. Returns count loaded."""
        result = await db.execute(select(FeatureFlag))
        flags = result.scalars().all()

        if not flags:
            return 0

        pipe = self._redis.pipeline()
        for flag in flags:
            data = {
                "is_active": flag.is_active,
                "config": flag.config or {},
            }
            pipe.hset(FLAGS_HASH_KEY, flag.key, json.dumps(data))
        await pipe.execute()

        return len(flags)
