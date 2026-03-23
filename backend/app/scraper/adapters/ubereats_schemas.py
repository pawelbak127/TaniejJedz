"""
Uber Eats API schemas — built from real API dumps (March 2026).

Endpoints (all POST to ubereats.com/_p/api/):
  Search:  getSearchSuggestionsV1 → store UUIDs + slugs
  Menu:    getStoreV1 → store info + full menu

Key insights:
  - Price already in GROSZ (2200 = 22.00 PLN)
  - Search via suggestions: query common terms → collect store UUIDs
  - Store identified by UUID (not slug)
  - Modifiers not in listing (hasCustomizations flag only)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# SEARCH — getSearchSuggestionsV1
# ═══════════════════════════════════════════════════════════════


class UberEatsSuggestionStore(BaseModel):
    """Store entry from search suggestion."""
    uuid: str = ""
    title: str = ""
    slug: str = ""
    categories: list[str | None] = Field(default_factory=list)
    heroImageUrl: str | None = None
    isOrderable: bool = False

    model_config = {"extra": "allow"}

    @property
    def cuisine_tags(self) -> list[str]:
        return [c for c in self.categories if c]


class UberEatsSuggestion(BaseModel):
    """Single suggestion result."""
    type: str = ""  # "store", "item", "search"
    title: str = ""
    store: UberEatsSuggestionStore | None = None

    model_config = {"extra": "allow"}


class UberEatsSuggestionsResponse(BaseModel):
    """getSearchSuggestionsV1 response."""
    data: list[UberEatsSuggestion] = Field(default_factory=list)
    status: str = ""

    model_config = {"extra": "allow"}

    def store_results(self) -> list[UberEatsSuggestionStore]:
        """Extract only store-type suggestions."""
        return [s.store for s in self.data if s.type == "store" and s.store]


# ═══════════════════════════════════════════════════════════════
# STORE + MENU — getStoreV1
# ═══════════════════════════════════════════════════════════════


class UberEatsLocation(BaseModel):
    address: str = ""
    streetAddress: str = ""
    city: str = ""
    country: str = ""
    postalCode: str = ""
    latitude: float = 0.0
    longitude: float = 0.0

    model_config = {"extra": "allow"}


class UberEatsRating(BaseModel):
    ratingValue: float = 0.0
    reviewCount: str | int = "0"

    model_config = {"extra": "allow"}

    @property
    def count(self) -> int:
        if isinstance(self.reviewCount, int):
            return self.reviewCount
        try:
            return int(self.reviewCount.replace("+", "").replace(",", ""))
        except (ValueError, AttributeError):
            return 0


class UberEatsCatalogItem(BaseModel):
    """Single menu item from catalogItems[]."""
    uuid: str = ""
    title: str = ""
    itemDescription: str | None = None
    price: int = 0  # Already GROSZ! (2200 = 22.00 PLN)
    imageUrl: str | None = None
    isSoldOut: bool = False
    isAvailable: bool = True
    hasCustomizations: bool = False
    subsectionUuid: str = ""
    sectionUuid: str = ""

    model_config = {"extra": "allow"}

    @property
    def price_grosz(self) -> int:
        return self.price


class UberEatsSectionTitle(BaseModel):
    text: str = ""

    model_config = {"extra": "allow"}


class UberEatsStandardItemsPayload(BaseModel):
    title: UberEatsSectionTitle | dict | str = Field(default_factory=UberEatsSectionTitle)
    catalogItems: list[UberEatsCatalogItem] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    @property
    def title_text(self) -> str:
        if isinstance(self.title, UberEatsSectionTitle):
            return self.title.text
        if isinstance(self.title, dict):
            return self.title.get("text", "")
        return str(self.title)


class UberEatsCatalogEntryPayload(BaseModel):
    standardItemsPayload: UberEatsStandardItemsPayload | None = None
    type: str = ""

    model_config = {"extra": "allow"}


class UberEatsCatalogEntry(BaseModel):
    type: str = ""
    payload: UberEatsCatalogEntryPayload = Field(default_factory=UberEatsCatalogEntryPayload)
    catalogSectionUUID: str = ""

    model_config = {"extra": "allow"}


class UberEatsEtaRange(BaseModel):
    text: str = ""

    model_config = {"extra": "allow"}


class UberEatsFareInfo(BaseModel):
    serviceFeeCents: int | None = None

    model_config = {"extra": "allow"}


class UberEatsStoreData(BaseModel):
    """Top-level store data from getStoreV1."""
    uuid: str = ""
    title: str = ""
    slug: str = ""
    isOpen: bool = False
    isOrderable: bool = False
    location: UberEatsLocation = Field(default_factory=UberEatsLocation)
    rating: UberEatsRating | None = None
    cuisineList: list[str] = Field(default_factory=list)
    etaRange: UberEatsEtaRange | None = None
    fareInfo: UberEatsFareInfo | None = None
    catalogSectionsMap: dict[str, list[UberEatsCatalogEntry]] = Field(default_factory=dict)
    sections: list[dict] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    def all_items(self) -> list[tuple[str, UberEatsCatalogItem]]:
        """Extract (section_title, item) pairs, deduped by uuid."""
        result: list[tuple[str, UberEatsCatalogItem]] = []
        seen: set[str] = set()

        for entries in self.catalogSectionsMap.values():
            for entry in entries:
                if not entry.payload or not entry.payload.standardItemsPayload:
                    continue
                sip = entry.payload.standardItemsPayload
                section_title = sip.title_text

                for item in sip.catalogItems:
                    if item.uuid and item.uuid not in seen:
                        seen.add(item.uuid)
                        result.append((section_title, item))

        return result

    @property
    def delivery_eta_text(self) -> str | None:
        return self.etaRange.text if self.etaRange else None

    @property
    def service_fee_grosz(self) -> int:
        if self.fareInfo and self.fareInfo.serviceFeeCents is not None:
            return self.fareInfo.serviceFeeCents
        return 0


class UberEatsStoreResponse(BaseModel):
    data: UberEatsStoreData = Field(default_factory=UberEatsStoreData)
    status: str = ""

    model_config = {"extra": "allow"}
