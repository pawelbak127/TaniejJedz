"""
Pyszne.pl adapter — built from real API dumps (March 2026).

CDN JOIN logic (verified):
  categories: cdn.restaurant.menus[0].categories[].itemIds → cdn.items
  modifiers:  item.variations[].modifierGroupsIds → modifierGroups (LIST by id)
              modifierGroup.modifiers[] → modifierSets (LIST by id)
              modifierSet.modifier.additionPrice → grosz

Prices: basePrice is INT PLN (56 = 56 zł → 5600 grosz)
        additionPrice is INT PLN (4 = 4 zł → 400 grosz)
"""

from __future__ import annotations

import json
import logging
import unicodedata

from redis.asyncio import Redis

from app.config import get_settings
from app.scraper.base_adapter import BaseAdapter, ScraperError
from app.scraper.budget_manager import Priority
from app.scraper.fingerprint import build_headers, human_delay
from app.scraper.schemas.normalized import (
    NormalizedDeliveryFee,
    NormalizedHours,
    NormalizedMenuItem,
    NormalizedModifierGroup,
    NormalizedModifierOption,
    NormalizedPromotion,
    NormalizedRestaurant,
)
from app.scraper.adapters.pyszne_schemas import (
    PyszneCdn,
    PyszneCdnItem,
    PyszneCdnVariation,
    PyszneModifierGroupEntry,
    PyszneModifierSetEntry,
    PyszneSearchResponse,
    PyszneRestaurant,
    extract_cdn,
)

logger = logging.getLogger(__name__)


class PyszneParseError(ScraperError):
    pass


class PyszneSchemaError(ScraperError):
    pass


class PyszneAdapter(BaseAdapter):

    PLATFORM_NAME = "pyszne"
    BASE_URL = "https://www.pyszne.pl"

    def __init__(self, redis: Redis) -> None:
        super().__init__(redis)
        s = get_settings()
        self._search_url = s.pyszne_search_url
        self._menu_base_url = s.pyszne_menu_base_url

    # ── Public interface ────────────────────────────────────

    async def search_restaurants(
        self, lat: float, lng: float, radius_km: float, *,
        priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedRestaurant]:
        resp = await self._get(
            self._search_url,
            params={"latitude": str(lat), "longitude": str(lng), "serviceType": "delivery"},
            priority=priority, referer="https://www.pyszne.pl",
        )
        try:
            data = PyszneSearchResponse.model_validate(resp.json())
        except Exception as exc:
            raise PyszneParseError(f"Search parse: {exc}") from exc

        real = data.real_restaurants()
        logger.info("pyszne search → %d total, %d real", len(data.restaurants), len(real))
        return [self._normalize_restaurant(r) for r in real]

    async def get_menu(
        self, unique_name: str, *, priority: Priority = Priority.NORMAL,
    ) -> list[NormalizedMenuItem]:
        await self._cb.check(self.PLATFORM_NAME)
        await self._budget.acquire(self.PLATFORM_NAME, priority)

        url = f"{self._menu_base_url}/{unique_name}"
        html = await self._fetch_menu_html(url)
        next_data = self._extract_next_data(html)

        cdn_raw = extract_cdn(next_data)
        if cdn_raw is None:
            await self._cb.record_failure(self.PLATFORM_NAME)
            raise PyszneSchemaError(f"SCHEMA_DRIFT: CDN not found for {unique_name}")

        try:
            cdn = PyszneCdn.model_validate(cdn_raw)
        except Exception as exc:
            await self._cb.record_failure(self.PLATFORM_NAME)
            raise PyszneParseError(f"CDN parse failed for {unique_name}: {exc}") from exc

        await self._cb.record_success(self.PLATFORM_NAME)

        # Build lookup tables from lists
        mg_lookup = cdn.modifier_group_lookup()
        ms_lookup = cdn.modifier_set_lookup()

        # Get categories from menus
        categories = cdn.get_categories()

        items: list[NormalizedMenuItem] = []
        for cat_idx, cat in enumerate(categories):
            for item_id in cat.itemIds:
                cdn_item = cdn.items.get(item_id)
                if not cdn_item:
                    continue
                items.append(
                    self._normalize_item(cdn_item, cat.name, cat_idx, mg_lookup, ms_lookup)
                )

        logger.info("pyszne menu slug=%s → %d items (%d categories)",
                     unique_name, len(items), len(categories))
        return items

    async def get_delivery_fee(
        self, unique_name: str, lat: float, lng: float, *,
        priority: Priority = Priority.NORMAL,
    ) -> NormalizedDeliveryFee:
        restaurants = await self.search_restaurants(lat, lng, 5.0, priority=priority)
        match = next((r for r in restaurants if r.platform_slug == unique_name), None)
        if match and match.delivery_fee:
            return match.delivery_fee
        return NormalizedDeliveryFee(fee_grosz=0)

    async def get_operating_hours(self, unique_name: str, **kw) -> list[NormalizedHours]:
        return []

    async def get_promotions(self, unique_name: str, **kw) -> list[NormalizedPromotion]:
        return []

    # ── HTML fetch ──────────────────────────────────────────

    async def _fetch_menu_html(self, url: str) -> str:
        headers = build_headers(referer="https://www.pyszne.pl", mobile=False)
        headers["Accept"] = "text/html,application/xhtml+xml"
        await human_delay(0.5, 2.0)

        proxy_cfg = self._proxy.get_proxy()
        proxy_url = proxy_cfg.url if proxy_cfg else None
        timeout = self._settings.scraper_timeout_realtime

        try:
            from curl_cffi.requests import AsyncSession
            async with AsyncSession(impersonate="chrome110") as session:
                resp = await session.get(url, headers=headers, proxy=proxy_url, timeout=timeout)
                if resp.status_code == 403:
                    raise PyszneParseError(f"Cloudflare 403 on {url}")
                resp.raise_for_status()
                return resp.text
        except ImportError:
            logger.warning("curl_cffi not installed — trying httpx")
            import httpx
            async with httpx.AsyncClient(
                proxy=proxy_url, timeout=httpx.Timeout(timeout), follow_redirects=True,
            ) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 403:
                    raise PyszneParseError("Cloudflare 403 — pip install curl_cffi")
                resp.raise_for_status()
                return resp.text

    @staticmethod
    def _extract_next_data(html: str) -> dict:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            raise PyszneParseError("__NEXT_DATA__ not found")
        try:
            return json.loads(script.string)
        except json.JSONDecodeError as exc:
            raise PyszneParseError(f"__NEXT_DATA__ JSON failed: {exc}") from exc

    # ── Normalization: search ───────────────────────────────

    def _normalize_restaurant(self, r: PyszneRestaurant) -> NormalizedRestaurant:
        fee = NormalizedDeliveryFee(
            fee_grosz=r.delivery_fee_grosz,
            minimum_order_grosz=r.minimum_order_grosz,
            estimated_minutes=r.delivery_minutes_avg,
        )
        return NormalizedRestaurant(
            platform="pyszne",
            platform_restaurant_id=r.uniqueName,
            platform_name=r.name,
            platform_slug=r.uniqueName,
            platform_url=f"https://www.pyszne.pl/menu/{r.uniqueName}",
            name=r.name,
            address_street=r.address_str,
            address_city=r.address_city,
            latitude=r.latitude,
            longitude=r.longitude,
            cuisine_tags=r.cuisine_tags,
            image_url=r.logoUrl,
            rating_score=r.rating.starRating if r.rating else None,
            rating_count=r.rating.count if r.rating else None,
            is_online=r.isOpenNowForDelivery,
            delivery_fee=fee,
        )

    # ── Normalization: menu ─────────────────────────────────

    def _normalize_item(
        self,
        item: PyszneCdnItem,
        category_name: str,
        category_sort: int,
        mg_lookup: dict[str, PyszneModifierGroupEntry],
        ms_lookup: dict[str, PyszneModifierSetEntry],
    ) -> NormalizedMenuItem:
        if not item.variations:
            return NormalizedMenuItem(
                platform_item_id=item.id, platform_name=item.name,
                description=item.description, price_grosz=0,
                is_available=True, category_name=category_name,
                category_sort_order=category_sort,
            )

        sorted_vars = sorted(item.variations, key=lambda v: v.price_grosz)
        base_var = sorted_vars[0]

        modifier_groups: list[NormalizedModifierGroup] = []

        # Synthetic "Rozmiar" if >1 named variation
        named_vars = [v for v in sorted_vars if v.name and v.name != "NoVariation"]
        if len(named_vars) > 1:
            modifier_groups.append(self._build_size_group(named_vars))
        elif len(item.variations) > 1 and len(named_vars) <= 1:
            # Multiple variations but unnamed — still build size group with IDs
            actual_vars = [v for v in sorted_vars if v.price_grosz > 0 or True]
            if len(actual_vars) > 1:
                modifier_groups.append(self._build_size_group(actual_vars))

        # Real modifier groups
        for idx, group_id in enumerate(base_var.modifierGroupsIds):
            mg = mg_lookup.get(group_id)
            if not mg:
                continue
            modifier_groups.append(
                self._normalize_modifier_group(mg, idx + 1, ms_lookup)
            )

        return NormalizedMenuItem(
            platform_item_id=item.id,
            platform_name=item.name,
            description=item.description,
            price_grosz=base_var.price_grosz,
            is_available=True,  # CDN items are available unless filtered out
            category_name=category_name,
            category_sort_order=category_sort,
            modifier_groups=modifier_groups,
        )

    def _build_size_group(self, sorted_vars: list[PyszneCdnVariation]) -> NormalizedModifierGroup:
        base_price = sorted_vars[0].price_grosz
        options = [
            NormalizedModifierOption(
                platform_option_id=var.id,
                name=var.name or f"Wariant {i+1}",
                normalized_name=_normalize_text(var.name or f"wariant {i+1}"),
                price_grosz=var.price_grosz - base_price,
                is_default=(i == 0),
                is_available=var.isAvailable,
            )
            for i, var in enumerate(sorted_vars)
        ]
        return NormalizedModifierGroup(
            platform_group_id="synthetic-rozmiar", name="Rozmiar",
            group_type="required", min_selections=1, max_selections=1,
            sort_order=0, options=options,
        )

    def _normalize_modifier_group(
        self,
        group: PyszneModifierGroupEntry,
        sort_order: int,
        ms_lookup: dict[str, PyszneModifierSetEntry],
    ) -> NormalizedModifierGroup:
        """JOIN: group.modifiers[] (IDs) → ms_lookup → modifier.additionPrice."""
        options = []
        for mod_id in group.modifiers:
            ms_entry = ms_lookup.get(mod_id)
            if not ms_entry:
                continue
            mod = ms_entry.modifier
            options.append(NormalizedModifierOption(
                platform_option_id=mod.id,
                name=mod.name,
                normalized_name=_normalize_text(mod.name),
                price_grosz=mod.price_grosz,
                is_default=(mod.defaultChoices > 0),
                is_available=True,
            ))
        return NormalizedModifierGroup(
            platform_group_id=group.id, name=group.name,
            group_type="required" if group.is_required else "optional",
            min_selections=group.minChoices, max_selections=group.maxChoices,
            sort_order=sort_order, options=options,
        )


def _normalize_text(text: str) -> str:
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))
