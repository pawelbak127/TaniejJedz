"""
Proxy Manager — Bright Data residential Polish IP rotation.

Features:
  - Per-request session ID rotation (new IP each request).
  - Sticky session mode for multi-step flows (e.g. auth + fetch).
  - httpx-compatible proxy URL builder.
  - Health check endpoint validation.
"""

from __future__ import annotations

import logging
import random
import string
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Resolved proxy configuration for a single request."""

    url: str
    session_id: str
    created_at: float = field(default_factory=time.time)


class ProxyManager:
    """
    Manages Bright Data residential proxy connections.

    Usage (rotating):
        pm = ProxyManager()
        proxy = pm.get_proxy()              # new IP each call
        async with httpx.AsyncClient(proxy=proxy.url) as client: ...

    Usage (sticky session — same IP for multi-step flow):
        pm = ProxyManager()
        session_id = pm.create_sticky_session()
        proxy = pm.get_proxy(session_id=session_id)  # same IP while session_id reused
    """

    def __init__(self) -> None:
        s = get_settings()
        self._enabled = s.proxy_enabled
        self._host = s.proxy_host
        self._port = s.proxy_port
        self._username = s.proxy_username
        self._password = s.proxy_password
        self._zone = s.proxy_zone
        self._country = s.proxy_country

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── public API ─────────────────────────────────────────────────────

    def get_proxy(self, *, session_id: Optional[str] = None) -> ProxyConfig | None:
        """
        Return a proxy URL for httpx, or None if proxy is disabled.

        Without session_id → rotating IP (new IP per request).
        With session_id   → sticky IP (same exit node for the session).
        """
        if not self._enabled:
            logger.debug("proxy DISABLED — direct connection")
            return None
        sid = session_id or self._random_session_id()
        url = self._build_url(sid)
        logger.debug("proxy session=%s rotating=%s", sid, session_id is None)
        return ProxyConfig(url=url, session_id=sid)

    def create_sticky_session(self) -> str:
        """Generate a session ID to reuse for sticky-IP flows."""
        return self._random_session_id(prefix="sticky")

    async def health_check(self) -> bool:
        """
        Quick connectivity test through the proxy.
        Returns True if we can reach the Bright Data lumtest endpoint with a Polish IP.
        Returns True immediately if proxy is disabled (not needed).
        """
        if not self._enabled:
            logger.info("proxy disabled — health check skipped")
            return True
        proxy = self.get_proxy()
        try:
            async with httpx.AsyncClient(
                proxy=proxy.url,
                timeout=httpx.Timeout(10.0),
            ) as client:
                resp = await client.get("https://lumtest.com/myip.json")
                data = resp.json()
                logger.info(
                    "proxy health OK  ip=%s country=%s",
                    data.get("ip"),
                    data.get("country"),
                )
                return data.get("country", "").upper() == "PL"
        except Exception:
            logger.exception("proxy health check FAILED")
            return False

    # ── internals ──────────────────────────────────────────────────────

    def _build_url(self, session_id: str) -> str:
        """
        Bright Data proxy URL format:
        http://user-zone-country-session:pass@host:port
        """
        user_part = (
            f"{self._username}"
            f"-zone-{self._zone}"
            f"-country-{self._country}"
            f"-session-{session_id}"
        )
        return f"http://{user_part}:{self._password}@{self._host}:{self._port}"

    @staticmethod
    def _random_session_id(prefix: str = "rot") -> str:
        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        return f"{prefix}_{rand}"
