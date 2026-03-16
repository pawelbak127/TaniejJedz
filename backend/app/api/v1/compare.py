"""POST /api/v1/compare — create comparison (stub for Sprint 2.4)."""

import uuid

from fastapi import APIRouter, Header

from app.dependencies import RedisClient
from app.schemas.compare import CompareRequest, CompareResponse

router = APIRouter(prefix="/api/v1", tags=["compare"])


@router.post("/compare", response_model=CompareResponse, status_code=202)
async def create_comparison(
    body: CompareRequest,
    redis: RedisClient,
    x_idempotency_key: str | None = Header(default=None),
) -> CompareResponse:
    """Create a price comparison. Returns comparison_id for SSE streaming.

    Stub implementation — returns comparison_id but does not enqueue jobs yet.
    Full implementation in Sprint 2.5.
    """
    idempotency_key = x_idempotency_key or body.compute_idempotency_key()

    # ── Idempotency check (60s window) ──────────────────────
    existing = await redis.get(f"idempotent:{idempotency_key}")
    if existing:
        return CompareResponse(comparison_id=existing, status="already_processing")

    # ── Create new comparison ───────────────────────────────
    comparison_id = str(uuid.uuid4())
    await redis.setex(f"idempotent:{idempotency_key}", 60, comparison_id)

    # TODO Sprint 2.5: enqueue Dramatiq jobs per platform here

    return CompareResponse(comparison_id=comparison_id, status="processing")
