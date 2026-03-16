"""POST /api/v1/feedback — user data quality feedback."""

import uuid

from fastapi import APIRouter, Request

from app.dependencies import DbSession
from app.models.feedback import UserFeedback
from app.schemas.feedback import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    body: FeedbackRequest,
    db: DbSession,
    request: Request,
) -> FeedbackResponse:
    """Submit a data quality report (wrong price, wrong match, etc.)."""

    # Session ID from header or generate ephemeral one
    session_id = request.headers.get("X-Session-Id", uuid.uuid4().hex[:16])

    feedback = UserFeedback(
        feedback_type=body.feedback_type,
        canonical_restaurant_id=(
            uuid.UUID(body.canonical_restaurant_id) if body.canonical_restaurant_id else None
        ),
        platform_menu_item_id=(
            uuid.UUID(body.platform_menu_item_id) if body.platform_menu_item_id else None
        ),
        description=body.description,
        session_id=session_id,
        context_snapshot=body.context_snapshot,
        status="pending",
    )
    db.add(feedback)
    await db.flush()

    return FeedbackResponse(
        id=str(feedback.id),
        message="Dziękujemy za zgłoszenie! Sprawdzimy to.",
    )
