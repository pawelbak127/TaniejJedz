"""
Budget Manager — daily request caps per platform with Redis counters.

Features:
  - Per-platform daily request budget (resets at midnight CET).
  - Three priority tiers: CRITICAL > NORMAL > LOW.
    LOW requests are rejected when budget ≥ 70%.
    NORMAL rejected at ≥ 90%.
    CRITICAL always allowed (for canary / health checks).
  - Redis-based atomic counters — safe for concurrent workers.
  - Alert callback at configurable threshold (default 90%).
  - Budget status introspection for dashboards.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from enum import IntEnum
from typing import Optional, Callable, Awaitable

from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)

# CET timezone for daily reset
_CET = timezone(timedelta(hours=1))


class Priority(IntEnum):
    """Request priority tier."""
    LOW = 0       # background pre-fetch, speculative
    NORMAL = 1    # user-triggered search result
    CRITICAL = 2  # canary checks, health probes


class BudgetExhaustedError(Exception):
    """Raised when daily budget for a platform is exhausted for the given priority."""

    def __init__(self, platform: str, used: int, cap: int, priority: Priority):
        self.platform = platform
        self.used = used
        self.cap = cap
        self.priority = priority
        super().__init__(
            f"Budget exhausted for {platform}: {used}/{cap} "
            f"(priority={priority.name})"
        )


class BudgetManager:
    """
    Tracks and enforces daily request budgets per platform.

    Usage:
        bm = BudgetManager(redis)
        await bm.acquire("wolt", Priority.NORMAL)     # raises BudgetExhaustedError
        await bm.acquire("pyszne", Priority.CRITICAL)  # always succeeds
        status = await bm.get_status("wolt")
    """

    # Priority tier thresholds (fraction of daily cap above which tier is rejected)
    _TIER_THRESHOLDS = {
        Priority.LOW: 0.70,
        Priority.NORMAL: 0.90,
        Priority.CRITICAL: 1.01,  # never auto-reject
    }

    def __init__(
        self,
        redis: Redis,
        *,
        alert_callback: Optional[Callable[[str, int, int], Awaitable[None]]] = None,
    ) -> None:
        self._redis = redis
        self._alert_callback = alert_callback
        self._settings = get_settings()
        self._caps: dict[str, int] = {
            "wolt": self._settings.budget_wolt_daily,
            "pyszne": self._settings.budget_pyszne_daily,
            "glovo": self._settings.budget_glovo_daily,
            "ubereats": self._settings.budget_ubereats_daily,
        }
        self._alert_threshold = self._settings.budget_alert_threshold

    # ── public API ─────────────────────────────────────────────────────

    async def acquire(
        self,
        platform: str,
        priority: Priority = Priority.NORMAL,
    ) -> int:
        """
        Consume one request from the platform's daily budget.

        Returns:
            The new counter value after increment.

        Raises:
            BudgetExhaustedError if the tier threshold is exceeded.
            ValueError if platform is unknown.
        """
        cap = self._caps.get(platform)
        if cap is None:
            raise ValueError(f"Unknown platform: {platform!r}. Known: {list(self._caps)}")

        key = self._counter_key(platform)
        new_count = await self._redis.incr(key)

        # Set TTL on first increment (expire at midnight CET)
        if new_count == 1:
            ttl = self._seconds_until_midnight_cet()
            await self._redis.expire(key, ttl)

        # Check tier threshold — CRITICAL is never rejected
        if priority != Priority.CRITICAL:
            threshold = self._TIER_THRESHOLDS[priority]
            if new_count > int(cap * threshold):
                # Decrement back — we didn't actually use the slot
                await self._redis.decr(key)
                raise BudgetExhaustedError(platform, new_count - 1, cap, priority)

        # Fire alert if crossing the global alert threshold
        alert_line = int(cap * self._alert_threshold)
        if new_count == alert_line:
            await self._fire_alert(platform, new_count, cap)

        return new_count

    async def get_status(self, platform: str) -> dict:
        """
        Return current budget status for a platform.

        Returns:
            {
                "platform": "wolt",
                "used": 1234,
                "cap": 5000,
                "remaining": 3766,
                "pct_used": 0.2468,
                "reset_in_seconds": 12345,
            }
        """
        cap = self._caps.get(platform, 0)
        key = self._counter_key(platform)
        used = int(await self._redis.get(key) or 0)
        ttl = await self._redis.ttl(key)
        return {
            "platform": platform,
            "used": used,
            "cap": cap,
            "remaining": max(0, cap - used),
            "pct_used": round(used / cap, 4) if cap else 0.0,
            "reset_in_seconds": max(0, ttl),
        }

    async def get_all_statuses(self) -> list[dict]:
        """Return budget status for all known platforms."""
        return [await self.get_status(p) for p in self._caps]

    def register_platform(self, platform: str, daily_cap: int) -> None:
        """Register or update a platform's daily cap at runtime."""
        self._caps[platform] = daily_cap

    # ── internals ──────────────────────────────────────────────────────

    def _counter_key(self, platform: str) -> str:
        today = datetime.now(_CET).strftime("%Y%m%d")
        return f"scraper:budget:{platform}:{today}"

    @staticmethod
    def _seconds_until_midnight_cet() -> int:
        now = datetime.now(_CET)
        midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        return int((midnight - now).total_seconds()) + 1  # +1 safety margin

    async def _fire_alert(self, platform: str, used: int, cap: int) -> None:
        logger.warning(
            "BUDGET ALERT: %s at %d/%d (%.0f%%)",
            platform, used, cap, (used / cap) * 100,
        )
        if self._alert_callback:
            try:
                await self._alert_callback(platform, used, cap)
            except Exception:
                logger.exception("Alert callback failed for %s", platform)
