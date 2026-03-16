import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScraperHealth(Base):
    """Partitioned by month on checked_at. Partitions created via migration."""

    __tablename__ = "scraper_health"
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (checked_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    city_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        primary_key=True,
    )

    __mapper_args__ = {
        "primary_key": [id, checked_at],
    }
