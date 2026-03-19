"""Tests for ProxyManager."""

from __future__ import annotations

import re
import pytest

from app.scraper.proxy_manager import ProxyManager, ProxyConfig


@pytest.fixture
def pm(monkeypatch):
    monkeypatch.setenv("PROXY_ENABLED", "true")
    monkeypatch.setenv("PROXY_USERNAME", "brd_user")
    monkeypatch.setenv("PROXY_PASSWORD", "s3cret")
    monkeypatch.setenv("PROXY_ZONE", "residential_pl")
    monkeypatch.setenv("PROXY_COUNTRY", "pl")
    from app.config import get_settings
    get_settings.cache_clear()
    return ProxyManager()


@pytest.fixture
def pm_disabled(monkeypatch):
    """ProxyManager with proxy_enabled=False (dev mode)."""
    monkeypatch.setenv("PROXY_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    return ProxyManager()


class TestProxyManager:
    def test_get_proxy_returns_proxy_config(self, pm):
        proxy = pm.get_proxy()
        assert isinstance(proxy, ProxyConfig)
        assert proxy.url.startswith("http://")
        assert proxy.session_id.startswith("rot_")

    def test_rotating_proxy_different_sessions(self, pm):
        p1 = pm.get_proxy()
        p2 = pm.get_proxy()
        assert p1.session_id != p2.session_id
        assert p1.url != p2.url

    def test_sticky_session_same_url(self, pm):
        sid = pm.create_sticky_session()
        assert sid.startswith("sticky_")
        p1 = pm.get_proxy(session_id=sid)
        p2 = pm.get_proxy(session_id=sid)
        assert p1.url == p2.url

    def test_proxy_url_format(self, pm):
        proxy = pm.get_proxy()
        assert "brd_user" in proxy.url
        assert "s3cret" in proxy.url
        assert "residential_pl" in proxy.url
        assert "country-pl" in proxy.url
        assert "session-" in proxy.url
        assert "brd.superproxy.io:22225" in proxy.url

    def test_proxy_url_is_valid_url(self, pm):
        proxy = pm.get_proxy()
        pattern = r"^http://[^:]+:[^@]+@[^:]+:\d+$"
        assert re.match(pattern, proxy.url), f"Invalid proxy URL: {proxy.url}"


class TestProxyDisabled:
    """Dev mode — proxy_enabled=false, direct connections."""

    def test_get_proxy_returns_none(self, pm_disabled):
        assert pm_disabled.get_proxy() is None

    def test_enabled_property_false(self, pm_disabled):
        assert pm_disabled.enabled is False

    @pytest.mark.asyncio
    async def test_health_check_skips(self, pm_disabled):
        result = await pm_disabled.health_check()
        assert result is True  # no-op success
