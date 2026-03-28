"""
Wolt contract tests — based on REAL API dumps (March 2026).
Tests schema parsing + two-level modifier JOIN + normalization.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scraper.adapters.wolt_schemas import (
    MARKETING_SECTIONS,
    WoltMenuResponse,
    WoltMenuItem,
    WoltSearchResponse,
    WoltVenue,
)
from app.scraper.adapters.wolt import WoltAdapter, _resolve_wolt_city_slug
from app.scraper.schemas.normalized import NormalizedMenuItem, NormalizedRestaurant

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def search_json() -> dict:
    return json.loads((FIXTURES / "wolt_search.json").read_text(encoding="utf-8"))


@pytest.fixture
def menu_json() -> dict:
    return json.loads((FIXTURES / "wolt_menu.json").read_text(encoding="utf-8"))


@pytest.fixture
def adapter(redis):
    a = WoltAdapter(redis)
    a._budget.register_platform("wolt", 100_000)
    return a


# ═══════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════


class TestSearchParsing:

    def test_parses(self, search_json):
        resp = WoltSearchResponse.model_validate(search_json)
        assert len(resp.sections) == 2

    def test_skips_category_section(self, search_json):
        """Section[0] is Categorylist — no venues there."""
        resp = WoltSearchResponse.model_validate(search_json)
        venues = resp.all_venues()
        assert len(venues) == 3  # only from restaurants-delivering-venues

    def test_venue_slug(self, search_json):
        resp = WoltSearchResponse.model_validate(search_json)
        assert resp.all_venues()[0].slug == "bella-ciao-solec"

    def test_location_lng_lat(self, search_json):
        resp = WoltSearchResponse.model_validate(search_json)
        v = resp.all_venues()[0]
        assert v.longitude == pytest.approx(21.034)
        assert v.latitude == pytest.approx(52.2288)

    def test_rating_volume(self, search_json):
        """Real API has 'volume' not 'count'."""
        resp = WoltSearchResponse.model_validate(search_json)
        v = resp.all_venues()[0]
        assert v.rating.volume == 312
        assert v.rating.score == pytest.approx(8.6)

    def test_delivers_flag(self, search_json):
        resp = WoltSearchResponse.model_validate(search_json)
        venues = resp.all_venues()
        assert venues[0].delivers is True
        assert venues[2].delivers is False

    def test_brand_image(self, search_json):
        resp = WoltSearchResponse.model_validate(search_json)
        v = resp.all_venues()[0]
        assert v.image_url == "https://imageproxy.wolt.com/venue/bella-ciao.jpg"

    def test_no_brand_image(self, search_json):
        resp = WoltSearchResponse.model_validate(search_json)
        v = resp.all_venues()[1]
        assert v.image_url is None

    def test_estimate_range(self, search_json):
        resp = WoltSearchResponse.model_validate(search_json)
        v = resp.all_venues()[0]
        assert v.delivery_minutes_avg == 30  # (25+35)//2

    def test_no_delivery_price_field(self, search_json):
        """Real API does NOT have delivery_price_int in venue."""
        resp = WoltSearchResponse.model_validate(search_json)
        v = resp.all_venues()[0]
        assert not hasattr(v, "delivery_price_int") or getattr(v, "delivery_price_int", None) is None


class TestSearchNormalization:

    def test_basic(self, search_json, adapter):
        resp = WoltSearchResponse.model_validate(search_json)
        n = adapter._normalize_venue(resp.all_venues()[0])
        assert isinstance(n, NormalizedRestaurant)
        assert n.platform == "wolt"
        assert n.platform_slug == "bella-ciao-solec"
        assert n.name == "Bella Ciao - Solec"

    def test_coords_swapped(self, search_json, adapter):
        resp = WoltSearchResponse.model_validate(search_json)
        n = adapter._normalize_venue(resp.all_venues()[0])
        assert n.latitude == pytest.approx(52.2288)
        assert n.longitude == pytest.approx(21.034)

    def test_rating_mapped(self, search_json, adapter):
        resp = WoltSearchResponse.model_validate(search_json)
        n = adapter._normalize_venue(resp.all_venues()[0])
        assert n.rating_score == pytest.approx(8.6)
        assert n.rating_count == 312

    def test_is_online(self, search_json, adapter):
        resp = WoltSearchResponse.model_validate(search_json)
        venues = resp.all_venues()
        assert adapter._normalize_venue(venues[0]).is_online is True
        assert adapter._normalize_venue(venues[2]).is_online is False

    def test_delivery_eta(self, search_json, adapter):
        resp = WoltSearchResponse.model_validate(search_json)
        n = adapter._normalize_venue(resp.all_venues()[0])
        assert n.delivery_fee is not None
        assert n.delivery_fee.estimated_minutes == 30

    def test_platform_url(self, search_json, adapter):
        resp = WoltSearchResponse.model_validate(search_json)
        n = adapter._normalize_venue(resp.all_venues()[0])
        assert "wolt.com" in n.platform_url
        assert "bella-ciao-solec" in n.platform_url

    def test_platform_url_uses_venue_city(self, search_json, adapter):
        """URL should use venue's city, not hardcoded warszawa."""
        resp = WoltSearchResponse.model_validate(search_json)
        v = resp.all_venues()[0]
        n = adapter._normalize_venue(v)
        # Venue has city field — URL should reflect it
        if v.city:
            city_slug = _resolve_wolt_city_slug(v.city)
            assert city_slug in n.platform_url


# ═══════════════════════════════════════════════════════════
# MENU — parsing + dedup + option lookup
# ═══════════════════════════════════════════════════════════


class TestMenuParsing:

    def test_parses(self, menu_json):
        resp = WoltMenuResponse.model_validate(menu_json)
        assert len(resp.sections) == 3

    def test_option_lookup_built(self, menu_json):
        resp = WoltMenuResponse.model_validate(menu_json)
        lookup = resp.build_option_lookup()
        assert "opt-ciasto-30" in lookup
        assert "opt-doladuj-pizza" in lookup
        assert "opt-sos" in lookup
        assert len(lookup["opt-ciasto-30"].values) == 2

    def test_dedup_marketing(self, menu_json):
        """Peperoni in 'Najczęściej zamawiane' AND 'Pizze' → keep Pizze."""
        resp = WoltMenuResponse.model_validate(menu_json)
        items = resp.deduplicated_items()
        peperoni_cats = [cat for cat, item in items if item.id == "item-peperoni"]
        assert len(peperoni_cats) == 1
        assert peperoni_cats[0] == "Pizze"

    def test_dedup_total_count(self, menu_json):
        resp = WoltMenuResponse.model_validate(menu_json)
        items = resp.deduplicated_items()
        # Pizze: peperoni, margherita, hawajska + Napoje: cola = 4
        assert len(items) == 4

    def test_item_price_is_grosz(self, menu_json):
        resp = WoltMenuResponse.model_validate(menu_json)
        items = resp.deduplicated_items()
        peperoni = next(i for _, i in items if i.id == "item-peperoni")
        assert peperoni.price == 4399

    def test_disabled_info(self, menu_json):
        resp = WoltMenuResponse.model_validate(menu_json)
        items = resp.deduplicated_items()
        hawajska = next(i for _, i in items if i.id == "item-hawajska")
        assert hawajska.is_available is False
        peperoni = next(i for _, i in items if i.id == "item-peperoni")
        assert peperoni.is_available is True

    def test_item_image(self, menu_json):
        resp = WoltMenuResponse.model_validate(menu_json)
        items = resp.deduplicated_items()
        peperoni = next(i for _, i in items if i.id == "item-peperoni")
        assert peperoni.image_url == "https://imageproxy.wolt.com/menu/peperoni.jpg"

    def test_item_options_are_references(self, menu_json):
        """Item options have option_id referencing section options."""
        resp = WoltMenuResponse.model_validate(menu_json)
        items = resp.deduplicated_items()
        peperoni = next(i for _, i in items if i.id == "item-peperoni")
        assert len(peperoni.options) == 3
        assert peperoni.options[0].option_id == "opt-ciasto-30"
        assert peperoni.options[1].option_id == "opt-doladuj-pizza"

    def test_multi_choice_config_range(self, menu_json):
        resp = WoltMenuResponse.model_validate(menu_json)
        items = resp.deduplicated_items()
        peperoni = next(i for _, i in items if i.id == "item-peperoni")
        doladuj = peperoni.options[1]
        assert doladuj.min_selections == 0
        assert doladuj.max_selections == 17
        assert doladuj.is_required is False

    def test_required_modifier(self, menu_json):
        """Margherita has ciasto with min=1 → required."""
        resp = WoltMenuResponse.model_validate(menu_json)
        items = resp.deduplicated_items()
        margherita = next(i for _, i in items if i.id == "item-margherita")
        assert margherita.options[0].is_required is True


# ═══════════════════════════════════════════════════════════
# MENU — normalization with JOIN
# ═══════════════════════════════════════════════════════════


class TestMenuNormalization:

    def _get_normalized(self, menu_json, adapter):
        resp = WoltMenuResponse.model_validate(menu_json)
        lookup = resp.build_option_lookup()
        deduped = resp.deduplicated_items()
        return [
            adapter._normalize_item(item, cat, idx, lookup)
            for idx, (cat, item) in enumerate(deduped)
        ]

    def test_item_fields(self, menu_json, adapter):
        items = self._get_normalized(menu_json, adapter)
        peperoni = next(i for i in items if i.platform_item_id == "item-peperoni")
        assert peperoni.platform_name == "Pizza Peperoni 30cm"
        assert peperoni.price_grosz == 4399
        assert peperoni.category_name == "Pizze"
        assert peperoni.is_available is True

    def test_modifier_groups_resolved(self, menu_json, adapter):
        """Item references → resolved to groups with values from section options."""
        items = self._get_normalized(menu_json, adapter)
        peperoni = next(i for i in items if i.platform_item_id == "item-peperoni")
        assert len(peperoni.modifier_groups) == 3

        ciasto = peperoni.modifier_groups[0]
        assert ciasto.name == "Wybierz Ciasto 30cm"
        assert ciasto.group_type == "optional"  # min=0
        assert len(ciasto.options) == 2

    def test_option_values_from_section(self, menu_json, adapter):
        items = self._get_normalized(menu_json, adapter)
        peperoni = next(i for i in items if i.platform_item_id == "item-peperoni")
        ciasto = peperoni.modifier_groups[0]

        assert ciasto.options[0].name == "Cienkie"
        assert ciasto.options[0].price_grosz == 0
        assert ciasto.options[0].is_default is True  # default_value = val-cienkie

        assert ciasto.options[1].name == "Grube"
        assert ciasto.options[1].price_grosz == 399
        assert ciasto.options[1].is_default is False

    def test_default_value_mapped(self, menu_json, adapter):
        items = self._get_normalized(menu_json, adapter)
        peperoni = next(i for i in items if i.platform_item_id == "item-peperoni")
        sos = peperoni.modifier_groups[2]
        default = next(o for o in sos.options if o.is_default)
        assert default.name == "Sos pomidorowy"

    def test_required_group(self, menu_json, adapter):
        items = self._get_normalized(menu_json, adapter)
        margherita = next(i for i in items if i.platform_item_id == "item-margherita")
        assert len(margherita.modifier_groups) == 1
        ciasto = margherita.modifier_groups[0]
        assert ciasto.group_type == "required"
        assert ciasto.min_selections == 1

    def test_disabled_item(self, menu_json, adapter):
        items = self._get_normalized(menu_json, adapter)
        hawajska = next(i for i in items if i.platform_item_id == "item-hawajska")
        assert hawajska.is_available is False

    def test_item_without_modifiers(self, menu_json, adapter):
        items = self._get_normalized(menu_json, adapter)
        cola = next(i for i in items if i.platform_item_id == "item-cola")
        assert cola.platform_name == "Coca-Cola 0.5L"
        assert cola.price_grosz == 899
        assert cola.modifier_groups == []

    def test_normalized_name_diacritics(self, menu_json, adapter):
        items = self._get_normalized(menu_json, adapter)
        peperoni = next(i for i in items if i.platform_item_id == "item-peperoni")
        doladuj = peperoni.modifier_groups[1]
        jalapeno = next(o for o in doladuj.options if "Jalap" in o.name)
        assert jalapeno.normalized_name == "jalapeno"


# ═══════════════════════════════════════════════════════════
# CITY RESOLUTION
# ═══════════════════════════════════════════════════════════


class TestCityResolution:

    def test_warszawa(self):
        assert _resolve_wolt_city_slug("Warszawa") == "warszawa"

    def test_krakow_with_diacritics(self):
        assert _resolve_wolt_city_slug("Kraków") == "krakow"

    def test_krakow_without_diacritics(self):
        assert _resolve_wolt_city_slug("krakow") == "krakow"

    def test_wroclaw(self):
        assert _resolve_wolt_city_slug("Wrocław") == "wroclaw"

    def test_lodz(self):
        assert _resolve_wolt_city_slug("Łódź") == "lodz"

    def test_gdansk(self):
        assert _resolve_wolt_city_slug("Gdańsk") == "gdansk"

    def test_empty_falls_back(self):
        assert _resolve_wolt_city_slug("") == "warszawa"

    def test_unknown_passthrough(self):
        assert _resolve_wolt_city_slug("sopot") == "sopot"

    def test_adapter_default_city(self, adapter):
        assert adapter._city_slug == "warszawa"


# ═══════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_empty_search(self):
        resp = WoltSearchResponse.model_validate({"sections": []})
        assert resp.all_venues() == []

    def test_venue_no_location(self):
        v = WoltVenue.model_validate({"slug": "t", "name": "T"})
        assert v.latitude == 0.0
        assert v.longitude == 0.0

    def test_venue_no_rating(self):
        v = WoltVenue.model_validate({"slug": "t"})
        assert v.rating is None

    def test_venue_no_estimate(self):
        v = WoltVenue.model_validate({"slug": "t"})
        assert v.delivery_minutes_avg is None

    def test_empty_menu(self):
        resp = WoltMenuResponse.model_validate({"sections": []})
        assert resp.deduplicated_items() == []
        assert resp.build_option_lookup() == {}

    def test_extra_fields_allowed(self):
        v = WoltVenue.model_validate({"slug": "t", "name": "T", "unknown_field": 42})
        assert v.slug == "t"

    def test_marketing_sections_include_real_names(self):
        assert "Najczęściej zamawiane" in MARKETING_SECTIONS
        assert "Popularne" in MARKETING_SECTIONS

    def test_sections_from_nested(self, adapter):
        raw = {"page": {"sections": [{"name": "Test", "items": []}]}}
        assert len(adapter._extract_sections(raw)) == 1

    def test_missing_option_id_skipped(self, adapter):
        """If option_id not in lookup → skip silently."""
        item = WoltMenuItem.model_validate({
            "id": "x", "name": "X", "price": 100,
            "options": [{"id": "ref", "option_id": "nonexistent", "name": "?"}],
        })
        n = adapter._normalize_item(item, "Cat", 0, {})
        assert n.modifier_groups == []


# ═══════════════════════════════════════════════════════════
# SSR MENU PARSING
# ═══════════════════════════════════════════════════════════


class TestSsrMenuParsing:

    @pytest.fixture
    def ssr_menu(self) -> dict:
        return json.loads((FIXTURES / "wolt_ssr_menu.json").read_text(encoding="utf-8"))

    def test_categories(self, ssr_menu):
        assert len(ssr_menu["categories"]) == 3
        assert ssr_menu["categories"][0]["name"] == "Zupy"

    def test_items_count(self, ssr_menu):
        assert len(ssr_menu["items"]) == 6

    def test_item_price_is_grosz(self, ssr_menu):
        barszcz = next(i for i in ssr_menu["items"] if i["id"] == "item-barszcz")
        assert barszcz["price"] == 2600

    def test_disabled_info(self, ssr_menu):
        golonka = next(i for i in ssr_menu["items"] if i["id"] == "item-golonka")
        assert golonka["disabled_info"] is not None
        barszcz = next(i for i in ssr_menu["items"] if i["id"] == "item-barszcz")
        assert barszcz["disabled_info"] is None

    def test_item_options_reference(self, ssr_menu):
        barszcz = next(i for i in ssr_menu["items"] if i["id"] == "item-barszcz")
        assert len(barszcz["options"]) == 1
        assert barszcz["options"][0]["option_id"] == "opt-sztucce"

    def test_options_lookup(self, ssr_menu):
        opts = ssr_menu["options"]
        assert "opt-sztucce" in opts
        assert "opt-sos" in opts
        assert len(opts["opt-sos"]["values"]) == 3

    def test_multi_choice_config(self, ssr_menu):
        pierogi = next(i for i in ssr_menu["items"] if i["id"] == "item-pierogi")
        sos_opt = pierogi["options"][0]
        assert sos_opt["multi_choice_config"]["total_range"]["min"] == 0
        assert sos_opt["multi_choice_config"]["total_range"]["max"] == 3


class TestSsrNormalization:

    @pytest.fixture
    def ssr_menu(self) -> dict:
        return json.loads((FIXTURES / "wolt_ssr_menu.json").read_text(encoding="utf-8"))

    def _get_items(self, ssr_menu, adapter):
        items_by_id = {i["id"]: i for i in ssr_menu["items"]}
        options = ssr_menu["options"]
        result = []
        seen = set()
        for cat_idx, cat in enumerate(ssr_menu["categories"]):
            for item_id in cat["item_ids"]:
                if item_id in seen:
                    continue
                seen.add(item_id)
                item = items_by_id.get(item_id)
                if item:
                    result.append(adapter._normalize_ssr_item(item, cat["name"], cat_idx, options))
        return result

    def test_total_items(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        assert len(items) == 6

    def test_item_fields(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        barszcz = next(i for i in items if i.platform_item_id == "item-barszcz")
        assert barszcz.platform_name == "Barszcz Czerwony"
        assert barszcz.price_grosz == 2600
        assert barszcz.category_name == "Zupy"
        assert barszcz.is_available is True

    def test_modifier_groups_resolved(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        pierogi = next(i for i in items if i.platform_item_id == "item-pierogi")
        assert len(pierogi.modifier_groups) == 2

    def test_option_values_from_lookup(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        pierogi = next(i for i in items if i.platform_item_id == "item-pierogi")
        sos = next(g for g in pierogi.modifier_groups if g.name == "Wybierz sos")
        assert len(sos.options) == 3
        assert sos.options[0].name == "Śmietana"
        assert sos.options[0].price_grosz == 0
        assert sos.options[2].name == "Sos czosnkowy"
        assert sos.options[2].price_grosz == 300

    def test_default_value_mapped(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        barszcz = next(i for i in items if i.platform_item_id == "item-barszcz")
        sztucce = barszcz.modifier_groups[0]
        default = next(o for o in sztucce.options if o.is_default)
        assert default.name == "Tak, poproszę"

    def test_required_group(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        barszcz = next(i for i in items if i.platform_item_id == "item-barszcz")
        sztucce = barszcz.modifier_groups[0]
        assert sztucce.group_type == "required"
        assert sztucce.min_selections == 1

    def test_optional_group(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        pierogi = next(i for i in items if i.platform_item_id == "item-pierogi")
        sos = next(g for g in pierogi.modifier_groups if g.name == "Wybierz sos")
        assert sos.group_type == "optional"
        assert sos.max_selections == 3

    def test_disabled_item(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        golonka = next(i for i in items if i.platform_item_id == "item-golonka")
        assert golonka.is_available is False

    def test_item_without_modifiers(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        cola = next(i for i in items if i.platform_item_id == "item-cola")
        assert cola.platform_name == "Coca-Cola 0.5L"
        assert cola.price_grosz == 800
        assert cola.modifier_groups == []

    def test_normalized_name_diacritics(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        pierogi = next(i for i in items if i.platform_item_id == "item-pierogi")
        sos = next(g for g in pierogi.modifier_groups if g.name == "Wybierz sos")
        smietana = next(o for o in sos.options if "mietana" in o.name)
        assert smietana.normalized_name == "smietana"

    def test_missing_option_skipped(self, adapter):
        """If option_id not in lookup → skip."""
        item = {
            "id": "x", "name": "X", "price": 100,
            "options": [{"id": "ref", "option_id": "nonexistent", "name": "?",
                        "multi_choice_config": {"total_range": {"min": 0, "max": 1}}}],
        }
        n = adapter._normalize_ssr_item(item, "Cat", 0, {})
        assert n.modifier_groups == []
