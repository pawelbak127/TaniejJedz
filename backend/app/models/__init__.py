"""SQLAlchemy ORM models for TaniejJedz.

All models are imported here so Alembic's autogenerate can discover them.
"""

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.city import City
from app.models.restaurant import CanonicalRestaurant, OperatingHours, PlatformRestaurant
from app.models.menu import CanonicalMenuItem, MenuCategory, PlatformMenuItem
from app.models.modifier import (
    CanonicalModifierGroup,
    CanonicalModifierOption,
    ModifierGroup,
    ModifierOption,
)
from app.models.delivery import DeliveryFee
from app.models.promotion import Promotion
from app.models.comparison import AffiliateClick, ComparisonLog
from app.models.feedback import EntityReviewQueue, UserFeedback
from app.models.analytics import AnalyticsEvent, PriceHistory
from app.models.scraper_health import ScraperHealth
from app.models.feature_flag import FeatureFlag

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "City",
    "CanonicalRestaurant",
    "PlatformRestaurant",
    "OperatingHours",
    "MenuCategory",
    "CanonicalMenuItem",
    "PlatformMenuItem",
    "ModifierGroup",
    "ModifierOption",
    "CanonicalModifierGroup",
    "CanonicalModifierOption",
    "DeliveryFee",
    "Promotion",
    "ComparisonLog",
    "AffiliateClick",
    "UserFeedback",
    "EntityReviewQueue",
    "AnalyticsEvent",
    "PriceHistory",
    "ScraperHealth",
    "FeatureFlag",
]
