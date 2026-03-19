"""Tests for CircuitBreaker."""

from __future__ import annotations

import time
import pytest

from app.scraper.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class TestCircuitBreaker:

    @pytest.mark.asyncio
    async def test_starts_closed(self, redis):
        cb = CircuitBreaker(redis)
        state = await cb.check("wolt")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_stays_closed_under_threshold(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=5)
        for _ in range(4):
            await cb.record_failure("wolt")
        state = await cb.check("wolt")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_at_threshold(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=5, cooldown_seconds=120)
        for _ in range(5):
            await cb.record_failure("wolt")

        with pytest.raises(CircuitOpenError) as exc_info:
            await cb.check("wolt")
        assert exc_info.value.platform == "wolt"
        assert exc_info.value.retry_after > 0

    @pytest.mark.asyncio
    async def test_half_open_after_cooldown(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=2, cooldown_seconds=1)
        await cb.record_failure("wolt")
        await cb.record_failure("wolt")

        # Should be open
        with pytest.raises(CircuitOpenError):
            await cb.check("wolt")

        # Wait for cooldown
        import asyncio
        await asyncio.sleep(1.1)

        # Should be half-open now
        state = await cb.check("wolt")
        assert state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=2, cooldown_seconds=1)
        await cb.record_failure("wolt")
        await cb.record_failure("wolt")

        import asyncio
        await asyncio.sleep(1.1)

        # Half-open → success → closed
        await cb.check("wolt")
        await cb.record_success("wolt")

        state = await cb.check("wolt")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=2, cooldown_seconds=1)
        await cb.record_failure("wolt")
        await cb.record_failure("wolt")

        import asyncio
        await asyncio.sleep(1.1)

        # Half-open → failure → back to open
        await cb.check("wolt")
        await cb.record_failure("wolt")

        with pytest.raises(CircuitOpenError):
            await cb.check("wolt")

    @pytest.mark.asyncio
    async def test_success_resets_failures(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=5)
        for _ in range(4):
            await cb.record_failure("wolt")
        await cb.record_success("wolt")

        # 4 more failures should not open (counter was reset)
        for _ in range(4):
            await cb.record_failure("wolt")
        state = await cb.check("wolt")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_platforms_isolated(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=3)
        for _ in range(3):
            await cb.record_failure("wolt")

        # Wolt is open
        with pytest.raises(CircuitOpenError):
            await cb.check("wolt")

        # Pyszne is still closed
        state = await cb.check("pyszne")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_get_info(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=5, cooldown_seconds=120)
        await cb.record_failure("wolt")
        await cb.record_failure("wolt")

        info = await cb.get_info("wolt")
        assert info["platform"] == "wolt"
        assert info["state"] == "closed"
        assert info["failures"] == 2
        assert info["threshold"] == 5
        assert info["cooldown_seconds"] == 120

    @pytest.mark.asyncio
    async def test_force_close(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=2, cooldown_seconds=300)
        await cb.record_failure("wolt")
        await cb.record_failure("wolt")

        # Should be open
        with pytest.raises(CircuitOpenError):
            await cb.check("wolt")

        # Force close
        await cb.force_close("wolt")
        state = await cb.check("wolt")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_force_open(self, redis):
        cb = CircuitBreaker(redis, failure_threshold=100, cooldown_seconds=300)
        state = await cb.check("wolt")
        assert state == CircuitState.CLOSED

        await cb.force_open("wolt")
        with pytest.raises(CircuitOpenError):
            await cb.check("wolt")
