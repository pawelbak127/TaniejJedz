"""Schemas for POST /api/v1/compare and GET /api/v1/compare/stream."""

import hashlib
import json

from pydantic import BaseModel, Field


class AddressCoords(BaseModel):
    """Delivery address coordinates."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class CartItem(BaseModel):
    """Single item in the comparison cart."""

    canonical_item_id: str
    quantity: int = Field(..., ge=1, le=99)
    selected_modifiers: dict[str, list[str]] = Field(
        default_factory=dict,
        description="platform → list of selected modifier option IDs",
    )


class CompareRequest(BaseModel):
    """Request body for POST /api/v1/compare."""

    restaurant_id: str
    address: AddressCoords
    items: list[CartItem] = Field(..., min_length=1)

    def compute_idempotency_key(self) -> str:
        """SHA-256 hash of restaurant + address + sorted items for dedup."""
        payload = json.dumps(
            {
                "restaurant_id": self.restaurant_id,
                "lat": self.address.latitude,
                "lng": self.address.longitude,
                "items": sorted(
                    [
                        {
                            "id": item.canonical_item_id,
                            "qty": item.quantity,
                            "mods": {
                                k: sorted(v)
                                for k, v in sorted(item.selected_modifiers.items())
                            },
                        }
                        for item in self.items
                    ],
                    key=lambda x: x["id"],
                ),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class CompareResponse(BaseModel):
    """Response for POST /api/v1/compare."""

    comparison_id: str
    status: str = "processing"  # "processing" | "already_processing"


class ComparisonItem(BaseModel):
    """Single item result within a platform comparison."""

    canonical_item_id: str
    name: str
    quantity: int
    unit_price_grosz: int
    modifiers_price_grosz: int = 0
    item_total_grosz: int


class PlatformComparisonResult(BaseModel):
    """Full comparison result for a single platform (SSE platform_status event)."""

    platform: str
    is_open: bool
    next_open: str | None = None
    items: list[ComparisonItem] = Field(default_factory=list)
    items_total_grosz: int = 0
    delivery_fee_grosz: int = 0
    promotion_discount_grosz: int = 0
    grand_total_grosz: int = 0
    meets_minimum_order: bool = True
    minimum_order_grosz: int | None = None
    estimated_delivery_minutes: int | None = None
    missing_items: list[str] = Field(default_factory=list)
    deep_link: str = ""


class ComparisonReadyPayload(BaseModel):
    """Payload for SSE comparison_ready event."""

    comparison_id: str
    cheapest_platform: str | None = None
    savings_grosz: int = 0
    platforms: dict[str, PlatformComparisonResult] = Field(default_factory=dict)
