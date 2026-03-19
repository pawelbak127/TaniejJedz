"""
Session Manager — per-platform cookie jars persisted in Redis.

Features:
  - Store / retrieve cookie jars (serialised as JSON) keyed by platform + session.
  - Automatic TTL expiry (default 1h, configurable via SESSION_COOKIE_TTL).
  - Transparent httpx.Cookies ↔ Redis serialisation.
  - Lock-free: multiple workers can read; last-writer-wins on update.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

import httpx
from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Persist and restore httpx cookie jars in Redis.

    Usage:
        sm = SessionManager(redis)

        # Restore cookies for a Pyszne session
        cookies = await sm.load_cookies("pyszne", "auth_session_1")
        client = httpx.AsyncClient(cookies=cookies)
        resp = await client.get(...)

        # After login flow, save updated cookies
        await sm.save_cookies("pyszne", "auth_session_1", client.cookies)
    """

    KEY_PREFIX = "scraper:session"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._ttl = get_settings().session_cookie_ttl

    # ── public API ─────────────────────────────────────────────────────

    async def save_cookies(
        self,
        platform: str,
        session_id: str,
        cookies: httpx.Cookies,
        *,
        ttl: Optional[int] = None,
    ) -> None:
        """
        Persist an httpx.Cookies jar to Redis.

        Args:
            platform:   "wolt" | "pyszne"
            session_id: Unique session identifier.
            cookies:    httpx.Cookies object.
            ttl:        Override default TTL (seconds).
        """
        key = self._key(platform, session_id)
        data = self._serialize_cookies(cookies)
        await self._redis.set(key, data, ex=ttl or self._ttl)
        logger.debug(
            "saved %d cookies for %s/%s (ttl=%ds)",
            len(cookies.jar), platform, session_id, ttl or self._ttl,
        )

    async def load_cookies(
        self,
        platform: str,
        session_id: str,
    ) -> httpx.Cookies:
        """
        Load cookie jar from Redis. Returns empty Cookies if not found.
        """
        key = self._key(platform, session_id)
        raw = await self._redis.get(key)
        if raw is None:
            logger.debug("no stored cookies for %s/%s", platform, session_id)
            return httpx.Cookies()

        cookies = self._deserialize_cookies(raw)
        logger.debug(
            "loaded %d cookies for %s/%s",
            len(cookies.jar), platform, session_id,
        )
        return cookies

    async def delete_session(self, platform: str, session_id: str) -> None:
        """Remove a stored session."""
        key = self._key(platform, session_id)
        await self._redis.delete(key)

    async def touch_session(
        self,
        platform: str,
        session_id: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Extend TTL of an existing session. Returns True if session exists.
        """
        key = self._key(platform, session_id)
        return await self._redis.expire(key, ttl or self._ttl)

    async def list_sessions(self, platform: str) -> list[str]:
        """List all active session IDs for a platform."""
        pattern = f"{self.KEY_PREFIX}:{platform}:*"
        keys = []
        async for key in self._redis.scan_iter(match=pattern, count=100):
            # Extract session_id from key
            session_id = key.rsplit(":", 1)[-1] if isinstance(key, str) else key.decode().rsplit(":", 1)[-1]
            keys.append(session_id)
        return keys

    # ── serialisation ──────────────────────────────────────────────────

    @staticmethod
    def _serialize_cookies(cookies: httpx.Cookies) -> str:
        """Convert httpx.Cookies to JSON string."""
        jar_data = []
        for cookie in cookies.jar:
            jar_data.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": cookie.secure,
                "expires": cookie.expires,
            })
        return json.dumps(jar_data)

    @staticmethod
    def _deserialize_cookies(raw: str) -> httpx.Cookies:
        """Restore httpx.Cookies from JSON string."""
        cookies = httpx.Cookies()
        try:
            jar_data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("corrupt cookie data, returning empty jar")
            return cookies

        now = time.time()
        for entry in jar_data:
            # Skip expired cookies
            expires = entry.get("expires")
            if expires is not None and expires < now:
                continue
            cookies.set(
                name=entry["name"],
                value=entry["value"],
                domain=entry.get("domain", ""),
                path=entry.get("path", "/"),
            )
        return cookies

    # ── helpers ────────────────────────────────────────────────────────

    def _key(self, platform: str, session_id: str) -> str:
        return f"{self.KEY_PREFIX}:{platform}:{session_id}"
