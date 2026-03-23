"""Canary scrape tests — result types, health logging, drift detection."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.jobs.canary_scrape import CanaryResult, _canary_platform, _log_canary_health
from app.scraper.schemas.normalized import NormalizedRestaurant, NormalizedMenuItem


def _restaurant(slug: str, online: bool = True) -> NormalizedRestaurant:
    return NormalizedRestaurant(
        platform="wolt", platform_restaurant_id=slug,
        platform_name=f"Test {slug}", platform_slug=slug,
        name=f"Test {slug}", latitude=52.23, longitude=21.01,
        is_online=online,
    )


def _item(name: str = "Pizza", price: int = 2500) -> NormalizedMenuItem:
    return NormalizedMenuItem(
        platform_item_id=f"id-{name}", platform_name=name, price_grosz=price,
    )


class TestCanaryResult:

    def test_ok_result(self):
        r = CanaryResult(
            platform="wolt", status="ok",
            search_count=100, menu_count=20, quality_score=0.92,
        )
        assert r.status == "ok"
        assert r.error is None

    def test_drift_result(self):
        r = CanaryResult(
            platform="pyszne", status="schema_drift",
            error="SCHEMA_DRIFT: CDN not found",
        )
        assert r.status == "schema_drift"
        assert "SCHEMA_DRIFT" in r.error


class TestCanaryPlatform:

    @pytest.mark.asyncio
    async def test_successful_canary(self, redis):
        """Mock adapter returns good data → status ok."""
        restaurants = [_restaurant("test-rest", online=True)]
        menu_items = [_item("Pizza", 2500), _item("Burger", 3000)]

        with patch("app.jobs.canary_scrape.AsyncRedis") as mock_redis_cls:
            mock_redis_cls.from_url.return_value = redis

            with patch("app.scraper.adapters.wolt.WoltAdapter") as mock_adapter_cls:
                mock_adapter = MagicMock()
                mock_adapter.search_restaurants = AsyncMock(return_value=restaurants)
                mock_adapter.get_menu = AsyncMock(return_value=menu_items)
                mock_adapter_cls.return_value = mock_adapter

                result = await _canary_platform("wolt")

        assert result.status == "ok"
        assert result.search_count == 1
        assert result.menu_count == 2
        assert result.quality_score > 0.5

    @pytest.mark.asyncio
    async def test_search_failure(self, redis):
        with patch("app.jobs.canary_scrape.AsyncRedis") as mock_redis_cls:
            mock_redis_cls.from_url.return_value = redis

            with patch("app.scraper.adapters.wolt.WoltAdapter") as mock_cls:
                mock = MagicMock()
                mock.search_restaurants = AsyncMock(side_effect=Exception("timeout"))
                mock_cls.return_value = mock

                result = await _canary_platform("wolt")

        assert result.status == "search_failed"
        assert "timeout" in result.error

    @pytest.mark.asyncio
    async def test_schema_drift_detection(self, redis):
        """Parse/Schema errors → schema_drift status."""
        from app.scraper.adapters.pyszne import PyszneSchemaError

        restaurants = [_restaurant("test", online=True)]

        with patch("app.jobs.canary_scrape.AsyncRedis") as mock_redis_cls:
            mock_redis_cls.from_url.return_value = redis

            with patch("app.scraper.adapters.pyszne.PyszneAdapter") as mock_cls:
                mock = MagicMock()
                mock.search_restaurants = AsyncMock(return_value=restaurants)
                mock.get_menu = AsyncMock(
                    side_effect=PyszneSchemaError("CDN not found")
                )
                mock_cls.return_value = mock

                result = await _canary_platform("pyszne")

        assert result.status == "schema_drift"
        assert "SCHEMA_DRIFT" in result.error

    @pytest.mark.asyncio
    async def test_unknown_platform(self, redis):
        result = await _canary_platform("deliveroo")
        assert result.status == "unknown_platform"


class TestHealthLogging:

    def test_logs_to_redis(self):
        results = [
            CanaryResult(platform="wolt", status="ok", search_count=10, quality_score=0.9),
            CanaryResult(platform="pyszne", status="schema_drift", error="CDN changed"),
        ]

        with patch("app.jobs.canary_scrape.SyncRedis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis_cls.from_url.return_value = mock_redis

            _log_canary_health(results)

            # Should rpush 2 entries
            assert mock_redis.rpush.call_count == 2

            # Schema drift should set alert key
            mock_redis.setex.assert_called_once()
            alert_call = mock_redis.setex.call_args
            assert "schema_drift:pyszne" in alert_call[0][0]
