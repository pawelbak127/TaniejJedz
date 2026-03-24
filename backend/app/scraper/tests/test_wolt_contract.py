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
    WoltSearchResponse,
    WoltVenue,
)
from app.scraper.adapters.wolt import WoltAdapter
from app.scraper.schemas.normalized import NormalizedMenuItem, NormalizedRestaurant

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def search_json() -> dict:
    return json.loads((FIXTURES / "wolt_search.json").read_text(encoding="utf-8"))


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


# ═══════════════════════════════════════════════════════════
# MENU — parsing + dedup + option lookup
# ═══════════════════════════════════════════════════════════


class TestMenuParsing:
    """Test SSR HTML menu parsing (React Query cache)."""

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

    def test_category_item_ids(self, ssr_menu):
        zupy = ssr_menu["categories"][0]
        assert len(zupy["item_ids"]) == 2
        assert "item-barszcz" in zupy["item_ids"]

    def test_ssr_parse_extracts_from_html(self, adapter):
        """Test _parse_ssr_menu with embedded React Query cache."""
        html = '<html><script>{"queries":[{"queryKey":["venue-assortment","category-listing","test"],"state":{"data":{"categories":[{"name":"Test","item_ids":["i1"]}],"items":[{"id":"i1","name":"Item","price":1000}],"options":{}}}}],"mutations":[]}</script></html>'
        menu = adapter._parse_ssr_menu(html, "test")
        assert len(menu["categories"]) == 1
        assert len(menu["items"]) == 1

    def test_ssr_parse_raises_on_missing(self, adapter):
        with pytest.raises(Exception, match="React Query"):
            adapter._parse_ssr_menu("<html><body></body></html>", "test")


# ═══════════════════════════════════════════════════════════
# MENU — SSR normalization
# ═══════════════════════════════════════════════════════════


class TestMenuNormalization:

    @pytest.fixture
    def ssr_menu(self) -> dict:
        return json.loads((FIXTURES / "wolt_ssr_menu.json").read_text(encoding="utf-8"))

    def _get_items(self, ssr_menu, adapter):
        categories = ssr_menu["categories"]
        items_list = ssr_menu["items"]
        options = ssr_menu["options"]

        items_by_id = {i["id"]: i for i in items_list}
        result = []
        seen = set()
        for cat_idx, cat in enumerate(categories):
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
        assert sztucce.group_type == "required"  # min=1
        assert sztucce.min_selections == 1

    def test_optional_group(self, ssr_menu, adapter):
        items = self._get_items(ssr_menu, adapter)
        pierogi = next(i for i in items if i.platform_item_id == "item-pierogi")
        sos = next(g for g in pierogi.modifier_groups if g.name == "Wybierz sos")
        assert sos.group_type == "optional"  # min=0
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

    def test_venue_no_rating(self):
        v = WoltVenue.model_validate({"slug": "t"})
        assert v.rating is None

    def test_venue_no_estimate(self):
        v = WoltVenue.model_validate({"slug": "t"})
        assert v.delivery_minutes_avg is None

    def test_extra_fields_allowed(self):
        v = WoltVenue.model_validate({"slug": "t", "name": "T", "unknown_field": 42})
        assert v.slug == "t"

    def test_marketing_sections_include_real_names(self):
        assert "Najczęściej zamawiane" in MARKETING_SECTIONS

    def test_missing_option_skipped(self, adapter):
        """If option_id not in lookup → skip."""
        item = {
            "id": "x", "name": "X", "price": 100,
            "options": [{"id": "ref", "option_id": "nonexistent", "name": "?",
                        "multi_choice_config": {"total_range": {"min": 0, "max": 1}}}],
        }
        n = adapter._normalize_ssr_item(item, "Cat", 0, {})
        assert n.modifier_groups == []

    def test_city_resolution(self):
        from app.scraper.adapters.wolt import _resolve_wolt_city
        assert _resolve_wolt_city(52.23, 21.01) == "warszawa"
        assert _resolve_wolt_city(50.06, 19.94) == "krakow"
        assert _resolve_wolt_city(51.11, 17.04) == "wroclaw"
