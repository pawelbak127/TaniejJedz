"""Pyszne.pl contract tests — real CDN structure (March 2026)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scraper.adapters.pyszne_schemas import (
    PyszneCdn, PyszneSearchResponse, PyszneRestaurant, extract_cdn,
)
from app.scraper.adapters.pyszne import PyszneAdapter
from app.scraper.schemas.normalized import NormalizedMenuItem, NormalizedRestaurant

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def search_json() -> dict:
    return json.loads((FIXTURES / "pyszne_search.json").read_text(encoding="utf-8"))


@pytest.fixture
def menu_html() -> str:
    return (FIXTURES / "pyszne_menu.html").read_text(encoding="utf-8")


@pytest.fixture
def cdn(menu_html) -> PyszneCdn:
    data = PyszneAdapter._extract_next_data(menu_html)
    return PyszneCdn.model_validate(extract_cdn(data))


@pytest.fixture
def adapter(redis):
    a = PyszneAdapter(redis)
    a._budget.register_platform("pyszne", 100_000)
    return a


# ═══════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════


class TestSearch:

    def test_parses(self, search_json):
        resp = PyszneSearchResponse.model_validate(search_json)
        assert len(resp.restaurants) == 5

    def test_filters_virtual(self, search_json):
        real = PyszneSearchResponse.model_validate(search_json).real_restaurants()
        assert len(real) == 3
        assert "pizza" not in [r.uniqueName for r in real]

    def test_location_from_address(self, search_json):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        assert r.latitude == pytest.approx(52.235, abs=0.01)
        assert r.longitude == pytest.approx(20.959, abs=0.01)

    def test_delivery_cost_grosz(self, search_json):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        assert r.deliveryCost == 10
        assert r.delivery_fee_grosz == 1000

    def test_minimum_order_grosz(self, search_json):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        assert r.minimum_order_grosz == 6000

    def test_rating(self, search_json):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        assert r.rating.starRating == pytest.approx(4.3)
        assert r.rating.count == 45

    def test_eta(self, search_json):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        assert r.delivery_minutes_avg == 25

    def test_cuisines(self, search_json):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        assert "Tajska" in r.cuisine_tags

    def test_address_str(self, search_json):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        assert "Sokołowska" in r.address_str

    def test_is_open(self, search_json):
        real = PyszneSearchResponse.model_validate(search_json).real_restaurants()
        assert real[0].isOpenNowForDelivery is True
        assert real[1].isOpenNowForDelivery is False


class TestSearchNormalization:

    def test_basic(self, search_json, adapter):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        n = adapter._normalize_restaurant(r)
        assert n.platform == "pyszne"
        assert n.platform_slug == "nocny-szafran-warszawa"

    def test_delivery(self, search_json, adapter):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        n = adapter._normalize_restaurant(r)
        assert n.delivery_fee.fee_grosz == 1000
        assert n.delivery_fee.minimum_order_grosz == 6000

    def test_platform_url(self, search_json, adapter):
        r = PyszneSearchResponse.model_validate(search_json).real_restaurants()[0]
        n = adapter._normalize_restaurant(r)
        assert "pyszne.pl/menu/nocny-szafran-warszawa" in n.platform_url


# ═══════════════════════════════════════════════════════════
# CDN PARSING
# ═══════════════════════════════════════════════════════════


class TestCdn:

    def test_categories_from_menus(self, cdn):
        cats = cdn.get_categories()
        assert len(cats) == 3
        assert cats[0].name == "Pizze"

    def test_items_dict(self, cdn):
        assert len(cdn.items) == 4
        assert cdn.items["item-margherita"].name == "Pizza Margherita"

    def test_modifier_groups_list(self, cdn):
        assert isinstance(cdn.modifierGroups, list)
        assert len(cdn.modifierGroups) == 2
        lookup = cdn.modifier_group_lookup()
        assert "mg-sos" in lookup
        assert lookup["mg-sos"].modifiers == ["ms-1", "ms-2", "ms-3"]

    def test_modifier_sets_list(self, cdn):
        assert isinstance(cdn.modifierSets, list)
        assert len(cdn.modifierSets) == 6
        lookup = cdn.modifier_set_lookup()
        assert "ms-1" in lookup
        assert lookup["ms-1"].modifier.name == "Sos pomidorowy"

    def test_base_price_int_pln(self, cdn):
        """basePrice is INT PLN: 23 = 23 zł = 2300 grosz."""
        marg = cdn.items["item-margherita"]
        assert marg.variations[0].basePrice == 23
        assert marg.variations[0].price_grosz == 2300

    def test_addition_price_int_pln(self, cdn):
        """additionPrice is INT PLN: 4 = 4 zł = 400 grosz."""
        lookup = cdn.modifier_set_lookup()
        assert lookup["ms-1"].modifier.additionPrice == 4
        assert lookup["ms-1"].modifier.price_grosz == 400

    def test_required_group(self, cdn):
        lookup = cdn.modifier_group_lookup()
        assert lookup["mg-dodatki"].is_required is True
        assert lookup["mg-sos"].is_required is False


# ═══════════════════════════════════════════════════════════
# MENU NORMALIZATION
# ═══════════════════════════════════════════════════════════


class TestMenuNormalization:

    def _items(self, cdn, adapter):
        mg = cdn.modifier_group_lookup()
        ms = cdn.modifier_set_lookup()
        items = []
        for idx, cat in enumerate(cdn.get_categories()):
            for item_id in cat.itemIds:
                it = cdn.items.get(item_id)
                if it:
                    items.append(adapter._normalize_item(it, cat.name, idx, mg, ms))
        return items

    def test_total(self, cdn, adapter):
        assert len(self._items(cdn, adapter)) == 4

    def test_base_price(self, cdn, adapter):
        marg = next(i for i in self._items(cdn, adapter) if "Margherita" in i.platform_name)
        assert marg.price_grosz == 2300  # cheapest variation: 23 PLN

    def test_synthetic_rozmiar(self, cdn, adapter):
        marg = next(i for i in self._items(cdn, adapter) if "Margherita" in i.platform_name)
        roz = next(g for g in marg.modifier_groups if g.name == "Rozmiar")
        assert roz.group_type == "required"
        assert len(roz.options) == 3
        assert roz.options[0].name == "25cm"
        assert roz.options[0].price_grosz == 0
        assert roz.options[0].is_default is True
        assert roz.options[1].name == "30cm"
        assert roz.options[1].price_grosz == 600   # 29-23=6 PLN = 600 gr
        assert roz.options[2].name == "40cm"
        assert roz.options[2].price_grosz == 1600  # 39-23=16 PLN = 1600 gr

    def test_single_var_no_rozmiar(self, cdn, adapter):
        pep = next(i for i in self._items(cdn, adapter) if "Pepperoni" in i.platform_name)
        assert "Rozmiar" not in [g.name for g in pep.modifier_groups]

    def test_modifier_join(self, cdn, adapter):
        """group.modifiers[] → modifierSets lookup → modifier.additionPrice."""
        pep = next(i for i in self._items(cdn, adapter) if "Pepperoni" in i.platform_name)
        sos = next(g for g in pep.modifier_groups if g.name == "Dodatkowy sos")
        assert len(sos.options) == 3
        assert sos.options[0].name == "Sos pomidorowy"
        assert sos.options[0].price_grosz == 400  # 4 PLN

    def test_required_group(self, cdn, adapter):
        pep = next(i for i in self._items(cdn, adapter) if "Pepperoni" in i.platform_name)
        dod = next(g for g in pep.modifier_groups if g.name == "Dodatki")
        assert dod.group_type == "required"
        assert dod.min_selections == 1

    def test_default_choice(self, cdn, adapter):
        pep = next(i for i in self._items(cdn, adapter) if "Pepperoni" in i.platform_name)
        dod = next(g for g in pep.modifier_groups if g.name == "Dodatki")
        ser = next(o for o in dod.options if "ser" in o.name.lower())
        assert ser.is_default is True  # defaultChoices=1

    def test_no_modifiers(self, cdn, adapter):
        cola = next(i for i in self._items(cdn, adapter) if "Cola" in i.platform_name)
        assert cola.price_grosz == 800
        assert cola.modifier_groups == []

    def test_category(self, cdn, adapter):
        marg = next(i for i in self._items(cdn, adapter) if "Margherita" in i.platform_name)
        assert marg.category_name == "Pizze"

    def test_diacritics(self, cdn, adapter):
        pep = next(i for i in self._items(cdn, adapter) if "Pepperoni" in i.platform_name)
        dod = next(g for g in pep.modifier_groups if g.name == "Dodatki")
        jal = next(o for o in dod.options if "Jalap" in o.name)
        assert jal.normalized_name == "jalapeno"


# ═══════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_empty_search(self):
        assert PyszneSearchResponse.model_validate({"restaurants": []}).real_restaurants() == []

    def test_empty_cdn(self):
        cdn = PyszneCdn.model_validate({"items": {}, "restaurant": {"menus": []}})
        assert cdn.get_categories() == []

    def test_no_variations(self, adapter):
        from app.scraper.adapters.pyszne_schemas import PyszneCdnItem
        n = adapter._normalize_item(PyszneCdnItem(id="x", name="X"), "C", 0, {}, {})
        assert n.price_grosz == 0

    def test_missing_mod_set(self, adapter):
        from app.scraper.adapters.pyszne_schemas import PyszneModifierGroupEntry
        g = PyszneModifierGroupEntry(id="g", name="G", modifiers=["missing"])
        mg = adapter._normalize_modifier_group(g, 0, {})
        assert mg.options == []

    def test_extra_fields(self):
        r = PyszneRestaurant.model_validate({"uniqueName": "t", "isDelivery": True, "x": 1})
        assert r.uniqueName == "t"

    def test_no_fee(self):
        assert PyszneRestaurant(uniqueName="t", name="T").delivery_fee_grosz == 0

    def test_cdn_path_fallback(self):
        data = {"props": {"initialState": {"menu": {"restaurant": {"cdn": {"items": {}}}}}}}
        assert extract_cdn(data) is not None

    def test_items_as_list_converted_to_dict(self):
        """Some restaurants (KFC) have items as list instead of dict."""
        cdn = PyszneCdn.model_validate({
            "items": [
                {"id": "item-1", "name": "Burger", "variations": [
                    {"id": "v1", "name": "", "basePrice": 25, "modifierGroupsIds": []}
                ]},
                {"id": "item-2", "name": "Cola", "variations": [
                    {"id": "v2", "name": "", "basePrice": 8, "modifierGroupsIds": []}
                ]},
            ],
            "modifierGroups": [],
            "modifierSets": [],
            "restaurant": {"menus": []},
        })
        assert isinstance(cdn.items, dict)
        assert len(cdn.items) == 2
        assert "item-1" in cdn.items
        assert cdn.items["item-1"].name == "Burger"
        assert cdn.items["item-2"].variations[0].price_grosz == 800
