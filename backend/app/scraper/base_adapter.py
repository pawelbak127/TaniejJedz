"""
Base Adapter — abstract interface for all platform scrapers.

Every platform adapter (Wolt, Pyszne) must inherit from BaseAdapter
and implement the abstract methods. The base class wires up:
  - proxy rotation (ProxyManager)
  - fingerprinting (build_headers)
  - budget enforcement (BudgetManager)
  - circuit breaker (CircuitBreaker)
  - session cookies (SessionManager)
  - httpx client lifecycle

This ensures consistent error handling and infrastructure across adapters.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from redis.asyncio import Redis

from app.scraper.proxy_manager import ProxyManager
from app.scraper.fingerprint import build_headers, human_delay
from app.scraper.budget_manager import BudgetManager, Priority, BudgetExhaustedError
from app.scraper.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.scraper.session_manager import SessionManager
from app.scraper.schemas.normalized import (
    NormalizedDeliveryFee,
    NormalizedHours,
    NormalizedMenuItem,
    NormalizedPromotion,
    NormalizedRestaurant,
)
from app.config import get_settings

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Base exception for scraper errors."""
    pass


class PlatformUnavailableError(ScraperError):
    """Platform returned 5xx or is down."""
    pass


class RateLimitedError(ScraperError):
    """Platform returned 429."""
    pass


class BaseAdapter(ABC):
    """
    Abstract base for platform adapters.

    Subclasses must define:
        PLATFORM_NAME: str    — e.g. "wolt", "pyszne"
        BASE_URL: str         — e.g. "https://restaurant-api.wolt.com"

    And implement the data-fetching methods.
    """

    PLATFORM_NAME: str = ""
    BASE_URL: str = ""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._proxy = ProxyManager()
        self._budget = BudgetManager(redis)
        self._cb = CircuitBreaker(redis)
        self._sessions = SessionManager(redis)
        self._settings = get_settings()

    # ── protected fetch helper ─────────────────────────────────────────

    async def _fetch(
        self,
        method: str,
        url: str,
        *,
        priority: Priority = Priority.NORMAL,
        timeout: Optional[float] = None,
        referer: Optional[str] = None,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
        session_id: Optional[str] = None,
        add_delay: bool = True,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """
        Core HTTP fetch with full infrastructure wiring.

        1. Check circuit breaker.
        2. Acquire budget slot.
        3. Build headers + proxy.
        4. Make request with timeout.
        5. Record success/failure on circuit breaker.
        6. Return response.
        """
        # 1. Circuit breaker
        await self._cb.check(self.PLATFORM_NAME)

        # 2. Budget
        await self._budget.acquire(self.PLATFORM_NAME, priority)

        # 3. Headers + proxy
        headers = build_headers(referer=referer, extra=extra_headers)
        proxy_cfg = self._proxy.get_proxy()
        proxy_url = proxy_cfg.url if proxy_cfg else None

        # Load session cookies if applicable
        cookies = httpx.Cookies()
        if session_id:
            cookies = await self._sessions.load_cookies(
                self.PLATFORM_NAME, session_id,
            )

        # Optional human delay
        if add_delay:
            await human_delay(0.3, 1.5)

        # 4. Request
        effective_timeout = timeout or self._settings.scraper_timeout_realtime
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(
                proxy=proxy_url,
                cookies=cookies,
                timeout=httpx.Timeout(effective_timeout),
                follow_redirects=True,
            ) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    params=params,
                )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ProxyError) as exc:
            elapsed = (time.monotonic() - start) * 1000
            await self._cb.record_failure(self.PLATFORM_NAME)
            logger.warning(
                "%s fetch FAIL url=%s elapsed=%.0fms err=%s",
                self.PLATFORM_NAME, url, elapsed, exc,
            )
            raise PlatformUnavailableError(
                f"{self.PLATFORM_NAME} unreachable: {exc}"
            ) from exc

        elapsed = (time.monotonic() - start) * 1000

        # Save updated cookies if session
        if session_id:
            # Merge response cookies back
            for cookie in resp.cookies.jar:
                cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
            await self._sessions.save_cookies(
                self.PLATFORM_NAME, session_id, cookies,
            )

        # 5. Record outcome
        if resp.status_code == 429:
            await self._cb.record_failure(self.PLATFORM_NAME)
            raise RateLimitedError(
                f"{self.PLATFORM_NAME} rate-limited (429) on {url}"
            )

        if resp.status_code >= 500:
            await self._cb.record_failure(self.PLATFORM_NAME)
            raise PlatformUnavailableError(
                f"{self.PLATFORM_NAME} server error {resp.status_code} on {url}"
            )

        await self._cb.record_success(self.PLATFORM_NAME)

        logger.info(
            "%s fetch OK url=%s status=%d elapsed=%.0fms",
            self.PLATFORM_NAME, url, resp.status_code, elapsed,
        )
        return resp

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._fetch("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._fetch("POST", url, **kwargs)

    # ── abstract interface ─────────────────────────────────────────────

    @abstractmethod
    async def search_restaurants(
        self, lat: float, lng: float, radius_km: float,
    ) -> list[NormalizedRestaurant]:
        ...

    @abstractmethod
    async def get_menu(self, restaurant_id: str) -> list[NormalizedMenuItem]:
        ...

    @abstractmethod
    async def get_delivery_fee(
        self, restaurant_id: str, lat: float, lng: float,
    ) -> NormalizedDeliveryFee:
        ...

    @abstractmethod
    async def get_operating_hours(self, restaurant_id: str) -> list[NormalizedHours]:
        ...

    @abstractmethod
    async def get_promotions(self, restaurant_id: str) -> list[NormalizedPromotion]:
        ...
