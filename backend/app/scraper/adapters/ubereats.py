"""
Uber Eats adapter — sitemap-driven discovery + getStoreV1 menus (April 2026).

v3 changes (CRITICAL FIX):
  - UUID decode: sitemap base64url → hex UUID before API calls
  - getStoreV1 rejects raw base64url ("invalid_store_uuid") but accepts decoded hex
  - search_restaurants() now stores decoded hex UUID as platform_slug
  - 10/10 test UUIDs confirmed working after decode

Redis keys consumed:
    scraper:ubereats:known_stores:{city_slug}  →  JSON list of {slug, uuid, locale}
    (uuid field is base64url from sitemap — decoded at runtime)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import time
import uuid as uuid_module

import httpx
from redis.asyncio import Redis

from app.config import get_settings
from app.scraper.base_adapter import BaseAdapter, ScraperError
from app.scraper.budget_manager import Priority
from app.scraper.fingerprint import build_headers
from app.scraper.schemas.normalized import (
    NormalizedDeliveryFee,
    NormalizedHours,
    NormalizedMenuItem,
    NormalizedModifierGroup,
    NormalizedModifierOption,
    NormalizedPromotion,
    NormalizedRestaurant,
)
from app.scraper.adapters.ubereats_schemas import (
    UberEatsCatalogItem,
    UberEatsStoreData,
    UberEatsStoreResponse,
    UberEatsSuggestionsResponse,
    UberEatsSuggestionStore,
)

logger = logging.getLogger(__name__)

_UBEREATS_BASE = "https://www.ubereats.com"

_UBEREATS_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "x-csrf-token": "x",
}

# ═══════════════════════════════════════════════════════════════
# UUID decode — sitemap base64url → hex UUID for API
# ═══════════════════════════════════════════════════════════════

def decode_ubereats_uuid(b64url: str) -> str:
    """Convert base64url UUID from sitemap to standard hex UUID.

    Sitemap URLs contain base64url-encoded UUIDs (22 chars, no padding):
        'skuqnuRLTnWC8PipFYCYfg' → 'b24baa9e-e44b-4e75-82f0-f8a91580987e'

    getStoreV1 API requires standard hex UUID format.
    Confirmed working: 10/10 test UUIDs return success after decode.
    """
    padding = "=" * (4 - (len(b64url) % 4)) if len(b64url) % 4 != 0 else ""
    raw_bytes = base64.urlsafe_b64decode(b64url + padding)
    if len(raw_bytes) != 16:
        raise ValueError(f"Expected 16 bytes, got {len(raw_bytes)} for '{b64url}'")
    return str(uuid_module.UUID(bytes=raw_bytes))


def _is_base64url_uuid(value: str) -> bool:
    """Check if a string looks like a base64url UUID (22 chars, no dashes)."""
    return len(value) == 22 and "-" not in value[:8]


def _ensure_hex_uuid(store_uuid: str) -> str:
    """Ensure UUID is in hex format. Decode from base64url if needed."""
    if _is_base64url_uuid(store_uuid):
        return decode_ubereats_uuid(store_uuid)
    return store_uuid


# ═══════════════════════════════════════════════════════════════
# City resolution
# ═══════════════════════════════════════════════════════════════

_POLISH_CITIES = [
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
    (50.8661, 20.6286, "kielce"),
    (53.0138, 18.5984, "torun"),
    (53.1235, 18.0084, "bydgoszcz"),
    (53.7784, 20.4801, "olsztyn"),
    (50.2964, 18.6544, "gliwice"),
    (50.8118, 19.1203, "czestochowa"),
    (50.3223, 19.2243, "sosnowiec"),
    (51.6724, 15.5082, "zielona-gora"),
    (49.8225, 19.0466, "bielsko-biala"),
    (50.6751, 17.9213, "opole"),
    (52.6483, 19.0700, "wloclawek"),
    (49.2992, 19.9496, "zakopane"),
    (51.4027, 21.1471, "radom"),
    (52.5468, 19.7064, "plock"),
    (54.1522, 19.4015, "elblag"),
    (54.1764, 15.5892, "kolobrzeg"),
    (54.1943, 16.1715, "koszalin"),
    (50.0121, 20.9858, "tarnow"),
    (51.7559, 18.0909, "kalisz"),
    (51.2070, 16.1551, "legnica"),
    (54.4641, 17.0285, "slupsk"),
    (50.0972, 18.5463, "rybnik"),
    (52.1058, 20.8272, "grodzisk-mazowiecki"),
    (52.7325, 15.2369, "gorzow-wielkopolski"),
]


def _resolve_city(lat: float, lng: float) -> str:
    best_dist = float("inf")
    best = "warszawa"
    for c_lat, c_lng, slug in _POLISH_CITIES:
        dist = math.sqrt((lat - c_lat) ** 2 + (lng - c_lng) ** 2)
        if dist < best_dist:
            best_dist = dist
            best = slug
    return best


# Fallback query pool
_SEARCH_QUERIES = [
    "pizza", "burger", "sushi", "kebab", "ramen",
    "pierogi", "zapiekanka", "tacos", "pasta", "bowl",
    "vegan", "fit", "poke", "pad thai", "obiad",
    "KFC", "McDonald", "Dominos", "Subway", "Starbucks",
    "indyjska", "turecka", "naleśniki", "restauracja", "lunch",
]

_SUGGESTION_CONCURRENCY = 10


class UberEatsParseError(ScraperError):
    pass


class UberEatsAdapter(BaseAdapter):

    PLATFORM_NAME = "ubereats"
    BASE_URL = _UBEREATS_BASE

    def __init__(self, redis: Redis) -> None:
        super().__init__(redis)

    # ── Public interface ────────────────────────────────────

    async def search_restaurants(
        self,
        lat: float,
        lng: float,
        radius_km: float,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedRestaurant]:
        """Search via sitemap-derived store list, filtered by city.

        Fallback chain:
          1. Per-city Redis key → decode base64url UUIDs → hex
          2. Live suggestion queries (~43 results)
        """
        cache_key = f"scraper:ubereats:search:{lat:.3f}:{lng:.3f}"
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return [NormalizedRestaurant.model_validate(d) for d in data]
            except Exception:
                pass

        city_slug = _resolve_city(lat, lng)

        # PRIMARY: Per-city sitemap stores (with UUID decode)
        restaurants = await self._search_from_sitemap(city_slug)

        # FALLBACK: Suggestion queries
        if not restaurants:
            logger.warning(
                "ubereats: no sitemap stores for %s — falling back to suggestions",
                city_slug,
            )
            await self._cb.check(self.PLATFORM_NAME)
            await self._budget.acquire(self.PLATFORM_NAME, priority)
            discovered = await self._batch_suggestions(priority=priority)
            restaurants = [self._normalize_suggestion(s) for s in discovered.values()]

        if restaurants:
            data = [r.model_dump(mode="json") for r in restaurants]
            await self._redis.setex(cache_key, 1800, json.dumps(data, default=str))

        logger.info("ubereats search: %d restaurants for %s", len(restaurants), city_slug)
        return restaurants

    async def _search_from_sitemap(self, city_slug: str) -> list[NormalizedRestaurant]:
        """Build restaurant list from per-city sitemap data in Redis.

        CRITICAL: Decodes base64url UUIDs to hex format for API compatibility.
        """
        redis_key = f"scraper:ubereats:known_stores:{city_slug}"
        raw = await self._redis.get(redis_key)

        if not raw:
            logger.debug("ubereats: no per-city key for %s", city_slug)
            return []

        try:
            stores: list[dict] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

        restaurants: list[NormalizedRestaurant] = []
        decode_errors = 0

        for s in stores:
            b64url = s.get("uuid", "")
            slug = s.get("slug", "")
            locale = s.get("locale", "pl-en")
            if not b64url:
                continue

            # Decode base64url → hex UUID
            try:
                hex_uuid = decode_ubereats_uuid(b64url)
            except (ValueError, Exception):
                decode_errors += 1
                continue

            restaurants.append(NormalizedRestaurant(
                platform="ubereats",
                platform_restaurant_id=hex_uuid,
                platform_name=self._slug_to_name(slug),
                # CRITICAL: platform_slug = decoded HEX UUID
                platform_slug=hex_uuid,
                platform_url=f"https://www.ubereats.com/{locale}/store/{slug}/{b64url}",
                name=self._slug_to_name(slug),
                latitude=0.0,
                longitude=0.0,
                is_online=True,
            ))

        if decode_errors:
            logger.warning("ubereats: %d UUID decode errors for %s", decode_errors, city_slug)

        logger.info("ubereats sitemap: %d restaurants for %s", len(restaurants), city_slug)
        return restaurants

    @staticmethod
    def _slug_to_name(slug: str) -> str:
        return slug.replace("-", " ").replace("&", "&").strip().title()

    async def get_menu(
        self,
        store_uuid: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedMenuItem]:
        hex_uuid = _ensure_hex_uuid(store_uuid)
        store_data = await self._fetch_store(hex_uuid, priority=priority)
        all_items = store_data.all_items()
        items = [
            self._normalize_item(item, cat, idx)
            for idx, (cat, item) in enumerate(all_items)
        ]
        logger.info("ubereats menu uuid=%s → %d items", hex_uuid[:12], len(items))
        return items

    async def get_store_info(
        self, store_uuid: str, *, priority: Priority = Priority.NORMAL,
    ) -> NormalizedRestaurant:
        hex_uuid = _ensure_hex_uuid(store_uuid)
        store = await self._fetch_store(hex_uuid, priority=priority)
        return self._normalize_store(store)

    async def get_delivery_fee(
        self, store_uuid: str, lat: float, lng: float, *,
        priority: Priority = Priority.NORMAL,
    ) -> NormalizedDeliveryFee:
        hex_uuid = _ensure_hex_uuid(store_uuid)
        store = await self._fetch_store(hex_uuid, priority=priority)
        return NormalizedDeliveryFee(fee_grosz=store.service_fee_grosz)

    async def get_operating_hours(self, store_uuid: str, **kw) -> list[NormalizedHours]:
        return []

    async def get_promotions(self, store_uuid: str, **kw) -> list[NormalizedPromotion]:
        return []

    # ── Batch suggestions (fallback) ────────────────────────

    async def _batch_suggestions(
        self, *, priority: Priority = Priority.NORMAL,
    ) -> dict[str, UberEatsSuggestionStore]:
        discovered: dict[str, UberEatsSuggestionStore] = {}
        semaphore = asyncio.Semaphore(_SUGGESTION_CONCURRENCY)
        url = f"{_UBEREATS_BASE}/_p/api/getSearchSuggestionsV1?localeCode=pl-en"
        headers = build_headers(referer=f"{_UBEREATS_BASE}/", extra=_UBEREATS_HEADERS)

        proxy_cfg = self._proxy.get_proxy()
        proxy_url = proxy_cfg.url if proxy_cfg else None
        timeout = self._settings.scraper_timeout_realtime

        async with httpx.AsyncClient(
            proxy=proxy_url, timeout=httpx.Timeout(timeout), follow_redirects=True,
        ) as client:
            async def _query_one(query: str) -> list[UberEatsSuggestionStore]:
                async with semaphore:
                    try:
                        resp = await client.post(
                            url, headers=headers,
                            json={"userQuery": query, "date": "", "startTime": 0, "endTime": 0},
                        )
                        if resp.status_code != 200:
                            return []
                        result = UberEatsSuggestionsResponse.model_validate(resp.json())
                        return result.store_results()
                    except Exception as exc:
                        logger.debug("ubereats suggestion '%s' failed: %s", query, exc)
                        return []

            results = await asyncio.gather(*[_query_one(q) for q in _SEARCH_QUERIES])

        for stores in results:
            for store in stores:
                if store.uuid and store.uuid not in discovered:
                    discovered[store.uuid] = store
        return discovered

    async def _search_suggestions(
        self, query: str, *, priority: Priority = Priority.NORMAL,
    ) -> list[UberEatsSuggestionStore]:
        resp = await self._post(
            f"{_UBEREATS_BASE}/_p/api/getSearchSuggestionsV1?localeCode=pl-en",
            json_body={"userQuery": query, "date": "", "startTime": 0, "endTime": 0},
            priority=priority, referer=f"{_UBEREATS_BASE}/",
            extra_headers=_UBEREATS_HEADERS, add_delay=False,
        )
        try:
            result = UberEatsSuggestionsResponse.model_validate(resp.json())
        except Exception as exc:
            raise UberEatsParseError(f"Suggestions parse failed: {exc}") from exc
        return result.store_results()

    # ── Store fetch ─────────────────────────────────────────

    async def _fetch_store(
        self, store_uuid: str, *, priority: Priority = Priority.NORMAL,
    ) -> UberEatsStoreData:
        """Fetch store details. store_uuid MUST be hex format."""
        cache_key = f"scraper:ubereats:store:{store_uuid}"
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                return UberEatsStoreData.model_validate(json.loads(cached))
            except Exception:
                pass

        resp = await self._post(
            f"{_UBEREATS_BASE}/_p/api/getStoreV1?localeCode=pl-en",
            json_body={
                "storeUuid": store_uuid,
                "diningMode": "DELIVERY",
                "time": {"asap": True},
            },
            priority=priority, referer=f"{_UBEREATS_BASE}/",
            extra_headers=_UBEREATS_HEADERS,
        )
        try:
            store_resp = UberEatsStoreResponse.model_validate(resp.json())
        except Exception as exc:
            raise UberEatsParseError(f"Store parse failed: {exc}") from exc

        store = store_resp.data
        await self._redis.setex(
            cache_key, 3600,
            json.dumps(store.model_dump(mode="json"), default=str),
        )
        return store

    # ── Normalization ───────────────────────────────────────

    def _normalize_suggestion(self, store: UberEatsSuggestionStore) -> NormalizedRestaurant:
        return NormalizedRestaurant(
            platform="ubereats",
            platform_restaurant_id=store.uuid,
            platform_name=store.title,
            platform_slug=store.uuid,
            platform_url=f"https://www.ubereats.com/pl-en/store/{store.slug}/{store.uuid}",
            name=store.title,
            latitude=0.0, longitude=0.0,
            cuisine_tags=store.cuisine_tags,
            image_url=store.heroImageUrl,
            is_online=store.isOrderable,
        )

    def _normalize_store(self, store: UberEatsStoreData) -> NormalizedRestaurant:
        return NormalizedRestaurant(
            platform="ubereats",
            platform_restaurant_id=store.uuid,
            platform_name=store.title,
            platform_slug=store.uuid,
            platform_url=f"https://www.ubereats.com/pl-en/store/{store.slug}/{store.uuid}",
            name=store.title,
            address_street=store.location.streetAddress,
            address_city=store.location.city,
            latitude=store.location.latitude,
            longitude=store.location.longitude,
            cuisine_tags=store.cuisineList,
            is_online=store.isOpen,
            rating_score=store.rating.ratingValue if store.rating else None,
            rating_count=store.rating.count if store.rating else None,
            delivery_fee=NormalizedDeliveryFee(fee_grosz=store.service_fee_grosz),
        )

    def _normalize_item(
        self, item: UberEatsCatalogItem, category_name: str, category_sort: int,
    ) -> NormalizedMenuItem:
        return NormalizedMenuItem(
            platform_item_id=item.uuid,
            platform_name=item.title,
            description=item.itemDescription,
            price_grosz=item.price_grosz,
            is_available=item.isAvailable and not item.isSoldOut,
            category_name=category_name,
            category_sort_order=category_sort,
            modifier_groups=[],
        )
