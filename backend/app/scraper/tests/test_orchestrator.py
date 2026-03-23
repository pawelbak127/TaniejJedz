"""
Orchestrator tests — parallel fetch, cache fallback, error isolation.
Uses fakeredis + mock adapters (no real HTTP).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.scraper.orchestrator import ScraperOrchestrator, OrchestratorResult
from app.scraper.schemas.normalized import (
    NormalizedMenuItem,
    NormalizedRestaurant,
    NormalizedDeliveryFee,
)


def _make_restaurant(platform: str, slug: str, online: bool = True) -> NormalizedRestaurant:
    return NormalizedRestaurant(
        platform=platform,
        platform_restaurant_id=slug,
        platform_name=f"Test {slug}",
        platform_slug=slug,
        name=f"Test {slug}",
        latitude=52.23,
        longitude=21.01,
        is_online=online,
    )


def _make_menu_item(item_id: str, price: int = 2500) -> NormalizedMenuItem:
    return NormalizedMenuItem(
        platform_item_id=item_id,
        platform_name=f"Item {item_id}",
        price_grosz=price,
    )


def _mock_glovo_empty(orch: ScraperOrchestrator) -> None:
    """Mock non-core adapters to return empty (avoid real HTTP in tests)."""
    if "glovo" in orch._adapters:
        orch._adapters["glovo"].search_restaurants = AsyncMock(return_value=[])
    if "ubereats" in orch._adapters:
        orch._adapters["ubereats"].search_restaurants = AsyncMock(return_value=[])


class TestOrchestratorSearch:

    @pytest.mark.asyncio
    async def test_search_merges_platforms(self, redis):
        orch = ScraperOrchestrator(redis)

        wolt_results = [_make_restaurant("wolt", "pizza-wolt")]
        pyszne_results = [_make_restaurant("pyszne", "pizza-pyszne")]
        glovo_results = [_make_restaurant("glovo", "pizza-glovo")]
        uber_results = [_make_restaurant("ubereats", "pizza-uber")]

        orch._adapters["wolt"].search_restaurants = AsyncMock(return_value=wolt_results)
        orch._adapters["pyszne"].search_restaurants = AsyncMock(return_value=pyszne_results)
        orch._adapters["glovo"].search_restaurants = AsyncMock(return_value=glovo_results)
        orch._adapters["ubereats"].search_restaurants = AsyncMock(return_value=uber_results)

        result = await orch.search_all(52.23, 21.01, 5.0)

        assert len(result.all_restaurants) == 4
        assert "wolt" in result.restaurants
        assert "ubereats" in result.restaurants
        assert result.errors == {}

    @pytest.mark.asyncio
    async def test_search_one_platform_fails(self, redis):
        """If Wolt fails, Pyszne still returns data."""
        orch = ScraperOrchestrator(redis)
        _mock_glovo_empty(orch)

        orch._adapters["wolt"].search_restaurants = AsyncMock(
            side_effect=Exception("Wolt down")
        )
        pyszne_results = [_make_restaurant("pyszne", "pizza-pyszne")]
        orch._adapters["pyszne"].search_restaurants = AsyncMock(return_value=pyszne_results)

        result = await orch.search_all(52.23, 21.01, 5.0)

        assert "wolt" in result.errors
        assert "pyszne" in result.restaurants
        assert len(result.restaurants["pyszne"]) == 1

    @pytest.mark.asyncio
    async def test_search_cache_fallback(self, redis):
        """On failure, serve from cache if available."""
        orch = ScraperOrchestrator(redis)
        _mock_glovo_empty(orch)

        # Pre-populate cache
        cached = [_make_restaurant("wolt", "cached-pizza")]
        cache_key = orch._search_cache_key("wolt", 52.23, 21.01)
        await redis.setex(cache_key, 3600, json.dumps(
            [r.model_dump(mode="json") for r in cached], default=str
        ))

        # Make adapter fail
        orch._adapters["wolt"].search_restaurants = AsyncMock(
            side_effect=Exception("fail")
        )
        orch._adapters["pyszne"].search_restaurants = AsyncMock(return_value=[])

        result = await orch.search_all(52.23, 21.01, 5.0)

        assert "wolt" in result.from_cache
        assert len(result.restaurants["wolt"]) == 1
        assert result.restaurants["wolt"][0].platform_slug == "cached-pizza"

    @pytest.mark.asyncio
    async def test_search_writes_cache(self, redis):
        """Successful search writes results to cache."""
        orch = ScraperOrchestrator(redis)
        _mock_glovo_empty(orch)

        restaurants = [_make_restaurant("wolt", "fresh-pizza")]
        orch._adapters["wolt"].search_restaurants = AsyncMock(return_value=restaurants)
        orch._adapters["pyszne"].search_restaurants = AsyncMock(return_value=[])

        await orch.search_all(52.23, 21.01, 5.0)

        # Check cache was written
        cache_key = orch._search_cache_key("wolt", 52.23, 21.01)
        raw = await redis.get(cache_key)
        assert raw is not None
        data = json.loads(raw)
        assert len(data) == 1
        assert data[0]["platform_slug"] == "fresh-pizza"

    @pytest.mark.asyncio
    async def test_search_records_timings(self, redis):
        orch = ScraperOrchestrator(redis)
        orch._adapters["wolt"].search_restaurants = AsyncMock(return_value=[])
        orch._adapters["pyszne"].search_restaurants = AsyncMock(return_value=[])
        orch._adapters["glovo"].search_restaurants = AsyncMock(return_value=[])
        orch._adapters["ubereats"].search_restaurants = AsyncMock(return_value=[])

        result = await orch.search_all(52.23, 21.01, 5.0)

        assert "wolt" in result.timings
        assert "pyszne" in result.timings
        assert "ubereats" in result.timings
        assert result.timings["wolt"] >= 0


class TestOrchestratorMenu:

    @pytest.mark.asyncio
    async def test_menu_parallel(self, redis):
        orch = ScraperOrchestrator(redis)

        wolt_items = [_make_menu_item("w1"), _make_menu_item("w2")]
        pyszne_items = [_make_menu_item("p1")]

        orch._adapters["wolt"].get_menu = AsyncMock(return_value=wolt_items)
        orch._adapters["pyszne"].get_menu = AsyncMock(return_value=pyszne_items)

        result = await orch.get_menu_all({"wolt": "slug-w", "pyszne": "slug-p"})

        assert len(result.all_menu_items) == 3
        assert len(result.menus["wolt"]) == 2
        assert len(result.menus["pyszne"]) == 1

    @pytest.mark.asyncio
    async def test_menu_cache_fallback(self, redis):
        orch = ScraperOrchestrator(redis)

        # Pre-populate cache
        cached_items = [_make_menu_item("cached-1")]
        cache_key = orch._menu_cache_key("wolt", "test-slug")
        await redis.setex(cache_key, 3600, json.dumps(
            [i.model_dump(mode="json") for i in cached_items], default=str
        ))

        orch._adapters["wolt"].get_menu = AsyncMock(side_effect=Exception("fail"))

        result = await orch.get_menu_all({"wolt": "test-slug"})

        assert "wolt" in result.from_cache
        assert len(result.menus["wolt"]) == 1
        assert result.menus["wolt"][0].platform_item_id == "cached-1"

    @pytest.mark.asyncio
    async def test_menu_writes_cache(self, redis):
        orch = ScraperOrchestrator(redis)

        items = [_make_menu_item("fresh-1")]
        orch._adapters["wolt"].get_menu = AsyncMock(return_value=items)

        await orch.get_menu_all({"wolt": "test-slug"})

        cache_key = orch._menu_cache_key("wolt", "test-slug")
        raw = await redis.get(cache_key)
        assert raw is not None


class TestOrchestratorIsolation:

    @pytest.mark.asyncio
    async def test_platform_failure_isolated(self, redis):
        """Wolt failure must not affect Pyszne results."""
        orch = ScraperOrchestrator(redis)
        _mock_glovo_empty(orch)

        orch._adapters["wolt"].search_restaurants = AsyncMock(
            side_effect=Exception("Wolt exploded")
        )
        orch._adapters["pyszne"].search_restaurants = AsyncMock(
            return_value=[_make_restaurant("pyszne", "ok")]
        )

        result = await orch.search_all(52.23, 21.01, 5.0)

        assert "wolt" in result.errors
        assert "Wolt exploded" in result.errors["wolt"]
        assert len(result.restaurants.get("pyszne", [])) == 1
        assert result.restaurants["pyszne"][0].is_online is True

    @pytest.mark.asyncio
    async def test_all_fail_empty_result(self, redis):
        orch = ScraperOrchestrator(redis)

        orch._adapters["wolt"].search_restaurants = AsyncMock(side_effect=Exception("fail"))
        orch._adapters["pyszne"].search_restaurants = AsyncMock(side_effect=Exception("fail"))
        orch._adapters["glovo"].search_restaurants = AsyncMock(side_effect=Exception("fail"))
        orch._adapters["ubereats"].search_restaurants = AsyncMock(side_effect=Exception("fail"))

        result = await orch.search_all(52.23, 21.01, 5.0)

        assert len(result.all_restaurants) == 0
        assert len(result.errors) == 4


class TestOrchestratorResult:

    def test_empty_result(self):
        r = OrchestratorResult()
        assert r.all_restaurants == []
        assert r.all_menu_items == []

    def test_merged_restaurants(self):
        r = OrchestratorResult()
        r.restaurants["wolt"] = [_make_restaurant("wolt", "a")]
        r.restaurants["pyszne"] = [_make_restaurant("pyszne", "b"), _make_restaurant("pyszne", "c")]
        assert len(r.all_restaurants) == 3

    def test_merged_menus(self):
        r = OrchestratorResult()
        r.menus["wolt"] = [_make_menu_item("w1")]
        r.menus["pyszne"] = [_make_menu_item("p1"), _make_menu_item("p2")]
        assert len(r.all_menu_items) == 3
