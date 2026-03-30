"""
Tests for entity_resolution.geocoding — Sprint 4.2.

Tests geocoding fallback chain, city center lookup, and error handling.
Nominatim tests use mock HTTP (no real Nominatim needed).
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.entity_resolution.geocoding import (
    GeoResult,
    Geocoder,
    _get_city_center,
    _slug_to_city_name,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ══════════════════════════════════════════════════════════════
# CITY CENTER LOOKUP
# ══════════════════════════════════════════════════════════════


class TestCityCenter:

    def test_warszawa(self):
        lat, lng = _get_city_center("warszawa")
        assert abs(lat - 52.23) < 0.01
        assert abs(lng - 21.01) < 0.01

    def test_krakow(self):
        lat, lng = _get_city_center("krakow")
        assert abs(lat - 50.06) < 0.01
        assert abs(lng - 19.94) < 0.01

    def test_unknown_defaults_to_warszawa(self):
        lat, lng = _get_city_center("unknown_city")
        assert abs(lat - 52.23) < 0.01

    def test_all_cities_have_valid_coords(self):
        from app.entity_resolution.geocoding import _CITY_CENTERS
        for slug, (lat, lng) in _CITY_CENTERS.items():
            assert 49.0 < lat < 55.0, f"{slug}: lat {lat} out of Poland range"
            assert 14.0 < lng < 24.0, f"{slug}: lng {lng} out of Poland range"


class TestSlugToName:

    def test_warszawa(self):
        assert _slug_to_city_name("warszawa") == "Warszawa"

    def test_krakow_with_diacritics(self):
        assert _slug_to_city_name("krakow") == "Kraków"

    def test_lodz_with_diacritics(self):
        assert _slug_to_city_name("lodz") == "Łódź"

    def test_unknown_titlecased(self):
        assert _slug_to_city_name("radom") == "Radom"


# ══════════════════════════════════════════════════════════════
# GeoResult
# ══════════════════════════════════════════════════════════════


class TestGeoResult:

    def test_fields(self):
        r = GeoResult(latitude=52.23, longitude=21.01, source="nominatim", display_name="Warszawa")
        assert r.latitude == 52.23
        assert r.source == "nominatim"

    def test_minimal(self):
        r = GeoResult(latitude=0.0, longitude=0.0, source="city_center")
        assert r.display_name == ""


# ══════════════════════════════════════════════════════════════
# GEOCODE WITH FALLBACK
# ══════════════════════════════════════════════════════════════


class TestGeocodeWithFallback:

    @pytest.mark.asyncio
    async def test_adapter_coordinates_used_first(self):
        """If adapter provides valid lat/lng, use those immediately."""
        geocoder = Geocoder()
        result = await geocoder.geocode_with_fallback(
            address="Marszałkowska 10",
            adapter_lat=52.2298,
            adapter_lng=21.0118,
            city_slug="warszawa",
        )
        assert result.source == "adapter"
        assert result.latitude == 52.2298
        assert result.longitude == 21.0118

    @pytest.mark.asyncio
    async def test_zero_coords_skipped(self):
        """Adapter coords of 0,0 (Glovo) should be skipped."""
        geocoder = Geocoder()
        result = await geocoder.geocode_with_fallback(
            address=None,
            adapter_lat=0.0,
            adapter_lng=0.0,
            city_slug="warszawa",
        )
        # Should fall through to city center (no Nominatim, no address)
        assert result.source == "city_center"
        assert abs(result.latitude - 52.23) < 0.01

    @pytest.mark.asyncio
    async def test_none_coords_skipped(self):
        """None adapter coords should be skipped."""
        geocoder = Geocoder()
        result = await geocoder.geocode_with_fallback(
            address=None,
            adapter_lat=None,
            adapter_lng=None,
            city_slug="krakow",
        )
        assert result.source == "city_center"
        assert abs(result.latitude - 50.06) < 0.01

    @pytest.mark.asyncio
    async def test_nominatim_used_when_no_adapter_coords(self):
        """If no adapter coords but address present, try Nominatim."""
        geocoder = Geocoder()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"lat": "52.2300", "lon": "21.0120", "display_name": "Marszałkowska, Warszawa"}
        ]

        with patch("app.entity_resolution.geocoding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await geocoder.geocode_with_fallback(
                address="Marszałkowska 10",
                adapter_lat=0.0,
                adapter_lng=0.0,
                city_slug="warszawa",
            )

        assert result.source == "nominatim"
        assert abs(result.latitude - 52.23) < 0.01

    @pytest.mark.asyncio
    async def test_city_center_fallback_on_all_failures(self):
        """If everything fails, use city center."""
        geocoder = Geocoder()

        with patch("app.entity_resolution.geocoding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Nominatim down"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await geocoder.geocode_with_fallback(
                address="Unknown Street 999",
                adapter_lat=0.0,
                adapter_lng=0.0,
                city_slug="warszawa",
            )

        assert result.source == "city_center"

    @pytest.mark.asyncio
    async def test_always_returns_result(self):
        """geocode_with_fallback must NEVER return None."""
        geocoder = Geocoder()
        result = await geocoder.geocode_with_fallback(
            address=None,
            adapter_lat=None,
            adapter_lng=None,
            city_slug="warszawa",
        )
        assert result is not None
        assert isinstance(result.latitude, float)
        assert isinstance(result.longitude, float)


# ══════════════════════════════════════════════════════════════
# GEOCODE (direct Nominatim)
# ══════════════════════════════════════════════════════════════


class TestGeocode:

    @pytest.mark.asyncio
    async def test_successful_geocode(self):
        geocoder = Geocoder()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"lat": "52.2300", "lon": "21.0120", "display_name": "Marszałkowska 10, Warszawa"}
        ]

        with patch("app.entity_resolution.geocoding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await geocoder.geocode("Marszałkowska 10")

        assert result is not None
        assert result.source == "nominatim"
        assert abs(result.latitude - 52.23) < 0.01

    @pytest.mark.asyncio
    async def test_no_results(self):
        geocoder = Geocoder()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("app.entity_resolution.geocoding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await geocoder.geocode("Nonexistent Address 99999")

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_address(self):
        geocoder = Geocoder()
        result = await geocoder.geocode("")
        assert result is None

    @pytest.mark.asyncio
    async def test_nominatim_http_error(self):
        geocoder = Geocoder()

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("app.entity_resolution.geocoding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await geocoder.geocode("Marszałkowska 10")

        assert result is None

    @pytest.mark.asyncio
    async def test_nominatim_connection_error(self):
        """Nominatim not running should return None gracefully."""
        geocoder = Geocoder()

        import httpx
        with patch("app.entity_resolution.geocoding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await geocoder.geocode("Marszałkowska 10")

        assert result is None
