from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.v1.search import router as search_router
from app.api.v1.restaurants import router as restaurants_router
from app.api.v1.compare import router as compare_router
from app.api.v1.compare_stream import router as compare_stream_router
from app.api.v1.redirect import router as redirect_router
from app.api.v1.feedback import router as feedback_router
from app.api.admin.entities import router as admin_entities_router
from app.api.admin.scrapers import router as admin_scrapers_router
from app.api.admin.feedback_review import router as admin_feedback_router
from app.config import Settings, get_settings
from app.schemas.common import ErrorResponse, ErrorDetail


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle: create DB engine, Redis pool."""
    settings = get_settings()
    app.state.settings = settings

    # ── SQLAlchemy async engine ──────────────────────────────
    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
        echo=settings.is_dev,
    )
    app.state.db_engine = engine
    app.state.db_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # ── Redis connection pool ────────────────────────────────
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=50,
    )
    app.state.redis = redis

    # ── Services ───────────────────────────────────────────────
    from app.cache.cache_service import CacheService
    from app.services.analytics_service import AnalyticsService
    from app.services.feature_flags import FeatureFlagService

    app.state.cache = CacheService(redis)
    app.state.analytics = AnalyticsService(redis)
    app.state.feature_flags = FeatureFlagService(redis)

    # ── Sync feature flags from DB to Redis on startup ─────────
    try:
        async with app.state.db_session_factory() as session:
            count = await app.state.feature_flags.sync_from_db(session)
            import logging
            logging.getLogger("app").info(f"Synced {count} feature flags to Redis.")
    except Exception as e:
        import logging
        logging.getLogger("app").warning(f"Failed to sync feature flags: {e}")

    yield

    # ── Shutdown ─────────────────────────────────────────────
    await redis.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="TaniejJedz API",
        description="Porównywarka cen dostaw jedzenia w Polsce",
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    # ── Rate limiting (slowapi) ─────────────────────────────
    if settings.rate_limit_enabled:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded

        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=settings.redis_url,
            enabled=True,
        )
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Routers ──────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(restaurants_router)
    app.include_router(compare_router)
    app.include_router(compare_stream_router)
    app.include_router(redirect_router)
    app.include_router(feedback_router)

    # Admin routers
    app.include_router(admin_entities_router)
    app.include_router(admin_scrapers_router)
    app.include_router(admin_feedback_router)

    # ── Error handlers (ErrorResponse envelope) ────────────
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(
                    code=f"HTTP_{exc.status_code}",
                    message=str(exc.detail),
                    retry=exc.status_code >= 500,
                )
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> ORJSONResponse:
        messages = []
        for err in exc.errors():
            loc = " → ".join(str(x) for x in err["loc"])
            messages.append(f"{loc}: {err['msg']}")
        return ORJSONResponse(
            status_code=422,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="; ".join(messages),
                    retry=False,
                )
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="Wystąpił nieoczekiwany błąd." if not settings.is_dev else str(exc),
                    retry=True,
                )
            ).model_dump(),
        )

    return app


app: FastAPI = create_app()
