"""POST /api/v1/compare — create comparison with idempotency, enqueue workers."""

import uuid

from fastapi import APIRouter, Header, Request

from app.dependencies import RedisClient, limiter
from app.jobs.compare_worker import fetch_platform_mock
from app.schemas.compare import CompareRequest, CompareResponse

router = APIRouter(prefix="/api/v1", tags=["compare"])

# Platforms enabled for Phase 1
ENABLED_PLATFORMS = ["wolt", "pyszne"]


@router.post("/compare", response_model=CompareResponse, status_code=202)
@limiter.limit("20/minute")
async def create_comparison(
    request: Request,
    body: CompareRequest,
    redis: RedisClient,
    x_idempotency_key: str | None = Header(default=None),
) -> CompareResponse:
    """Create a price comparison. Returns comparison_id for SSE streaming.

    Idempotency: SHA256(restaurant_id + address + items) with 60s Redis TTL.
    Enqueues one Dramatiq job per platform. Results arrive via SSE.
    """
    idempotency_key = x_idempotency_key or body.compute_idempotency_key()
    redis_key = f"idempotent:{idempotency_key}"

    # ── Atomic idempotency (SET NX) ─────────────────────────
    comparison_id = str(uuid.uuid4())
    was_set = await redis.set(redis_key, comparison_id, ex=60, nx=True)

    if not was_set:
        # Key already existed — another request won the race
        existing = await redis.get(redis_key)
        return CompareResponse(
            comparison_id=existing or comparison_id,
            status="already_processing",
        )

    # ── Enqueue Dramatiq job per platform ───────────────────
    for platform in ENABLED_PLATFORMS:
        fetch_platform_mock.send(
            comparison_id,
            platform,
            body.model_dump_json(),
        )

    return CompareResponse(comparison_id=comparison_id, status="processing")
