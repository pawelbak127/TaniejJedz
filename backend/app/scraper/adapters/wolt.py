"""
Wolt adapter — built from real API dumps (March 2026).

Key design:
  - Search: REST API /v1/pages/restaurants → full venue list
  - Menu: SSR HTML parsing (React Query cache) → FULL menu (150+ items)
    API /venue-content/slug/ returns only 12-item preview!
    SSR HTML contains complete categories + items + options in React Query cache.
  - Fallback: API endpoint if SSR parsing fails
  - Price is in 'price' field, already grosz
  - Modifiers: TWO-LEVEL (section defines options, items reference via option_id)
  - Availability: disabled_info is null when available
"""

from __future__ import annotations

import json
import logging
import re
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

# Wolt city slugs (URL path component)
_WOLT_CITY_SLUGS = {
    "warszawa": "warszawa",
    "krakow": "krakow",
    "krak\u00f3w": "krakow",
    "wroclaw": "wroclaw",
    "wroc\u0142aw": "wroclaw",
    "poznan": "poznan",
    "pozna\u0144": "poznan",
    "gdansk": "gdansk",
    "gda\u0144sk": "gdansk",
    "lodz": "lodz",
    "\u0142\u00f3d\u017a": "lodz",
    "katowice": "katowice",
    "lublin": "lublin",
    "bialystok": "bialystok",
    "bia\u0142ystok": "bialystok",
    "rzeszow": "rzeszow",
    "rzesz\u00f3w": "rzeszow",
    "szczecin": "szczecin",
    "kielce": "kielce",
    "torun": "torun",
    "toru\u0144": "torun",
}


def _resolve_wolt_city_slug(city: str) -> str:
    """Resolve city name to Wolt URL slug. Falls back to 'warszawa'."""
    if not city:
        return "warszawa"
    key = city.lower().strip()
    return _WOLT_CITY_SLUGS.get(key, key)


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
        self._city_slug = "warszawa"  # Updated by search_restaurants()

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
            referer=f"https://wolt.com/pl/pol/{self._city_slug}/restaurants",
            extra_headers=_WOLT_HEADERS,
        )

        try:
            data = WoltSearchResponse.model_validate(resp.json())
        except Exception as exc:
            raise WoltParseError(f"Search parse failed: {exc}") from exc

        venues = data.all_venues()

        # Update city slug from first venue's city field
        if venues:
            first_city = venues[0].city
            if first_city:
                self._city_slug = _resolve_wolt_city_slug(first_city)

        logger.info("wolt search lat=%.4f lng=%.4f → %d venues (city=%s)",
                     lat, lng, len(venues), self._city_slug)
        return [self._normalize_venue(v) for v in venues]

    async def get_menu(
        self,
        slug: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedMenuItem]:
        """Fetch full menu via SSR HTML parsing, fallback to API.

        SSR HTML contains the React Query cache with complete menu
        (150+ items), while the API returns only a 12-item preview.
        """
        # Try SSR HTML first (full menu)
        try:
            items = await self._get_menu_ssr(slug, priority=priority)
            if items:
                logger.info("wolt menu slug=%s → %d items (SSR)", slug, len(items))
                return items
        except Exception as exc:
            logger.warning("wolt SSR menu failed for %s, falling back to API: %s", slug, exc)

        # Fallback: API endpoint (12-item preview)
        return await self._get_menu_api(slug, priority=priority)

    async def get_delivery_fee(
        self,
        slug: str,
        lat: float,
        lng: float,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> NormalizedDeliveryFee:
        restaurants = await self.search_restaurants(lat, lng, 5.0, priority=priority)
        match = next((r for r in restaurants if r.platform_slug == slug), None)
        if match and match.delivery_fee:
            return match.delivery_fee
        return NormalizedDeliveryFee(fee_grosz=0)

    async def get_operating_hours(self, slug: str, **kw) -> list[NormalizedHours]:
        return []

    async def get_promotions(self, slug: str, **kw) -> list[NormalizedPromotion]:
        return []

    # ── SSR HTML menu parsing ───────────────────────────────

    async def _get_menu_ssr(
        self, slug: str, *, priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedMenuItem]:
        """Fetch restaurant page HTML → parse React Query cache → full menu."""
        url = f"https://wolt.com/pl/pol/{self._city_slug}/restaurant/{slug}"
        resp = await self._get(
            url, priority=priority,
            extra_headers={"Accept": "text/html"},
        )
        html = resp.text
        menu_data = self._parse_ssr_menu(html, slug)

        categories = menu_data["categories"]
        items_by_id = {item["id"]: item for item in menu_data["items"]}
        options_lookup = menu_data["options"]

        # Marketing sections to deprioritize
        marketing = {"Najczęściej zamawiane", "Popularne", "Popular",
                      "Bestsellery", "Polecane", "Recommended"}

        result: list[NormalizedMenuItem] = []
        seen_ids: set[str] = set()

        # Non-marketing categories first
        for cat_idx, cat in enumerate(categories):
            if cat["name"] in marketing:
                continue
            for item_id in cat["item_ids"]:
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                item = items_by_id.get(item_id)
                if item:
                    result.append(
                        self._normalize_ssr_item(item, cat["name"], cat_idx, options_lookup)
                    )

        # Marketing-only items
        for cat_idx, cat in enumerate(categories):
            if cat["name"] not in marketing:
                continue
            for item_id in cat["item_ids"]:
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                item = items_by_id.get(item_id)
                if item:
                    result.append(
                        self._normalize_ssr_item(item, cat["name"], cat_idx, options_lookup)
                    )

        return result

    def _parse_ssr_menu(self, html: str, slug: str) -> dict:
        """Extract menu data from React Query cache in SSR HTML.

        category-listing query structure (verified March 2026):
          data.categories: array[11] — {id, name, description, item_ids[]}
          data.items: array[185] — flat list of items with price, options[]
          data.options: array[234] — flat list of option definitions

        Returns: {
            "categories": [{"name": "...", "item_ids": [...]}],
            "items": [{"id": "...", "name": "...", "price": 1234, ...}],
            "options": {"opt_id": {"name": "...", "values": [...], "default_value": "..."}}
        }
        """
        rq_data = self._extract_react_query_json(html, slug)
        if not rq_data:
            raise WoltParseError(f"React Query cache not found in SSR for {slug}")

        # Categories — use "description" as display name, fallback to "name"
        categories = []
        for cat in rq_data.get("categories", []):
            cat_name = cat.get("description") or cat.get("name") or ""
            item_ids = cat.get("item_ids", [])
            if item_ids:
                categories.append({
                    "name": cat_name,
                    "item_ids": item_ids,
                })

        # Items — flat array, each has id, name, price, options[], disabled_info
        items_list = rq_data.get("items", [])

        # Options — flat array → build dict {id: definition}
        options_dict: dict[str, dict] = {}
        for opt in rq_data.get("options", []):
            if isinstance(opt, dict) and "id" in opt:
                options_dict[opt["id"]] = opt

        if not categories:
            raise WoltParseError(f"No categories found in SSR for {slug}")

        logger.info("wolt SSR parsed: %d categories, %d items, %d options for %s",
                     len(categories), len(items_list), len(options_dict), slug)

        return {
            "categories": categories,
            "items": items_list,
            "options": options_dict,
        }

    def _extract_react_query_json(self, html: str, slug: str) -> dict | None:
        """Find and parse the React Query dehydrated state containing menu data."""
        # The React Query cache is in a <script> tag containing "venue-assortment"
        # and "category-listing" with the slug
        scripts = re.findall(
            r'<script[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )

        for script_content in scripts:
            if "venue-assortment" not in script_content:
                continue
            if "category-listing" not in script_content:
                continue

            # Find the dehydrated data JSON — it's inside {"queries":[...]}
            try:
                data = json.loads(script_content)
            except json.JSONDecodeError:
                continue

            # Navigate queries to find the category-listing one
            for query in data.get("queries", []):
                qk = query.get("queryKey", [])
                if len(qk) >= 2 and qk[0] == "venue-assortment" and qk[1] == "category-listing":
                    state_data = query.get("state", {}).get("data", {})
                    if state_data:
                        return state_data

            # Also check mutations array (sometimes data is there)
            return None

        return None

    # ── SSR item normalization ──────────────────────────────

    def _normalize_ssr_item(
        self,
        item: dict,
        category_name: str,
        category_sort: int,
        options_lookup: dict[str, dict],
    ) -> NormalizedMenuItem:
        """Normalize an item from SSR React Query cache."""
        modifier_groups: list[NormalizedModifierGroup] = []

        for idx, item_opt in enumerate(item.get("options", [])):
            opt_id = item_opt.get("option_id", "")
            opt_def = options_lookup.get(opt_id)
            if not opt_def:
                continue

            mg = self._normalize_ssr_modifier_group(item_opt, opt_def, idx)
            modifier_groups.append(mg)

        is_available = item.get("disabled_info") is None

        return NormalizedMenuItem(
            platform_item_id=item.get("id", ""),
            platform_name=item.get("name", ""),
            description=item.get("description"),
            price_grosz=item.get("price", 0),
            is_available=is_available,
            category_name=category_name,
            category_sort_order=category_sort,
            modifier_groups=modifier_groups,
        )

    def _normalize_ssr_modifier_group(
        self,
        item_opt: dict,
        opt_def: dict,
        sort_order: int,
    ) -> NormalizedModifierGroup:
        """Normalize a modifier group from SSR data.

        item_opt: item-level reference (option_id, name, multi_choice_config)
        opt_def: section-level definition (name, type, values[], default_value)
        """
        multi = item_opt.get("multi_choice_config", {})
        total_range = multi.get("total_range", {})
        min_sel = total_range.get("min", 0)
        max_sel = total_range.get("max", 1)

        options = [
            NormalizedModifierOption(
                platform_option_id=val.get("id", ""),
                name=val.get("name", ""),
                normalized_name=_normalize_text(val.get("name", "")),
                price_grosz=val.get("price", 0),
                is_default=(val.get("id") == opt_def.get("default_value")),
                is_available=True,
            )
            for val in opt_def.get("values", [])
        ]

        return NormalizedModifierGroup(
            platform_group_id=opt_def.get("id", ""),
            name=item_opt.get("name") or opt_def.get("name", ""),
            group_type="required" if min_sel > 0 else "optional",
            min_selections=min_sel,
            max_selections=max_sel,
            sort_order=sort_order,
            options=options,
        )

    # ── API menu (fallback — 12 item preview) ──────────────

    async def _get_menu_api(
        self, slug: str, *, priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedMenuItem]:
        """Fallback: API endpoint returns ~12 item preview."""
        url = f"{self._menu_url}/{slug}"
        resp = await self._get(
            url, priority=priority,
            referer=f"https://wolt.com/pl/pol/{self._city_slug}/restaurant/{slug}",
            extra_headers=_WOLT_HEADERS,
        )

        try:
            raw = resp.json()
        except Exception as exc:
            raise WoltParseError(f"Menu JSON decode failed for {slug}: {exc}") from exc

        sections_data = self._extract_sections(raw)

        try:
            menu = WoltMenuResponse.model_validate({"sections": sections_data})
        except Exception as exc:
            raise WoltParseError(f"Menu schema failed for {slug}: {exc}") from exc

        option_lookup = menu.build_option_lookup()
        deduped = menu.deduplicated_items()
        items: list[NormalizedMenuItem] = []
        for cat_idx, (cat_name, wolt_item) in enumerate(deduped):
            items.append(
                self._normalize_item(wolt_item, cat_name, cat_idx, option_lookup)
            )

        logger.info("wolt menu (API fallback) slug=%s → %d items", slug, len(items))
        return items

    # ── Section extraction (API fallback) ───────────────────

    def _extract_sections(self, raw: dict) -> list[dict]:
        """Find sections array in API response."""
        if "detail" in raw and "sections" not in raw:
            raise WoltParseError(f"Wolt API error: {raw.get('detail', 'unknown')}")

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
            fee_grosz=0,
            estimated_minutes=v.delivery_minutes_avg,
        ) if v.delivery_minutes_avg else None

        city_slug = _resolve_wolt_city_slug(v.city) if v.city else self._city_slug

        return NormalizedRestaurant(
            platform="wolt",
            platform_restaurant_id=v.slug,
            platform_name=v.name,
            platform_slug=v.slug,
            platform_url=f"https://wolt.com/pl/pol/{city_slug}/restaurant/{v.slug}",
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

    # ── Normalization: API menu item + modifiers ────────────

    def _normalize_item(
        self,
        item: WoltMenuItem,
        category_name: str,
        category_sort: int,
        option_lookup: dict[str, WoltSectionOption],
    ) -> NormalizedMenuItem:
        """Normalize item from API response (fallback path)."""
        modifier_groups: list[NormalizedModifierGroup] = []

        for idx, item_opt in enumerate(item.options):
            section_opt = option_lookup.get(item_opt.option_id)
            if not section_opt:
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
        """JOIN item-level reference + section-level definition (API path)."""
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
