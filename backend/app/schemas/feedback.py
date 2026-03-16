"""Schemas for POST /api/v1/feedback."""

from typing import Literal

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    """User-submitted data quality feedback."""

    feedback_type: Literal["wrong_price", "wrong_match", "other"]
    canonical_restaurant_id: str | None = None
    platform_menu_item_id: str | None = None
    description: str = Field(default="", max_length=1000)
    context_snapshot: dict = Field(
        default_factory=dict,
        description="Prices/state shown to user at time of report",
    )


class FeedbackResponse(BaseModel):
    """Response for POST /api/v1/feedback."""

    id: str
    message: str = "Dziękujemy za zgłoszenie! Sprawdzimy to."
