import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class ComparisonLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "comparison_logs"
    __table_args__ = (
        Index(
            "idx_comparison_idempotency",
            "idempotency_key",
            postgresql_where="idempotency_key IS NOT NULL",
        ),
    )

    canonical_restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_restaurants.id"),
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    city_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platform_totals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    configured_items: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cheapest_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    savings_grosz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    affiliate_clicks: Mapped[list["AffiliateClick"]] = relationship(
        "AffiliateClick",
        back_populates="comparison_log",
        lazy="noload",
    )


class AffiliateClick(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "affiliate_clicks"

    comparison_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("comparison_logs.id"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    handoff_method: Mapped[str] = mapped_column(
        String(50), nullable=False, default="clipboard"
    )
    utm_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    comparison_log: Mapped["ComparisonLog"] = relationship(
        "ComparisonLog", back_populates="affiliate_clicks"
    )
