"""
Circuit Breaker — per-platform fail-fast on repeated failures.

States:
  CLOSED   → normal operation, requests pass through.
  OPEN     → failures exceeded threshold, all requests fail-fast for cooldown period.
  HALF_OPEN → after cooldown, allow ONE probe request; success → CLOSED, failure → OPEN.

State is stored in Redis so all workers share the same circuit state.
Default: 5 consecutive failures → 120s cooldown (configurable via config.py).
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit is OPEN and requests are blocked."""

    def __init__(self, platform: str, retry_after: float):
        self.platform = platform
        self.retry_after = retry_after
        super().__init__(
            f"Circuit OPEN for {platform} — retry after {retry_after:.0f}s"
        )


class CircuitBreaker:
    """
    Per-platform circuit breaker backed by Redis.

    Usage:
        cb = CircuitBreaker(redis)

        # Before making a request:
        await cb.check("wolt")  # raises CircuitOpenError if open

        try:
            result = await fetch_from_wolt(...)
            await cb.record_success("wolt")
        except SomeError:
            await cb.record_failure("wolt")
            raise
    """

    KEY_PREFIX = "scraper:cb"

    def __init__(
        self,
        redis: Redis,
        *,
        failure_threshold: Optional[int] = None,
        cooldown_seconds: Optional[int] = None,
    ) -> None:
        self._redis = redis
        s = get_settings()
        self._failure_threshold = failure_threshold or s.cb_failure_threshold
        self._cooldown = cooldown_seconds or s.cb_cooldown_seconds

    # ── public API ─────────────────────────────────────────────────────

    async def check(self, platform: str) -> CircuitState:
        """
        Check if the circuit allows a request.

        Returns:
            Current CircuitState (CLOSED or HALF_OPEN).

        Raises:
            CircuitOpenError if the circuit is OPEN and cooldown has not elapsed.
        """
        state = await self._get_state(platform)

        if state == CircuitState.CLOSED:
            return state

        if state == CircuitState.OPEN:
            opened_at = await self._get_float(self._key(platform, "opened_at"))
            elapsed = time.time() - (opened_at or 0)
            if elapsed < self._cooldown:
                raise CircuitOpenError(platform, self._cooldown - elapsed)
            # Cooldown expired → transition to HALF_OPEN
            await self._set_state(platform, CircuitState.HALF_OPEN)
            logger.info("circuit %s → HALF_OPEN (probe allowed)", platform)
            return CircuitState.HALF_OPEN

        # HALF_OPEN — allow the probe request
        return state

    async def record_success(self, platform: str) -> None:
        """Record a successful request. Resets failure count; closes circuit."""
        state = await self._get_state(platform)
        await self._redis.set(self._key(platform, "failures"), 0)

        if state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
            await self._set_state(platform, CircuitState.CLOSED)
            logger.info("circuit %s → CLOSED (success)", platform)

    async def record_failure(self, platform: str) -> None:
        """
        Record a failed request. Increments failure counter.
        If threshold is reached → open the circuit.
        """
        key = self._key(platform, "failures")
        failures = await self._redis.incr(key)
        # Expire the failure counter after 2x cooldown to auto-heal
        await self._redis.expire(key, self._cooldown * 2)

        state = await self._get_state(platform)

        if state == CircuitState.HALF_OPEN:
            # Probe failed → back to OPEN
            await self._open_circuit(platform)
            logger.warning(
                "circuit %s → OPEN (half-open probe failed)", platform,
            )
            return

        if failures >= self._failure_threshold:
            await self._open_circuit(platform)
            logger.warning(
                "circuit %s → OPEN (failures=%d >= threshold=%d)",
                platform, failures, self._failure_threshold,
            )

    async def get_info(self, platform: str) -> dict:
        """Introspect circuit state for dashboards."""
        state = await self._get_state(platform)
        failures = int(await self._redis.get(self._key(platform, "failures")) or 0)
        opened_at = await self._get_float(self._key(platform, "opened_at"))
        return {
            "platform": platform,
            "state": state.value,
            "failures": failures,
            "threshold": self._failure_threshold,
            "cooldown_seconds": self._cooldown,
            "opened_at": opened_at,
        }

    async def force_close(self, platform: str) -> None:
        """Admin override: force circuit closed."""
        await self._redis.set(self._key(platform, "failures"), 0)
        await self._set_state(platform, CircuitState.CLOSED)
        logger.info("circuit %s FORCE CLOSED by admin", platform)

    async def force_open(self, platform: str) -> None:
        """Admin override: force circuit open."""
        await self._open_circuit(platform)
        logger.info("circuit %s FORCE OPENED by admin", platform)

    # ── internals ──────────────────────────────────────────────────────

    def _key(self, platform: str, suffix: str) -> str:
        return f"{self.KEY_PREFIX}:{platform}:{suffix}"

    async def _get_state(self, platform: str) -> CircuitState:
        raw = await self._redis.get(self._key(platform, "state"))
        if raw is None:
            return CircuitState.CLOSED
        try:
            return CircuitState(raw)
        except ValueError:
            return CircuitState.CLOSED

    async def _set_state(self, platform: str, state: CircuitState) -> None:
        await self._redis.set(self._key(platform, "state"), state.value)

    async def _open_circuit(self, platform: str) -> None:
        await self._set_state(platform, CircuitState.OPEN)
        await self._redis.set(
            self._key(platform, "opened_at"),
            str(time.time()),
        )

    async def _get_float(self, key: str) -> Optional[float]:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None
