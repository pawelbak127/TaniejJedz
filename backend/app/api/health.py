from fastapi import APIRouter, Request
from fastapi.responses import ORJSONResponse
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness probe — is the process alive."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(request: Request) -> ORJSONResponse:
    """Readiness probe — check PG + Redis + Meilisearch connectivity."""
    checks: dict[str, bool] = {"pg": False, "redis": False, "meili": False}

    # ── PostgreSQL ──────────────────────────────────────────
    try:
        async with request.app.state.db_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["pg"] = True
    except Exception:
        pass

    # ── Redis ───────────────────────────────────────────────
    try:
        redis = request.app.state.redis
        pong = await redis.ping()
        checks["redis"] = pong is True
    except Exception:
        pass

    # ── Meilisearch ─────────────────────────────────────────
    try:
        import httpx

        meili_url = request.app.state.settings.meili_url
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{meili_url}/health")
            checks["meili"] = resp.status_code == 200
    except Exception:
        pass

    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503

    return ORJSONResponse(
        content={"status": "ready" if all_ok else "degraded", **checks},
        status_code=status_code,
    )
