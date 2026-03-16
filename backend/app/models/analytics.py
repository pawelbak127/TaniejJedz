import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class PriceHistory(Base):
    """Partitioned by month on recorded_at. Partitions created via migration."""

    __tablename__ = "price_history"
    __table_args__ = (
        Index("idx_price_history_item_date", "platform_menu_item_id", "recorded_at"),
        {"postgresql_partition_by": "RANGE (recorded_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
        nullable=False,
    )
    platform_menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    price_grosz: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        primary_key=True,
    )

    # Note: composite PK (id, recorded_at) required for partitioning
    __mapper_args__ = {
        "primary_key": [id, recorded_at],
    }


class AnalyticsEvent(Base):
    """Partitioned by month on created_at. Partitions created via migration."""

    __tablename__ = "analytics_events"
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        primary_key=True,
    )

    __mapper_args__ = {
        "primary_key": [id, created_at],
    }
