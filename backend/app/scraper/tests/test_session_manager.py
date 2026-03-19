"""Tests for SessionManager."""

from __future__ import annotations

import pytest
import httpx

from app.scraper.session_manager import SessionManager


class TestSessionManager:

    @pytest.mark.asyncio
    async def test_save_and_load_cookies(self, redis):
        sm = SessionManager(redis)

        cookies = httpx.Cookies()
        cookies.set("session_id", "abc123", domain="wolt.com", path="/")
        cookies.set("_csrf", "tok456", domain="wolt.com", path="/")

        await sm.save_cookies("wolt", "sess_1", cookies)
        loaded = await sm.load_cookies("wolt", "sess_1")

        assert loaded.get("session_id") == "abc123"
        assert loaded.get("_csrf") == "tok456"

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_empty(self, redis):
        sm = SessionManager(redis)
        loaded = await sm.load_cookies("wolt", "nonexistent")
        assert len(loaded.jar) == 0

    @pytest.mark.asyncio
    async def test_delete_session(self, redis):
        sm = SessionManager(redis)

        cookies = httpx.Cookies()
        cookies.set("token", "xyz", domain="pyszne.pl")
        await sm.save_cookies("pyszne", "s1", cookies)

        await sm.delete_session("pyszne", "s1")
        loaded = await sm.load_cookies("pyszne", "s1")
        assert len(loaded.jar) == 0

    @pytest.mark.asyncio
    async def test_separate_platforms_isolated(self, redis):
        sm = SessionManager(redis)

        c1 = httpx.Cookies()
        c1.set("wolt_tok", "w1", domain="wolt.com")
        await sm.save_cookies("wolt", "s1", c1)

        c2 = httpx.Cookies()
        c2.set("pyszne_tok", "p1", domain="pyszne.pl")
        await sm.save_cookies("pyszne", "s1", c2)

        loaded_wolt = await sm.load_cookies("wolt", "s1")
        loaded_pyszne = await sm.load_cookies("pyszne", "s1")

        assert loaded_wolt.get("wolt_tok") == "w1"
        assert loaded_wolt.get("pyszne_tok") is None
        assert loaded_pyszne.get("pyszne_tok") == "p1"
        assert loaded_pyszne.get("wolt_tok") is None

    @pytest.mark.asyncio
    async def test_overwrite_session(self, redis):
        sm = SessionManager(redis)

        c1 = httpx.Cookies()
        c1.set("tok", "old_value", domain="wolt.com")
        await sm.save_cookies("wolt", "s1", c1)

        c2 = httpx.Cookies()
        c2.set("tok", "new_value", domain="wolt.com")
        await sm.save_cookies("wolt", "s1", c2)

        loaded = await sm.load_cookies("wolt", "s1")
        assert loaded.get("tok") == "new_value"

    @pytest.mark.asyncio
    async def test_list_sessions(self, redis):
        sm = SessionManager(redis)

        for sid in ["s1", "s2", "s3"]:
            cookies = httpx.Cookies()
            cookies.set("t", sid, domain="wolt.com")
            await sm.save_cookies("wolt", sid, cookies)

        sessions = await sm.list_sessions("wolt")
        assert set(sessions) == {"s1", "s2", "s3"}

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, redis):
        sm = SessionManager(redis)
        sessions = await sm.list_sessions("wolt")
        assert sessions == []

    @pytest.mark.asyncio
    async def test_touch_session_extends_ttl(self, redis):
        sm = SessionManager(redis)

        cookies = httpx.Cookies()
        cookies.set("t", "v", domain="wolt.com")
        await sm.save_cookies("wolt", "s1", cookies, ttl=60)

        result = await sm.touch_session("wolt", "s1", ttl=3600)
        assert result is True

        # Key should still exist
        loaded = await sm.load_cookies("wolt", "s1")
        assert loaded.get("t") == "v"

    @pytest.mark.asyncio
    async def test_touch_nonexistent_returns_false(self, redis):
        sm = SessionManager(redis)
        result = await sm.touch_session("wolt", "nope")
        assert result is False

    @pytest.mark.asyncio
    async def test_corrupt_data_returns_empty(self, redis):
        sm = SessionManager(redis)
        # Manually store garbage
        key = f"{sm.KEY_PREFIX}:wolt:corrupt"
        await redis.set(key, "not-json!!!")
        loaded = await sm.load_cookies("wolt", "corrupt")
        assert len(loaded.jar) == 0
