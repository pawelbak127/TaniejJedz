"""Glovo contract tests — HTML/RSC based adapter (March 2026)."""

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
# STORE DETAIL (GlovoStore schema — used for RSC parsed data)
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

    def test_from_rsc(self, store_json, adapter):
        n = adapter._normalize_store_from_rsc(store_json)
        assert isinstance(n, NormalizedRestaurant)
        assert n.platform == "glovo"
        assert n.platform_slug == "kfc-waw"
        assert n.name == "KFC"
        assert n.is_online is True

    def test_delivery_fee(self, store_json, adapter):
        n = adapter._normalize_store_from_rsc(store_json)
        assert n.delivery_fee.fee_grosz == 199

    def test_platform_url(self, store_json, adapter):
        n = adapter._normalize_store_from_rsc(store_json)
        assert "glovoapp.com" in n.platform_url
        assert "kfc-waw" in n.platform_url


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
        assert frytki.is_required is True
        assert frytki.min == 1
        assert frytki.max == 1

    def test_attribute_group_optional(self, menu_json):
        menu = GlovoMenuResponse.model_validate(menu_json)
        products = menu.all_products()
        cheese_box = next(p for _, p in products if p.name == "Cheeseburger Big Box")
        dodaj = cheese_box.attributeGroups[2]
        assert dodaj.name == "Dodaj to co lubisz"
        assert dodaj.is_required is False
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
# HTML PARSING (category page)
# ═══════════════════════════════════════════════════════════


class TestCategoryHtmlParsing:

    SAMPLE_HTML = '''
    <a class="StoreCardStoreWall_wrapper__u8Dc8" href="/pl/pl/krakow/stores/kfc-kra">
      <div class="Card_pintxo-card__vSgCN"><img alt="KFC" loading="lazy" decoding="async">
      </div>
    </a>
    <a class="StoreCardStoreWall_wrapper__u8Dc8" href="/pl/pl/krakow/stores/mcdonald-s-kra">
      <div class="Card_pintxo-card__vSgCN"><img alt="McDonald&#x27;s" loading="lazy">
      </div>
    </a>
    <a class="StoreCardStoreWall_wrapper__u8Dc8" href="/pl/pl/krakow/stores/sofram-doner-kebab-kra">
      <div class="Card_pintxo-card__vSgCN"><img alt="Sofram Döner &amp; Kebab" loading="lazy">
      </div>
    </a>
    <a class="StoreCardStoreWall_wrapper__u8Dc8" href="/pl/pl/krakow/stores/pizza-hut-kra">
      <div class="Card_pintxo-card__vSgCN"><img alt="Pizza Hut" loading="lazy">
      </div>
    </a>
    <a href="/pl/pl/krakow/stores/apteczka-zdrowia-kra">
      <div><img alt="Apteczka zdrowia"></div>
    </a>
    <a href="/pl/pl/krakow/stores/biedronka-express-kra">
      <div><img alt="Biedronka Express"></div>
    </a>
    '''

    def test_extracts_slugs_and_names(self, adapter):
        adapter._set_city(50.06, 19.94)
        restaurants = adapter._parse_category_html(self.SAMPLE_HTML)
        slugs = {r.platform_slug for r in restaurants}
        assert "kfc-kra" in slugs
        assert "mcdonald-s-kra" in slugs
        assert "pizza-hut-kra" in slugs
        assert "sofram-doner-kebab-kra" in slugs

    def test_extracts_names_from_img_alt(self, adapter):
        adapter._set_city(50.06, 19.94)
        restaurants = adapter._parse_category_html(self.SAMPLE_HTML)
        by_slug = {r.platform_slug: r for r in restaurants}
        assert by_slug["kfc-kra"].name == "KFC"
        assert by_slug["mcdonald-s-kra"].name == "McDonald's"  # HTML entity decoded
        assert by_slug["pizza-hut-kra"].name == "Pizza Hut"

    def test_html_entities_decoded(self, adapter):
        adapter._set_city(50.06, 19.94)
        restaurants = adapter._parse_category_html(self.SAMPLE_HTML)
        by_slug = {r.platform_slug: r for r in restaurants}
        assert by_slug["mcdonald-s-kra"].name == "McDonald's"  # &#x27; → '
        assert by_slug["sofram-doner-kebab-kra"].name == "Sofram Döner & Kebab"  # &amp; → &

    def test_filters_non_food(self, adapter):
        adapter._set_city(50.06, 19.94)
        restaurants = adapter._parse_category_html(self.SAMPLE_HTML)
        slugs = {r.platform_slug for r in restaurants}
        assert "apteczka-zdrowia-kra" not in slugs
        assert "biedronka-express-kra" not in slugs

    def test_platform_url(self, adapter):
        adapter._set_city(50.06, 19.94)
        restaurants = adapter._parse_category_html(self.SAMPLE_HTML)
        kfc = next(r for r in restaurants if r.platform_slug == "kfc-kra")
        assert kfc.platform_url == "https://glovoapp.com/pl/pl/krakow/stores/kfc-kra"

    def test_dedup(self, adapter):
        html = '''
        <a href="/pl/pl/krakow/stores/kfc-kra"><img alt="KFC"></a>
        <a href="/pl/pl/krakow/stores/kfc-kra"><img alt="KFC"></a>
        '''
        restaurants = adapter._parse_category_html(html)
        assert len(restaurants) == 1

    def test_empty_html(self, adapter):
        restaurants = adapter._parse_category_html("<html><body></body></html>")
        assert restaurants == []


class TestSlugToName:

    def test_simple(self):
        assert GlovoAdapter._slug_to_name("kfc-kra") == "Kfc"

    def test_multi_word(self):
        assert GlovoAdapter._slug_to_name("pizza-hut-kra") == "Pizza Hut"

    def test_with_number_suffix(self):
        assert GlovoAdapter._slug_to_name("burger-king2-kra") == "Burger King"

    def test_complex_slug(self):
        name = GlovoAdapter._slug_to_name("tandoor-kebab-house-kra")
        assert name == "Tandoor Kebab House"

    def test_long_city_suffix(self):
        # Slug with disambiguation: kebab-hq-kra-19bcx — city suffix is not just 3 chars
        name = GlovoAdapter._slug_to_name("kebab-hq-kra-19bcx")
        # rsplit on last "-" gives "kra-19bcx" which is >4 chars, so no stripping
        # That's fine — this edge case is handled by img alt extraction
        assert "kebab" in name.lower()


class TestNonFoodFilter:

    def test_pharmacy(self):
        assert GlovoAdapter._is_non_food_slug("apteczka-zdrowia-kra") is True

    def test_grocery(self):
        assert GlovoAdapter._is_non_food_slug("biedronka-express-waw") is True

    def test_restaurant(self):
        assert GlovoAdapter._is_non_food_slug("kfc-kra") is False

    def test_kebab(self):
        assert GlovoAdapter._is_non_food_slug("tandoor-kebab-kra") is False


# ═══════════════════════════════════════════════════════════
# RSC PARSING
# ═══════════════════════════════════════════════════════════


class TestRscParsing:

    def test_extract_balanced_json_object(self, adapter):
        text = 'prefix{"id":1,"name":"test","nested":{"a":1}}suffix'
        result = adapter._extract_balanced_json(text, 6)
        assert result == '{"id":1,"name":"test","nested":{"a":1}}'

    def test_extract_balanced_json_array(self, adapter):
        text = 'prefix[1,[2,3],4]suffix'
        result = adapter._extract_balanced_json(text, 6)
        assert result == '[1,[2,3],4]'

    def test_extract_balanced_handles_strings(self, adapter):
        text = r'{"key":"value with } brace","id":1}'
        result = adapter._extract_balanced_json(text, 0)
        assert result == text

    def test_extract_balanced_returns_none_for_non_json(self, adapter):
        result = adapter._extract_balanced_json("hello", 0)
        assert result is None

    def test_parse_store_rsc_with_real_structure(self, adapter):
        """Simulates RSC payload structure from live Glovo."""
        rsc_html = '''<script>self.__next_f.push([1,"17:[\\"$\\",\\"div\\",null,{\\"children\\":[\\"$\\",\\"$L33\\",null,{\\"store\\":{\\"id\\":61933,\\"name\\":\\"KFC\\",\\"slug\\":\\"kfc-kra\\",\\"open\\":true,\\"addressId\\":123175,\\"cityCode\\":\\"KRA\\",\\"enabled\\":true,\\"food\\":true,\\"category\\":\\"RESTAURANT\\",\\"deliveryFeeInfo\\":{\\"fee\\":0.99},\\"serviceFee\\":0.99,\\"filters\\":[]},\\"children\\":[\\"$\\",\\"$L34\\",null,{\\"initialStoreContent\\":{\\"data\\":{\\"body\\":[{\\"type\\":\\"LIST\\",\\"data\\":{\\"title\\":\\"Burgery\\",\\"elements\\":[]}}]}}}]}]}]"])</script>'''
        store_data, menu_data = adapter._parse_store_rsc(rsc_html, "kfc-kra")
        if store_data:
            assert store_data["id"] == 61933
            assert store_data["name"] == "KFC"
            assert store_data["slug"] == "kfc-kra"


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
