"""Schemas for GET /api/v1/restaurants/{id}/menu."""

from pydantic import BaseModel, Field


class ModifierOptionSchema(BaseModel):
    """Single modifier option (e.g. 'Extra cheese +3.50 zł')."""

    id: str
    name: str
    price_grosz: int
    is_default: bool = False
    is_available: bool = True
    platform_option_id: str | None = None


class ModifierGroupSchema(BaseModel):
    """Group of modifier options (e.g. 'Rozmiar', 'Dodatki')."""

    id: str
    name: str
    group_type: str = "optional"  # required | optional
    min_selections: int = 0
    max_selections: int = 1
    options: list[ModifierOptionSchema] = Field(default_factory=list)


class PlatformPrice(BaseModel):
    """Price + modifiers for a single item on a single platform."""

    platform: str
    platform_item_id: str
    platform_name: str
    price_grosz: int
    is_available: bool = True
    last_scraped_at: str | None = None
    modifier_groups: list[ModifierGroupSchema] = Field(default_factory=list)


class MenuItem(BaseModel):
    """Canonical menu item with per-platform prices and modifiers."""

    id: str
    name: str
    description: str | None = None
    size_label: str | None = None
    platform_prices: list[PlatformPrice] = Field(default_factory=list)


class MenuCategorySchema(BaseModel):
    """Menu category grouping items."""

    id: str
    name: str
    sort_order: int = 0
    items: list[MenuItem] = Field(default_factory=list)


class MenuResponse(BaseModel):
    """Response for GET /api/v1/restaurants/{id}/menu."""

    restaurant_id: str
    restaurant_name: str
    categories: list[MenuCategorySchema] = Field(default_factory=list)
    platforms_available: list[str] = Field(default_factory=list)
