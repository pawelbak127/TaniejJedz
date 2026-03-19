"""
Shared pytest fixtures for scraper infrastructure tests.
Uses fakeredis for all Redis-dependent tests — no real Redis needed.
"""

from __future__ import annotations

import os
import pytest
import pytest_asyncio
import fakeredis.aioredis


# Ensure test env vars are set before config is imported.
# pydantic-settings with case_sensitive=False matches these to lowercase fields.
os.environ.setdefault("PROXY_USERNAME", "test_user")
os.environ.setdefault("PROXY_PASSWORD", "test_pass")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Clear lru_cache on get_settings so env overrides take effect."""
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def redis():
    """Fake async Redis for unit tests."""
    server = fakeredis.FakeServer()
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    yield client
    await client.aclose()
