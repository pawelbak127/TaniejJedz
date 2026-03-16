import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MenuCategory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "menu_categories"

    canonical_restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_restaurants.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    canonical_restaurant: Mapped["CanonicalRestaurant"] = relationship(
        "CanonicalRestaurant", back_populates="menu_categories"
    )
    canonical_menu_items: Mapped[list["CanonicalMenuItem"]] = relationship(
        "CanonicalMenuItem",
        back_populates="category",
        lazy="selectin",
    )


class CanonicalMenuItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_menu_items"

    canonical_restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_restaurants.id"),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_categories.id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_label: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    canonical_restaurant: Mapped["CanonicalRestaurant"] = relationship(
        "CanonicalRestaurant", back_populates="canonical_menu_items"
    )
    category: Mapped["MenuCategory | None"] = relationship(
        "MenuCategory", back_populates="canonical_menu_items"
    )
    platform_menu_items: Mapped[list["PlatformMenuItem"]] = relationship(
        "PlatformMenuItem",
        back_populates="canonical_menu_item",
        lazy="selectin",
    )
    canonical_modifier_groups: Mapped[list["CanonicalModifierGroup"]] = relationship(
        "CanonicalModifierGroup",
        back_populates="canonical_menu_item",
        lazy="noload",
    )


class PlatformMenuItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "platform_menu_items"
    __table_args__ = (
        Index("idx_menu_items_restaurant", "platform_restaurant_id", "is_available"),
    )

    canonical_menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_menu_items.id"),
        nullable=False,
    )
    platform_restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_restaurants.id"),
        nullable=False,
    )
    platform_item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform_name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_grosz: Mapped[int] = mapped_column(Integer, nullable=False)
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    canonical_menu_item: Mapped["CanonicalMenuItem"] = relationship(
        "CanonicalMenuItem", back_populates="platform_menu_items"
    )
    platform_restaurant: Mapped["PlatformRestaurant"] = relationship(
        "PlatformRestaurant", back_populates="platform_menu_items"
    )
    modifier_groups: Mapped[list["ModifierGroup"]] = relationship(
        "ModifierGroup",
        back_populates="platform_menu_item",
        lazy="selectin",
    )
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory",
        back_populates="platform_menu_item",
        lazy="noload",
    )
    feedbacks: Mapped[list["UserFeedback"]] = relationship(
        "UserFeedback",
        back_populates="platform_menu_item",
        lazy="noload",
    )
