"""Uber Eats contract tests — real API structure (March 2026)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scraper.adapters.ubereats_schemas import (
    UberEatsCatalogItem,
    UberEatsStoreData,
    UberEatsStoreResponse,
)
from app.scraper.adapters.ubereats import UberEatsAdapter

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def store_response() -> dict:
    return json.loads((FIXTURES / "ubereats_store.json").read_text(encoding="utf-8"))


@pytest.fixture
def store_data(store_response) -> UberEatsStoreData:
    return UberEatsStoreResponse.model_validate(store_response).data


@pytest.fixture
def adapter(redis):
    a = UberEatsAdapter(redis)
    a._budget.register_platform("ubereats", 100_000)
    return a


# ═══════════════════════════════════════════════════════════
# STORE DETAIL
# ═══════════════════════════════════════════════════════════


class TestStoreDetail:

    def test_parses(self, store_data):
        assert store_data.uuid == "6aaa3cb9-03a0-5d35-a00a-500f982d2120"
        assert store_data.title == "Bollywood Lounge Restaurant"
        assert store_data.isOpen is True

    def test_location(self, store_data):
        assert store_data.location.city == "Warszawa"
        assert store_data.location.latitude == pytest.approx(52.23, abs=0.01)
        assert store_data.location.longitude == pytest.approx(21.01, abs=0.01)

    def test_rating(self, store_data):
        assert store_data.rating.ratingValue == pytest.approx(4.9)
        assert store_data.rating.count == 10

    def test_cuisines(self, store_data):
        assert "Indian" in store_data.cuisineList

    def test_service_fee(self, store_data):
        assert store_data.service_fee_grosz == 399

    def test_eta(self, store_data):
        assert store_data.delivery_eta_text == "30–40 Min"


class TestStoreNormalization:

    def test_basic(self, store_data, adapter):
        n = adapter._normalize_store(store_data)
        assert n.platform == "ubereats"
        assert n.name == "Bollywood Lounge Restaurant"
        assert n.is_online is True

    def test_platform_slug_is_uuid(self, store_data, adapter):
        """platform_slug must be UUID — orchestrator passes it to get_menu()."""
        n = adapter._normalize_store(store_data)
        assert n.platform_slug == "6aaa3cb9-03a0-5d35-a00a-500f982d2120"
        assert n.platform_slug == n.platform_restaurant_id

    def test_location(self, store_data, adapter):
        n = adapter._normalize_store(store_data)
        assert n.latitude == pytest.approx(52.23, abs=0.01)
        assert n.address_street == "Nowogrodzka 22"
        assert n.address_city == "Warszawa"

    def test_rating(self, store_data, adapter):
        n = adapter._normalize_store(store_data)
        assert n.rating_score == pytest.approx(4.9)
        assert n.rating_count == 10

    def test_delivery_fee(self, store_data, adapter):
        n = adapter._normalize_store(store_data)
        assert n.delivery_fee.fee_grosz == 399

    def test_url_contains_both_slug_and_uuid(self, store_data, adapter):
        n = adapter._normalize_store(store_data)
        assert "ubereats.com" in n.platform_url
        # URL uses human slug for readability + UUID for identification
        assert "6aaa3cb9-03a0-5d35-a00a-500f982d2120" in n.platform_url


# ═══════════════════════════════════════════════════════════
# MENU PARSING
# ═══════════════════════════════════════════════════════════


class TestMenuParsing:

    def test_all_items(self, store_data):
        items = store_data.all_items()
        assert len(items) == 5  # 2+2+1

    def test_dedup(self, store_data):
        items = store_data.all_items()
        uuids = [item.uuid for _, item in items]
        assert len(uuids) == len(set(uuids))

    def test_section_titles(self, store_data):
        items = store_data.all_items()
        categories = set(cat for cat, _ in items)
        assert "Indyjskie Przekąski" in categories
        assert "Dania z Kurczakiem" in categories
        assert "Napoje" in categories

    def test_price_already_grosz(self, store_data):
        """Price is already in grosz — 2200 = 22.00 PLN."""
        items = store_data.all_items()
        hummus = next(item for _, item in items if "Hummus" in item.title)
        assert hummus.price == 2200
        assert hummus.price_grosz == 2200

    def test_butter_chicken_price(self, store_data):
        items = store_data.all_items()
        bc = next(item for _, item in items if "Butter Chicken" in item.title)
        assert bc.price_grosz == 5600

    def test_sold_out(self, store_data):
        items = store_data.all_items()
        tikka = next(item for _, item in items if "Tikka" in item.title)
        assert tikka.isSoldOut is True
        assert tikka.isAvailable is False

    def test_has_customizations_flag(self, store_data):
        items = store_data.all_items()
        bc = next(item for _, item in items if "Butter Chicken" in item.title)
        assert bc.hasCustomizations is True
        hummus = next(item for _, item in items if "Hummus" in item.title)
        assert hummus.hasCustomizations is False


# ═══════════════════════════════════════════════════════════
# MENU NORMALIZATION
# ═══════════════════════════════════════════════════════════


class TestMenuNormalization:

    def _items(self, store_data, adapter):
        return [
            adapter._normalize_item(item, cat, idx)
            for idx, (cat, item) in enumerate(store_data.all_items())
        ]

    def test_total(self, store_data, adapter):
        assert len(self._items(store_data, adapter)) == 5

    def test_price(self, store_data, adapter):
        items = self._items(store_data, adapter)
        hummus = next(i for i in items if "Hummus" in i.platform_name)
        assert hummus.price_grosz == 2200

    def test_availability(self, store_data, adapter):
        items = self._items(store_data, adapter)
        tikka = next(i for i in items if "Tikka" in i.platform_name)
        assert tikka.is_available is False

    def test_category(self, store_data, adapter):
        items = self._items(store_data, adapter)
        hummus = next(i for i in items if "Hummus" in i.platform_name)
        assert hummus.category_name == "Indyjskie Przekąski"

    def test_no_modifiers(self, store_data, adapter):
        """Modifiers not available in listing endpoint."""
        items = self._items(store_data, adapter)
        for item in items:
            assert item.modifier_groups == []

    def test_description(self, store_data, adapter):
        items = self._items(store_data, adapter)
        bc = next(i for i in items if "Butter Chicken" in i.platform_name)
        assert "tandoor" in bc.description


# ═══════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_empty_catalog(self):
        store = UberEatsStoreData.model_validate({"uuid": "x", "catalogSectionsMap": {}})
        assert store.all_items() == []

    def test_no_rating(self):
        store = UberEatsStoreData.model_validate({"uuid": "x"})
        assert store.service_fee_grosz == 0

    def test_review_count_string(self):
        from app.scraper.adapters.ubereats_schemas import UberEatsRating
        r = UberEatsRating(ratingValue=4.5, reviewCount="1,234")
        assert r.count == 1234

    def test_review_count_with_plus(self):
        from app.scraper.adapters.ubereats_schemas import UberEatsRating
        r = UberEatsRating(ratingValue=4.0, reviewCount="500+")
        assert r.count == 500

    def test_extra_fields_allowed(self):
        store = UberEatsStoreData.model_validate({"uuid": "x", "unknownField": 42})
        assert store.uuid == "x"

    def test_item_price_is_grosz(self):
        item = UberEatsCatalogItem.model_validate({"uuid": "x", "title": "T", "price": 3499})
        assert item.price_grosz == 3499  # Already grosz!


# ═══════════════════════════════════════════════════════════
# SEARCH SUGGESTIONS
# ═══════════════════════════════════════════════════════════


class TestSearchSuggestions:

    def test_parses_store_suggestion(self):
        from app.scraper.adapters.ubereats_schemas import UberEatsSuggestionsResponse
        data = {
            "data": [
                {
                    "type": "store",
                    "title": "KFC Wadowicka",
                    "store": {
                        "uuid": "235b3727-test",
                        "title": "KFC Wadowicka",
                        "slug": "kfc-wadowicka",
                        "categories": [None, "American", "BBQ"],
                        "isOrderable": True,
                    },
                },
                {"type": "item", "title": "kfc chicken"},
                {"type": "search", "title": "Search for KFC"},
            ],
            "status": "success",
        }
        resp = UberEatsSuggestionsResponse.model_validate(data)
        stores = resp.store_results()
        assert len(stores) == 1
        assert stores[0].uuid == "235b3727-test"
        assert stores[0].title == "KFC Wadowicka"
        assert stores[0].cuisine_tags == ["American", "BBQ"]  # None filtered

    def test_empty_suggestions(self):
        from app.scraper.adapters.ubereats_schemas import UberEatsSuggestionsResponse
        resp = UberEatsSuggestionsResponse.model_validate({"data": [], "status": "success"})
        assert resp.store_results() == []

    def test_suggestion_normalization_slug_is_uuid(self, adapter):
        """platform_slug must be UUID for get_menu() compatibility."""
        from app.scraper.adapters.ubereats_schemas import UberEatsSuggestionStore
        store = UberEatsSuggestionStore(
            uuid="abc-123-def", title="Test Restaurant", slug="test-rest",
            categories=["Pizza", None, "Italian"], isOrderable=True,
            heroImageUrl="https://img.uber.com/test.jpg",
        )
        n = adapter._normalize_suggestion(store)
        assert n.platform == "ubereats"
        assert n.platform_slug == "abc-123-def"  # UUID, not human slug
        assert n.platform_restaurant_id == "abc-123-def"
        assert n.name == "Test Restaurant"
        assert n.is_online is True
        assert "Pizza" in n.cuisine_tags
        assert "Italian" in n.cuisine_tags
        # URL contains both human slug and UUID
        assert "test-rest" in n.platform_url
        assert "abc-123-def" in n.platform_url

    def test_query_pool_size(self):
        """Verify we have enough queries for good coverage."""
        from app.scraper.adapters.ubereats import _SEARCH_QUERIES
        assert len(_SEARCH_QUERIES) >= 20
        assert len(_SEARCH_QUERIES) <= 30  # Don't exceed timeout budget
