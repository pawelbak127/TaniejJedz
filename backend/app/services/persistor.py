"""
DataPersistor — bridge NormalizedSchemas → PostgreSQL.

Sprint 4.1: Upsert platform data into existing SQLAlchemy models.

Key design:
  - platform_restaurants are saved with canonical_restaurant_id=NULL.
    RestaurantMatcher (Sprint 4.3) later links them to canonical entities.
  - platform_menu_items are saved with canonical_menu_item_id=NULL.
    MenuMatcher (Sprint 4.5) later links them.
  - lat/lng go into dedicated platform_restaurants.latitude/longitude columns
    (added by migration 0002_platform_rest_geo.py).
  - Rating, cuisine_tags, image_url, is_online → platform_metadata JSONB.
  - Modifier groups are replaced on each scrape (DELETE old → INSERT new).

Usage:
    async with session_factory() as session:
        persistor = DataPersistor(session)
        stats = await persistor.persist_restaurants(restaurants, "warszawa", "wolt")
        await session.commit()
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.city import City
from app.models.delivery import DeliveryFee
from app.models.menu import PlatformMenuItem
from app.models.modifier import ModifierGroup, ModifierOption
from app.models.restaurant import (
    OperatingHours,
    PlatformRestaurant,
)
from app.entity_resolution.normalizers import normalize_restaurant_name
from app.scraper.schemas.normalized import (
    NormalizedDeliveryFee,
    NormalizedHours,
    NormalizedMenuItem,
    NormalizedModifierGroup,
    NormalizedRestaurant,
)

logger = logging.getLogger(__name__)


class PersistorStats:
    """Tracks upsert statistics for a single persist call."""

    def __init__(self) -> None:
        self.inserted: int = 0
        self.updated: int = 0
        self.errors: int = 0
        self.skipped: int = 0

    def __repr__(self) -> str:
        return (
            f"PersistorStats(inserted={self.inserted}, updated={self.updated}, "
            f"errors={self.errors}, skipped={self.skipped})"
        )

    @property
    def total(self) -> int:
        return self.inserted + self.updated


class DataPersistor:
    """
    Persists normalized scraper output to PostgreSQL.

    Accepts an AsyncSession — caller is responsible for commit/rollback.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._city_cache: dict[str, uuid.UUID] = {}

    # ══════════════════════════════════════════════════════════
    # RESTAURANTS
    # ══════════════════════════════════════════════════════════

    async def persist_restaurants(
        self,
        restaurants: list[NormalizedRestaurant],
        city_slug: str,
        platform: str,
    ) -> PersistorStats:
        """
        Upsert platform_restaurants from normalized scraper output.

        Every platform_restaurant is saved with canonical_restaurant_id=NULL.
        The RestaurantMatcher in Sprint 4.3 will set this FK after matching.
        """
        stats = PersistorStats()
        now = datetime.now(timezone.utc)

        # Ensure city exists (for delivery fee context, not FK on platform_restaurants)
        await self._get_or_create_city(city_slug)

        for nr in restaurants:
            try:
                await self._upsert_one_restaurant(nr, platform, now, stats)
            except Exception:
                stats.errors += 1
                logger.exception(
                    "persist_restaurants error: platform=%s pid=%s name=%s",
                    platform, nr.platform_restaurant_id, nr.name,
                )

        await self._session.flush()
        logger.info(
            "persist_restaurants done: platform=%s city=%s %s",
            platform, city_slug, stats,
        )
        return stats

    async def _upsert_one_restaurant(
        self,
        nr: NormalizedRestaurant,
        platform: str,
        now: datetime,
        stats: PersistorStats,
    ) -> PlatformRestaurant:
        """Upsert a single platform_restaurant. No canonical creation."""
        # Look up existing by unique constraint (platform, platform_restaurant_id)
        result = await self._session.execute(
            select(PlatformRestaurant).where(
                and_(
                    PlatformRestaurant.platform == platform,
                    PlatformRestaurant.platform_restaurant_id == nr.platform_restaurant_id,
                )
            )
        )
        existing_pr = result.scalar_one_or_none()

        metadata = self._build_platform_metadata(nr)

        if existing_pr is not None:
            # UPDATE existing
            existing_pr.platform_name = nr.platform_name
            existing_pr.platform_slug = nr.platform_slug
            existing_pr.platform_url = nr.platform_url
            if nr.latitude != 0.0:
                existing_pr.latitude = nr.latitude
            if nr.longitude != 0.0:
                existing_pr.longitude = nr.longitude
            existing_pr.platform_metadata = metadata
            existing_pr.is_active = True
            existing_pr.last_scraped_at = now
            # NOTE: do NOT overwrite canonical_restaurant_id — matcher owns that FK

            stats.updated += 1
            return existing_pr

        # INSERT new — canonical_restaurant_id stays NULL
        pr = PlatformRestaurant(
            canonical_restaurant_id=None,
            platform=platform,
            platform_restaurant_id=nr.platform_restaurant_id,
            platform_name=nr.platform_name,
            platform_slug=nr.platform_slug,
            platform_url=nr.platform_url,
            latitude=nr.latitude if nr.latitude != 0.0 else None,
            longitude=nr.longitude if nr.longitude != 0.0 else None,
            match_confidence=0.0,
            platform_metadata=metadata,
            is_active=True,
            last_scraped_at=now,
        )
        self._session.add(pr)
        await self._session.flush()

        stats.inserted += 1
        return pr

    @staticmethod
    def _build_platform_metadata(nr: NormalizedRestaurant) -> dict[str, Any]:
        """Build platform_metadata JSONB from normalized data.

        Stores platform-specific fields that don't have dedicated columns:
        normalized_name (for matching), rating, cuisine_tags, image_url, address, is_online.
        lat/lng go into dedicated columns — NOT here.
        """
        meta: dict[str, Any] = {}
        # Normalized name for entity matching (Sprint 4.3)
        meta["normalized_name"] = normalize_restaurant_name(nr.name)
        if nr.rating_score is not None:
            meta["rating_score"] = nr.rating_score
        if nr.rating_count is not None:
            meta["rating_count"] = nr.rating_count
        if nr.cuisine_tags:
            meta["cuisine_tags"] = nr.cuisine_tags
        if nr.image_url:
            meta["image_url"] = nr.image_url
        if nr.address_street:
            meta["address_street"] = nr.address_street
        if nr.address_city:
            meta["address_city"] = nr.address_city
        meta["is_online"] = nr.is_online
        return meta

    # ══════════════════════════════════════════════════════════
    # MENU ITEMS
    # ══════════════════════════════════════════════════════════

    async def persist_menu(
        self,
        items: list[NormalizedMenuItem],
        platform_restaurant_id: uuid.UUID,
    ) -> PersistorStats:
        """
        Upsert platform_menu_items + modifier_groups + modifier_options.

        Every platform_menu_item is saved with canonical_menu_item_id=NULL.
        The MenuMatcher in Sprint 4.5 will link them to canonical entities.
        """
        stats = PersistorStats()
        now = datetime.now(timezone.utc)

        # Verify platform_restaurant exists
        result = await self._session.execute(
            select(PlatformRestaurant.id).where(
                PlatformRestaurant.id == platform_restaurant_id
            )
        )
        if result.scalar_one_or_none() is None:
            logger.error(
                "persist_menu: platform_restaurant_id=%s not found",
                platform_restaurant_id,
            )
            return stats

        for item in items:
            try:
                await self._upsert_one_menu_item(
                    item, platform_restaurant_id, now, stats
                )
            except Exception:
                stats.errors += 1
                logger.exception(
                    "persist_menu error: pr_id=%s item=%s",
                    platform_restaurant_id, item.platform_item_id,
                )

        await self._session.flush()
        logger.info(
            "persist_menu done: pr_id=%s %s",
            str(platform_restaurant_id)[:12], stats,
        )
        return stats

    async def _upsert_one_menu_item(
        self,
        item: NormalizedMenuItem,
        platform_restaurant_id: uuid.UUID,
        now: datetime,
        stats: PersistorStats,
    ) -> PlatformMenuItem:
        """Upsert a single platform_menu_item + modifiers. No canonical creation."""
        # Look up existing by (platform_restaurant_id, platform_item_id)
        result = await self._session.execute(
            select(PlatformMenuItem).where(
                and_(
                    PlatformMenuItem.platform_restaurant_id == platform_restaurant_id,
                    PlatformMenuItem.platform_item_id == item.platform_item_id,
                )
            )
        )
        existing_pmi = result.scalar_one_or_none()

        if existing_pmi is not None:
            # UPDATE
            existing_pmi.platform_name = item.platform_name
            existing_pmi.price_grosz = item.price_grosz
            existing_pmi.is_available = item.is_available
            existing_pmi.last_scraped_at = now
            # NOTE: do NOT overwrite canonical_menu_item_id — matcher owns that FK

            # Replace modifiers (delete old, insert new)
            await self._replace_modifiers(existing_pmi.id, item.modifier_groups)

            stats.updated += 1
            return existing_pmi

        # INSERT new — canonical_menu_item_id stays NULL
        pmi = PlatformMenuItem(
            canonical_menu_item_id=None,
            platform_restaurant_id=platform_restaurant_id,
            platform_item_id=item.platform_item_id,
            platform_name=item.platform_name,
            price_grosz=item.price_grosz,
            match_confidence=0.0,
            is_available=item.is_available,
            last_scraped_at=now,
        )
        self._session.add(pmi)
        await self._session.flush()

        # Insert modifiers
        await self._insert_modifiers(pmi.id, item.modifier_groups)

        stats.inserted += 1
        return pmi

    # ══════════════════════════════════════════════════════════
    # MODIFIERS
    # ══════════════════════════════════════════════════════════

    async def _replace_modifiers(
        self,
        platform_menu_item_id: uuid.UUID,
        groups: list[NormalizedModifierGroup],
    ) -> None:
        """Delete existing modifiers and insert fresh ones."""
        # Get existing modifier_group IDs for this item
        result = await self._session.execute(
            select(ModifierGroup.id).where(
                ModifierGroup.platform_menu_item_id == platform_menu_item_id
            )
        )
        group_ids = [row[0] for row in result.all()]

        # Delete options for each group, then delete groups
        if group_ids:
            await self._session.execute(
                delete(ModifierOption).where(
                    ModifierOption.modifier_group_id.in_(group_ids)
                )
            )
            await self._session.execute(
                delete(ModifierGroup).where(
                    ModifierGroup.platform_menu_item_id == platform_menu_item_id
                )
            )
            await self._session.flush()

        # Insert new
        await self._insert_modifiers(platform_menu_item_id, groups)

    async def _insert_modifiers(
        self,
        platform_menu_item_id: uuid.UUID,
        groups: list[NormalizedModifierGroup],
    ) -> None:
        """Insert modifier_groups + modifier_options."""
        for group in groups:
            mg = ModifierGroup(
                platform_menu_item_id=platform_menu_item_id,
                name=group.name,
                group_type=group.group_type,
                min_selections=group.min_selections,
                max_selections=group.max_selections,
                sort_order=group.sort_order,
                platform_group_id=group.platform_group_id,
            )
            self._session.add(mg)
            await self._session.flush()

            for option in group.options:
                mo = ModifierOption(
                    modifier_group_id=mg.id,
                    name=option.name,
                    normalized_name=option.normalized_name,
                    price_grosz=option.price_grosz,
                    is_default=option.is_default,
                    is_available=option.is_available,
                    platform_option_id=option.platform_option_id,
                )
                self._session.add(mo)

        if groups:
            await self._session.flush()

    # ══════════════════════════════════════════════════════════
    # DELIVERY FEES
    # ══════════════════════════════════════════════════════════

    async def persist_delivery_fee(
        self,
        fee: NormalizedDeliveryFee | None,
        platform_restaurant_id: uuid.UUID,
        geohash: str = "default",
    ) -> None:
        """Upsert delivery_fees for a platform restaurant."""
        if fee is None:
            return

        result = await self._session.execute(
            select(DeliveryFee).where(
                and_(
                    DeliveryFee.platform_restaurant_id == platform_restaurant_id,
                    DeliveryFee.geohash == geohash,
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.fee_grosz = fee.fee_grosz
            existing.min_order_grosz = fee.minimum_order_grosz or None
            existing.estimated_minutes = fee.estimated_minutes
            existing.free_delivery_above_grosz = fee.free_delivery_threshold_grosz
            existing.fetched_at = datetime.now(timezone.utc)
        else:
            df = DeliveryFee(
                platform_restaurant_id=platform_restaurant_id,
                geohash=geohash,
                fee_grosz=fee.fee_grosz,
                min_order_grosz=fee.minimum_order_grosz or None,
                estimated_minutes=fee.estimated_minutes,
                free_delivery_above_grosz=fee.free_delivery_threshold_grosz,
                fetched_at=datetime.now(timezone.utc),
            )
            self._session.add(df)

        await self._session.flush()

    # ══════════════════════════════════════════════════════════
    # OPERATING HOURS
    # ══════════════════════════════════════════════════════════

    async def persist_hours(
        self,
        hours: list[NormalizedHours],
        platform_restaurant_id: uuid.UUID,
    ) -> None:
        """Replace operating_hours for a platform restaurant."""
        if not hours:
            return

        # Delete existing
        await self._session.execute(
            delete(OperatingHours).where(
                OperatingHours.platform_restaurant_id == platform_restaurant_id
            )
        )

        for h in hours:
            oh = OperatingHours(
                platform_restaurant_id=platform_restaurant_id,
                day_of_week=h.day_of_week,
                open_time=h.open_time,
                close_time=h.close_time,
                is_closed=h.is_closed,
            )
            self._session.add(oh)

        await self._session.flush()

    # ══════════════════════════════════════════════════════════
    # CITY LOOKUP
    # ══════════════════════════════════════════════════════════

    async def _get_or_create_city(self, city_slug: str) -> uuid.UUID:
        """Get city_id by slug, or create from launch_cities config."""
        if city_slug in self._city_cache:
            return self._city_cache[city_slug]

        result = await self._session.execute(
            select(City).where(City.slug == city_slug)
        )
        city = result.scalar_one_or_none()

        if city is not None:
            self._city_cache[city_slug] = city.id
            return city.id

        # Create from config
        from app.config import get_settings

        settings = get_settings()
        city_config = next(
            (c for c in settings.launch_cities if c["slug"] == city_slug),
            None,
        )

        if city_config is None:
            city_config = {
                "name": city_slug.title(),
                "slug": city_slug,
                "center_lat": 52.2297,
                "center_lng": 21.0122,
                "radius_km": 15,
            }

        city = City(
            name=city_config["name"],
            slug=city_config["slug"],
            center_lat=city_config["center_lat"],
            center_lng=city_config["center_lng"],
            radius_km=city_config.get("radius_km", 15),
            is_active=True,
        )
        self._session.add(city)
        await self._session.flush()

        self._city_cache[city_slug] = city.id
        return city.id

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    async def get_platform_restaurant_id(
        self, platform: str, platform_restaurant_id: str,
    ) -> uuid.UUID | None:
        """Lookup PlatformRestaurant DB id by platform + external id."""
        result = await self._session.execute(
            select(PlatformRestaurant.id).where(
                and_(
                    PlatformRestaurant.platform == platform,
                    PlatformRestaurant.platform_restaurant_id == platform_restaurant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_platform_restaurant_by_slug(
        self, platform: str, slug: str,
    ) -> uuid.UUID | None:
        """Lookup PlatformRestaurant DB id by platform + platform_slug."""
        result = await self._session.execute(
            select(PlatformRestaurant.id).where(
                and_(
                    PlatformRestaurant.platform == platform,
                    PlatformRestaurant.platform_slug == slug,
                )
            )
        )
        return result.scalar_one_or_none()
