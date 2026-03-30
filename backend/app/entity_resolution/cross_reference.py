"""
Cross-reference discovery — expand Glovo/UberEats coverage.

Problem:
  Glovo returns ~50 restaurants (HTML SSR limit).
  UberEats returns ~43 (suggestion API limit).
  Wolt has ~1400, Pyszne ~700. Many exist on Glovo/UberEats but weren't discovered.

Solution:
  Take canonical_restaurant names (built from Wolt+Pyszne in Sprint 4.3).
  For each, search on Glovo/UberEats:
    - UberEats: getSearchSuggestionsV1(restaurant_name) → if match → persist
    - Glovo: generate slug "{name}-{city_short}" → fetch store page → if 200 → persist

  Then run matcher on newly discovered restaurants.

Usage:
    async with get_async_session() as session:
        xref = CrossReferenceDiscovery(session, redis)
        stats = await xref.discover_all("warszawa")
        await session.commit()

Budget: Uses Priority.LOW to avoid impacting user-facing requests.
Rate limiting: 1 request/second per platform (configurable).
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.city import City
from app.models.restaurant import CanonicalRestaurant, PlatformRestaurant
from app.services.persistor import DataPersistor

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryStats:
    """Statistics for a cross-reference discovery run."""
    canonical_checked: int = 0
    ubereats_found: int = 0
    ubereats_already_known: int = 0
    ubereats_errors: int = 0
    glovo_found: int = 0
    glovo_already_known: int = 0
    glovo_errors: int = 0

    @property
    def total_new(self) -> int:
        return self.ubereats_found + self.glovo_found

    def __repr__(self) -> str:
        return (
            f"DiscoveryStats(checked={self.canonical_checked}, "
            f"ue_found={self.ubereats_found}, ue_known={self.ubereats_already_known}, "
            f"gl_found={self.glovo_found}, gl_known={self.glovo_already_known})"
        )


class CrossReferenceDiscovery:
    """
    Discovers restaurants on Glovo/UberEats using names from canonical_restaurants.

    Flow:
      1. Load all canonical_restaurants for a city
      2. For each, check if already known on target platform
      3. If not → search on target platform
      4. If found → persist via DataPersistor
      5. Rate-limited: 1 req/sec per platform
    """

    # Delay between requests (seconds) to respect platform rate limits
    REQUEST_DELAY = 1.0

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis
        self._settings = get_settings()
        self._persistor = DataPersistor(session)

    async def discover_all(
        self,
        city_slug: str,
        *,
        platforms: list[str] | None = None,
        limit: int | None = None,
    ) -> DiscoveryStats:
        """
        Run cross-reference discovery for all canonical restaurants in a city.

        Args:
            city_slug: City to process.
            platforms: Which platforms to search. Default: ["ubereats", "glovo"].
            limit: Max canonical restaurants to check (for testing). None = all.
        """
        if platforms is None:
            platforms = ["ubereats", "glovo"]

        stats = DiscoveryStats()

        city_id = await self._get_city_id(city_slug)
        if city_id is None:
            logger.error("discover_all: city '%s' not found", city_slug)
            return stats

        # Load canonical restaurants
        canonicals = await self._get_canonicals(city_id, limit)
        stats.canonical_checked = len(canonicals)

        if not canonicals:
            logger.info("discover_all: no canonical restaurants in %s", city_slug)
            return stats

        logger.info(
            "discover_all START: city=%s canonicals=%d platforms=%s",
            city_slug, len(canonicals), platforms,
        )

        # Get known platform_restaurant_ids per platform
        known_ubereats = await self._get_known_pids("ubereats") if "ubereats" in platforms else set()
        known_glovo = await self._get_known_pids("glovo") if "glovo" in platforms else set()

        city_short = _get_city_short(city_slug)

        for canonical in canonicals:
            if "ubereats" in platforms:
                await self._discover_ubereats(
                    canonical, known_ubereats, city_slug, stats
                )

            if "glovo" in platforms:
                await self._discover_glovo(
                    canonical, known_glovo, city_slug, city_short, stats
                )

        logger.info("discover_all DONE: city=%s %s", city_slug, stats)
        return stats

    # ══════════════════════════════════════════════════════════
    # UBEREATS DISCOVERY
    # ══════════════════════════════════════════════════════════

    async def _discover_ubereats(
        self,
        canonical: CanonicalRestaurant,
        known_pids: set[str],
        city_slug: str,
        stats: DiscoveryStats,
    ) -> None:
        """Search UberEats for a canonical restaurant by name."""
        from app.scraper.adapters.ubereats import UberEatsAdapter
        from app.scraper.budget_manager import Priority

        try:
            adapter = UberEatsAdapter(self._redis)
            suggestions = await adapter._search_suggestions(
                canonical.name, priority=Priority.LOW,
            )

            for store in suggestions:
                if not store.uuid:
                    continue

                # Already known?
                if store.uuid in known_pids:
                    stats.ubereats_already_known += 1
                    continue

                # Name similarity check (avoid false positives)
                if not _names_match(canonical.name, store.title):
                    continue

                # Persist new platform_restaurant
                from app.scraper.schemas.normalized import NormalizedRestaurant
                nr = NormalizedRestaurant(
                    platform="ubereats",
                    platform_restaurant_id=store.uuid,
                    platform_name=store.title,
                    platform_slug=store.uuid,
                    platform_url=f"https://www.ubereats.com/pl-en/store/{store.slug}/{store.uuid}",
                    name=store.title,
                    latitude=0.0,
                    longitude=0.0,
                    cuisine_tags=store.cuisine_tags,
                    image_url=store.heroImageUrl,
                    is_online=store.isOrderable,
                )
                await self._persistor.persist_restaurants(
                    [nr], city_slug, "ubereats"
                )
                known_pids.add(store.uuid)
                stats.ubereats_found += 1

                logger.debug(
                    "xref UberEats: '%s' → '%s' (uuid=%s)",
                    canonical.name, store.title, store.uuid[:12],
                )
                break  # Take first matching store per canonical

            await asyncio.sleep(self.REQUEST_DELAY)

        except Exception:
            stats.ubereats_errors += 1
            logger.debug(
                "xref UberEats error for '%s': %s",
                canonical.name, exc_info=True,
            )

    # ══════════════════════════════════════════════════════════
    # GLOVO DISCOVERY
    # ══════════════════════════════════════════════════════════

    async def _discover_glovo(
        self,
        canonical: CanonicalRestaurant,
        known_pids: set[str],
        city_slug: str,
        city_short: str,
        stats: DiscoveryStats,
    ) -> None:
        """Try to find a Glovo store page by generating a slug from the name."""
        from app.scraper.adapters.glovo import GlovoAdapter
        from app.scraper.budget_manager import Priority

        # Generate candidate slugs
        slugs = _generate_glovo_slugs(canonical.name, city_short)

        for slug in slugs:
            if slug in known_pids:
                stats.glovo_already_known += 1
                return

        try:
            adapter = GlovoAdapter(self._redis)
            adapter._set_city(canonical.latitude, canonical.longitude)

            for slug in slugs:
                try:
                    store_data, menu_data = await adapter._fetch_store_page(
                        slug, priority=Priority.LOW,
                    )

                    if store_data and store_data.get("name"):
                        # Verify it's actually the right restaurant
                        if not _names_match(canonical.name, store_data["name"]):
                            continue

                        # Persist
                        from app.scraper.schemas.normalized import (
                            NormalizedRestaurant,
                            NormalizedDeliveryFee,
                        )
                        fee_info = store_data.get("deliveryFeeInfo", {})
                        fee_grosz = int(round(fee_info.get("fee", 0) * 100)) if fee_info else 0

                        nr = NormalizedRestaurant(
                            platform="glovo",
                            platform_restaurant_id=slug,
                            platform_name=store_data["name"],
                            platform_slug=slug,
                            platform_url=f"https://glovoapp.com/pl/pl/{city_slug}/stores/{slug}",
                            name=store_data["name"],
                            latitude=0.0,
                            longitude=0.0,
                            is_online=store_data.get("open", False),
                            delivery_fee=NormalizedDeliveryFee(fee_grosz=fee_grosz) if fee_grosz else None,
                        )
                        await self._persistor.persist_restaurants(
                            [nr], city_slug, "glovo"
                        )
                        known_pids.add(slug)
                        stats.glovo_found += 1

                        logger.debug(
                            "xref Glovo: '%s' → slug '%s' (store: %s)",
                            canonical.name, slug, store_data["name"],
                        )
                        await asyncio.sleep(self.REQUEST_DELAY)
                        return

                except Exception:
                    pass  # Slug didn't work, try next

            await asyncio.sleep(self.REQUEST_DELAY * 0.5)

        except Exception:
            stats.glovo_errors += 1
            logger.debug(
                "xref Glovo error for '%s'", canonical.name, exc_info=True,
            )

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    async def _get_city_id(self, city_slug: str) -> uuid.UUID | None:
        result = await self._session.execute(
            select(City.id).where(City.slug == city_slug)
        )
        return result.scalar_one_or_none()

    async def _get_canonicals(
        self, city_id: uuid.UUID, limit: int | None = None,
    ) -> list[CanonicalRestaurant]:
        """Get canonical restaurants ordered by name (deterministic)."""
        stmt = (
            select(CanonicalRestaurant)
            .where(
                and_(
                    CanonicalRestaurant.city_id == city_id,
                    CanonicalRestaurant.is_active.is_(True),
                )
            )
            .order_by(CanonicalRestaurant.name)
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _get_known_pids(self, platform: str) -> set[str]:
        """Get all known platform_restaurant_ids for a platform."""
        result = await self._session.execute(
            select(PlatformRestaurant.platform_restaurant_id).where(
                PlatformRestaurant.platform == platform
            )
        )
        return {row[0] for row in result.all()}


# ══════════════════════════════════════════════════════════════
# SLUG GENERATION (Glovo)
# ══════════════════════════════════════════════════════════════


def _generate_glovo_slugs(name: str, city_short: str) -> list[str]:
    """
    Generate candidate Glovo store slugs from a restaurant name.

    Glovo slugs follow pattern: "{name}-{city_short}"
    e.g. "KFC" in Warszawa → "kfc-waw"
         "Pizza Hut" → "pizza-hut-waw"
         "McDonald's" → "mcdonald-s-waw"

    Returns up to 3 slug candidates (with/without city suffix).
    """
    # Lowercase
    slug_base = name.lower().strip()
    # Replace ł explicitly before NFKD
    slug_base = slug_base.replace("ł", "l").replace("Ł", "L")
    # Remove diacritics
    nfkd = unicodedata.normalize("NFKD", slug_base)
    slug_base = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Replace non-alphanumeric with dashes
    slug_base = re.sub(r"[^a-z0-9]+", "-", slug_base)
    # Collapse multiple dashes, strip leading/trailing
    slug_base = re.sub(r"-+", "-", slug_base).strip("-")

    if not slug_base:
        return []

    slugs = []
    # With city suffix (most common Glovo pattern)
    slugs.append(f"{slug_base}-{city_short}")
    # Without city suffix (some stores)
    slugs.append(slug_base)
    # With trailing number disambiguation (e.g. kfc2-waw)
    if not slug_base[-1].isdigit():
        slugs.append(f"{slug_base}2-{city_short}")

    return slugs


# ══════════════════════════════════════════════════════════════
# NAME MATCHING
# ══════════════════════════════════════════════════════════════


def _names_match(canonical_name: str, platform_name: str) -> bool:
    """
    Quick name similarity check for cross-reference validation.

    Uses rapidfuzz token_sort_ratio with a lower threshold (0.50)
    than entity matching — we just want to avoid obvious false positives
    like "KFC" matching "Kebab Fresh Corner".
    """
    from app.entity_resolution.matching_utils import name_similarity
    from app.entity_resolution.normalizers import normalize_restaurant_name

    norm_a = normalize_restaurant_name(canonical_name)
    norm_b = normalize_restaurant_name(platform_name)

    if not norm_a or not norm_b:
        return False

    return name_similarity(norm_a, norm_b) >= 0.50


def _get_city_short(city_slug: str) -> str:
    """Map city slug to Glovo short code."""
    mapping = {
        "warszawa": "waw",
        "krakow": "kra",
        "wroclaw": "wro",
        "poznan": "poz",
        "gdansk": "gdn",
        "lodz": "ldz",
        "katowice": "ktw",
        "lublin": "lub",
        "bialystok": "bia",
        "rzeszow": "rze",
        "szczecin": "szz",
        "kielce": "kie",
        "torun": "tor",
    }
    return mapping.get(city_slug, city_slug[:3])
