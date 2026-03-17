"""Admin API: entity review queue — list, approve, reject."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.dependencies import DbSession
from app.models.feedback import EntityReviewQueue
from app.models.restaurant import CanonicalRestaurant, PlatformRestaurant

router = APIRouter(prefix="/api/admin/entities", tags=["admin-entities"])


# ── Response schemas ────────────────────────────────────────

class EntityReviewItem(BaseModel):
    id: str
    platform_restaurant_id: str
    platform_name: str | None = None
    platform: str | None = None
    candidate_canonical_id: str | None = None
    candidate_name: str | None = None
    confidence_score: float
    status: str
    match_details: dict | None = None
    created_at: str
    reviewed_at: str | None = None


class EntityReviewListResponse(BaseModel):
    items: list[EntityReviewItem]
    total: int
    page: int
    per_page: int


class EntityReviewAction(BaseModel):
    action: str  # "approve" | "reject"
    canonical_restaurant_id: str | None = None  # required if approve + no candidate


# ── Endpoints ───────────────────────────────────────────────

@router.get("", response_model=EntityReviewListResponse)
async def list_entity_reviews(
    db: DbSession,
    status: str = Query(default="pending", pattern="^(pending|approved|rejected|all)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> EntityReviewListResponse:
    """List entity review queue items."""
    conditions = []
    if status != "all":
        conditions.append(EntityReviewQueue.status == status)

    count_result = await db.execute(
        select(func.count(EntityReviewQueue.id)).where(*conditions)
    )
    total = count_result.scalar() or 0

    offset = (page - 1) * per_page
    stmt = (
        select(EntityReviewQueue)
        .where(*conditions)
        .order_by(EntityReviewQueue.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    reviews = result.scalars().all()

    items = []
    for r in reviews:
        # Fetch platform restaurant info
        pr_result = await db.execute(
            select(PlatformRestaurant).where(PlatformRestaurant.id == r.platform_restaurant_id)
        )
        pr = pr_result.scalar_one_or_none()

        candidate_name = None
        if r.candidate_canonical_id:
            cr_result = await db.execute(
                select(CanonicalRestaurant.name).where(
                    CanonicalRestaurant.id == r.candidate_canonical_id
                )
            )
            candidate_name = cr_result.scalar_one_or_none()

        items.append(
            EntityReviewItem(
                id=str(r.id),
                platform_restaurant_id=str(r.platform_restaurant_id),
                platform_name=pr.platform_name if pr else None,
                platform=pr.platform if pr else None,
                candidate_canonical_id=str(r.candidate_canonical_id) if r.candidate_canonical_id else None,
                candidate_name=candidate_name,
                confidence_score=r.confidence_score,
                status=r.status,
                match_details=r.match_details,
                created_at=r.created_at.isoformat(),
                reviewed_at=r.reviewed_at.isoformat() if r.reviewed_at else None,
            )
        )

    return EntityReviewListResponse(
        items=items, total=total, page=page, per_page=per_page
    )


@router.put("/{review_id}")
async def update_entity_review(
    review_id: str,
    body: EntityReviewAction,
    db: DbSession,
) -> dict:
    """Approve or reject an entity review."""
    try:
        rid = uuid.UUID(review_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid review ID")

    result = await db.execute(
        select(EntityReviewQueue).where(EntityReviewQueue.id == rid)
    )
    review = result.scalar_one_or_none()

    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.status != "pending":
        raise HTTPException(status_code=409, detail=f"Review already {review.status}")

    now = datetime.now(timezone.utc)

    if body.action == "approve":
        canonical_id = body.canonical_restaurant_id or (
            str(review.candidate_canonical_id) if review.candidate_canonical_id else None
        )
        if not canonical_id:
            raise HTTPException(
                status_code=400,
                detail="canonical_restaurant_id required for approval when no candidate exists",
            )

        # Link platform restaurant to canonical
        await db.execute(
            update(PlatformRestaurant)
            .where(PlatformRestaurant.id == review.platform_restaurant_id)
            .values(canonical_restaurant_id=uuid.UUID(canonical_id))
        )

        review.status = "approved"
        review.reviewed_at = now

    elif body.action == "reject":
        review.status = "rejected"
        review.reviewed_at = now

    else:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    return {"id": str(review.id), "status": review.status, "reviewed_at": now.isoformat()}
