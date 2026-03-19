"""
Wolt adapter — built from real API dumps (March 2026).

Key design:
  - Search: venue has NO delivery fee field — fee comes from elsewhere
  - Menu: TWO-LEVEL modifiers — section defines options (values/prices),
    items reference them via option_id. Adapter JOINs them.
  - Price is in 'price' field (not 'baseprice'), already grosz
  - Availability: disabled_info is null when available
"""

from __future__ import annotations

import logging
import unicodedata

from redis.asyncio import Redis

from app.config import get_settings
from app.scraper.base_adapter import BaseAdapter, ScraperError
from app.scraper.budget_manager import Priority
from app.scraper.schemas.normalized import (
    NormalizedDeliveryFee,
    NormalizedHours,
    NormalizedMenuItem,
    NormalizedModifierGroup,
    NormalizedModifierOption,
    NormalizedPromotion,
    NormalizedRestaurant,
)
from app.scraper.adapters.wolt_schemas import (
    WoltItemOption,
    WoltMenuResponse,
    WoltMenuItem,
    WoltSearchResponse,
    WoltSectionOption,
    WoltVenue,
)

logger = logging.getLogger(__name__)

_WOLT_HEADERS = {
    "Origin": "https://wolt.com",
    "Wolt-Language": "pl",
    "Accept": "application/json",
}


class WoltParseError(ScraperError):
    """Wolt response couldn't be parsed."""
    pass


class WoltAdapter(BaseAdapter):

    PLATFORM_NAME = "wolt"
    BASE_URL = "https://wolt.com"

    def __init__(self, redis: Redis) -> None:
        super().__init__(redis)
        s = get_settings()
        self._search_url = s.wolt_search_url
        self._menu_url = s.wolt_menu_url

    # ── Public interface ────────────────────────────────────

    async def search_restaurants(
        self,
        lat: float,
        lng: float,
        radius_km: float,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedRestaurant]:
        resp = await self._get(
            self._search_url,
            params={"lat": str(lat), "lon": str(lng)},
            priority=priority,
            referer="https://wolt.com/pl/pol/warszawa/restaurants",
            extra_headers=_WOLT_HEADERS,
        )

        try:
            data = WoltSearchResponse.model_validate(resp.json())
        except Exception as exc:
            raise WoltParseError(f"Search parse failed: {exc}") from exc

        venues = data.all_venues()
        logger.info("wolt search lat=%.4f lng=%.4f → %d venues", lat, lng, len(venues))
        return [self._normalize_venue(v) for v in venues]

    async def get_menu(
        self,
        slug: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedMenuItem]:
        url = f"{self._menu_url}/{slug}"

        resp = await self._get(
            url,
            priority=priority,
            referer=f"https://wolt.com/pl/pol/warszawa/restaurant/{slug}",
            extra_headers=_WOLT_HEADERS,
        )

        try:
            raw = resp.json()
        except Exception as exc:
            raise WoltParseError(f"Menu JSON decode failed for {slug}: {exc}") from exc

        # Extract sections from response (may be at different paths)
        sections_data = self._extract_sections(raw)

        try:
            menu = WoltMenuResponse.model_validate({"sections": sections_data})
        except Exception as exc:
            raise WoltParseError(f"Menu schema failed for {slug}: {exc}") from exc

        # Build the JOIN table: option_id → definition with values
        option_lookup = menu.build_option_lookup()

        # Deduplicate and normalize
        deduped = menu.deduplicated_items()
        items: list[NormalizedMenuItem] = []
        for cat_idx, (cat_name, wolt_item) in enumerate(deduped):
            items.append(
                self._normalize_item(wolt_item, cat_name, cat_idx, option_lookup)
            )

        logger.info("wolt menu slug=%s → %d items (deduped from %d sections, %d option defs)",
                     slug, len(items), len(menu.sections), len(option_lookup))
        return items

    async def get_delivery_fee(
        self,
        slug: str,
        lat: float,
        lng: float,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> NormalizedDeliveryFee:
        # Venue in search has no delivery_price — return estimate only
        restaurants = await self.search_restaurants(lat, lng, 5.0, priority=priority)
        match = next((r for r in restaurants if r.platform_slug == slug), None)
        if match and match.delivery_fee:
            return match.delivery_fee
        return NormalizedDeliveryFee(fee_grosz=0)

    async def get_operating_hours(
        self,
        slug: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedHours]:
        return []  # Search only gives delivers=bool, not detailed hours

    async def get_promotions(
        self,
        slug: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedPromotion]:
        return []  # Requires separate recon

    # ── Section extraction ──────────────────────────────────

    def _extract_sections(self, raw: dict) -> list[dict]:
        """Find sections array in response (Wolt nests at varying paths)."""
        if "sections" in raw and isinstance(raw["sections"], list):
            return raw["sections"]
        for key in ("page", "content"):
            nested = raw.get(key, {})
            if isinstance(nested, dict) and "sections" in nested:
                return nested["sections"]
        logger.warning("wolt: could not find sections, keys=%s", list(raw.keys())[:10])
        return []

    # ── Normalization: venue ────────────────────────────────

    def _normalize_venue(self, v: WoltVenue) -> NormalizedRestaurant:
        fee = NormalizedDeliveryFee(
            fee_grosz=0,  # not available in search venue
            estimated_minutes=v.delivery_minutes_avg,
        ) if v.delivery_minutes_avg else None

        return NormalizedRestaurant(
            platform="wolt",
            platform_restaurant_id=v.slug,
            platform_name=v.name,
            platform_slug=v.slug,
            platform_url=f"https://wolt.com/pl/pol/warszawa/restaurant/{v.slug}",
            name=v.name,
            address_street=v.address or None,
            address_city=v.city or None,
            latitude=v.latitude,
            longitude=v.longitude,
            cuisine_tags=v.tags,
            image_url=v.image_url,
            rating_score=v.rating.score if v.rating else None,
            rating_count=v.rating.volume if v.rating else None,
            is_online=v.delivers and v.online,
            delivery_fee=fee,
        )

    # ── Normalization: menu item + modifiers ────────────────

    def _normalize_item(
        self,
        item: WoltMenuItem,
        category_name: str,
        category_sort: int,
        option_lookup: dict[str, WoltSectionOption],
    ) -> NormalizedMenuItem:
        """Normalize item, resolving modifier references via option_lookup."""
        modifier_groups: list[NormalizedModifierGroup] = []

        for idx, item_opt in enumerate(item.options):
            # JOIN: item option_id → section option definition
            section_opt = option_lookup.get(item_opt.option_id)
            if not section_opt:
                logger.debug("option_id %s not found in lookup for item %s",
                             item_opt.option_id, item.id)
                continue

            mg = self._normalize_modifier_group(item_opt, section_opt, idx)
            modifier_groups.append(mg)

        return NormalizedMenuItem(
            platform_item_id=item.id,
            platform_name=item.name,
            description=item.description,
            price_grosz=item.price,
            is_available=item.is_available,
            category_name=category_name,
            category_sort_order=category_sort,
            modifier_groups=modifier_groups,
        )

    def _normalize_modifier_group(
        self,
        item_opt: WoltItemOption,
        section_opt: WoltSectionOption,
        sort_order: int,
    ) -> NormalizedModifierGroup:
        """JOIN item-level reference + section-level definition → normalized group."""
        options = [
            NormalizedModifierOption(
                platform_option_id=val.id,
                name=val.name,
                normalized_name=_normalize_text(val.name),
                price_grosz=val.price,
                is_default=(val.id == section_opt.default_value),
                is_available=True,
            )
            for val in section_opt.values
        ]

        return NormalizedModifierGroup(
            platform_group_id=section_opt.id,
            name=item_opt.name or section_opt.name,
            group_type="required" if item_opt.is_required else "optional",
            min_selections=item_opt.min_selections,
            max_selections=item_opt.max_selections,
            sort_order=sort_order,
            options=options,
        )


def _normalize_text(text: str) -> str:
    """Lowercase, strip diacritics."""
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))
