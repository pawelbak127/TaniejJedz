import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class UserFeedback(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_feedback"
    __table_args__ = (
        Index(
            "idx_feedback_pending",
            "status",
            "created_at",
            postgresql_where="status = 'pending'",
        ),
    )

    canonical_restaurant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_restaurants.id"),
        nullable=True,
    )
    platform_menu_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_menu_items.id"),
        nullable=True,
    )
    feedback_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # wrong_price | wrong_match | other
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    city_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | resolved | dismissed
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    canonical_restaurant: Mapped["CanonicalRestaurant | None"] = relationship(
        "CanonicalRestaurant", back_populates="feedbacks"
    )
    platform_menu_item: Mapped["PlatformMenuItem | None"] = relationship(
        "PlatformMenuItem", back_populates="feedbacks"
    )


class EntityReviewQueue(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "entity_review_queue"
    __table_args__ = (
        Index(
            "idx_review_pending",
            "status",
            "created_at",
            postgresql_where="status = 'pending'",
        ),
    )

    platform_restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_restaurants.id"),
        nullable=False,
    )
    candidate_canonical_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_restaurants.id"),
        nullable=True,
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | approved | rejected
    match_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    platform_restaurant: Mapped["PlatformRestaurant"] = relationship(
        "PlatformRestaurant", back_populates="entity_reviews"
    )
