"""Analytics service — buffer events in Redis, flush to PG in batches.

Events go to Redis list via RPUSH. Dramatiq job flushes every 10s
using LPOP in batches, INSERTing into analytics_events table.

This prevents data loss during PG hiccups.
"""

import json
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ANALYTICS_BUFFER_KEY = "analytics:buffer"
DEFAULT_BATCH_SIZE = 500


class AnalyticsService:
    """Async analytics service used by API endpoints."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def track(
        self,
        event_type: str,
        session_id: str,
        payload: dict | None = None,
    ) -> None:
        """Buffer an analytics event in Redis."""
        event = {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "session_id": session_id,
            "payload": payload or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._redis.rpush(ANALYTICS_BUFFER_KEY, json.dumps(event))

    async def buffer_length(self) -> int:
        """Return current buffer size (for monitoring)."""
        return await self._redis.llen(ANALYTICS_BUFFER_KEY)


class AnalyticsFlusher:
    """Sync flusher used by Dramatiq job."""

    def __init__(self, redis_url: str) -> None:
        from redis import Redis as SyncRedis

        self._redis = SyncRedis.from_url(redis_url, decode_responses=True)

    def flush(self, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
        """Pop events from Redis buffer and return as parsed dicts.

        Returns the number of events flushed.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from app.config import get_settings

        settings = get_settings()

        # Use sync engine for Dramatiq context
        engine = create_engine(
            settings.database_url.replace("+asyncpg", ""),
            pool_pre_ping=True,
        )

        # Pop up to batch_size events atomically via pipeline
        pipe = self._redis.pipeline()
        for _ in range(batch_size):
            pipe.lpop(ANALYTICS_BUFFER_KEY)
        results = pipe.execute()

        rows = []
        for raw in results:
            if raw is None:
                continue
            try:
                event = json.loads(raw)
                rows.append(event)
            except (json.JSONDecodeError, TypeError):
                continue

        if not rows:
            engine.dispose()
            return 0

        # Batch INSERT into analytics_events
        with Session(engine) as session:
            for row in rows:
                session.execute(
                    text("""
                        INSERT INTO analytics_events (id, event_type, session_id, payload, created_at)
                        VALUES (:id, :event_type, :session_id, :payload, :created_at)
                    """),
                    {
                        "id": row["id"],
                        "event_type": row["event_type"],
                        "session_id": row["session_id"],
                        "payload": json.dumps(row.get("payload", {})),
                        "created_at": row["created_at"],
                    },
                )
            session.commit()

        engine.dispose()
        return len(rows)

    def close(self) -> None:
        self._redis.close()
