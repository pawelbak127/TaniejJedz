"""
Pyszne.pl schemas — built from REAL API dumps (March 2026).

SEARCH: JET Discovery API — verified from diag_pyszne_restaurant.json
  - address.location.coordinates [lng, lat] (GeoJSON Point)
  - deliveryCost: float|int PLN
  - rating: {count, starRating}
  - cuisines[].name

MENU CDN: verified from diag dumps
  - Categories in cdn.restaurant.menus[0].categories[] (LIST with itemIds)
  - Items in cdn.items (DICT {id: item})
  - item.variations[].basePrice is INT PLN (56 = 56 zł)
  - modifierGroups is a LIST, key 'modifiers' (not modifierSetIds)
  - modifierSets is a LIST, price in modifier.additionPrice (INT PLN)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# SEARCH — JET Discovery API
# ═══════════════════════════════════════════════════════════════


class PyszneGeoLocation(BaseModel):
    type: str = "Point"
    coordinates: list[float] = Field(default_factory=list)  # [lng, lat]

    model_config = {"extra": "allow"}

    @property
    def lat(self) -> float:
        return self.coordinates[1] if len(self.coordinates) >= 2 else 0.0

    @property
    def lng(self) -> float:
        return self.coordinates[0] if len(self.coordinates) >= 2 else 0.0


class PyszneAddress(BaseModel):
    city: str = ""
    firstLine: str = ""
    postalCode: str = ""
    location: PyszneGeoLocation | None = None

    model_config = {"extra": "allow"}

    @property
    def full_address(self) -> str | None:
        parts = []
        if self.firstLine:
            parts.append(self.firstLine)
        if self.city:
            parts.append(self.city)
        return ", ".join(parts) if parts else None


class PyszneRating(BaseModel):
    count: int = 0
    starRating: float = 0.0
    userRating: float | None = None

    model_config = {"extra": "allow"}


class PyszneCuisine(BaseModel):
    name: str = ""
    uniqueName: str = ""

    model_config = {"extra": "allow"}


class PyszneEtaMinutes(BaseModel):
    approximate: int | None = None
    rangeLower: int | None = None
    rangeUpper: int | None = None

    model_config = {"extra": "allow"}

    @property
    def avg(self) -> int | None:
        if self.rangeLower and self.rangeUpper:
            return (self.rangeLower + self.rangeUpper) // 2
        return self.approximate


class PyszneRestaurant(BaseModel):
    id: str = ""
    uniqueName: str = ""
    name: str = ""
    address: PyszneAddress | dict | None = None
    rating: PyszneRating | None = None
    isOpenNowForDelivery: bool = False
    isDelivery: bool = False
    deliveryOpeningTimeLocal: str | None = None
    cuisines: list[PyszneCuisine] = Field(default_factory=list)
    logoUrl: str | None = None
    deliveryCost: float | int | None = None
    minimumDeliveryValue: float | int | None = None
    deliveryEtaMinutes: PyszneEtaMinutes | None = None
    deals: list[dict] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    @property
    def is_real_restaurant(self) -> bool:
        addr = self._parsed_address
        if not addr or not addr.location:
            return False
        if addr.location.lat == 0.0:
            return False
        return self.isDelivery

    @property
    def _parsed_address(self) -> PyszneAddress | None:
        if isinstance(self.address, PyszneAddress):
            return self.address
        if isinstance(self.address, dict):
            return PyszneAddress.model_validate(self.address)
        return None

    @property
    def latitude(self) -> float:
        addr = self._parsed_address
        return addr.location.lat if addr and addr.location else 0.0

    @property
    def longitude(self) -> float:
        addr = self._parsed_address
        return addr.location.lng if addr and addr.location else 0.0

    @property
    def cuisine_tags(self) -> list[str]:
        return [c.name for c in self.cuisines if c.name]

    @property
    def delivery_fee_grosz(self) -> int:
        if self.deliveryCost is not None:
            return int(round(self.deliveryCost * 100))
        return 0

    @property
    def minimum_order_grosz(self) -> int:
        if self.minimumDeliveryValue is not None:
            return int(round(self.minimumDeliveryValue * 100))
        return 0

    @property
    def delivery_minutes_avg(self) -> int | None:
        if self.deliveryEtaMinutes:
            return self.deliveryEtaMinutes.avg
        return None

    @property
    def address_str(self) -> str | None:
        addr = self._parsed_address
        return addr.full_address if addr else None

    @property
    def address_city(self) -> str | None:
        addr = self._parsed_address
        return addr.city if addr else None


class PyszneSearchResponse(BaseModel):
    restaurants: list[PyszneRestaurant] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    def real_restaurants(self) -> list[PyszneRestaurant]:
        return [r for r in self.restaurants if r.is_real_restaurant]


# ═══════════════════════════════════════════════════════════════
# MENU CDN — from __NEXT_DATA__
#
# Real structure (verified):
#   cdn.restaurant.menus[0].categories[] — {id, name, itemIds[]}
#   cdn.items — dict {id: {name, variations[], ...}}
#   cdn.modifierGroups — LIST [{id, name, minChoices, maxChoices, modifiers[]}]
#   cdn.modifierSets — LIST [{id, modifier: {name, additionPrice, ...}}]
#
#   variation.basePrice — INT PLN (56 = 56 zł → 5600 grosz)
#   modifier.additionPrice — INT PLN (4 = 4 zł → 400 grosz)
# ═══════════════════════════════════════════════════════════════


class PyszneModifierInner(BaseModel):
    """Inner modifier object inside a modifierSet entry."""
    id: str = ""
    name: str = ""
    additionPrice: float | int = 0    # PLN
    removePrice: float | int = 0
    defaultChoices: int = 0
    minChoices: int = 0
    maxChoices: int = 1

    model_config = {"extra": "allow"}

    @property
    def price_grosz(self) -> int:
        return int(round(self.additionPrice * 100))


class PyszneModifierSetEntry(BaseModel):
    """Entry in modifierSets LIST: {id, modifier: {...}}."""
    id: str = ""
    modifier: PyszneModifierInner = Field(default_factory=PyszneModifierInner)

    model_config = {"extra": "allow"}


class PyszneModifierGroupEntry(BaseModel):
    """Entry in modifierGroups LIST: {id, name, modifiers[] (IDs)}."""
    id: str = ""
    name: str = ""
    minChoices: int = 0
    maxChoices: int = 1
    modifiers: list[str] = Field(default_factory=list)  # IDs → modifierSets

    model_config = {"extra": "allow"}

    @property
    def is_required(self) -> bool:
        return self.minChoices > 0


class PyszneCdnVariation(BaseModel):
    """Item variation. basePrice is INT or FLOAT in PLN."""
    id: str = ""
    name: str = ""
    basePrice: float | int = 0  # PLN
    modifierGroupsIds: list[str] = Field(default_factory=list)
    isAvailable: bool = True
    menuGroupIds: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    @property
    def price_grosz(self) -> int:
        return int(round(float(self.basePrice) * 100))


class PyszneCdnItem(BaseModel):
    """Menu item with variations."""
    id: str = ""
    name: str = ""
    description: str | None = None
    variations: list[PyszneCdnVariation] = Field(default_factory=list)
    imageSources: list[dict] = Field(default_factory=list)
    type: str = ""

    model_config = {"extra": "allow"}

    @property
    def image_url(self) -> str | None:
        if self.imageSources:
            return self.imageSources[0].get("path")
        return None


class PyszneCdnCategory(BaseModel):
    """Menu category from menus[0].categories[]."""
    id: str = ""
    name: str = ""
    itemIds: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class PyszneCdnMenu(BaseModel):
    """Single menu entry inside cdn.restaurant.menus[]."""
    categories: list[PyszneCdnCategory] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class PyszneCdnRestaurant(BaseModel):
    """cdn.restaurant — contains menus with categories."""
    menus: list[PyszneCdnMenu] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class PyszneCdn(BaseModel):
    """Full CDN from __NEXT_DATA__.

    Key variants discovered:
      - items: DICT {id: item} (most restaurants) OR LIST [{id, name, ...}] (KFC etc.)
      - modifierGroups: LIST
      - modifierSets: LIST
      - categories in restaurant.menus[0].categories
    """
    items: dict[str, PyszneCdnItem] | list = Field(default_factory=dict)
    modifierGroups: list[PyszneModifierGroupEntry] = Field(default_factory=list)
    modifierSets: list[PyszneModifierSetEntry] = Field(default_factory=list)
    restaurant: PyszneCdnRestaurant = Field(default_factory=PyszneCdnRestaurant)

    model_config = {"extra": "allow"}

    def model_post_init(self, __context) -> None:
        """Convert items from list to dict if needed."""
        if isinstance(self.items, list):
            items_dict: dict[str, PyszneCdnItem] = {}
            for item_data in self.items:
                if isinstance(item_data, dict):
                    item_id = item_data.get("id", "")
                    if item_id:
                        try:
                            items_dict[item_id] = PyszneCdnItem.model_validate(item_data)
                        except Exception:
                            pass
                elif isinstance(item_data, PyszneCdnItem):
                    items_dict[item_data.id] = item_data
            self.items = items_dict

    def get_categories(self) -> list[PyszneCdnCategory]:
        """Get categories from first menu."""
        if self.restaurant.menus:
            return self.restaurant.menus[0].categories
        return []

    def modifier_group_lookup(self) -> dict[str, PyszneModifierGroupEntry]:
        """Build {id: group} from list."""
        return {g.id: g for g in self.modifierGroups}

    def modifier_set_lookup(self) -> dict[str, PyszneModifierSetEntry]:
        """Build {id: set} from list."""
        return {s.id: s for s in self.modifierSets}


# ═══════════════════════════════════════════════════════════════
# CDN path extraction
# ═══════════════════════════════════════════════════════════════

CDN_PATHS = [
    ["props", "appProps", "preloadedState", "menu", "restaurant", "cdn"],
    ["props", "initialState", "menu", "restaurant", "cdn"],
    ["props", "pageProps", "initialState", "menu", "restaurant", "cdn"],
    ["props", "pageProps", "menu", "restaurant", "cdn"],
]


def extract_cdn(next_data: dict) -> dict | None:
    for path in CDN_PATHS:
        node = next_data
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break
        if node is not None and isinstance(node, dict):
            return node
    return None
