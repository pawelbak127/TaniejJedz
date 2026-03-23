"""
Glovo adapter — with slug probing for restaurant discovery (March 2026).

Search strategy (since there's no search/feed API):
  1. HTML scraping: city listing page (gets ~2 SSR results)
  2. Chain slug probing: try known patterns like "kfc-{city}", "mcdonalds-{city}"
  3. All discovered slugs → /v3/stores/{slug} detail → normalize

This finds ~20-40 restaurants per city from known chains.
For full discovery, cross-reference names from Wolt/Pyszne in Epic 4.

Endpoints:
  Store detail: GET api.glovoapp.com/v3/stores/{slug}?cityCode={code}
  Menu content: GET api.glovoapp.com/v4/stores/{id}/addresses/{addressId}/content/main
"""

from __future__ import annotations

import asyncio
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

_GLOVO_API = "https://api.glovoapp.com"

# ═══════════════════════════════════════════════════════════════
# City mapping + slug probing
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


# Known chains with Glovo slug patterns: "{brand}-{city_short}"
_CHAIN_SLUGS = [
    "kfc", "mcdonalds", "burger-king", "pizza-hut", "subway",
    "starbucks", "costa-coffee", "popeyes", "north-fish",
    "biedronka-express", "apteczka-zdrowia",
    "telepizza", "dominos", "papa-johns",
    "sushi-master", "sushi-kushi", "thai-wok",
    "sphinx", "kebab-king", "berlin-doner",
]

_PROBE_CONCURRENCY = 10


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

    def _glovo_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Glovo-Location-City-Code": self._city_code,
        }

    # ── Public interface ────────────────────────────────────

    async def search_restaurants(
        self,
        lat: float,
        lng: float,
        radius_km: float,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedRestaurant]:
        """Search via HTML scraping + chain slug probing."""
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

        # 1. HTML scraping (gets ~2 SSR results)
        html_slugs = await self._get_slugs_from_html(priority=priority)

        # 2. Chain slug probing (generates candidates, probes API)
        chain_slugs = self._generate_chain_slugs()

        # Combine and deduplicate
        all_slugs = list(set(html_slugs + chain_slugs))
        logger.info("glovo search: probing %d slug candidates (%d html + %d chains)",
                     len(all_slugs), len(html_slugs), len(chain_slugs))

        # 3. Probe all slugs concurrently
        restaurants = await self._probe_slugs(all_slugs, priority=priority)

        # Filter to food only (RESTAURANT category)
        restaurants = [r for r in restaurants if r.cuisine_tags or "express" not in r.name.lower()]

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
        store = await self._get_store_detail(slug, priority=priority)
        if store.cityCode:
            self._city_code = store.cityCode

        url = f"{_GLOVO_API}/v4/stores/{store.id}/addresses/{store.addressId}/content/main"
        resp = await self._get(
            url,
            priority=priority,
            referer=f"https://glovoapp.com/pl/pl/{self._city_slug}/stores/{slug}",
            extra_headers=self._glovo_headers(),
        )

        try:
            menu = GlovoMenuResponse.model_validate(resp.json())
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
        store = await self._get_store_detail(slug, priority=priority)
        return NormalizedDeliveryFee(fee_grosz=store.delivery_fee_grosz)

    async def get_operating_hours(self, slug: str, **kw) -> list[NormalizedHours]:
        return []

    async def get_promotions(self, slug: str, **kw) -> list[NormalizedPromotion]:
        return []

    # ── Slug discovery ──────────────────────────────────────

    def _generate_chain_slugs(self) -> list[str]:
        """Generate slug candidates from known chains + city suffix."""
        slugs = []
        for chain in _CHAIN_SLUGS:
            # Try common patterns: brand-city_short, brand-city_slug
            slugs.append(f"{chain}-{self._city_short}")
            if self._city_slug != self._city_short:
                slugs.append(f"{chain}-{self._city_slug}")
        return slugs

    async def _get_slugs_from_html(
        self, *, priority: Priority = Priority.NORMAL,
    ) -> list[str]:
        """Scrape slugs from city listing (limited — SSR only)."""
        try:
            url = f"{self.BASE_URL}/pl/pl/{self._city_slug}/restaurants_702/"
            resp = await self._get(url, priority=priority, extra_headers={"Accept": "text/html"})
            html = resp.text
            slugs = list(set(re.findall(r'/stores/([a-z0-9\-]+)', html)))
            return [s for s in slugs if len(s) > 3]
        except Exception as exc:
            logger.debug("glovo HTML scraping failed: %s", exc)
            return []

    async def _probe_slugs(
        self,
        slugs: list[str],
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedRestaurant]:
        """Probe store detail API for each slug concurrently."""
        semaphore = asyncio.Semaphore(_PROBE_CONCURRENCY)
        results: list[NormalizedRestaurant] = []

        async def _try_one(slug: str) -> NormalizedRestaurant | None:
            async with semaphore:
                try:
                    store = await self._get_store_detail(slug, priority=priority)
                    if store.enabled and store.food:
                        return self._normalize_store(store)
                except Exception:
                    return None
            return None

        outcomes = await asyncio.gather(
            *[_try_one(s) for s in slugs],
            return_exceptions=True,
        )

        for outcome in outcomes:
            if isinstance(outcome, NormalizedRestaurant):
                results.append(outcome)

        return results

    # ── Store detail ────────────────────────────────────────

    async def _get_store_detail(
        self, slug: str, *, priority: Priority = Priority.NORMAL,
    ) -> GlovoStore:
        cache_key = f"scraper:glovo:store:{slug}"
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                return GlovoStore.model_validate(json.loads(cached))
            except Exception:
                pass

        url = f"{_GLOVO_API}/v3/stores/{slug}"
        resp = await self._get(
            url,
            params={"cityCode": self._city_code},
            priority=priority,
            extra_headers=self._glovo_headers(),
            add_delay=False,  # Skip delay for probing
        )

        try:
            store = GlovoStore.model_validate(resp.json())
        except Exception as exc:
            raise GlovoParseError(f"Store parse failed for {slug}: {exc}") from exc

        await self._redis.setex(
            cache_key, 3600,
            json.dumps(store.model_dump(mode="json"), default=str),
        )
        return store

    # ── Normalization ───────────────────────────────────────

    def _normalize_store(self, store: GlovoStore) -> NormalizedRestaurant:
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
