"""POST /api/v1/compare — create comparison with idempotency, enqueue workers."""

import uuid

from fastapi import APIRouter, Header

from app.dependencies import RedisClient
from app.jobs.compare_worker import fetch_platform_mock
from app.schemas.compare import CompareRequest, CompareResponse

router = APIRouter(prefix="/api/v1", tags=["compare"])

# Platforms enabled for Phase 1
ENABLED_PLATFORMS = ["wolt", "pyszne"]


@router.post("/compare", response_model=CompareResponse, status_code=202)
async def create_comparison(
    body: CompareRequest,
    redis: RedisClient,
    x_idempotency_key: str | None = Header(default=None),
) -> CompareResponse:
    """Create a price comparison. Returns comparison_id for SSE streaming.

    Idempotency: SHA256(restaurant_id + address + items) with 60s Redis TTL.
    Enqueues one Dramatiq job per platform. Results arrive via SSE.
    """
    idempotency_key = x_idempotency_key or body.compute_idempotency_key()

    # ── Idempotency check (60s window) ──────────────────────
    existing = await redis.get(f"idempotent:{idempotency_key}")
    if existing:
        return CompareResponse(comparison_id=existing, status="already_processing")

    # ── Create new comparison ───────────────────────────────
    comparison_id = str(uuid.uuid4())
    await redis.setex(f"idempotent:{idempotency_key}", 60, comparison_id)

    # ── Enqueue Dramatiq job per platform ───────────────────
    for platform in ENABLED_PLATFORMS:
        fetch_platform_mock.send(
            comparison_id,
            platform,
            body.model_dump_json(),
        )

    return CompareResponse(comparison_id=comparison_id, status="processing")
