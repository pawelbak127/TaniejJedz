import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class ModifierGroup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "modifier_groups"
    __table_args__ = (
        Index("idx_modifier_groups_item", "platform_menu_item_id"),
    )

    platform_menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_menu_items.id"),
        nullable=False,
    )
    canonical_modifier_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_modifier_groups.id"),
        nullable=True,  # Phase 2
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="optional"
    )  # required | optional
    min_selections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_selections: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    platform_group_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    platform_menu_item: Mapped["PlatformMenuItem"] = relationship(
        "PlatformMenuItem", back_populates="modifier_groups"
    )
    canonical_modifier_group: Mapped["CanonicalModifierGroup | None"] = relationship(
        "CanonicalModifierGroup", back_populates="modifier_groups"
    )
    modifier_options: Mapped[list["ModifierOption"]] = relationship(
        "ModifierOption",
        back_populates="modifier_group",
        lazy="selectin",
    )


class ModifierOption(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "modifier_options"
    __table_args__ = (
        Index("idx_modifier_options_group", "modifier_group_id"),
    )

    modifier_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modifier_groups.id"),
        nullable=False,
    )
    canonical_modifier_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_modifier_options.id"),
        nullable=True,  # Phase 2
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    price_grosz: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    platform_option_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    modifier_group: Mapped["ModifierGroup"] = relationship(
        "ModifierGroup", back_populates="modifier_options"
    )
    canonical_modifier_option: Mapped["CanonicalModifierOption | None"] = relationship(
        "CanonicalModifierOption", back_populates="modifier_options"
    )


# ── Phase 2 canonical modifier tables ──────────────────────


class CanonicalModifierGroup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "canonical_modifier_groups"

    canonical_menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_menu_items.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_type: Mapped[str] = mapped_column(String(20), nullable=False, default="optional")
    min_selections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_selections: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    canonical_menu_item: Mapped["CanonicalMenuItem"] = relationship(
        "CanonicalMenuItem", back_populates="canonical_modifier_groups"
    )
    canonical_modifier_options: Mapped[list["CanonicalModifierOption"]] = relationship(
        "CanonicalModifierOption",
        back_populates="canonical_modifier_group",
        lazy="selectin",
    )
    modifier_groups: Mapped[list["ModifierGroup"]] = relationship(
        "ModifierGroup",
        back_populates="canonical_modifier_group",
        lazy="noload",
    )


class CanonicalModifierOption(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "canonical_modifier_options"

    canonical_modifier_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_modifier_groups.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    canonical_modifier_group: Mapped["CanonicalModifierGroup"] = relationship(
        "CanonicalModifierGroup", back_populates="canonical_modifier_options"
    )
    modifier_options: Mapped[list["ModifierOption"]] = relationship(
        "ModifierOption",
        back_populates="canonical_modifier_option",
        lazy="noload",
    )
