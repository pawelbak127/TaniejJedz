"""
Wolt API response schemas — built from REAL response dumps (March 2026).

SEARCH venue fields verified from diag_venue.json.
MENU structure verified from diag_menu_sections.json + diag_menu_item.json.

Key architecture insight: modifiers are TWO-LEVEL.
  - Section level: options[] contain full definitions (values with prices)
  - Item level: options[] contain REFERENCES (option_id → section option)
  Adapter must JOIN them via option_id lookup.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# SEARCH — /v1/pages/restaurants
# ═══════════════════════════════════════════════════════════════


class WoltBrandImage(BaseModel):
    url: str = ""
    blurhash: str | None = None

    model_config = {"extra": "allow"}


class WoltRating(BaseModel):
    rating: int = 0        # 1-5 stars
    score: float = 0       # 0-10
    volume: int = 0        # number of ratings

    model_config = {"extra": "allow"}


class WoltVenue(BaseModel):
    """Venue from search results — fields verified against real API."""

    slug: str = ""
    name: str = ""
    address: str = ""
    city: str = ""
    location: list[float] = Field(default_factory=list)  # [lng, lat]
    rating: WoltRating | None = None
    delivers: bool = False
    online: bool = True
    estimate: int | None = None          # minutes (single number)
    estimate_range: str | None = None    # "15-25"
    tags: list[str] = Field(default_factory=list)
    brand_image: WoltBrandImage | None = None
    short_description: str | None = None
    price_range: int | None = None
    product_line: str | None = None
    promotions: list[dict] = Field(default_factory=list)
    # NOTE: delivery fee is NOT in venue object

    model_config = {"extra": "allow"}

    @property
    def latitude(self) -> float:
        return self.location[1] if len(self.location) >= 2 else 0.0

    @property
    def longitude(self) -> float:
        return self.location[0] if len(self.location) >= 2 else 0.0

    @property
    def image_url(self) -> str | None:
        return self.brand_image.url if self.brand_image else None

    @property
    def delivery_minutes_avg(self) -> int | None:
        if self.estimate_range:
            try:
                parts = self.estimate_range.split("-")
                return (int(parts[0]) + int(parts[1])) // 2
            except (ValueError, IndexError):
                pass
        return self.estimate


class WoltSearchItem(BaseModel):
    venue: WoltVenue | None = None

    model_config = {"extra": "allow"}


class WoltSearchSection(BaseModel):
    name: str = ""
    title: str = ""
    items: list[WoltSearchItem] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class WoltSearchResponse(BaseModel):
    sections: list[WoltSearchSection] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    def all_venues(self) -> list[WoltVenue]:
        """Extract all venues, deduped by slug. Skip non-venue sections."""
        seen: set[str] = set()
        venues: list[WoltVenue] = []
        for section in self.sections:
            for item in section.items:
                if item.venue and item.venue.slug and item.venue.slug not in seen:
                    seen.add(item.venue.slug)
                    venues.append(item.venue)
        return venues


# ═══════════════════════════════════════════════════════════════
# MENU — /venue-content/slug/{slug}
#
# Architecture: Server-Driven UI
#   response.sections[] — each section is a menu category
#   section.items[]     — menu items (with option REFERENCES)
#   section.options[]   — modifier group DEFINITIONS (with values/prices)
#
# JOIN: item.options[].option_id → section.options[].id
# ═══════════════════════════════════════════════════════════════


class WoltOptionValue(BaseModel):
    """A single modifier choice (e.g. 'Grube ciasto +3.99', 'Sos BBQ +3.99')."""
    id: str = ""
    name: str = ""
    price: int = 0  # grosz

    model_config = {"extra": "allow"}


class WoltSectionOption(BaseModel):
    """Modifier group DEFINITION at section level — has values with prices."""
    id: str = ""
    name: str = ""
    type: str = "multi_choice"
    values: list[WoltOptionValue] = Field(default_factory=list)
    default_value: str | None = None

    model_config = {"extra": "allow"}


class WoltTotalRange(BaseModel):
    min: int = 0
    max: int = 1

    model_config = {"extra": "allow"}


class WoltItemMultiChoiceConfig(BaseModel):
    """Per-item min/max override for a modifier group."""
    total_range: WoltTotalRange = Field(default_factory=WoltTotalRange)
    max_single_selections: int = 1
    free_selections: int = 0

    model_config = {"extra": "allow"}


class WoltItemOption(BaseModel):
    """Modifier group REFERENCE on item — points to section option via option_id."""
    id: str = ""
    option_id: str = ""   # JOIN key → WoltSectionOption.id
    name: str = ""
    multi_choice_config: WoltItemMultiChoiceConfig = Field(
        default_factory=WoltItemMultiChoiceConfig
    )

    model_config = {"extra": "allow"}

    @property
    def min_selections(self) -> int:
        return self.multi_choice_config.total_range.min

    @property
    def max_selections(self) -> int:
        return self.multi_choice_config.total_range.max

    @property
    def is_required(self) -> bool:
        return self.min_selections > 0


class WoltMenuItem(BaseModel):
    """Menu item — verified from diag_menu_item.json.

    - price (not baseprice) in grosz
    - disabled_info: null = available, dict = disabled
    - images: list of {url, blurhash}
    - options: REFERENCES (option_id), not inline definitions
    """
    id: str = ""
    name: str = ""
    description: str | None = None
    price: int = 0
    disabled_info: dict | None = None
    images: list[dict] = Field(default_factory=list)
    options: list[WoltItemOption] = Field(default_factory=list)
    original_price: int | None = None

    model_config = {"extra": "allow"}

    @property
    def is_available(self) -> bool:
        return self.disabled_info is None

    @property
    def image_url(self) -> str | None:
        if self.images:
            return self.images[0].get("url")
        return None


class WoltMenuSection(BaseModel):
    """Menu section — has items AND option definitions."""
    name: str = ""
    slug: str = ""
    items: list[WoltMenuItem] = Field(default_factory=list)
    options: list[WoltSectionOption] = Field(default_factory=list)

    model_config = {"extra": "allow"}


MARKETING_SECTIONS = {
    "Najczęściej zamawiane", "Popularne", "Popular",
    "Bestsellery", "Polecane", "Recommended",
}


class WoltMenuResponse(BaseModel):
    """Top-level menu response."""
    sections: list[WoltMenuSection] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    def build_option_lookup(self) -> dict[str, WoltSectionOption]:
        """Build {option_id: definition} from all sections' options."""
        lookup: dict[str, WoltSectionOption] = {}
        for section in self.sections:
            for opt in section.options:
                if opt.id:
                    lookup[opt.id] = opt
        return lookup

    def deduplicated_items(self) -> list[tuple[str, WoltMenuItem]]:
        """(category_name, item) pairs, deduped by id. Non-marketing first."""
        seen: set[str] = set()
        result: list[tuple[str, WoltMenuItem]] = []

        for section in self.sections:
            if section.name in MARKETING_SECTIONS:
                continue
            for item in section.items:
                if item.id and item.id not in seen:
                    seen.add(item.id)
                    result.append((section.name, item))

        for section in self.sections:
            if section.name not in MARKETING_SECTIONS:
                continue
            for item in section.items:
                if item.id and item.id not in seen:
                    seen.add(item.id)
                    result.append((section.name, item))

        return result
