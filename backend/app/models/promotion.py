import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class Promotion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "promotions"

    platform_restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_restaurants.id"),
        nullable=False,
    )
    promo_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_order_grosz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subscription_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    platform_restaurant: Mapped["PlatformRestaurant"] = relationship(
        "PlatformRestaurant", back_populates="promotions"
    )
