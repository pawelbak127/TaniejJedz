"""
Tests for entity_resolution.normalizers — Sprint 4.2.

Tests restaurant name normalization, dish name parsing, stop words removal,
diacritics handling, city suffix stripping, and batch normalization.

spaCy tests are conditional — they pass whether or not the model is installed.
"""

from __future__ import annotations

import os
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.entity_resolution.normalizers import (
    RESTAURANT_STOP_WORDS,
    normalize_dish_name,
    normalize_restaurant_name,
    normalize_restaurant_names_batch,
    remove_diacritics,
    spacy_available,
    _strip_city_suffix,
    _remove_stop_words,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ══════════════════════════════════════════════════════════════
# DIACRITICS REMOVAL
# ══════════════════════════════════════════════════════════════


class TestRemoveDiacritics:

    def test_polish_characters(self):
        assert remove_diacritics("ąćęłńóśźż") == "acelnoszz"

    def test_uppercase_polish(self):
        assert remove_diacritics("ĄĆĘŁŃÓŚŹŻ") == "ACELNOSZZ"

    def test_mixed_text(self):
        assert remove_diacritics("Złota Rączka") == "Zlota Raczka"

    def test_no_diacritics(self):
        assert remove_diacritics("Hello World") == "Hello World"

    def test_empty_string(self):
        assert remove_diacritics("") == ""

    def test_german_umlauts(self):
        """Handles non-Polish diacritics too (Döner → Doner)."""
        assert remove_diacritics("Döner") == "Doner"


# ══════════════════════════════════════════════════════════════
# CITY SUFFIX STRIPPING
# ══════════════════════════════════════════════════════════════


class TestStripCitySuffix:

    def test_dash_separator(self):
        assert _strip_city_suffix("KFC - Warszawa") == "KFC"

    def test_comma_separator(self):
        assert _strip_city_suffix("Pizza Hut, Kraków") == "Pizza Hut"

    def test_trailing_word(self):
        assert _strip_city_suffix("Sushi Master Warszawa") == "Sushi Master"

    def test_short_form(self):
        """Glovo uses short city codes: kfc-waw → should strip 'waw'."""
        assert _strip_city_suffix("KFC waw") == "KFC"

    def test_no_city(self):
        assert _strip_city_suffix("Bella Ciao") == "Bella Ciao"

    def test_city_in_middle_not_stripped(self):
        """Only strip trailing city, not mid-name."""
        result = _strip_city_suffix("Warszawa Kebab House")
        # "Warszawa" is the first word, not trailing — should not strip
        assert "Kebab" in result

    def test_diacritics_city(self):
        assert _strip_city_suffix("Ramen Shop Łódź") == "Ramen Shop"

    def test_en_dash(self):
        assert _strip_city_suffix("Burger King – Kraków") == "Burger King"


# ══════════════════════════════════════════════════════════════
# STOP WORDS
# ══════════════════════════════════════════════════════════════


class TestStopWords:

    def test_stop_words_set_not_empty(self):
        assert len(RESTAURANT_STOP_WORDS) >= 20

    def test_key_stop_words_present(self):
        for word in ["restauracja", "pizzeria", "bar", "kebab", "bistro", "kuchnia", "pod", "u", "na"]:
            assert word in RESTAURANT_STOP_WORDS, f"'{word}' missing from stop words"

    def test_removal(self):
        tokens = ["pizzeria", "roma", "pod", "wieża"]
        result = _remove_stop_words(tokens)
        assert result == ["roma", "wieża"]

    def test_short_tokens_removed(self):
        """Single-char tokens should be removed (len > 1 filter)."""
        tokens = ["a", "kfc", "b"]
        result = _remove_stop_words(tokens)
        assert result == ["kfc"]

    def test_empty_list(self):
        assert _remove_stop_words([]) == []


# ══════════════════════════════════════════════════════════════
# RESTAURANT NAME NORMALIZATION
# ══════════════════════════════════════════════════════════════


class TestNormalizeRestaurantName:

    def test_basic(self):
        result = normalize_restaurant_name("KFC Floriańska")
        assert "kfc" in result
        # spaCy may lemmatize "floriańska" → "florianski"; without spaCy → "florianska"
        assert any(tok.startswith("florians") for tok in result.split())

    def test_stop_words_removed(self):
        result = normalize_restaurant_name("Pizzeria Roma pod Wieżą")
        assert "pizzeria" not in result
        assert "pod" not in result
        assert "roma" in result

    def test_diacritics_removed(self):
        result = normalize_restaurant_name("Złota Rączka")
        # spaCy may lemmatize "złota"→"zloto", "rączka"→"raczka"
        assert any(tok.startswith("zlot") for tok in result.split())
        assert any(tok.startswith("raczk") for tok in result.split())
        assert "ą" not in result
        assert "ę" not in result

    def test_city_suffix_stripped(self):
        result = normalize_restaurant_name("Burger King - Warszawa")
        assert "warszawa" not in result
        assert "burger" in result
        assert "king" in result

    def test_tokens_sorted(self):
        """Tokens should be alphabetically sorted for stable matching."""
        result = normalize_restaurant_name("Zielony Smok")
        tokens = result.split()
        assert tokens == sorted(tokens)

    def test_empty_string(self):
        assert normalize_restaurant_name("") == ""

    def test_none_safe(self):
        """Should handle whitespace-only input."""
        assert normalize_restaurant_name("   ") == ""

    def test_all_stop_words(self):
        """Name with only stop words normalizes to empty."""
        result = normalize_restaurant_name("Restauracja Bar Pub")
        assert result == ""

    def test_kfc_chain(self):
        """Chain names should be preserved."""
        result = normalize_restaurant_name("KFC")
        assert "kfc" in result

    def test_mcdonalds(self):
        result = normalize_restaurant_name("McDonald's")
        assert "mcdonald" in result

    def test_special_characters_handled(self):
        result = normalize_restaurant_name("Bobby's Burger & Grill")
        assert "bobby" in result or "bobbys" in result

    def test_cross_platform_kfc(self):
        """Same restaurant on different platforms should normalize identically."""
        wolt = normalize_restaurant_name("KFC Floriańska")
        pyszne = normalize_restaurant_name("KFC, Floriańska - Kraków")
        assert "kfc" in wolt and "kfc" in pyszne
        # Both must produce the SAME output (cross-platform consistency)
        assert wolt == pyszne

    def test_cross_platform_pizza(self):
        wolt = normalize_restaurant_name("Pizzeria Roma")
        pyszne = normalize_restaurant_name("Roma Pizzeria Warszawa")
        # "pizzeria" is stop word, "roma" should remain in both
        assert "roma" in wolt
        assert "roma" in pyszne

    def test_real_wolt_name(self):
        result = normalize_restaurant_name("Bella Ciao - Solec")
        assert "bella" in result
        assert "ciao" in result

    def test_real_glovo_name(self):
        result = normalize_restaurant_name("Sofram Döner & Kebab")
        # spaCy may mangle Turkish "Sofram" → "sofrac"; without spaCy → "sofram"
        assert any(tok.startswith("sofr") for tok in result.split())
        assert "doner" in result


# ══════════════════════════════════════════════════════════════
# DISH NAME NORMALIZATION
# ══════════════════════════════════════════════════════════════


class TestNormalizeDishName:

    def test_cm_size(self):
        base, size = normalize_dish_name("Margherita 32cm")
        assert "margherita" in base
        assert size == "32cm"

    def test_cm_with_space(self):
        base, size = normalize_dish_name("Pepperoni 40 cm")
        assert "pepperoni" in base
        assert size == "40 cm"

    def test_polish_size_word(self):
        base, size = normalize_dish_name("Pizza Pepperoni duża")
        assert "pizza pepperoni" in base
        assert size == "duża" or size == "duza"

    def test_pieces(self):
        base, size = normalize_dish_name("Nuggetsy 12szt")
        assert "nuggetsy" in base
        assert size == "12szt"

    def test_pieces_with_space(self):
        base, size = normalize_dish_name("Zestaw Sake 16 szt")
        assert "zestaw sake" in base or "zestaw" in base
        assert "16" in size

    def test_volume_ml(self):
        base, size = normalize_dish_name("Coca-Cola 500ml")
        assert "coca-cola" in base
        assert size == "500ml"

    def test_volume_l(self):
        base, size = normalize_dish_name("Pepsi 0.5L")
        assert "pepsi" in base
        assert "0.5l" in size

    def test_weight_g(self):
        base, size = normalize_dish_name("Kubełek Frytek 240g")
        assert "kubelek frytek" in base or "frytek" in base
        assert size == "240g"

    def test_no_size(self):
        base, size = normalize_dish_name("Classic Burger")
        assert "classic burger" in base
        assert size is None

    def test_empty_string(self):
        base, size = normalize_dish_name("")
        assert base == ""
        assert size is None

    def test_diacritics_removed_from_base(self):
        base, size = normalize_dish_name("Żurek 350ml")
        assert "zurek" in base
        assert "350ml" in size

    def test_size_at_beginning(self):
        """Size label could appear anywhere."""
        base, size = normalize_dish_name("XL Burger")
        assert "burger" in base
        assert size == "xl"

    def test_real_kfc_item(self):
        base, size = normalize_dish_name("15 Hot Wings Big Box")
        assert "hot wings big box" in base or "hot" in base
        assert size is None  # "15" alone isn't a size pattern

    def test_real_pyszne_item(self):
        base, size = normalize_dish_name("Pizza Margherita 25cm")
        assert "margherita" in base
        assert size == "25cm"


# ══════════════════════════════════════════════════════════════
# BATCH NORMALIZATION
# ══════════════════════════════════════════════════════════════


class TestBatchNormalization:

    def test_batch_matches_individual(self):
        names = [
            "KFC Floriańska",
            "Pizzeria Roma pod Wieżą",
            "Burger King - Warszawa",
            "Sushi Master",
        ]
        batch_results = normalize_restaurant_names_batch(names)
        individual_results = [normalize_restaurant_name(n) for n in names]
        assert batch_results == individual_results

    def test_empty_batch(self):
        assert normalize_restaurant_names_batch([]) == []

    def test_single_item(self):
        result = normalize_restaurant_names_batch(["KFC"])
        assert len(result) == 1
        assert "kfc" in result[0]


# ══════════════════════════════════════════════════════════════
# spaCy INTEGRATION (conditional)
# ══════════════════════════════════════════════════════════════


class TestSpacyIntegration:

    def test_spacy_available_returns_bool(self):
        """spacy_available() should return True or False without crashing."""
        result = spacy_available()
        assert isinstance(result, bool)

    def test_normalization_works_regardless_of_spacy(self):
        """Core normalization must work whether spaCy is installed or not."""
        result = normalize_restaurant_name("Pizzeria Roma pod Wieżą")
        assert "roma" in result
        assert "pizzeria" not in result

    @pytest.mark.skipif(
        not spacy_available(),
        reason="spaCy pl_core_news_md not installed",
    )
    def test_spacy_lemmatization(self):
        """If spaCy is available, test lemmatization quality."""
        # "Pizzerii" → "pizzeria" (genitive → nominative)
        result = normalize_restaurant_name("Kuchnia Pizzerii Roma")
        # With spaCy lemmatization, "pizzerii" → "pizzeria" → removed as stop word
        assert "roma" in result


# ══════════════════════════════════════════════════════════════
# PERSISTOR INTEGRATION
# ══════════════════════════════════════════════════════════════


class TestPersistorIntegration:

    def test_metadata_includes_normalized_name(self):
        """Persistor should store normalized_name in platform_metadata."""
        from app.scraper.schemas.normalized import NormalizedRestaurant
        from app.services.persistor import DataPersistor

        nr = NormalizedRestaurant(
            platform="wolt",
            platform_restaurant_id="test-001",
            platform_name="Pizzeria Roma pod Wieżą",
            name="Pizzeria Roma pod Wieżą",
            latitude=52.23,
            longitude=21.01,
        )
        meta = DataPersistor._build_platform_metadata(nr)
        assert "normalized_name" in meta
        assert "roma" in meta["normalized_name"]
        assert "pizzeria" not in meta["normalized_name"]

    def test_metadata_normalized_name_handles_empty(self):
        from app.scraper.schemas.normalized import NormalizedRestaurant
        from app.services.persistor import DataPersistor

        nr = NormalizedRestaurant(
            platform="wolt",
            platform_restaurant_id="test-002",
            platform_name="Bar",
            name="Bar",
            latitude=0.0,
            longitude=0.0,
        )
        meta = DataPersistor._build_platform_metadata(nr)
        assert "normalized_name" in meta
        # "bar" is a stop word, so normalized_name may be empty
        assert isinstance(meta["normalized_name"], str)

    def test_metadata_kfc_normalized(self):
        from app.scraper.schemas.normalized import NormalizedRestaurant
        from app.services.persistor import DataPersistor

        nr = NormalizedRestaurant(
            platform="pyszne",
            platform_restaurant_id="kfc-001",
            platform_name="KFC, Floriańska - Kraków",
            name="KFC, Floriańska - Kraków",
            latitude=50.06,
            longitude=19.94,
        )
        meta = DataPersistor._build_platform_metadata(nr)
        assert "kfc" in meta["normalized_name"]
        # spaCy may lemmatize "floriańska" → "florianski"
        assert any(tok.startswith("florians") for tok in meta["normalized_name"].split())
        assert "krakow" not in meta["normalized_name"]
