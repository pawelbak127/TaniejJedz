"""Admin API: user feedback review — list, resolve, dismiss."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.dependencies import DbSession
from app.models.feedback import UserFeedback

router = APIRouter(prefix="/api/admin/feedback", tags=["admin-feedback"])


class FeedbackItem(BaseModel):
    id: str
    feedback_type: str
    canonical_restaurant_id: str | None = None
    platform_menu_item_id: str | None = None
    description: str
    session_id: str
    city_slug: str | None = None
    status: str
    context_snapshot: dict | None = None
    created_at: str
    resolved_at: str | None = None


class FeedbackListResponse(BaseModel):
    items: list[FeedbackItem]
    total: int
    page: int
    per_page: int


class FeedbackAction(BaseModel):
    action: str  # "resolve" | "dismiss"
    note: str = ""


@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    db: DbSession,
    status: str = Query(default="pending", pattern="^(pending|resolved|dismissed|all)$"),
    feedback_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> FeedbackListResponse:
    """List user feedback items with filters."""
    conditions = []
    if status != "all":
        conditions.append(UserFeedback.status == status)
    if feedback_type:
        conditions.append(UserFeedback.feedback_type == feedback_type)

    count_result = await db.execute(
        select(func.count(UserFeedback.id)).where(*conditions)
    )
    total = count_result.scalar() or 0

    offset = (page - 1) * per_page
    stmt = (
        select(UserFeedback)
        .where(*conditions)
        .order_by(UserFeedback.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    feedbacks = result.scalars().all()

    items = [
        FeedbackItem(
            id=str(fb.id),
            feedback_type=fb.feedback_type,
            canonical_restaurant_id=str(fb.canonical_restaurant_id) if fb.canonical_restaurant_id else None,
            platform_menu_item_id=str(fb.platform_menu_item_id) if fb.platform_menu_item_id else None,
            description=fb.description,
            session_id=fb.session_id,
            city_slug=fb.city_slug,
            status=fb.status,
            context_snapshot=fb.context_snapshot,
            created_at=fb.created_at.isoformat(),
            resolved_at=fb.resolved_at.isoformat() if fb.resolved_at else None,
        )
        for fb in feedbacks
    ]

    return FeedbackListResponse(
        items=items, total=total, page=page, per_page=per_page
    )


@router.put("/{feedback_id}")
async def update_feedback(
    feedback_id: str,
    body: FeedbackAction,
    db: DbSession,
) -> dict:
    """Resolve or dismiss a feedback item."""
    try:
        fid = uuid.UUID(feedback_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid feedback ID")

    result = await db.execute(
        select(UserFeedback).where(UserFeedback.id == fid)
    )
    feedback = result.scalar_one_or_none()

    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if feedback.status != "pending":
        raise HTTPException(status_code=409, detail=f"Feedback already {feedback.status}")

    now = datetime.now(timezone.utc)

    if body.action == "resolve":
        feedback.status = "resolved"
        feedback.resolved_at = now
    elif body.action == "dismiss":
        feedback.status = "dismissed"
        feedback.resolved_at = now
    else:
        raise HTTPException(status_code=400, detail="Action must be 'resolve' or 'dismiss'")

    return {
        "id": str(feedback.id),
        "status": feedback.status,
        "resolved_at": now.isoformat(),
    }
