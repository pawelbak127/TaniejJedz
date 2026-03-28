"""
Uber Eats adapter — with parallel search via suggestions (March 2026).

Search strategy:
  POST getSearchSuggestionsV1 with ~25 food terms IN PARALLEL.
  API returns max 2 store results per query.
  Uses shared httpx client for all suggestions (single TLS handshake).
  Single budget/CB check for the whole batch (not per-query).
  ~25 queries with 10 concurrent ≈ 2-3s total (within 8s timeout).

Menu: POST getStoreV1 → store info + full catalog.
Price already in GROSZ — zero conversion.

IMPORTANT: platform_slug = UUID (not human-readable slug).
  UberEats API identifies stores by UUID, so all internal references
  use UUID to ensure get_menu() receives the correct identifier.
  The human-readable slug is only used for constructing platform_url.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

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

# Expanded query pool — verified via diag (March 2026).
# API returns max 2 stores per query. Only queries yielding >0 results included.
# 25 queries / 10 concurrent = 3 rounds × ~750ms = ~2.5s with shared client.
_SEARCH_QUERIES = [
    # Food types (high yield — 2 each)
    "pizza", "burger", "sushi", "kebab", "ramen",
    "pierogi", "zapiekanka", "tacos", "pasta", "bowl",
    "vegan", "fit", "poke", "pad thai", "obiad",
    # Chains (1 each)
    "KFC", "McDonald", "Dominos", "Subway", "Starbucks",
    # Cuisine + misc (1-2 each)
    "indyjska", "turecka", "naleśniki", "restauracja", "lunch",
]

# Max concurrent suggestion requests
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
        """Search via parallel getSearchSuggestionsV1 queries.

        Uses batched infrastructure: single CB check + budget acquire
        for the whole search, then shared httpx client for all suggestions.
        This avoids per-query overhead (TLS handshake + Redis roundtrips).
        """
        cache_key = f"scraper:ubereats:search:{lat:.3f}:{lng:.3f}"
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return [NormalizedRestaurant.model_validate(d) for d in data]
            except Exception:
                pass

        # Single infrastructure check for the whole batch
        await self._cb.check(self.PLATFORM_NAME)
        await self._budget.acquire(self.PLATFORM_NAME, priority)

        # Run all suggestions with a shared httpx client
        discovered = await self._batch_suggestions(priority=priority)

        logger.info("ubereats search: discovered %d unique stores from %d queries",
                     len(discovered), len(_SEARCH_QUERIES))

        restaurants = [self._normalize_suggestion(s) for s in discovered.values()]

        if restaurants:
            data = [r.model_dump(mode="json") for r in restaurants]
            await self._redis.setex(cache_key, 1800, json.dumps(data, default=str))

        return restaurants

    async def get_menu(
        self,
        store_uuid: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedMenuItem]:
        store_data = await self._fetch_store(store_uuid, priority=priority)
        all_items = store_data.all_items()
        items = [
            self._normalize_item(item, cat, idx)
            for idx, (cat, item) in enumerate(all_items)
        ]
        logger.info("ubereats menu uuid=%s → %d items", store_uuid[:12], len(items))
        return items

    async def get_store_info(
        self, store_uuid: str, *, priority: Priority = Priority.NORMAL,
    ) -> NormalizedRestaurant:
        store = await self._fetch_store(store_uuid, priority=priority)
        return self._normalize_store(store)

    async def get_delivery_fee(
        self, store_uuid: str, lat: float, lng: float, *,
        priority: Priority = Priority.NORMAL,
    ) -> NormalizedDeliveryFee:
        store = await self._fetch_store(store_uuid, priority=priority)
        return NormalizedDeliveryFee(fee_grosz=store.service_fee_grosz)

    async def get_operating_hours(self, store_uuid: str, **kw) -> list[NormalizedHours]:
        return []

    async def get_promotions(self, store_uuid: str, **kw) -> list[NormalizedPromotion]:
        return []

    # ── Batch suggestions (shared client, minimal overhead) ─

    async def _batch_suggestions(
        self,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> dict[str, UberEatsSuggestionStore]:
        """Run all suggestion queries with a SHARED httpx client.

        Single TLS handshake + connection reuse → ~3x faster than per-query clients.
        Budget/CB already checked by caller.
        """
        discovered: dict[str, UberEatsSuggestionStore] = {}
        semaphore = asyncio.Semaphore(_SUGGESTION_CONCURRENCY)
        url = f"{_UBEREATS_BASE}/_p/api/getSearchSuggestionsV1?localeCode=pl-en"
        headers = build_headers(
            referer=f"{_UBEREATS_BASE}/",
            extra=_UBEREATS_HEADERS,
        )

        proxy_cfg = self._proxy.get_proxy()
        proxy_url = proxy_cfg.url if proxy_cfg else None
        timeout = self._settings.scraper_timeout_realtime

        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
        ) as client:

            async def _query_one(query: str) -> list[UberEatsSuggestionStore]:
                async with semaphore:
                    try:
                        resp = await client.post(
                            url,
                            headers=headers,
                            json={"userQuery": query, "date": "", "startTime": 0, "endTime": 0},
                        )
                        if resp.status_code != 200:
                            return []
                        result = UberEatsSuggestionsResponse.model_validate(resp.json())
                        return result.store_results()
                    except Exception as exc:
                        logger.debug("ubereats suggestion '%s' failed: %s", query, exc)
                        return []

            results = await asyncio.gather(
                *[_query_one(q) for q in _SEARCH_QUERIES]
            )

        for stores in results:
            for store in stores:
                if store.uuid and store.uuid not in discovered:
                    discovered[store.uuid] = store

        return discovered

    # ── Single suggestion (for direct use, e.g. manual tests) ─

    async def _search_suggestions(
        self,
        query: str,
        *,
        priority: Priority = Priority.NORMAL,
    ) -> list[UberEatsSuggestionStore]:
        """POST getSearchSuggestionsV1 — single query via base _post."""
        resp = await self._post(
            f"{_UBEREATS_BASE}/_p/api/getSearchSuggestionsV1?localeCode=pl-en",
            json_body={"userQuery": query, "date": "", "startTime": 0, "endTime": 0},
            priority=priority,
            referer=f"{_UBEREATS_BASE}/",
            extra_headers=_UBEREATS_HEADERS,
            add_delay=False,
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
            priority=priority,
            referer=f"{_UBEREATS_BASE}/",
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
            # CRITICAL: platform_slug = UUID, not human slug.
            # Orchestrator passes platform_slug to get_menu(),
            # and UberEats API requires UUID, not slug.
            platform_slug=store.uuid,
            platform_url=f"https://www.ubereats.com/pl-en/store/{store.slug}/{store.uuid}",
            name=store.title,
            latitude=0.0,
            longitude=0.0,
            cuisine_tags=store.cuisine_tags,
            image_url=store.heroImageUrl,
            is_online=store.isOrderable,
        )

    def _normalize_store(self, store: UberEatsStoreData) -> NormalizedRestaurant:
        return NormalizedRestaurant(
            platform="ubereats",
            platform_restaurant_id=store.uuid,
            platform_name=store.title,
            platform_slug=store.uuid,  # UUID — consistent with _normalize_suggestion
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
