from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings

# ── Rate limiter (shared singleton) ─────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_settings().redis_url,
    enabled=get_settings().rate_limit_enabled,
)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session from the app-level sessionmaker."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis(request: Request) -> Redis:
    """Return the app-level Redis connection pool."""
    return request.app.state.redis


def get_settings_dep() -> Settings:
    return get_settings()


# Type aliases for Depends injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
