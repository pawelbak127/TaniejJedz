"""
Database session helper for background jobs (Dramatiq actors).

Provides an async session factory usable outside of FastAPI's request lifecycle.
Used by crawl_restaurants, crawl_menus, and other Dramatiq actors that need
to write to PostgreSQL.

Usage:
    from app.jobs.db import get_async_session

    async with get_async_session() as session:
        persistor = DataPersistor(session)
        await persistor.persist_restaurants(...)
        await session.commit()
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine = None
_session_factory = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Lazy-init async engine + session factory for background jobs."""
    global _engine, _session_factory

    if _session_factory is not None:
        return _session_factory

    settings = get_settings()
    _engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        echo=False,
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return _session_factory


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async SQLAlchemy session with auto-commit/rollback.

    Usage:
        async with get_async_session() as session:
            # do work
            await session.commit()
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
