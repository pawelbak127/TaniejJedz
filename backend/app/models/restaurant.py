import uuid
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CanonicalRestaurant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_restaurants"
    __table_args__ = (
        Index("idx_restaurants_city", "city_id", "is_active"),
        Index(
            "idx_restaurants_chain",
            "chain_slug",
            postgresql_where="chain_slug IS NOT NULL",
        ),
    )

    city_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cities.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    address_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cuisine_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    chain_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    city: Mapped["City"] = relationship("City", back_populates="canonical_restaurants")
    platform_restaurants: Mapped[list["PlatformRestaurant"]] = relationship(
        "PlatformRestaurant",
        back_populates="canonical_restaurant",
        lazy="selectin",
    )
    menu_categories: Mapped[list["MenuCategory"]] = relationship(
        "MenuCategory",
        back_populates="canonical_restaurant",
        lazy="selectin",
    )
    canonical_menu_items: Mapped[list["CanonicalMenuItem"]] = relationship(
        "CanonicalMenuItem",
        back_populates="canonical_restaurant",
        lazy="selectin",
    )
    feedbacks: Mapped[list["UserFeedback"]] = relationship(
        "UserFeedback",
        back_populates="canonical_restaurant",
        lazy="noload",
    )


class PlatformRestaurant(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "platform_restaurants"
    __table_args__ = (
        UniqueConstraint("platform", "platform_restaurant_id", name="uq_platform_rest_unique"),
        Index("idx_platform_rest_canonical", "canonical_restaurant_id", "platform"),
        Index(
            "idx_platform_rest_geo",
            "latitude",
            "longitude",
            postgresql_where="latitude IS NOT NULL AND longitude IS NOT NULL",
        ),
        Index(
            "idx_platform_rest_unmatched",
            "platform",
            "canonical_restaurant_id",
            postgresql_where="canonical_restaurant_id IS NULL",
        ),
    )

    # ── NULLABLE: platform restaurant can exist before entity matching ──
    canonical_restaurant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_restaurants.id"),
        nullable=True,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_restaurant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform_name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # ── Geolocation from platform (for PostGIS blocking in matcher) ──
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    platform_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    canonical_restaurant: Mapped["CanonicalRestaurant | None"] = relationship(
        "CanonicalRestaurant", back_populates="platform_restaurants"
    )
    operating_hours: Mapped[list["OperatingHours"]] = relationship(
        "OperatingHours",
        back_populates="platform_restaurant",
        lazy="selectin",
    )
    platform_menu_items: Mapped[list["PlatformMenuItem"]] = relationship(
        "PlatformMenuItem",
        back_populates="platform_restaurant",
        lazy="selectin",
    )
    delivery_fees: Mapped[list["DeliveryFee"]] = relationship(
        "DeliveryFee",
        back_populates="platform_restaurant",
        lazy="noload",
    )
    promotions: Mapped[list["Promotion"]] = relationship(
        "Promotion",
        back_populates="platform_restaurant",
        lazy="noload",
    )
    entity_reviews: Mapped[list["EntityReviewQueue"]] = relationship(
        "EntityReviewQueue",
        back_populates="platform_restaurant",
        lazy="noload",
    )


class OperatingHours(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "operating_hours"
    __table_args__ = (
        Index("idx_hours_lookup", "platform_restaurant_id", "day_of_week"),
    )

    platform_restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_restaurants.id"),
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon, 6=Sun
    open_time: Mapped[time] = mapped_column(Time, nullable=False)
    close_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    platform_restaurant: Mapped["PlatformRestaurant"] = relationship(
        "PlatformRestaurant", back_populates="operating_hours"
    )
