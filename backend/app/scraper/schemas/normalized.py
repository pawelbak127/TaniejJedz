"""
Normalized scraper output schemas — platform-agnostic.

These map directly to existing SQLAlchemy models:
  NormalizedRestaurant  → models.restaurant.PlatformRestaurant
  NormalizedMenuItem    → models.menu.PlatformMenuItem
  NormalizedModifier*   → models.modifier.ModifierGroup / ModifierOption
  NormalizedHours       → models.restaurant.OperatingHours
  NormalizedDeliveryFee → models.restaurant.DeliveryFee
  NormalizedPromotion   → models.restaurant.Promotion

All adapters (Wolt, Pyszne) normalise their raw responses to these schemas.
"""

from __future__ import annotations

from datetime import time
from pydantic import BaseModel, Field


class NormalizedModifierOption(BaseModel):
    """Single modifier option → models.modifier.ModifierOption."""

    platform_option_id: str
    name: str
    normalized_name: str = ""
    price_grosz: int = 0
    is_default: bool = False
    is_available: bool = True


class NormalizedModifierGroup(BaseModel):
    """Modifier group → models.modifier.ModifierGroup."""

    platform_group_id: str
    name: str
    group_type: str = "optional"  # "required" | "optional"
    min_selections: int = 0
    max_selections: int = 1
    sort_order: int = 0
    options: list[NormalizedModifierOption] = Field(default_factory=list)


class NormalizedMenuItem(BaseModel):
    """Menu item → models.menu.PlatformMenuItem."""

    platform_item_id: str
    platform_name: str  # display name on the platform
    description: str | None = None
    price_grosz: int
    is_available: bool = True
    category_name: str = ""  # for grouping into MenuCategory
    category_sort_order: int = 0
    modifier_groups: list[NormalizedModifierGroup] = Field(default_factory=list)


class NormalizedHours(BaseModel):
    """Operating hours for one day → models.restaurant.OperatingHours."""

    day_of_week: int  # 0=Mon, 6=Sun
    open_time: time
    close_time: time
    is_closed: bool = False


class NormalizedDeliveryFee(BaseModel):
    """Delivery fee for a location → models.restaurant.DeliveryFee."""

    fee_grosz: int
    minimum_order_grosz: int = 0
    free_delivery_threshold_grosz: int | None = None
    estimated_minutes: int | None = None


class NormalizedPromotion(BaseModel):
    """Platform promotion → models.restaurant.Promotion."""

    platform_promo_id: str
    title: str
    description: str = ""
    promo_type: str = "discount"  # discount | free_delivery | bogo | other
    discount_percentage: float | None = None
    discount_amount_grosz: int | None = None
    minimum_order_grosz: int | None = None
    valid_from: str | None = None
    valid_until: str | None = None


class NormalizedRestaurant(BaseModel):
    """
    Full restaurant data from a single platform.
    Maps to models.restaurant.PlatformRestaurant + relations.
    """

    platform: str  # "wolt" | "pyszne"
    platform_restaurant_id: str
    platform_name: str
    platform_slug: str | None = None
    platform_url: str | None = None

    # Location
    name: str
    address_street: str | None = None
    address_city: str | None = None
    latitude: float
    longitude: float

    # Metadata
    cuisine_tags: list[str] = Field(default_factory=list)
    image_url: str | None = None
    rating_score: float | None = None
    rating_count: int | None = None
    is_online: bool = True

    # Nested data (populated by separate adapter calls)
    menu_items: list[NormalizedMenuItem] = Field(default_factory=list)
    operating_hours: list[NormalizedHours] = Field(default_factory=list)
    delivery_fee: NormalizedDeliveryFee | None = None
    promotions: list[NormalizedPromotion] = Field(default_factory=list)
