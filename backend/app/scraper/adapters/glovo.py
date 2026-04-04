"""
Glovo adapter — sitemap-driven discovery + RSC menu parsing (April 2026).

Strategy (updated from HTML-only):
  - Search: read pre-synced slug list from Redis (populated by sync_glovo_slugs job)
  - Fallback: scrape /categories/jedzenie_1 HTML if Redis empty (first run)
  - Menu: fetch store page HTML → parse RSC payload → store info + full menu

Redis keys consumed:
    scraper:glovo:known_slugs:{city_slug}  →  JSON list of slugs (from sync job)

Expected coverage after sitemap sync:
    Warszawa: 50 → ~2,701 restaurants
    Kraków:   50 → ~1,211 restaurants
    Total PL: 50 → ~9,218 restaurants
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
    (50.0647, 19.9450, "KRA", "krakow", "Kraków", "kra"),
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


# Regex for fallback HTML scraping (kept for first-run before sitemap sync)
_SLUG_HREF_RE = re.compile(
    r'href="/pl/pl/\w+/stores/([a-z0-9][a-z0-9\-]*[a-z0-9])"'
)

# Non-food filtering — expanded list (matches sync_glovo_slugs.py)
_NON_FOOD_KEYWORDS = [
    "apteczka", "apteka", "pharmacy",
    "biedronka", "rossmann", "hebe", "stokrotka",
    "carrefour", "auchan", "lidl", "kaufland",
    "zabka", "żabka", "lewiatan", "dino-market",
    "intermarche", "netto", "polomarket", "polo-market",
    "delikatesy", "spolem", "freshmarket", "fresh-market",
    "a-kwiaty", "kwiaciarnia", "florist",
    "mediamarkt", "media-markt", "empik", "decathlon",
    "pepco", "action", "tedi",
    "zooplus", "maxi-zoo", "kakadu",
    "alkohole", "duzy-ben", "specjaly",
]


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
        """Search via sitemap-derived slug list from Redis.

        Primary: read known slugs from Redis (populated by sync_glovo_slugs job).
        Fallback: HTML scraping of /categories/jedzenie_1 (~50 results).

        No API probing or budget spend for sitemap-based search — just Redis read.
        """
        self._set_city(lat, lng)
        logger.info("glovo search: city=%s (%s)", self._city_code, self._city_name)

        # Check response cache first
        cache_key = f"scraper:glovo:search:{self._city_code}"
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return [NormalizedRestaurant.model_validate(d) for d in data]
            except Exception:
                pass

        # PRIMARY: Read sitemap-derived slugs from Redis
        restaurants = await self._search_from_sitemap_slugs()

        # FALLBACK: HTML scraping if sitemap not yet synced
        if not restaurants:
            logger.warning(
                "glovo: no sitemap slugs for %s — falling back to HTML scraping. "
                "Run sync_glovo_slugs job to populate.",
                self._city_slug,
            )
            restaurants = await self._scrape_category_page(priority=priority)

        # Cache result (30 min)
        if restaurants:
            data = [r.model_dump(mode="json") for r in restaurants]
            await self._redis.setex(cache_key, 1800, json.dumps(data, default=str))

        logger.info("glovo search: %d restaurants found in %s",
                     len(restaurants), self._city_name)
        return restaurants

    async def _search_from_sitemap_slugs(self) -> list[NormalizedRestaurant]:
        """Build restaurant list from pre-synced sitemap slugs in Redis.

        Zero HTTP requests — pure Redis read + NormalizedRestaurant construction.
        Menu details (name, price, etc.) will be filled on-demand by get_menu().
        """
        redis_key = f"scraper:glovo:known_slugs:{self._city_slug}"
        raw = await self._redis.get(redis_key)
        if not raw:
            return []

        try:
            slugs: list[str] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.error("glovo: invalid JSON in %s", redis_key)
            return []

        restaurants: list[NormalizedRestaurant] = []
        for slug in slugs:
            # Double-check non-food filter (sync job should have filtered already,
            # but belt-and-suspenders)
            if self._is_non_food_slug(slug):
                continue

            restaurants.append(NormalizedRestaurant(
                platform="glovo",
                platform_restaurant_id=slug,
                platform_name=self._slug_to_name(slug),
                platform_slug=slug,
                platform_url=f"https://glovoapp.com/pl/pl/{self._city_slug}/stores/{slug}",
                name=self._slug_to_name(slug),
                latitude=0.0,
                longitude=0.0,
                is_online=True,  # Assume available — menu fetch will confirm
            ))

        logger.info(
            "glovo sitemap: %d restaurants from Redis for %s",
            len(restaurants), self._city_slug,
        )
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

    async def get_restaurant_details(
        self,
        slug: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> NormalizedRestaurant | None:
        """Fetch full restaurant details from RSC (name, address, fees, etc.).

        Useful for enriching sitemap-derived entries that only have a slug.
        """
        store_data, _ = await self._fetch_store_page(slug, priority=priority)
        if not store_data:
            return None
        return self._normalize_store_from_rsc(store_data)

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

    # ── HTML scraping fallback: category page → restaurant list ──

    async def _scrape_category_page(
        self, *, priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedRestaurant]:
        """FALLBACK: Scrape /categories/jedzenie_1 for ~50 restaurant slugs.

        Only used when sitemap slugs not yet in Redis.
        """
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
        logger.info("glovo category scraping (fallback): %d restaurants from %s",
                     len(restaurants), url)
        return restaurants

    def _parse_category_html(self, html: str) -> list[NormalizedRestaurant]:
        """Extract restaurant slug+name from SSR HTML store cards."""
        restaurants: list[NormalizedRestaurant] = []
        seen_slugs: set[str] = set()

        slug_name_pairs = self._extract_slug_name_pairs(html)

        for slug, name in slug_name_pairs:
            if slug in seen_slugs:
                continue
            if len(slug) <= 3:
                continue
            seen_slugs.add(slug)

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
                is_online=True,
            ))

        return restaurants

    def _extract_slug_name_pairs(self, html: str) -> list[tuple[str, str]]:
        """Extract (slug, name) pairs from HTML."""
        pairs: list[tuple[str, str]] = []
        seen: set[str] = set()

        # Method 1: href + img alt within same block
        for match in re.finditer(
            r'href="/pl/pl/\w+/stores/([a-z0-9][a-z0-9\-]*[a-z0-9])"'
            r'.*?'
            r'alt="([^"]*)"',
            html,
            re.DOTALL,
        ):
            slug, name = match.group(1), match.group(2)
            name = html_module.unescape(name)
            if match.end() - match.start() > 3000:
                continue
            if slug not in seen:
                seen.add(slug)
                pairs.append((slug, name))

        # Method 2: href-only fallback
        for slug_match in _SLUG_HREF_RE.finditer(html):
            slug = slug_match.group(1)
            if slug not in seen:
                seen.add(slug)
                pairs.append((slug, ""))

        return pairs

    @staticmethod
    def _is_non_food_slug(slug: str) -> bool:
        """Filter out non-restaurant stores."""
        slug_lower = slug.lower()
        return any(kw in slug_lower for kw in _NON_FOOD_KEYWORDS)

    @staticmethod
    def _slug_to_name(slug: str) -> str:
        """Convert slug to display name: 'kfc-kra' → 'Kfc'."""
        parts = slug.rsplit("-", 1)
        if len(parts) == 2 and len(parts[1]) <= 4:
            name_part = parts[0]
        else:
            name_part = slug
        name_part = re.sub(r'\d+$', '', name_part)
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
        """Parse RSC flight payload from store page HTML."""
        store_data: dict | None = None
        menu_data: dict | None = None

        rsc_chunks: list[str] = []
        for match in re.finditer(
            r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)',
            html,
        ):
            chunk = match.group(1)
            try:
                chunk = json.loads('"' + chunk + '"')
            except (json.JSONDecodeError, Exception):
                chunk = chunk.replace('\\"', '"').replace('\\\\', '\\')
            rsc_chunks.append(chunk)

        full_rsc = "".join(rsc_chunks)

        store_data = self._extract_store_from_rsc(full_rsc, slug)
        menu_data = self._extract_menu_from_rsc(full_rsc)

        return store_data, menu_data

    def _extract_store_from_rsc(self, rsc: str, slug: str) -> dict | None:
        """Extract store JSON from RSC payload using balanced brace matching."""
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
        """Extract a balanced JSON object or array starting at position `start`."""
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
