"""Tests for BudgetManager."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.scraper.budget_manager import BudgetManager, BudgetExhaustedError, Priority


class TestBudgetManager:

    @pytest.mark.asyncio
    async def test_acquire_increments_counter(self, redis):
        bm = BudgetManager(redis)
        count = await bm.acquire("wolt", Priority.NORMAL)
        assert count == 1
        count = await bm.acquire("wolt", Priority.NORMAL)
        assert count == 2

    @pytest.mark.asyncio
    async def test_acquire_unknown_platform_raises(self, redis):
        bm = BudgetManager(redis)
        with pytest.raises(ValueError, match="Unknown platform"):
            await bm.acquire("ubereats", Priority.NORMAL)

    @pytest.mark.asyncio
    async def test_low_priority_rejected_at_70pct(self, redis):
        bm = BudgetManager(redis)
        bm._caps["wolt"] = 100  # small cap for testing

        # Fill to 70 requests (70%)
        for _ in range(70):
            await bm.acquire("wolt", Priority.NORMAL)

        # 71st LOW request should fail
        with pytest.raises(BudgetExhaustedError) as exc_info:
            await bm.acquire("wolt", Priority.LOW)
        assert exc_info.value.priority == Priority.LOW

    @pytest.mark.asyncio
    async def test_normal_priority_rejected_at_90pct(self, redis):
        bm = BudgetManager(redis)
        bm._caps["wolt"] = 100

        # Fill to 90 requests
        for _ in range(90):
            await bm.acquire("wolt", Priority.CRITICAL)  # critical always passes

        # 91st NORMAL should fail
        with pytest.raises(BudgetExhaustedError) as exc_info:
            await bm.acquire("wolt", Priority.NORMAL)
        assert exc_info.value.priority == Priority.NORMAL

    @pytest.mark.asyncio
    async def test_critical_always_passes(self, redis):
        bm = BudgetManager(redis)
        bm._caps["wolt"] = 10

        # Fill completely with CRITICAL
        for _ in range(10):
            await bm.acquire("wolt", Priority.CRITICAL)

        # 11th CRITICAL still passes (threshold is 1.01x)
        count = await bm.acquire("wolt", Priority.CRITICAL)
        assert count == 11

    @pytest.mark.asyncio
    async def test_budget_decrements_on_rejection(self, redis):
        """When a request is rejected, the counter should be decremented back."""
        bm = BudgetManager(redis)
        bm._caps["wolt"] = 10

        # Fill to 7 (70%)
        for _ in range(7):
            await bm.acquire("wolt", Priority.CRITICAL)

        # LOW is rejected at 70%
        with pytest.raises(BudgetExhaustedError):
            await bm.acquire("wolt", Priority.LOW)

        # Counter should still be 7, not 8
        status = await bm.get_status("wolt")
        assert status["used"] == 7

    @pytest.mark.asyncio
    async def test_get_status(self, redis):
        bm = BudgetManager(redis)
        await bm.acquire("wolt", Priority.NORMAL)
        await bm.acquire("wolt", Priority.NORMAL)

        status = await bm.get_status("wolt")
        assert status["platform"] == "wolt"
        assert status["used"] == 2
        assert status["cap"] == 5000
        assert status["remaining"] == 4998
        assert 0 < status["pct_used"] < 0.01

    @pytest.mark.asyncio
    async def test_get_all_statuses(self, redis):
        bm = BudgetManager(redis)
        statuses = await bm.get_all_statuses()
        platforms = {s["platform"] for s in statuses}
        assert "wolt" in platforms
        assert "pyszne" in platforms

    @pytest.mark.asyncio
    async def test_register_platform(self, redis):
        bm = BudgetManager(redis)
        bm.register_platform("glovo", 3000)
        count = await bm.acquire("glovo", Priority.NORMAL)
        assert count == 1
        status = await bm.get_status("glovo")
        assert status["cap"] == 3000

    @pytest.mark.asyncio
    async def test_alert_callback_fires(self, redis):
        alerts = []

        async def on_alert(platform, used, cap):
            alerts.append((platform, used, cap))

        bm = BudgetManager(redis, alert_callback=on_alert)
        bm._caps["wolt"] = 10
        # Alert threshold = 90% → fires at request #9

        for _ in range(10):
            try:
                await bm.acquire("wolt", Priority.CRITICAL)
            except BudgetExhaustedError:
                break

        assert len(alerts) == 1
        assert alerts[0][0] == "wolt"
        assert alerts[0][1] == 9  # 90% of 10

    @pytest.mark.asyncio
    async def test_separate_platforms_separate_counters(self, redis):
        bm = BudgetManager(redis)
        await bm.acquire("wolt", Priority.NORMAL)
        await bm.acquire("wolt", Priority.NORMAL)
        await bm.acquire("pyszne", Priority.NORMAL)

        wolt = await bm.get_status("wolt")
        pyszne = await bm.get_status("pyszne")
        assert wolt["used"] == 2
        assert pyszne["used"] == 1
