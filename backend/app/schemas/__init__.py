"""Pydantic v2 request/response schemas for TaniejJedz API."""

from app.schemas.common import ErrorDetail, ErrorResponse, OrmBase, PaginationMeta
from app.schemas.search import (
    DataFreshnessInfo,
    PlatformAvailability,
    RestaurantSummary,
    SearchRequest,
    SearchResponse,
)
from app.schemas.menu import (
    MenuCategorySchema,
    MenuItem,
    MenuResponse,
    ModifierGroupSchema,
    ModifierOptionSchema,
    PlatformPrice,
)
from app.schemas.compare import (
    AddressCoords,
    CartItem,
    CompareRequest,
    CompareResponse,
    ComparisonItem,
    ComparisonReadyPayload,
    PlatformComparisonResult,
)
from app.schemas.feedback import FeedbackRequest, FeedbackResponse

__all__ = [
    # common
    "ErrorDetail",
    "ErrorResponse",
    "OrmBase",
    "PaginationMeta",
    # search
    "SearchRequest",
    "SearchResponse",
    "RestaurantSummary",
    "PlatformAvailability",
    "DataFreshnessInfo",
    # menu
    "MenuResponse",
    "MenuCategorySchema",
    "MenuItem",
    "PlatformPrice",
    "ModifierGroupSchema",
    "ModifierOptionSchema",
    # compare
    "AddressCoords",
    "CartItem",
    "CompareRequest",
    "CompareResponse",
    "ComparisonItem",
    "PlatformComparisonResult",
    "ComparisonReadyPayload",
    # feedback
    "FeedbackRequest",
    "FeedbackResponse",
]
