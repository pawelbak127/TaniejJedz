"""Schemas for POST /api/v1/search."""

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Address-based restaurant search request."""

    address: str = Field(..., min_length=1, max_length=500, examples=["Marszałkowska 1, Warszawa"])
    latitude: float = Field(..., ge=-90, le=90, examples=[52.2297])
    longitude: float = Field(..., ge=-180, le=180, examples=[21.0122])
    radius_km: float = Field(default=3.0, ge=0.5, le=15.0)
    cuisine_filter: list[str] = Field(default_factory=list)
    sort_by: str = Field(
        default="relevance",
        pattern="^(relevance|cheapest_delivery|rating)$",
    )
    show_closed: bool = False
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=50)


class PlatformAvailability(BaseModel):
    """Per-platform availability info shown on restaurant card."""

    available: bool
    is_open: bool
    next_open: str | None = None
    rating: float | None = None
    delivery_minutes: int | None = None
    delivery_fee_grosz: int | None = None


class RestaurantSummary(BaseModel):
    """Single restaurant in search results."""

    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    cuisine_tags: list[str]
    image_url: str | None = None
    data_quality_score: float
    platforms: dict[str, PlatformAvailability]
    cheapest_open_platform: str | None = None
    cheapest_delivery_fee_grosz: int | None = None


class DataFreshnessInfo(BaseModel):
    """Freshness info for a single platform in a city."""

    last_scraped_at: str | None = None
    staleness_label: str | None = None  # "fresh" | "stale_minutes" | "stale_warning"


class SearchResponse(BaseModel):
    """Response for POST /api/v1/search."""

    restaurants: list[RestaurantSummary]
    total: int
    page: int
    per_page: int
    city: str
    data_freshness: dict[str, DataFreshnessInfo] = Field(default_factory=dict)
