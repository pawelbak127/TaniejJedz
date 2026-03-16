import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class DeliveryFee(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "delivery_fees"
    __table_args__ = (
        Index("idx_delfee_lookup", "platform_restaurant_id", "geohash"),
    )

    platform_restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_restaurants.id"),
        nullable=False,
    )
    geohash: Mapped[str | None] = mapped_column(String(12), nullable=True)
    fee_grosz: Mapped[int] = mapped_column(Integer, nullable=False)
    min_order_grosz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_delivery_above_grosz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    platform_restaurant: Mapped["PlatformRestaurant"] = relationship(
        "PlatformRestaurant", back_populates="delivery_fees"
    )
