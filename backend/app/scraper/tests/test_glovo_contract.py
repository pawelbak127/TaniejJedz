"""Glovo contract tests — real API structure (March 2026)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scraper.adapters.glovo_schemas import (
    GlovoMenuResponse,
    GlovoProduct,
    GlovoStore,
)
from app.scraper.adapters.glovo import GlovoAdapter
from app.scraper.schemas.normalized import NormalizedMenuItem, NormalizedRestaurant

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def store_json() -> dict:
    return json.loads((FIXTURES / "glovo_store.json").read_text(encoding="utf-8"))


@pytest.fixture
def menu_json() -> dict:
    return json.loads((FIXTURES / "glovo_menu.json").read_text(encoding="utf-8"))


@pytest.fixture
def adapter(redis):
    a = GlovoAdapter(redis)
    a._budget.register_platform("glovo", 100_000)
    return a


# ═══════════════════════════════════════════════════════════
# STORE DETAIL
# ═══════════════════════════════════════════════════════════


class TestStoreDetail:

    def test_parses(self, store_json):
        store = GlovoStore.model_validate(store_json)
        assert store.id == 60309
        assert store.slug == "kfc-waw"
        assert store.name == "KFC"

    def test_open_status(self, store_json):
        store = GlovoStore.model_validate(store_json)
        assert store.is_online is True
        assert store.open is True

    def test_delivery_fee(self, store_json):
        store = GlovoStore.model_validate(store_json)
        assert store.deliveryFeeInfo.fee == 1.99
        assert store.delivery_fee_grosz == 199

    def test_service_fee(self, store_json):
        store = GlovoStore.model_validate(store_json)
        assert store.service_fee_grosz == 199

    def test_cuisine_tags(self, store_json):
        store = GlovoStore.model_validate(store_json)
        tags = store.cuisine_tags
        assert "Amerykańskie" in tags
        assert "Burgery" in tags

    def test_address(self, store_json):
        store = GlovoStore.model_validate(store_json)
        assert "Widok 26" in store.address

    def test_closed_store(self):
        store = GlovoStore.model_validate({
            "id": 1, "slug": "closed",
            "availability": {"status": "CLOSED"},
            "open": False, "enabled": True,
        })
        assert store.is_online is False


class TestStoreNormalization:

    def test_basic(self, store_json, adapter):
        store = GlovoStore.model_validate(store_json)
        n = adapter._normalize_store(store)
        assert isinstance(n, NormalizedRestaurant)
        assert n.platform == "glovo"
        assert n.platform_slug == "kfc-waw"
        assert n.name == "KFC"
        assert n.is_online is True

    def test_delivery_fee(self, store_json, adapter):
        store = GlovoStore.model_validate(store_json)
        n = adapter._normalize_store(store)
        assert n.delivery_fee.fee_grosz == 199

    def test_platform_url(self, store_json, adapter):
        store = GlovoStore.model_validate(store_json)
        n = adapter._normalize_store(store)
        assert "glovoapp.com" in n.platform_url
        assert "kfc-waw" in n.platform_url

    def test_address_newlines_replaced(self, store_json, adapter):
        store = GlovoStore.model_validate(store_json)
        n = adapter._normalize_store(store)
        assert "\n" not in n.address_street
        assert "Widok 26" in n.address_street


# ═══════════════════════════════════════════════════════════
# MENU PARSING
# ═══════════════════════════════════════════════════════════


class TestMenuParsing:

    def test_parses(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        assert menu.type == "LIST_VIEW_LAYOUT"
        assert len(menu.data.body) == 3

    def test_sections(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        titles = [s.data.title for s in menu.data.body]
        assert "BURGERY" in titles
        assert "NAPOJE" in titles

    def test_dedup_top_sellers(self, menu_json):
        """Hot Wings Big Box is in 'Top sellers' only — should still appear."""
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        names = [p.name for _, p in products]
        assert "15 Hot Wings Big Box" in names

    def test_dedup_no_duplicates(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        ids = [p.id for _, p in products]
        assert len(ids) == len(set(ids))

    def test_total_products(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        # BURGERY: 3 + NAPOJE: 1 + Top sellers: Hot Wings (unique) = 5
        assert len(products) == 5

    def test_product_price(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        cheese_box = next(p for _, p in products if p.name == "Cheeseburger Big Box")
        assert cheese_box.price == 34.99
        assert cheese_box.price_grosz == 3499

    def test_out_of_stock(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        zinger = next(p for _, p in products if p.name == "Zinger Burger")
        assert zinger.is_available is False

    def test_inline_attribute_groups(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        cheese_box = next(p for _, p in products if p.name == "Cheeseburger Big Box")
        assert len(cheese_box.attributeGroups) == 3

    def test_attribute_group_required(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        cheese_box = next(p for _, p in products if p.name == "Cheeseburger Big Box")
        frytki = cheese_box.attributeGroups[1]
        assert frytki.name == "Wybierz frytki"
        assert frytki.is_required is True  # min=1
        assert frytki.min == 1
        assert frytki.max == 1

    def test_attribute_group_optional(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        cheese_box = next(p for _, p in products if p.name == "Cheeseburger Big Box")
        dodaj = cheese_box.attributeGroups[2]
        assert dodaj.name == "Dodaj to co lubisz"
        assert dodaj.is_required is False  # min=0
        assert dodaj.max == 3

    def test_attribute_price_impact(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        cheese_box = next(p for _, p in products if p.name == "Cheeseburger Big Box")
        frytki = cheese_box.attributeGroups[1]
        onion = next(a for a in frytki.attributes if "Onion" in a.name)
        assert onion.priceImpact == 1.0
        assert onion.price_grosz == 100

    def test_attribute_selected(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        cheese_box = next(p for _, p in products if p.name == "Cheeseburger Big Box")
        frytki = cheese_box.attributeGroups[1]
        default = next(a for a in frytki.attributes if a.selected)
        assert default.name == "Duże Frytki"


# ═══════════════════════════════════════════════════════════
# MENU NORMALIZATION
# ═══════════════════════════════════════════════════════════


class TestMenuNormalization:

    def _items(self, menu_json, adapter):
        menu = GlovoMenuResponse.model_validate(menu_json)
        return [
            adapter._normalize_product(p, cat, idx)
            for idx, (cat, p) in enumerate(menu.all_products())
        ]

    def test_item_fields(self, menu_json, adapter):
        items = self._items(menu_json, adapter)
        cheese_box = next(i for i in items if "Cheeseburger Big Box" in i.platform_name)
        assert cheese_box.price_grosz == 3499
        assert cheese_box.category_name == "BURGERY"
        assert cheese_box.is_available is True

    def test_modifier_groups(self, menu_json, adapter):
        items = self._items(menu_json, adapter)
        cheese_box = next(i for i in items if "Cheeseburger Big Box" in i.platform_name)
        assert len(cheese_box.modifier_groups) == 3

        frytki = cheese_box.modifier_groups[1]
        assert frytki.group_type == "required"
        assert frytki.min_selections == 1
        assert len(frytki.options) == 4

    def test_modifier_prices(self, menu_json, adapter):
        items = self._items(menu_json, adapter)
        cheese_box = next(i for i in items if "Cheeseburger Big Box" in i.platform_name)
        dodaj = cheese_box.modifier_groups[2]
        ser = next(o for o in dodaj.options if "ser" in o.name.lower())
        assert ser.price_grosz == 200

    def test_default_option(self, menu_json, adapter):
        items = self._items(menu_json, adapter)
        cheese_box = next(i for i in items if "Cheeseburger Big Box" in i.platform_name)
        frytki = cheese_box.modifier_groups[1]
        default = next(o for o in frytki.options if o.is_default)
        assert "Frytki" in default.name

    def test_out_of_stock(self, menu_json, adapter):
        items = self._items(menu_json, adapter)
        zinger = next(i for i in items if "Zinger" in i.platform_name)
        assert zinger.is_available is False

    def test_no_modifiers(self, menu_json, adapter):
        items = self._items(menu_json, adapter)
        pepsi = next(i for i in items if "Pepsi" in i.platform_name)
        assert pepsi.price_grosz == 699
        assert pepsi.modifier_groups == []

    def test_normalized_text(self, menu_json, adapter):
        items = self._items(menu_json, adapter)
        cheese_box = next(i for i in items if "Cheeseburger Big Box" in i.platform_name)
        frytki = cheese_box.modifier_groups[1]
        kubek = next(o for o in frytki.options if "Kubełek" in o.name or "Kubelek" in o.normalized_name)
        assert kubek.normalized_name == "kubełek frytek" or "kubelek" in kubek.normalized_name


# ═══════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_empty_menu(self):
        menu = GlovoMenuResponse.model_validate({"type": "LIST_VIEW_LAYOUT", "data": {"body": []}})
        assert menu.all_products() == []

    def test_store_no_delivery_fee(self):
        store = GlovoStore.model_validate({"id": 1, "slug": "t"})
        assert store.delivery_fee_grosz == 0

    def test_store_no_filters(self):
        store = GlovoStore.model_validate({"id": 1, "slug": "t"})
        assert store.cuisine_tags == []

    def test_extra_fields_allowed(self):
        store = GlovoStore.model_validate({"id": 1, "slug": "t", "unknownField": 42})
        assert store.slug == "t"

    def test_product_price_rounding(self):
        p = GlovoProduct.model_validate({"id": 1, "name": "T", "price": 28.99})
        assert p.price_grosz == 2899


# ═══════════════════════════════════════════════════════════
# CITY RESOLUTION
# ═══════════════════════════════════════════════════════════


class TestCityResolution:

    def test_warsaw_coordinates(self):
        from app.scraper.adapters.glovo import _resolve_city
        code, slug, name, short = _resolve_city(52.2297, 21.0122)
        assert code == "WAW"
        assert slug == "warszawa"
        assert short == "waw"

    def test_krakow_coordinates(self):
        from app.scraper.adapters.glovo import _resolve_city
        code, slug, name, short = _resolve_city(50.0614, 19.9372)
        assert code == "KRK"
        assert slug == "krakow"
        assert short == "kra"

    def test_wroclaw_coordinates(self):
        from app.scraper.adapters.glovo import _resolve_city
        code, slug, name, short = _resolve_city(51.1079, 17.0385)
        assert code == "WRO"
        assert slug == "wroclaw"

    def test_gdansk_coordinates(self):
        from app.scraper.adapters.glovo import _resolve_city
        code, slug, name, short = _resolve_city(54.35, 18.65)
        assert code == "GDN"
        assert slug == "gdansk"

    def test_adapter_sets_city(self, adapter):
        adapter._set_city(50.06, 19.94)
        assert adapter._city_code == "KRK"
        assert adapter._city_slug == "krakow"
        assert adapter._city_short == "kra"

    def test_adapter_default_warsaw(self, adapter):
        assert adapter._city_code == "WAW"

    def test_headers_use_current_city(self, adapter):
        adapter._set_city(50.06, 19.94)
        headers = adapter._glovo_headers()
        assert headers["Glovo-Location-City-Code"] == "KRK"

    def test_chain_slugs_generated(self, adapter):
        adapter._set_city(50.06, 19.94)  # Kraków
        slugs = adapter._generate_chain_slugs()
        assert "kfc-kra" in slugs
        assert "mcdonalds-kra" in slugs
        assert "kfc-krakow" in slugs
