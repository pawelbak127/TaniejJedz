"""
Glovo adapter — HTML/RSC scraping (March 2026).

Strategy (verified against live Glovo):
  - NO API endpoints used (v3/stores returns 404 without auth)
  - Search: scrape /categories/jedzenie_1 HTML → extract slug+name from store cards
  - Menu: fetch store page HTML → parse RSC payload → store info + full menu

Discovery yields ~50 restaurants per city from SSR HTML.

RSC structure on store page (verified):
  self.__next_f.push([1,"...<JSON with store + initialStoreContent>..."])
  store: {id, name, slug, open, addressId, cityCode, deliveryFeeInfo, ...}
  initialStoreContent: {data: {body: [sections with PRODUCT_ROW elements]}}
"""

from __future__ import annotations

import asyncio
import html as html_module
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
from app.scraper.adapters.glovo_schemas import (
    GlovoAttributeGroup,
    GlovoMenuResponse,
    GlovoProduct,
    GlovoStore,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# City mapping
# ═══════════════════════════════════════════════════════════════

_POLISH_CITIES = [
    (52.2297, 21.0122, "WAW", "warszawa", "Warszawa", "waw"),
    (50.0647, 19.9450, "KRK", "krakow", "Kraków", "kra"),
    (51.1079, 17.0385, "WRO", "wroclaw", "Wrocław", "wro"),
    (52.4064, 16.9252, "POZ", "poznan", "Poznań", "poz"),
    (54.3520, 18.6466, "GDN", "gdansk", "Gdańsk", "gdn"),
    (51.7592, 19.4560, "LDZ", "lodz", "Łódź", "ldz"),
    (50.2649, 19.0238, "KTW", "katowice", "Katowice", "ktw"),
    (51.2465, 22.5684, "LUB", "lublin", "Lublin", "lub"),
    (53.1325, 23.1688, "BIA", "bialystok", "Białystok", "bia"),
    (50.0413, 21.9991, "RZE", "rzeszow", "Rzeszów", "rze"),
    (53.4285, 14.5528, "SZZ", "szczecin", "Szczecin", "szz"),
    (50.8661, 20.6286, "KIE", "kielce", "Kielce", "kie"),
    (53.0138, 18.5984, "TOR", "torun", "Toruń", "tor"),
]


def _resolve_city(lat: float, lng: float) -> tuple[str, str, str, str]:
    """Returns: (city_code, url_slug, display_name, short_slug)."""
    best_dist = float("inf")
    best = ("WAW", "warszawa", "Warszawa", "waw")
    for c_lat, c_lng, code, slug, name, short in _POLISH_CITIES:
        dist = math.sqrt((lat - c_lat) ** 2 + (lng - c_lng) ** 2)
        if dist < best_dist:
            best_dist = dist
            best = (code, slug, name, short)
    return best


# Regex: extract store slug + name from SSR HTML store cards.
# Pattern: href="/pl/pl/{city}/stores/{slug}" ... img alt="{name}"
_STORE_CARD_RE = re.compile(
    r'href="/pl/pl/\w+/stores/([a-z0-9][a-z0-9\-]*[a-z0-9])"'
    r'[^>]*>.*?'
    r'(?:alt="([^"]*)")?',
    re.DOTALL,
)

# Simpler fallback: just slugs from href
_SLUG_HREF_RE = re.compile(
    r'href="/pl/pl/\w+/stores/([a-z0-9][a-z0-9\-]*[a-z0-9])"'
)

# RSC payload: extract store JSON object from __next_f.push scripts
# Matches: "store":{...JSON...},"children"
_RSC_STORE_RE = re.compile(
    r'"store"\s*:\s*(\{[^}]*"slug"\s*:\s*"[^"]*"[^}]*"addressId"\s*:\s*\d+[^}]*\})',
)

# RSC payload: extract initialStoreContent JSON
_RSC_MENU_RE = re.compile(
    r'"initialStoreContent"\s*:\s*(\{"data"\s*:\s*\{"body"\s*:\s*\[)',
)


class GlovoParseError(ScraperError):
    pass


class GlovoAdapter(BaseAdapter):

    PLATFORM_NAME = "glovo"
    BASE_URL = "https://glovoapp.com"

    def __init__(self, redis: Redis) -> None:
        super().__init__(redis)
        self._city_code = "WAW"
        self._city_slug = "warszawa"
        self._city_name = "Warszawa"
        self._city_short = "waw"

    def _set_city(self, lat: float, lng: float) -> None:
        self._city_code, self._city_slug, self._city_name, self._city_short = _resolve_city(lat, lng)

    # ── Public interface ────────────────────────────────────

    async def search_restaurants(
        self,
        lat: float,
        lng: float,
        radius_km: float,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedRestaurant]:
        """Search via HTML scraping of /categories/jedzenie_1.

        Extracts ~50 restaurant slugs+names from SSR HTML.
        No API probing needed.
        """
        self._set_city(lat, lng)
        logger.info("glovo search: city=%s (%s)", self._city_code, self._city_name)

        # Check cache
        cache_key = f"scraper:glovo:search:{self._city_code}"
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return [NormalizedRestaurant.model_validate(d) for d in data]
            except Exception:
                pass

        # Scrape food category page
        restaurants = await self._scrape_category_page(priority=priority)

        # Cache 30 min
        if restaurants:
            data = [r.model_dump(mode="json") for r in restaurants]
            await self._redis.setex(cache_key, 1800, json.dumps(data, default=str))

        logger.info("glovo search: %d restaurants found in %s",
                     len(restaurants), self._city_name)
        return restaurants

    async def get_menu(
        self,
        slug: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedMenuItem]:
        """Fetch store page HTML → parse RSC → store + menu."""
        store_data, menu_data = await self._fetch_store_page(slug, priority=priority)

        if menu_data is None:
            raise GlovoParseError(f"Menu not found in RSC for {slug}")

        try:
            menu = GlovoMenuResponse.model_validate(menu_data)
        except Exception as exc:
            raise GlovoParseError(f"Menu parse failed for {slug}: {exc}") from exc

        products = menu.all_products()
        items = [
            self._normalize_product(p, cat, idx)
            for idx, (cat, p) in enumerate(products)
        ]
        logger.info("glovo menu slug=%s → %d items", slug, len(items))
        return items

    async def get_delivery_fee(
        self, slug: str, lat: float, lng: float, *,
        priority: Priority = Priority.NORMAL,
    ) -> NormalizedDeliveryFee:
        self._set_city(lat, lng)
        store_data, _ = await self._fetch_store_page(slug, priority=priority)
        if store_data:
            store = GlovoStore.model_validate(store_data)
            return NormalizedDeliveryFee(fee_grosz=store.delivery_fee_grosz)
        return NormalizedDeliveryFee(fee_grosz=0)

    async def get_operating_hours(self, slug: str, **kw) -> list[NormalizedHours]:
        return []

    async def get_promotions(self, slug: str, **kw) -> list[NormalizedPromotion]:
        return []

    # ── HTML scraping: category page → restaurant list ──────

    async def _scrape_category_page(
        self, *, priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedRestaurant]:
        """Scrape /categories/jedzenie_1 for restaurant slugs + names."""
        url = f"{self.BASE_URL}/pl/pl/{self._city_slug}/categories/jedzenie_1"
        try:
            resp = await self._get(
                url, priority=priority,
                extra_headers={"Accept": "text/html"},
            )
        except Exception as exc:
            logger.warning("glovo category scraping failed: %s", exc)
            return []

        html = resp.text
        restaurants = self._parse_category_html(html)
        logger.info("glovo category scraping: %d restaurants from %s",
                     len(restaurants), url)
        return restaurants

    def _parse_category_html(self, html: str) -> list[NormalizedRestaurant]:
        """Extract restaurant slug+name from SSR HTML store cards.

        HTML pattern (verified):
          <a class="StoreCard..." href="/pl/pl/{city}/stores/{slug}">
            <div ...><img alt="{Name}" loading="lazy" ...>
        """
        # Strategy: find all store hrefs, then for each find the nearest img alt
        restaurants: list[NormalizedRestaurant] = []
        seen_slugs: set[str] = set()

        # Extract slug → name pairs from store card pattern
        slug_name_pairs = self._extract_slug_name_pairs(html)

        for slug, name in slug_name_pairs:
            if slug in seen_slugs:
                continue
            if len(slug) <= 3:
                continue
            seen_slugs.add(slug)

            # Skip known non-food stores
            if self._is_non_food_slug(slug):
                continue

            restaurants.append(NormalizedRestaurant(
                platform="glovo",
                platform_restaurant_id=slug,
                platform_name=name or self._slug_to_name(slug),
                platform_slug=slug,
                platform_url=f"https://glovoapp.com/pl/pl/{self._city_slug}/stores/{slug}",
                name=name or self._slug_to_name(slug),
                latitude=0.0,
                longitude=0.0,
                is_online=True,  # Visible on category page = available
            ))

        return restaurants

    def _extract_slug_name_pairs(self, html: str) -> list[tuple[str, str]]:
        """Extract (slug, name) pairs from HTML.

        Tries store card pattern first (href + img alt), falls back to href-only.
        """
        pairs: list[tuple[str, str]] = []
        seen: set[str] = set()

        # Method 1: Find href="/stores/{slug}" followed by img alt="{name}"
        # within the same <a> block
        for match in re.finditer(
            r'href="/pl/pl/\w+/stores/([a-z0-9][a-z0-9\-]*[a-z0-9])"'
            r'.*?'
            r'alt="([^"]*)"',
            html,
            re.DOTALL,
        ):
            slug, name = match.group(1), match.group(2)
            # Decode HTML entities: &#x27; → ', &amp; → &
            name = html_module.unescape(name)
            # Limit match distance — alt should be within ~2000 chars of href
            if match.end() - match.start() > 3000:
                continue
            if slug not in seen:
                seen.add(slug)
                pairs.append((slug, name))

        # Method 2: Fallback — href-only slugs not found in method 1
        for slug_match in _SLUG_HREF_RE.finditer(html):
            slug = slug_match.group(1)
            if slug not in seen:
                seen.add(slug)
                pairs.append((slug, ""))

        return pairs

    @staticmethod
    def _is_non_food_slug(slug: str) -> bool:
        """Filter out non-restaurant stores (pharmacy, grocery)."""
        non_food = [
            "apteczka-zdrowia", "biedronka-express", "rossmann",
            "hebe", "żabka", "zabka", "stokrotka", "carrefour",
            "auchan", "lidl", "kaufland",
        ]
        slug_lower = slug.lower()
        return any(nf in slug_lower for nf in non_food)

    @staticmethod
    def _slug_to_name(slug: str) -> str:
        """Convert slug to display name: 'kfc-kra' → 'Kfc'."""
        # Remove city suffix (-kra, -waw, etc.)
        parts = slug.rsplit("-", 1)
        if len(parts) == 2 and len(parts[1]) <= 4:
            name_part = parts[0]
        else:
            name_part = slug
        # Also strip trailing numbers/disambiguation: burger-king2 → burger-king
        name_part = re.sub(r'\d+$', '', name_part)
        # Convert dashes to spaces, title case
        return name_part.replace("-", " ").strip().title()

    # ── RSC parsing: store page → store + menu ──────────────

    async def _fetch_store_page(
        self,
        slug: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> tuple[dict | None, dict | None]:
        """Fetch store page HTML and parse RSC payload.

        Returns: (store_dict, menu_dict) — both can be None if parsing fails.
        """
        # Check cache
        cache_key = f"scraper:glovo:store_rsc:{slug}"
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return data.get("store"), data.get("menu")
            except Exception:
                pass

        url = f"{self.BASE_URL}/pl/pl/{self._city_slug}/stores/{slug}"
        try:
            resp = await self._get(
                url, priority=priority,
                extra_headers={"Accept": "text/html"},
            )
        except Exception as exc:
            logger.warning("glovo store page fetch failed for %s: %s", slug, exc)
            return None, None

        html = resp.text
        store_data, menu_data = self._parse_store_rsc(html, slug)

        # Cache for 1 hour
        if store_data or menu_data:
            cache_data = {"store": store_data, "menu": menu_data}
            await self._redis.setex(
                cache_key, 3600,
                json.dumps(cache_data, default=str),
            )

        return store_data, menu_data

    def _parse_store_rsc(
        self, html: str, slug: str,
    ) -> tuple[dict | None, dict | None]:
        """Parse RSC flight payload from store page HTML.

        RSC structure (verified from live scrape):
          __next_f.push([1,"...<encoded JSON>..."])
          Contains: "store":{id,name,slug,open,addressId,...}
          And: "initialStoreContent":{data:{body:[sections]}}
        """
        store_data: dict | None = None
        menu_data: dict | None = None

        # Collect all __next_f.push payloads
        rsc_chunks: list[str] = []
        for match in re.finditer(
            r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)',
            html,
        ):
            chunk = match.group(1)
            # Unescape JSON string escapes properly (handles \u0141 → Ł etc.)
            try:
                chunk = json.loads('"' + chunk + '"')
            except (json.JSONDecodeError, Exception):
                # Fallback: at least handle basic escapes
                chunk = chunk.replace('\\"', '"').replace('\\\\', '\\')
            rsc_chunks.append(chunk)

        full_rsc = "".join(rsc_chunks)

        # Extract store object
        store_data = self._extract_store_from_rsc(full_rsc, slug)

        # Extract menu (initialStoreContent)
        menu_data = self._extract_menu_from_rsc(full_rsc)

        return store_data, menu_data

    def _extract_store_from_rsc(self, rsc: str, slug: str) -> dict | None:
        """Extract store JSON from RSC payload using balanced brace matching."""
        # Find "store":{ in RSC
        marker = '"store":{'
        idx = rsc.find(marker)
        if idx == -1:
            logger.debug("glovo RSC: 'store' key not found for %s", slug)
            return None

        json_start = idx + len('"store":')
        store_json = self._extract_balanced_json(rsc, json_start)
        if store_json is None:
            return None

        try:
            return json.loads(store_json)
        except json.JSONDecodeError as exc:
            logger.debug("glovo RSC: store JSON parse failed for %s: %s", slug, exc)
            return None

    def _extract_menu_from_rsc(self, rsc: str) -> dict | None:
        """Extract initialStoreContent from RSC payload."""
        marker = '"initialStoreContent":'
        idx = rsc.find(marker)
        if idx == -1:
            logger.debug("glovo RSC: 'initialStoreContent' not found")
            return None

        json_start = idx + len(marker)
        menu_json = self._extract_balanced_json(rsc, json_start)
        if menu_json is None:
            return None

        try:
            return json.loads(menu_json)
        except json.JSONDecodeError as exc:
            logger.debug("glovo RSC: menu JSON parse failed: %s", exc)
            return None

    @staticmethod
    def _extract_balanced_json(text: str, start: int) -> str | None:
        """Extract a balanced JSON object or array starting at position `start`.

        Handles nested braces/brackets and string escapes.
        """
        if start >= len(text):
            return None

        open_char = text[start]
        if open_char == '{':
            close_char = '}'
        elif open_char == '[':
            close_char = ']'
        else:
            return None

        depth = 0
        in_string = False
        escape_next = False
        i = start

        while i < len(text):
            ch = text[i]

            if escape_next:
                escape_next = False
                i += 1
                continue

            if ch == '\\' and in_string:
                escape_next = True
                i += 1
                continue

            if ch == '"' and not escape_next:
                in_string = not in_string
                i += 1
                continue

            if not in_string:
                if ch == open_char:
                    depth += 1
                elif ch == close_char:
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]

            i += 1

        # If we hit a very long string (>500KB), truncation likely — return None
        logger.debug("glovo RSC: balanced JSON extraction failed (depth=%d, scanned %d chars)", depth, i - start)
        return None

    # ── Normalization ───────────────────────────────────────

    def _normalize_store_from_rsc(self, store_data: dict) -> NormalizedRestaurant:
        """Normalize store data from RSC payload."""
        store = GlovoStore.model_validate(store_data)

        fee = NormalizedDeliveryFee(
            fee_grosz=store.delivery_fee_grosz,
        ) if store.deliveryFeeInfo else None

        city_slug = self._city_slug
        if store.cityCode:
            for _, _, code, slug, _, _ in _POLISH_CITIES:
                if code == store.cityCode:
                    city_slug = slug
                    break

        return NormalizedRestaurant(
            platform="glovo",
            platform_restaurant_id=str(store.id),
            platform_name=store.name,
            platform_slug=store.slug,
            platform_url=f"https://glovoapp.com/pl/pl/{city_slug}/stores/{store.slug}",
            name=store.name,
            address_street=store.address.replace("\n", ", ") if store.address else None,
            latitude=0.0,
            longitude=0.0,
            cuisine_tags=store.cuisine_tags,
            image_url=None,
            is_online=store.is_online,
            delivery_fee=fee,
        )

    def _normalize_product(
        self, product: GlovoProduct, category_name: str, category_sort: int,
    ) -> NormalizedMenuItem:
        modifier_groups = [
            self._normalize_attribute_group(ag, idx)
            for idx, ag in enumerate(product.attributeGroups)
        ]
        return NormalizedMenuItem(
            platform_item_id=str(product.id),
            platform_name=product.name,
            description=product.description,
            price_grosz=product.price_grosz,
            is_available=product.is_available,
            category_name=category_name,
            category_sort_order=category_sort,
            modifier_groups=modifier_groups,
        )

    def _normalize_attribute_group(
        self, ag: GlovoAttributeGroup, sort_order: int,
    ) -> NormalizedModifierGroup:
        options = [
            NormalizedModifierOption(
                platform_option_id=str(attr.id),
                name=attr.name,
                normalized_name=_normalize_text(attr.name),
                price_grosz=attr.price_grosz,
                is_default=attr.selected,
                is_available=True,
            )
            for attr in ag.attributes
        ]
        return NormalizedModifierGroup(
            platform_group_id=str(ag.id),
            name=ag.name,
            group_type="required" if ag.is_required else "optional",
            min_selections=ag.min,
            max_selections=ag.max,
            sort_order=sort_order,
            options=options,
        )


def _normalize_text(text: str) -> str:
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))
