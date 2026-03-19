"""Tests for fingerprint module."""

from __future__ import annotations

import asyncio
import time
import pytest

from app.scraper.fingerprint import (
    build_headers,
    get_random_ua,
    human_delay,
    _USER_AGENTS,
)


class TestUserAgents:
    def test_pool_has_at_least_50(self):
        assert len(_USER_AGENTS) >= 50

    def test_all_are_strings(self):
        for ua in _USER_AGENTS:
            assert isinstance(ua, str)
            assert len(ua) > 20

    def test_has_desktop_and_mobile(self):
        mobile = [ua for ua in _USER_AGENTS if "Mobile" in ua]
        desktop = [ua for ua in _USER_AGENTS if "Mobile" not in ua]
        assert len(mobile) >= 10, "need ≥10 mobile UAs"
        assert len(desktop) >= 10, "need ≥10 desktop UAs"

    def test_has_multiple_browsers(self):
        chrome = any("Chrome" in ua and "Edg" not in ua for ua in _USER_AGENTS)
        firefox = any("Firefox" in ua for ua in _USER_AGENTS)
        safari = any("Safari" in ua and "Chrome" not in ua for ua in _USER_AGENTS)
        edge = any("Edg/" in ua for ua in _USER_AGENTS)
        assert chrome and firefox and safari and edge

    def test_get_random_ua_returns_from_pool(self):
        for _ in range(20):
            ua = get_random_ua()
            assert ua in _USER_AGENTS


class TestBuildHeaders:
    def test_has_required_headers(self):
        h = build_headers()
        assert "User-Agent" in h
        assert "Accept" in h
        assert "Accept-Language" in h
        assert "Accept-Encoding" in h

    def test_polish_locale(self):
        h = build_headers()
        assert "pl" in h["Accept-Language"]

    def test_referer_added(self):
        h = build_headers(referer="https://wolt.com/pl/pol/warszawa")
        assert h["Referer"] == "https://wolt.com/pl/pol/warszawa"

    def test_no_referer_by_default(self):
        h = build_headers()
        assert "Referer" not in h

    def test_extra_headers_merged(self):
        h = build_headers(extra={"X-Custom": "test123"})
        assert h["X-Custom"] == "test123"

    def test_mobile_forced(self):
        for _ in range(10):
            h = build_headers(mobile=True)
            assert "Mobile" in h["User-Agent"]

    def test_desktop_forced(self):
        for _ in range(10):
            h = build_headers(mobile=False)
            assert "Mobile" not in h["User-Agent"]

    def test_chrome_sec_headers(self):
        # Force a Chrome UA by trying multiple times
        for _ in range(50):
            h = build_headers()
            ua = h["User-Agent"]
            if "Chrome" in ua and "Edg" not in ua and "OPR" not in ua:
                assert "Sec-CH-UA" in h
                assert "Sec-Fetch-Dest" in h
                return
        pytest.skip("Didn't get Chrome UA in 50 tries")

    def test_randomization(self):
        uas = {build_headers()["User-Agent"] for _ in range(30)}
        assert len(uas) > 1, "Headers should randomise User-Agent"


class TestHumanDelay:
    @pytest.mark.asyncio
    async def test_delay_within_bounds(self):
        start = time.monotonic()
        await human_delay(0.05, 0.15)
        elapsed = time.monotonic() - start
        assert 0.04 <= elapsed <= 0.3  # small tolerance

    @pytest.mark.asyncio
    async def test_delay_respects_custom_range(self):
        start = time.monotonic()
        await human_delay(0.01, 0.05)
        elapsed = time.monotonic() - start
        assert elapsed < 0.2
