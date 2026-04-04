"""
Tests for Glovo sitemap discovery job.

Run: pytest tests/test_sync_glovo_slugs.py -v
"""

from __future__ import annotations

import json
import pytest

# We import from the job module directly — these are pure functions, no Redis needed
from app.jobs.sync_glovo_slugs import (
    _is_non_food_slug,
    _parse_sitemap_urls,
    _resolve_city,
    _TRANSLITERATED_CITY_MAP,
)


# ═══════════════════════════════════════════════════════════════
# _resolve_city — transliterated → city_slug
# ═══════════════════════════════════════════════════════════════

class TestResolveCity:
    def test_known_city(self):
        assert _resolve_city("varshava") == "warszawa"

    def test_krakow(self):
        assert _resolve_city("krakiv") == "krakow"

    def test_alternative_rzeszow(self):
        """Both transliterations should map to rzeszow."""
        assert _resolve_city("zheshuv") == "rzeszow"
        assert _resolve_city("ryashiv") == "rzeszow"

    def test_alternative_zielona_gora(self):
        assert _resolve_city("zelyona-gura") == "zielona-gora"
        assert _resolve_city("zelena-gura") == "zielona-gora"

    def test_sitemap_o_alternative_transliterations(self):
        """sitemap-o.xml has different transliterations than sitemap-p.xml."""
        assert _resolve_city("krakov") == "krakow"     # vs krakiv in p.xml
        assert _resolve_city("bydgoshch") == "bydgoszcz"  # vs bidgoshch
        assert _resolve_city("belostok") == "bialystok"    # vs bilostok
        assert _resolve_city("olshtyn") == "olsztyn"       # vs olshtin

    def test_new_cities(self):
        """Cities discovered from live sitemap data."""
        assert _resolve_city("koshalin") == "koszalin"
        assert _resolve_city("plotsk") == "plock"
        assert _resolve_city("elblong") == "elblag"
        assert _resolve_city("kalish") == "kalisz"
        assert _resolve_city("tarnuv") == "tarnow"
        assert _resolve_city("bitom") == "bytom"

    def test_polish_direct_forms(self):
        """Polish city names appearing directly in sitemap-o.xml."""
        assert _resolve_city("katowice") == "katowice"
        assert _resolve_city("bytom") == "bytom"
        assert _resolve_city("tychy") == "tychy"
        assert _resolve_city("koszalin") == "koszalin"

    def test_direct_match(self):
        """Polish city names that match directly."""
        assert _resolve_city("gdansk") == "gdansk"
        assert _resolve_city("poznan") == "poznan"
        assert _resolve_city("opole") == "opole"

    def test_unknown_city(self):
        assert _resolve_city("unknown-city-xyz") is None

    def test_case_insensitive(self):
        assert _resolve_city("Varshava") == "warszawa"
        assert _resolve_city("KRAKIV") == "krakow"


# ═══════════════════════════════════════════════════════════════
# _is_non_food_slug
# ═══════════════════════════════════════════════════════════════

class TestIsNonFoodSlug:
    def test_food_restaurant(self):
        assert not _is_non_food_slug("kfc-waw")
        assert not _is_non_food_slug("pizza-hut-krakow")
        assert not _is_non_food_slug("burger-king-wro")

    def test_pharmacy(self):
        assert _is_non_food_slug("apteczka-zdrowia-waw")
        assert _is_non_food_slug("apteka-centrum")

    def test_grocery(self):
        assert _is_non_food_slug("biedronka-express-mokotow")
        assert _is_non_food_slug("carrefour-express-centrum")
        assert _is_non_food_slug("lidl-krakow")
        assert _is_non_food_slug("zabka-marszalkowska")

    def test_cosmetics(self):
        assert _is_non_food_slug("rossmann-waw")
        assert _is_non_food_slug("hebe-galeria")

    def test_florist(self):
        assert _is_non_food_slug("a-kwiaty-warszawa")
        assert _is_non_food_slug("kwiaciarnia-rosa")

    def test_electronics(self):
        assert _is_non_food_slug("mediamarkt-wola")
        assert _is_non_food_slug("empik-centrum")


# ═══════════════════════════════════════════════════════════════
# _parse_sitemap_urls
# ═══════════════════════════════════════════════════════════════

class TestParseSitemapUrls:
    def _make_sitemap(self, urls: list[str]) -> str:
        locs = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
        return f"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{locs}
</urlset>"""

    def test_basic_extraction(self):
        xml = self._make_sitemap([
            "https://glovoapp.com/pl/ru/varshava/kfc-waw/",
            "https://glovoapp.com/pl/uk/varshava/kfc-waw/",
            "https://glovoapp.com/pl/ru/krakiv/pizza-hut-kra/",
        ])
        pairs = _parse_sitemap_urls(xml)
        # kfc-waw appears in both /ru/ and /uk/ but should be deduped per city
        cities = {city for city, slug in pairs}
        assert "varshava" in cities
        assert "krakiv" in cities

    def test_dedup_across_languages(self):
        """Same city+slug in /ru/ and /uk/ → single entry."""
        xml = self._make_sitemap([
            "https://glovoapp.com/pl/ru/varshava/kfc-waw/",
            "https://glovoapp.com/pl/uk/varshava/kfc-waw/",
        ])
        pairs = _parse_sitemap_urls(xml)
        # Should still appear — dedup is by (city, slug)
        slugs = [slug for city, slug in pairs if slug == "kfc-waw"]
        assert len(slugs) == 1  # Only once despite 2 language variants

    def test_categories_skipped(self):
        xml = self._make_sitemap([
            "https://glovoapp.com/pl/ru/varshava/categories/jedzenie_1/",
            "https://glovoapp.com/pl/ru/varshava/kfc-waw/",
        ])
        pairs = _parse_sitemap_urls(xml)
        slugs = [slug for _, slug in pairs]
        assert "kfc-waw" in slugs
        assert not any("categories" in s for s in slugs)

    def test_non_polish_urls_ignored(self):
        xml = self._make_sitemap([
            "https://glovoapp.com/de/de/berlin/pizza-place/",
            "https://glovoapp.com/pl/ru/varshava/kfc-waw/",
            "https://glovoapp.com/es/es/madrid/tacos/",
        ])
        pairs = _parse_sitemap_urls(xml)
        assert len(pairs) == 1
        assert pairs[0] == ("varshava", "kfc-waw")

    def test_trailing_slash_handling(self):
        xml = self._make_sitemap([
            "https://glovoapp.com/pl/ru/varshava/kfc-waw",
            "https://glovoapp.com/pl/ru/varshava/burger-king-waw/",
        ])
        pairs = _parse_sitemap_urls(xml)
        slugs = [slug for _, slug in pairs]
        assert "kfc-waw" in slugs
        assert "burger-king-waw" in slugs

    def test_empty_sitemap(self):
        xml = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
</urlset>"""
        pairs = _parse_sitemap_urls(xml)
        assert pairs == []

    def test_pl_pl_language_variant(self):
        """URLs with /pl/pl/ should also be matched."""
        xml = self._make_sitemap([
            "https://glovoapp.com/pl/pl/varshava/kfc-waw/",
        ])
        pairs = _parse_sitemap_urls(xml)
        assert len(pairs) == 1
        assert pairs[0] == ("varshava", "kfc-waw")


# ═══════════════════════════════════════════════════════════════
# City map completeness check
# ═══════════════════════════════════════════════════════════════

class TestCityMapCompleteness:
    """Verify all documented transliterations are in the map."""

    EXPECTED_MAPPINGS = {
        # Original transliterations (sitemap-p.xml)
        "varshava": "warszawa",
        "vrotslav": "wroclaw",
        "krakiv": "krakow",
        "gdansk": "gdansk",
        "poznan": "poznan",
        "lodz": "lodz",
        "katovitse": "katowice",
        "shchetsin": "szczecin",
        "lyublin": "lublin",
        "bidgoshch": "bydgoszcz",
        "bilostok": "bialystok",
        "zheshuv": "rzeszow",
        "ryashiv": "rzeszow",
        "olshtin": "olsztyn",
        "sosnovets": "sosnowiec",
        "glivitse": "gliwice",
        "chenstohova": "czestochowa",
        "keltse": "kielce",
        "torun": "torun",
        "zelyona-gura": "zielona-gora",
        "zelena-gura": "zielona-gora",
        "belsko-byala": "bielsko-biala",
        "opole": "opole",
        "vlotslavek": "wloclawek",
        "zakopane": "zakopane",
        "radom": "radom",
        # Alternative transliterations (sitemap-o.xml, discovered live)
        "krakov": "krakow",
        "bydgoshch": "bydgoszcz",
        "belostok": "bialystok",
        "olshtyn": "olsztyn",
        # New cities (top 20 by count)
        "koshalin": "koszalin",
        "plotsk": "plock",
        "elblong": "elblag",
        "kalish": "kalisz",
        "legnitsa": "legnica",
        "ribnik": "rybnik",
        "tarnuv": "tarnow",
        "bitom": "bytom",
        "tihi": "tychy",
        "lomzha": "lomza",
        "tchev": "tczew",
        "sedltse": "siedlce",
        # Direct Polish matches
        "katowice": "katowice",
        "koszalin": "koszalin",
        "bytom": "bytom",
        "tychy": "tychy",
    }

    def test_all_documented_cities_in_map(self):
        for transliterated, expected_slug in self.EXPECTED_MAPPINGS.items():
            actual = _TRANSLITERATED_CITY_MAP.get(transliterated)
            assert actual == expected_slug, (
                f"Missing or wrong mapping: {transliterated} → {actual} "
                f"(expected {expected_slug})"
            )
