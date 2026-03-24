"""
Wolt adapter — SSR HTML menu + REST search (March 2026).

SEARCH: GET restaurant-api.wolt.com/v1/pages/restaurants?lat={lat}&lon={lng}
  → REST API, returns venue list with coordinates

MENU: GET wolt.com/pl/pol/{city}/restaurant/{slug} → HTML
  → Parse React Query cache from <script> tag
  → Find query key 'venue-assortment/category-listing'
  → Extract categories[], items[], options{}
  → 35+ items (FULL menu) vs old API which returned only 12 popular

Structure:
  categories[]: {name, item_ids[]}
  items[]: {id, name, price (grosz), description, disabled_info, options[]}
  options{}: {option_id: {name, values[{id, name, price}]}}
  item.options[]: {option_id → top-level options} (same JOIN as old API)
"""

from __future__ import annotations

import json
import logging
import math
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
    WoltSearchResponse,
    WoltVenue,
)

logger = logging.getLogger(__name__)

_WOLT_HEADERS = {
    "Origin": "https://wolt.com",
    "Wolt-Language": "pl",
    "Accept": "application/json",
}

# City mapping for Wolt URL: /pl/pol/{city_slug}/restaurant/{slug}
_WOLT_CITIES = [
    (52.2297, 21.0122, "warszawa"),
    (50.0647, 19.9450, "krakow"),
    (51.1079, 17.0385, "wroclaw"),
    (52.4064, 16.9252, "poznan"),
    (54.3520, 18.6466, "gdansk"),
    (51.7592, 19.4560, "lodz"),
    (50.2649, 19.0238, "katowice"),
    (51.2465, 22.5684, "lublin"),
    (53.1325, 23.1688, "bialystok"),
    (50.0413, 21.9991, "rzeszow"),
    (53.4285, 14.5528, "szczecin"),
]


def _resolve_wolt_city(lat: float, lng: float) -> str:
    """Find nearest city slug for Wolt URL."""
    best_dist = float("inf")
    best = "warszawa"
    for c_lat, c_lng, slug in _WOLT_CITIES:
        dist = math.sqrt((lat - c_lat) ** 2 + (lng - c_lng) ** 2)
        if dist < best_dist:
            best_dist = dist
            best = slug
    return best


class WoltParseError(ScraperError):
    pass


class WoltAdapter(BaseAdapter):

    PLATFORM_NAME = "wolt"
    BASE_URL = "https://wolt.com"

    def __init__(self, redis: Redis) -> None:
        super().__init__(redis)
        s = get_settings()
        self._search_url = s.wolt_search_url
        self._city_slug = "warszawa"

    # ── Public interface ────────────────────────────────────

    async def search_restaurants(
        self,
        lat: float,
        lng: float,
        radius_km: float,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedRestaurant]:
        """Search via REST API (works fine, returns all venues)."""
        self._city_slug = _resolve_wolt_city(lat, lng)

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
        logger.info("wolt search lat=%.4f lng=%.4f → %d venues", lat, lng, len(venues))
        return [self._normalize_venue(v) for v in venues]

    async def get_menu(
        self,
        slug: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedMenuItem]:
        """Fetch menu from SSR HTML (React Query cache).

        New approach (March 2026): Wolt embeds full menu in HTML as React Query cache.
        Old API (venue-content-api/v3) returns only 12 popular items.
        """
        menu_data = await self._fetch_ssr_menu(slug, priority=priority)

        categories = menu_data.get("categories", [])
        items_list = menu_data.get("items", [])
        options_raw = menu_data.get("options", {})

        # Build items lookup: {id: item}
        items_by_id: dict[str, dict] = {}
        if isinstance(items_list, list):
            for item in items_list:
                if isinstance(item, dict) and "id" in item:
                    items_by_id[item["id"]] = item
        elif isinstance(items_list, dict):
            items_by_id = items_list

        # Build options lookup: {option_id: option_def}
        option_lookup: dict[str, dict] = {}
        if isinstance(options_raw, list):
            for opt in options_raw:
                if isinstance(opt, dict) and "id" in opt:
                    option_lookup[opt["id"]] = opt
        elif isinstance(options_raw, dict):
            option_lookup = options_raw

        # Walk categories → items → normalize
        result: list[NormalizedMenuItem] = []
        seen: set[str] = set()

        for cat_idx, category in enumerate(categories):
            cat_name = category.get("name", "")
            for item_id in category.get("item_ids", []):
                if item_id in seen:
                    continue
                seen.add(item_id)

                item = items_by_id.get(item_id)
                if not item:
                    continue

                result.append(
                    self._normalize_ssr_item(item, cat_name, cat_idx, option_lookup)
                )

        logger.info("wolt menu (SSR) slug=%s → %d items (%d categories)",
                     slug, len(result), len(categories))
        return result

    async def get_delivery_fee(
        self, slug: str, lat: float, lng: float, *,
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

    # ── SSR HTML parsing ────────────────────────────────────

    async def _fetch_ssr_menu(
        self,
        slug: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> dict:
        """Fetch Wolt page HTML → extract React Query cache → find menu query."""
        cache_key = f"scraper:wolt:ssr_menu:{slug}"
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

        url = f"{self.BASE_URL}/pl/pol/{self._city_slug}/restaurant/{slug}"
        resp = await self._get(
            url,
            priority=priority,
            extra_headers={"Accept": "text/html", "Accept-Language": "pl-PL,pl;q=0.9"},
        )

        html = resp.text

        # Extract React Query cache from <script> tags
        menu_data = self._parse_ssr_menu(html, slug)

        # Cache 30 min
        await self._redis.setex(cache_key, 1800, json.dumps(menu_data, default=str))

        return menu_data

    @staticmethod
    def _parse_ssr_menu(html: str, slug: str) -> dict:
        """Extract menu from React Query cache in SSR HTML."""
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)

        rq_cache = None
        for s in scripts:
            s = s.strip()
            if s.startswith("{") and '"queries"' in s[:200]:
                try:
                    rq_cache = json.loads(s)
                    break
                except json.JSONDecodeError:
                    pass

        if not rq_cache:
            raise WoltParseError(f"React Query cache not found in HTML for {slug}")

        # Find venue-assortment/category-listing query
        for q in rq_cache.get("queries", []):
            qk = q.get("queryKey", [])
            qk_str = str(qk)
            if "venue-assortment" in qk_str and "category-listing" in qk_str:
                data = q.get("state", {}).get("data")
                if data and isinstance(data, dict):
                    return data

        # Fallback: find any query with "categories" and "items"
        for q in rq_cache.get("queries", []):
            data = q.get("state", {}).get("data")
            if isinstance(data, dict) and "categories" in data and "items" in data:
                return data

        raise WoltParseError(f"Menu query not found in React Query cache for {slug}")

    # ── Normalization: venue (from search) ──────────────────

    def _normalize_venue(self, v: WoltVenue) -> NormalizedRestaurant:
        fee = NormalizedDeliveryFee(
            fee_grosz=0,
            estimated_minutes=v.delivery_minutes_avg,
        ) if v.delivery_minutes_avg else None

        return NormalizedRestaurant(
            platform="wolt",
            platform_restaurant_id=v.slug,
            platform_name=v.name,
            platform_slug=v.slug,
            platform_url=f"https://wolt.com/pl/pol/{self._city_slug}/restaurant/{v.slug}",
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

    # ── Normalization: SSR menu item ────────────────────────

    def _normalize_ssr_item(
        self,
        item: dict,
        category_name: str,
        category_sort: int,
        option_lookup: dict[str, dict],
    ) -> NormalizedMenuItem:
        """Normalize item from SSR React Query cache."""
        modifier_groups: list[NormalizedModifierGroup] = []

        for idx, item_opt in enumerate(item.get("options", [])):
            opt_id = item_opt.get("option_id", "")
            opt_def = option_lookup.get(opt_id)
            if not opt_def:
                continue

            mg = self._normalize_ssr_modifier(item_opt, opt_def, idx)
            if mg:
                modifier_groups.append(mg)

        is_available = item.get("disabled_info") is None

        return NormalizedMenuItem(
            platform_item_id=item.get("id", ""),
            platform_name=item.get("name", ""),
            description=item.get("description"),
            price_grosz=item.get("price", 0),  # Already grosz
            is_available=is_available,
            category_name=category_name,
            category_sort_order=category_sort,
            modifier_groups=modifier_groups,
        )

    def _normalize_ssr_modifier(
        self,
        item_opt: dict,
        opt_def: dict,
        sort_order: int,
    ) -> NormalizedModifierGroup | None:
        """JOIN item option ref + option definition → NormalizedModifierGroup."""
        values = opt_def.get("values", [])
        if not values:
            return None

        # Multi choice config
        mcc = item_opt.get("multi_choice_config", {})
        total_range = mcc.get("total_range", {})
        min_sel = total_range.get("min", 0)
        max_sel = total_range.get("max", 1)

        default_value = opt_def.get("default_value", "")

        options = [
            NormalizedModifierOption(
                platform_option_id=v.get("id", ""),
                name=v.get("name", ""),
                normalized_name=_normalize_text(v.get("name", "")),
                price_grosz=v.get("price", 0),
                is_default=(v.get("id", "") == default_value),
                is_available=True,
            )
            for v in values
        ]

        return NormalizedModifierGroup(
            platform_group_id=opt_def.get("id", ""),
            name=item_opt.get("name", "") or opt_def.get("name", ""),
            group_type="required" if min_sel > 0 else "optional",
            min_selections=min_sel,
            max_selections=max_sel,
            sort_order=sort_order,
            options=options,
        )


def _normalize_text(text: str) -> str:
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))
