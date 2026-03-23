"""
Glovo API response schemas — built from real API dumps (March 2026).

Store detail: GET api.glovoapp.com/v3/stores/{slug}?cityCode=WAW
Menu content: GET api.glovoapp.com/v4/stores/{id}/addresses/{addressId}/content/main

Key insights:
  - No search/discovery API (decommissioned) — store list from HTML or known slugs
  - Store detail returns id + addressId needed for menu endpoint
  - Menu is flat: sections → PRODUCT_ROW elements with inline attributeGroups
  - Prices in PLN float (priceInfo.amount), modifiers have priceImpact (PLN float)
  - Modifiers are INLINE (not references like Wolt/Pyszne) — simpler
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# STORE DETAIL — /v3/stores/{slug}
# ═══════════════════════════════════════════════════════════════


class GlovoDeliveryFeeInfo(BaseModel):
    fee: float = 0.0  # PLN
    style: str = "DEFAULT"

    model_config = {"extra": "allow"}


class GlovoStoreAvailability(BaseModel):
    status: str = ""  # "OPEN", "CLOSED"
    nextSchedulingOrOpeningTime: str | None = None
    footerLabel: str | None = None

    model_config = {"extra": "allow"}


class GlovoStoreFilter(BaseModel):
    """Cuisine/tag filter — serves as cuisine tags."""
    id: int = 0
    name: str = ""
    displayName: str = ""
    slug: str = ""

    model_config = {"extra": "allow"}


class GlovoStore(BaseModel):
    """Store detail from /v3/stores/{slug}."""
    id: int = 0
    slug: str = ""
    name: str = ""
    address: str = ""
    addressId: int = 0
    cityCode: str = ""
    category: str = ""
    open: bool = False
    enabled: bool = True
    food: bool = True
    imageId: str | None = None
    logoImageId: str | None = None
    serviceFee: float | None = None  # PLN
    deliveryFeeInfo: GlovoDeliveryFeeInfo | None = None
    availability: GlovoStoreAvailability | None = None
    filters: list[GlovoStoreFilter] = Field(default_factory=list)
    promotions: list[dict] = Field(default_factory=list)
    rating: str | None = None  # "91%" format in RSC, null in API
    nextOpeningTime: str | None = None
    schedulingEnabled: bool = False

    model_config = {"extra": "allow"}

    @property
    def delivery_fee_grosz(self) -> int:
        if self.deliveryFeeInfo:
            return int(round(self.deliveryFeeInfo.fee * 100))
        return 0

    @property
    def service_fee_grosz(self) -> int:
        if self.serviceFee is not None:
            return int(round(self.serviceFee * 100))
        return 0

    @property
    def cuisine_tags(self) -> list[str]:
        return [f.displayName or f.name for f in self.filters if f.name]

    @property
    def is_online(self) -> bool:
        if self.availability:
            return self.availability.status == "OPEN"
        return self.open and self.enabled


# ═══════════════════════════════════════════════════════════════
# MENU CONTENT — /v4/stores/{id}/addresses/{addressId}/content/main
#
# Structure:
#   {type: "LIST_VIEW_LAYOUT", data: {body: [sections]}}
#   section: {type: "LIST", data: {title, elements: [products]}}
#   product: {type: "PRODUCT_ROW", data: {id, name, price, priceInfo, attributeGroups}}
#   attributeGroup: {name, min, max, multipleSelection, attributes[]}
#   attribute: {name, priceImpact, priceInfo: {amount}, selected}
# ═══════════════════════════════════════════════════════════════


class GlovoAttribute(BaseModel):
    """Single modifier option — inline in attributeGroup."""
    id: int = 0
    name: str = ""
    priceImpact: float = 0.0  # PLN delta
    priceInfo: dict = Field(default_factory=dict)  # {amount, currencyCode, displayText}
    selected: bool = False
    externalId: str = ""

    model_config = {"extra": "allow"}

    @property
    def price_grosz(self) -> int:
        return int(round(self.priceImpact * 100))


class GlovoAttributeGroup(BaseModel):
    """Modifier group — inline with all options."""
    id: int = 0
    name: str = ""
    min: int = 0
    max: int = 1
    attributes: list[GlovoAttribute] = Field(default_factory=list)
    position: int = 0
    multipleSelection: bool = False
    collapsedByDefault: bool = False
    externalId: str = ""

    model_config = {"extra": "allow"}

    @property
    def is_required(self) -> bool:
        return self.min > 0


class GlovoPriceInfo(BaseModel):
    amount: float = 0.0  # PLN
    currencyCode: str = "PLN"
    displayText: str = ""

    model_config = {"extra": "allow"}


class GlovoProduct(BaseModel):
    """Single product from menu content."""
    id: int = 0
    name: str = ""
    description: str | None = None
    price: float = 0.0  # PLN
    priceInfo: GlovoPriceInfo = Field(default_factory=GlovoPriceInfo)
    imageUrl: str | None = None
    imageId: str | None = None
    attributeGroups: list[GlovoAttributeGroup] = Field(default_factory=list)
    outOfStock: bool = False
    externalId: str = ""
    storeProductId: str = ""

    model_config = {"extra": "allow"}

    @property
    def price_grosz(self) -> int:
        return int(round(self.price * 100))

    @property
    def is_available(self) -> bool:
        return not self.outOfStock


class GlovoMenuElement(BaseModel):
    """Wrapper for elements in a section."""
    type: str = ""
    data: GlovoProduct | dict = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class GlovoMenuSectionData(BaseModel):
    """Section data containing title and product elements."""
    title: str = ""
    slug: str = ""
    elements: list[GlovoMenuElement] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class GlovoMenuSection(BaseModel):
    """Section in menu body."""
    type: str = ""
    data: GlovoMenuSectionData = Field(default_factory=GlovoMenuSectionData)

    model_config = {"extra": "allow"}


class GlovoMenuBody(BaseModel):
    body: list[GlovoMenuSection] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class GlovoMenuResponse(BaseModel):
    """Top-level menu response."""
    type: str = ""
    data: GlovoMenuBody = Field(default_factory=GlovoMenuBody)

    model_config = {"extra": "allow"}

    def all_products(self) -> list[tuple[str, GlovoProduct]]:
        """Extract (section_title, product) pairs, deduped by product id."""
        seen: set[int] = set()
        result: list[tuple[str, GlovoProduct]] = []

        # Skip "Top sellers" — same dedup logic as Wolt "Popularne"
        marketing = {"Top sellers", "Bestsellery", "Popularne"}

        # Non-marketing first
        for section in self.data.body:
            if section.data.title in marketing:
                continue
            for element in section.data.elements:
                if element.type != "PRODUCT_ROW":
                    continue
                product = self._parse_product(element)
                if product and product.id not in seen:
                    seen.add(product.id)
                    result.append((section.data.title, product))

        # Marketing-only items
        for section in self.data.body:
            if section.data.title not in marketing:
                continue
            for element in section.data.elements:
                if element.type != "PRODUCT_ROW":
                    continue
                product = self._parse_product(element)
                if product and product.id not in seen:
                    seen.add(product.id)
                    result.append((section.data.title, product))

        return result

    @staticmethod
    def _parse_product(element: GlovoMenuElement) -> GlovoProduct | None:
        if isinstance(element.data, GlovoProduct):
            return element.data
        if isinstance(element.data, dict):
            try:
                return GlovoProduct.model_validate(element.data)
            except Exception:
                return None
        return None
