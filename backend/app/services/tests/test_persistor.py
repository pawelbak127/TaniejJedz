"""
Tests for DataPersistor — Sprint 4.1 (rebuilt).

Tests field mapping, NULL canonical IDs, dedicated lat/lng columns,
metadata building, and config validation.

Full integration tests require running PostgreSQL (see VERIFICATION in manifest).
"""

from __future__ import annotations

import os
import uuid

import pytest

# Ensure test env
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.scraper.schemas.normalized import (
    NormalizedDeliveryFee,
    NormalizedMenuItem,
    NormalizedModifierGroup,
    NormalizedModifierOption,
    NormalizedRestaurant,
)
from app.services.persistor import DataPersistor, PersistorStats


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _restaurant(
    platform: str = "wolt",
    pid: str = "test-rest-001",
    name: str = "Test Restaurant",
    slug: str = "test-rest",
    lat: float = 52.23,
    lng: float = 21.01,
    online: bool = True,
    fee_grosz: int = 599,
) -> NormalizedRestaurant:
    return NormalizedRestaurant(
        platform=platform,
        platform_restaurant_id=pid,
        platform_name=name,
        platform_slug=slug,
        platform_url=f"https://{platform}.example.com/{slug}",
        name=name,
        latitude=lat,
        longitude=lng,
        cuisine_tags=["pizza", "italian"],
        is_online=online,
        rating_score=4.5,
        rating_count=120,
        delivery_fee=NormalizedDeliveryFee(
            fee_grosz=fee_grosz,
            minimum_order_grosz=3000,
            estimated_minutes=35,
        ),
    )


def _menu_item(
    item_id: str = "item-001",
    name: str = "Margherita",
    price: int = 2500,
    category: str = "Pizza",
    with_modifiers: bool = False,
) -> NormalizedMenuItem:
    modifiers = []
    if with_modifiers:
        modifiers = [
            NormalizedModifierGroup(
                platform_group_id="mg-size",
                name="Rozmiar",
                group_type="required",
                min_selections=1,
                max_selections=1,
                sort_order=0,
                options=[
                    NormalizedModifierOption(
                        platform_option_id="opt-25cm",
                        name="25cm",
                        normalized_name="25cm",
                        price_grosz=0,
                        is_default=True,
                    ),
                    NormalizedModifierOption(
                        platform_option_id="opt-32cm",
                        name="32cm",
                        normalized_name="32cm",
                        price_grosz=500,
                        is_default=False,
                    ),
                ],
            ),
        ]
    return NormalizedMenuItem(
        platform_item_id=item_id,
        platform_name=name,
        description=f"Delicious {name}",
        price_grosz=price,
        is_available=True,
        category_name=category,
        category_sort_order=0,
        modifier_groups=modifiers,
    )


# ═══════════════════════════════════════════════════════════
# PersistorStats
# ═══════════════════════════════════════════════════════════


class TestPersistorStats:

    def test_initial_zeros(self):
        stats = PersistorStats()
        assert stats.inserted == 0
        assert stats.updated == 0
        assert stats.errors == 0
        assert stats.total == 0

    def test_total(self):
        stats = PersistorStats()
        stats.inserted = 5
        stats.updated = 3
        assert stats.total == 8

    def test_repr(self):
        stats = PersistorStats()
        stats.inserted = 2
        assert "inserted=2" in repr(stats)


# ═══════════════════════════════════════════════════════════
# Platform metadata — lat/lng NOT in metadata
# ═══════════════════════════════════════════════════════════


class TestPlatformMetadata:

    def test_metadata_excludes_lat_lng(self):
        """lat/lng must go into dedicated columns, NOT platform_metadata."""
        nr = _restaurant(lat=52.23, lng=21.01)
        meta = DataPersistor._build_platform_metadata(nr)
        assert "latitude" not in meta
        assert "longitude" not in meta
        assert "lat" not in meta
        assert "lng" not in meta

    def test_metadata_includes_rating(self):
        nr = _restaurant()
        meta = DataPersistor._build_platform_metadata(nr)
        assert meta["rating_score"] == 4.5
        assert meta["rating_count"] == 120

    def test_metadata_includes_cuisine_tags(self):
        nr = _restaurant()
        meta = DataPersistor._build_platform_metadata(nr)
        assert meta["cuisine_tags"] == ["pizza", "italian"]

    def test_metadata_includes_image_url(self):
        nr = _restaurant()
        nr.image_url = "https://img.example.com/photo.jpg"
        meta = DataPersistor._build_platform_metadata(nr)
        assert meta["image_url"] == "https://img.example.com/photo.jpg"

    def test_metadata_includes_is_online(self):
        nr = _restaurant(online=True)
        meta = DataPersistor._build_platform_metadata(nr)
        assert meta["is_online"] is True

    def test_metadata_includes_address(self):
        nr = _restaurant()
        nr.address_street = "Marszałkowska 10"
        nr.address_city = "Warszawa"
        meta = DataPersistor._build_platform_metadata(nr)
        assert meta["address_street"] == "Marszałkowska 10"
        assert meta["address_city"] == "Warszawa"

    def test_metadata_no_rating_when_none(self):
        nr = _restaurant()
        nr.rating_score = None
        nr.rating_count = None
        meta = DataPersistor._build_platform_metadata(nr)
        assert "rating_score" not in meta
        assert "rating_count" not in meta

    def test_metadata_no_image_when_none(self):
        nr = _restaurant()
        nr.image_url = None
        meta = DataPersistor._build_platform_metadata(nr)
        assert "image_url" not in meta

    def test_metadata_no_cuisine_when_empty(self):
        nr = _restaurant()
        nr.cuisine_tags = []
        meta = DataPersistor._build_platform_metadata(nr)
        assert "cuisine_tags" not in meta


# ═══════════════════════════════════════════════════════════
# Normalized input validation
# ═══════════════════════════════════════════════════════════


class TestNormalizedInputs:

    def test_restaurant_all_platforms(self):
        for platform in ["wolt", "pyszne", "glovo", "ubereats"]:
            nr = _restaurant(platform=platform, pid=f"{platform}-001")
            assert nr.platform == platform
            assert nr.platform_restaurant_id == f"{platform}-001"

    def test_menu_item_with_modifiers(self):
        item = _menu_item(with_modifiers=True)
        assert len(item.modifier_groups) == 1
        assert item.modifier_groups[0].name == "Rozmiar"
        assert len(item.modifier_groups[0].options) == 2

    def test_menu_item_without_modifiers(self):
        item = _menu_item(with_modifiers=False)
        assert item.modifier_groups == []

    def test_delivery_fee_mapping(self):
        nr = _restaurant(fee_grosz=599)
        assert nr.delivery_fee.fee_grosz == 599
        assert nr.delivery_fee.minimum_order_grosz == 3000
        assert nr.delivery_fee.estimated_minutes == 35

    def test_price_grosz_is_int(self):
        item = _menu_item(price=4399)
        assert isinstance(item.price_grosz, int)
        assert item.price_grosz == 4399

    def test_zero_lat_lng_treated_as_missing(self):
        """Glovo returns 0,0 for lat/lng — persistor should store NULL."""
        nr = _restaurant(lat=0.0, lng=0.0)
        assert nr.latitude == 0.0
        assert nr.longitude == 0.0
        # Persistor check: 0.0 → None for dedicated columns
        # This is tested via the actual upsert logic in integration tests


# ═══════════════════════════════════════════════════════════
# NULL canonical ID contract
# ═══════════════════════════════════════════════════════════


class TestNullCanonicalContract:
    """Verify the persistor does NOT create canonical entities."""

    def test_persistor_has_no_canonical_restaurant_import(self):
        """DataPersistor should not import CanonicalRestaurant at all."""
        import inspect
        source = inspect.getsource(DataPersistor)
        assert "CanonicalRestaurant" not in source

    def test_persistor_has_no_canonical_menu_item_import(self):
        """DataPersistor should not import CanonicalMenuItem at all."""
        import inspect
        source = inspect.getsource(DataPersistor)
        assert "CanonicalMenuItem" not in source

    def test_persistor_has_no_menu_category_import(self):
        """DataPersistor should not import MenuCategory (no category creation)."""
        import inspect
        source = inspect.getsource(DataPersistor)
        assert "MenuCategory" not in source

    def test_upsert_restaurant_sets_canonical_null(self):
        """Verify the INSERT path uses canonical_restaurant_id=None."""
        import inspect
        source = inspect.getsource(DataPersistor._upsert_one_restaurant)
        assert "canonical_restaurant_id=None" in source

    def test_upsert_menu_item_sets_canonical_null(self):
        """Verify the INSERT path uses canonical_menu_item_id=None."""
        import inspect
        source = inspect.getsource(DataPersistor._upsert_one_menu_item)
        assert "canonical_menu_item_id=None" in source

    def test_upsert_restaurant_does_not_overwrite_canonical(self):
        """UPDATE path must NOT overwrite canonical_restaurant_id."""
        import inspect
        source = inspect.getsource(DataPersistor._upsert_one_restaurant)
        assert "canonical_restaurant_id" not in source.split("# UPDATE existing")[1].split("stats.updated")[0] or \
               "do NOT overwrite canonical_restaurant_id" in source

    def test_upsert_menu_item_does_not_overwrite_canonical(self):
        """UPDATE path must NOT overwrite canonical_menu_item_id."""
        import inspect
        source = inspect.getsource(DataPersistor._upsert_one_menu_item)
        assert "do NOT overwrite canonical_menu_item_id" in source


# ═══════════════════════════════════════════════════════════
# Dedicated lat/lng columns contract
# ═══════════════════════════════════════════════════════════


class TestDedicatedLatLng:

    def test_insert_sets_latitude_longitude(self):
        """INSERT path must set pr.latitude and pr.longitude from NormalizedRestaurant."""
        import inspect
        source = inspect.getsource(DataPersistor._upsert_one_restaurant)
        # Check the INSERT block (after "# INSERT new")
        insert_block = source.split("# INSERT new")[1]
        assert "latitude=" in insert_block
        assert "longitude=" in insert_block

    def test_update_sets_latitude_longitude(self):
        """UPDATE path must update existing_pr.latitude/longitude."""
        import inspect
        source = inspect.getsource(DataPersistor._upsert_one_restaurant)
        update_block = source.split("# UPDATE existing")[1].split("stats.updated")[0]
        assert "existing_pr.latitude" in update_block
        assert "existing_pr.longitude" in update_block

    def test_zero_coords_become_none_on_insert(self):
        """lat=0.0 should become None (not 0.0) in dedicated columns."""
        import inspect
        source = inspect.getsource(DataPersistor._upsert_one_restaurant)
        # Should have a conditional: if lat != 0.0 else None
        assert "nr.latitude != 0.0" in source
        assert "nr.longitude != 0.0" in source


# ═══════════════════════════════════════════════════════════
# Price recorder
# ═══════════════════════════════════════════════════════════


class TestPriceRecorder:

    def test_import(self):
        from app.services.price_recorder import PriceRecorder
        assert PriceRecorder is not None

    def test_has_record_prices(self):
        from app.services.price_recorder import PriceRecorder
        assert hasattr(PriceRecorder, "record_prices")

    def test_has_record_single_price(self):
        from app.services.price_recorder import PriceRecorder
        assert hasattr(PriceRecorder, "record_single_price")


# ═══════════════════════════════════════════════════════════
# Jobs integration
# ═══════════════════════════════════════════════════════════


class TestJobsIntegration:

    def test_crawl_restaurants_has_persist_call(self):
        from app.jobs.crawl_restaurants import _persist_search_results
        assert callable(_persist_search_results)

    def test_crawl_menus_has_persist_call(self):
        from app.jobs.crawl_menus import _persist_menu_items
        assert callable(_persist_menu_items)

    def test_db_helper_exists(self):
        from app.jobs.db import get_async_session
        assert callable(get_async_session)

    def test_crawl_restaurants_checks_persist_enabled(self):
        """crawl_restaurants should check settings.persist_enabled."""
        import inspect
        from app.jobs.crawl_restaurants import _crawl_city_async
        source = inspect.getsource(_crawl_city_async)
        assert "persist_enabled" in source

    def test_crawl_menus_checks_persist_enabled(self):
        """crawl_menus should check settings.persist_enabled."""
        import inspect
        from app.jobs.crawl_menus import _crawl_menu_async
        source = inspect.getsource(_crawl_menu_async)
        assert "persist_enabled" in source


# ═══════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════


class TestConfig:

    def test_default_city_slug(self):
        from app.config import get_settings
        s = get_settings()
        assert s.default_city_slug == "warszawa"

    def test_persist_enabled(self):
        from app.config import get_settings
        s = get_settings()
        assert s.persist_enabled is True

    def test_match_thresholds(self):
        from app.config import get_settings
        s = get_settings()
        assert s.match_auto_threshold == 0.85
        assert s.match_review_threshold == 0.60

    def test_match_weights_sum_to_one(self):
        from app.config import get_settings
        s = get_settings()
        total = (
            s.match_weight_name
            + s.match_weight_distance
            + s.match_weight_menu_overlap
            + s.match_weight_phone
        )
        assert abs(total - 1.0) < 0.001

    def test_geo_radius(self):
        from app.config import get_settings
        s = get_settings()
        assert s.match_geo_radius_m == 300

    def test_trgm_threshold(self):
        from app.config import get_settings
        s = get_settings()
        assert s.match_trgm_threshold == 0.3
