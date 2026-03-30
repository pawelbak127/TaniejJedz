"""
Geocoding service for entity resolution.

Primary: Nominatim (self-hosted via docker-compose --profile full)
Fallback: lat/lng already stored in platform_restaurants from adapters

Used to fill coordinates for restaurants where adapters returned 0,0
(Glovo returns no coordinates from HTML scraping).

Usage:
    geocoder = Geocoder()
    lat, lng = await geocoder.geocode("Marszałkowska 10, Warszawa")
    # or
    lat, lng = await geocoder.geocode_restaurant(platform_restaurant)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class GeoResult:
    """Geocoding result."""
    latitude: float
    longitude: float
    source: str  # "nominatim" | "adapter" | "city_center"
    display_name: str = ""


class Geocoder:
    """
    Geocoding service with Nominatim + fallback chain.

    Fallback order:
      1. Nominatim (self-hosted) — full address → lat/lng
      2. Adapter coordinates — already in platform_restaurants.latitude/longitude
      3. City center — last resort, uses city center coordinates
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._nominatim_url = settings.nominatim_url
        self._timeout = 5.0

    async def geocode(
        self,
        address: str,
        *,
        city: str = "Warszawa",
        country: str = "pl",
    ) -> GeoResult | None:
        """
        Geocode an address string via Nominatim.

        Returns GeoResult or None if geocoding fails.
        """
        if not address or not address.strip():
            return None

        query = f"{address}, {city}" if city and city not in address else address

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._nominatim_url}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "limit": "1",
                        "countrycodes": country,
                        "addressdetails": "0",
                    },
                    headers={"User-Agent": "TaniejJedz/1.0"},
                )

            if resp.status_code != 200:
                logger.warning("Nominatim HTTP %d for '%s'", resp.status_code, query)
                return None

            results = resp.json()
            if not results:
                logger.debug("Nominatim no results for '%s'", query)
                return None

            hit = results[0]
            lat = float(hit["lat"])
            lng = float(hit["lon"])
            display = hit.get("display_name", "")

            logger.debug("Nominatim OK: '%s' → %.5f, %.5f", query, lat, lng)
            return GeoResult(
                latitude=lat,
                longitude=lng,
                source="nominatim",
                display_name=display,
            )

        except httpx.TimeoutException:
            logger.warning("Nominatim timeout for '%s'", query)
            return None
        except httpx.ConnectError:
            logger.debug(
                "Nominatim not reachable at %s (run with --profile full)",
                self._nominatim_url,
            )
            return None
        except Exception:
            logger.exception("Nominatim error for '%s'", query)
            return None

    async def geocode_with_fallback(
        self,
        address: str | None,
        adapter_lat: float | None,
        adapter_lng: float | None,
        city_slug: str = "warszawa",
    ) -> GeoResult:
        """
        Geocode with full fallback chain.

        1. If adapter provided valid coordinates → use those
        2. Try Nominatim with address
        3. Fall back to city center

        Returns GeoResult always (never None).
        """
        # Fallback 1: adapter coordinates (most common, most reliable)
        if adapter_lat and adapter_lng and adapter_lat != 0.0 and adapter_lng != 0.0:
            return GeoResult(
                latitude=adapter_lat,
                longitude=adapter_lng,
                source="adapter",
            )

        # Fallback 2: Nominatim
        if address:
            city_name = _slug_to_city_name(city_slug)
            result = await self.geocode(address, city=city_name)
            if result is not None:
                return result

        # Fallback 3: city center
        center = _get_city_center(city_slug)
        logger.debug(
            "Geocoding fallback to city center: %s (%.4f, %.4f)",
            city_slug, center[0], center[1],
        )
        return GeoResult(
            latitude=center[0],
            longitude=center[1],
            source="city_center",
        )

    async def is_available(self) -> bool:
        """Check if Nominatim service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(
                    f"{self._nominatim_url}/status",
                    headers={"User-Agent": "TaniejJedz/1.0"},
                )
                return resp.status_code == 200
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

_CITY_CENTERS: dict[str, tuple[float, float]] = {
    "warszawa": (52.2297, 21.0122),
    "krakow": (50.0647, 19.9450),
    "wroclaw": (51.1079, 17.0385),
    "poznan": (52.4064, 16.9252),
    "gdansk": (54.3520, 18.6466),
    "lodz": (51.7592, 19.4560),
    "katowice": (50.2649, 19.0238),
    "lublin": (51.2465, 22.5684),
    "bialystok": (53.1325, 23.1688),
    "rzeszow": (50.0413, 21.9991),
    "szczecin": (53.4285, 14.5528),
    "kielce": (50.8661, 20.6286),
    "torun": (53.0138, 18.5984),
}


def _get_city_center(city_slug: str) -> tuple[float, float]:
    """Get city center coordinates by slug."""
    return _CITY_CENTERS.get(city_slug, (52.2297, 21.0122))


def _slug_to_city_name(slug: str) -> str:
    """Convert city slug to display name for geocoding queries."""
    names: dict[str, str] = {
        "warszawa": "Warszawa",
        "krakow": "Kraków",
        "wroclaw": "Wrocław",
        "poznan": "Poznań",
        "gdansk": "Gdańsk",
        "lodz": "Łódź",
        "katowice": "Katowice",
        "lublin": "Lublin",
        "bialystok": "Białystok",
        "rzeszow": "Rzeszów",
        "szczecin": "Szczecin",
        "kielce": "Kielce",
        "torun": "Toruń",
    }
    return names.get(slug, slug.title())
