"""Tests for BaseAdapter — infrastructure wiring (not HTTP)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.scraper.base_adapter import BaseAdapter, PlatformUnavailableError
from app.scraper.budget_manager import BudgetExhaustedError, Priority
from app.scraper.circuit_breaker import CircuitOpenError
from app.scraper.schemas.normalized import NormalizedDeliveryFee


class _DummyAdapter(BaseAdapter):
    """Concrete subclass for testing base wiring."""
    PLATFORM_NAME = "test_platform"
    BASE_URL = "https://test.example.com"

    async def search_restaurants(self, lat, lng, radius_km):
        return []

    async def get_menu(self, restaurant_id):
        return []

    async def get_delivery_fee(self, restaurant_id, lat, lng):
        return NormalizedDeliveryFee(fee_grosz=0)

    async def get_operating_hours(self, restaurant_id):
        return []

    async def get_promotions(self, restaurant_id):
        return []


class TestBaseAdapter:

    @pytest.fixture
    def adapter(self, redis):
        # Register the test platform in budget manager
        a = _DummyAdapter(redis)
        a._budget.register_platform("test_platform", 10000)
        return a

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_fetch(self, adapter):
        """If circuit is open, _fetch should raise CircuitOpenError."""
        await adapter._cb.force_open("test_platform")
        with pytest.raises(CircuitOpenError):
            await adapter._get("https://test.example.com/api")

    @pytest.mark.asyncio
    async def test_budget_blocks_fetch(self, adapter):
        """If budget is exhausted, _fetch should raise BudgetExhaustedError."""
        adapter._budget._caps["test_platform"] = 1
        # Consume the only slot
        await adapter._budget.acquire("test_platform", Priority.CRITICAL)
        with pytest.raises(BudgetExhaustedError):
            await adapter._get(
                "https://test.example.com/api",
                priority=Priority.NORMAL,
                add_delay=False,
            )
