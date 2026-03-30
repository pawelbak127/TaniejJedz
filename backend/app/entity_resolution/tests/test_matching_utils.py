"""
Tests for entity_resolution.matching_utils — Sprint 4.3.

Pure function tests — no DB, no mocks needed.
"""

from __future__ import annotations

import pytest

from app.entity_resolution.matching_utils import (
    distance_score,
    haversine_distance,
    jaccard_menu_overlap,
    name_similarity,
    phones_match,
)


# ══════════════════════════════════════════════════════════════
# HAVERSINE DISTANCE
# ══════════════════════════════════════════════════════════════


class TestHaversineDistance:

    def test_same_point(self):
        d = haversine_distance(52.23, 21.01, 52.23, 21.01)
        assert d == 0.0

    def test_short_distance(self):
        """Two points ~100m apart in central Warsaw."""
        d = haversine_distance(52.2297, 21.0122, 52.2306, 21.0122)
        assert 90 < d < 110

    def test_medium_distance(self):
        """Warszawa centrum → Mokotów ~3km."""
        d = haversine_distance(52.2297, 21.0122, 52.2050, 21.0050)
        assert 2000 < d < 4000

    def test_cross_city(self):
        """Warszawa → Kraków ~250km."""
        d = haversine_distance(52.2297, 21.0122, 50.0647, 19.9450)
        assert 250_000 < d < 300_000

    def test_zero_lat_returns_inf(self):
        d = haversine_distance(0.0, 21.01, 52.23, 21.01)
        assert d == float("inf")

    def test_zero_lng_returns_inf(self):
        d = haversine_distance(52.23, 0.0, 52.23, 21.01)
        assert d == float("inf")

    def test_both_zero_returns_inf(self):
        d = haversine_distance(0.0, 0.0, 0.0, 0.0)
        assert d == float("inf")

    def test_symmetry(self):
        d1 = haversine_distance(52.23, 21.01, 50.06, 19.94)
        d2 = haversine_distance(50.06, 19.94, 52.23, 21.01)
        assert abs(d1 - d2) < 0.01


# ══════════════════════════════════════════════════════════════
# NAME SIMILARITY
# ══════════════════════════════════════════════════════════════


class TestNameSimilarity:

    def test_identical(self):
        assert name_similarity("kfc florianska", "kfc florianska") == 1.0

    def test_similar(self):
        score = name_similarity("florianska kfc", "kfc florianska")
        assert score > 0.9  # token_sort handles order

    def test_different(self):
        score = name_similarity("kfc", "pizza hut")
        assert score < 0.3

    def test_partial_overlap(self):
        score = name_similarity("burger king", "burger joint")
        assert 0.3 < score < 0.8

    def test_empty_a(self):
        assert name_similarity("", "kfc") == 0.0

    def test_empty_b(self):
        assert name_similarity("kfc", "") == 0.0

    def test_both_empty(self):
        assert name_similarity("", "") == 0.0

    def test_cross_platform_kfc(self):
        """Same restaurant normalized from different platforms should score high."""
        score = name_similarity("florianska kfc", "florianska kfc")
        assert score >= 0.95

    def test_cross_platform_similar(self):
        """Similar but not identical names."""
        score = name_similarity("bella ciao solec", "bella ciao")
        assert score > 0.7


# ══════════════════════════════════════════════════════════════
# JACCARD MENU OVERLAP
# ══════════════════════════════════════════════════════════════


class TestJaccardMenuOverlap:

    def test_identical(self):
        items = ["margherita", "pepperoni", "hawaii"]
        assert jaccard_menu_overlap(items, items) == 1.0

    def test_no_overlap(self):
        a = ["margherita", "pepperoni"]
        b = ["ramen", "pho"]
        assert jaccard_menu_overlap(a, b) == 0.0

    def test_partial_overlap(self):
        a = ["margherita", "pepperoni", "hawaii"]
        b = ["margherita", "pepperoni", "quattro formaggi"]
        score = jaccard_menu_overlap(a, b)
        assert abs(score - 0.5) < 0.01  # 2 / 4 = 0.5

    def test_empty_a_neutral(self):
        """Empty menu should return 0.5 (neutral), not penalize."""
        assert jaccard_menu_overlap([], ["margherita"]) == 0.5

    def test_empty_b_neutral(self):
        assert jaccard_menu_overlap(["margherita"], []) == 0.5

    def test_both_empty_neutral(self):
        assert jaccard_menu_overlap([], []) == 0.5

    def test_single_match(self):
        score = jaccard_menu_overlap(["margherita"], ["margherita"])
        assert score == 1.0

    def test_duplicates_ignored(self):
        """Sets deduplicate — duplicate items shouldn't inflate score."""
        a = ["margherita", "margherita", "margherita"]
        b = ["margherita"]
        assert jaccard_menu_overlap(a, b) == 1.0


# ══════════════════════════════════════════════════════════════
# PHONE MATCHING
# ══════════════════════════════════════════════════════════════


class TestPhonesMatch:

    def test_identical(self):
        assert phones_match("123456789", "123456789") is True

    def test_with_country_code(self):
        assert phones_match("+48 123 456 789", "123456789") is True

    def test_with_dashes(self):
        assert phones_match("123-456-789", "+48 123 456 789") is True

    def test_with_spaces(self):
        assert phones_match("12 345 67 89", "123456789") is True

    def test_different(self):
        assert phones_match("123456789", "987654321") is False

    def test_none_a(self):
        assert phones_match(None, "123456789") is False

    def test_none_b(self):
        assert phones_match("123456789", None) is False

    def test_both_none(self):
        assert phones_match(None, None) is False

    def test_empty_string(self):
        assert phones_match("", "123456789") is False

    def test_short_number(self):
        assert phones_match("12345", "12345") is False  # < 9 digits


# ══════════════════════════════════════════════════════════════
# DISTANCE SCORE
# ══════════════════════════════════════════════════════════════


class TestDistanceScore:

    def test_zero_distance(self):
        assert distance_score(0.0) == 1.0

    def test_max_radius(self):
        assert distance_score(300.0, 300.0) == 0.0

    def test_beyond_radius(self):
        assert distance_score(500.0, 300.0) == 0.0

    def test_mid_distance(self):
        score = distance_score(150.0, 300.0)
        assert abs(score - 0.5) < 0.01

    def test_inf_distance(self):
        assert distance_score(float("inf")) == 0.0

    def test_custom_radius(self):
        score = distance_score(500.0, 1000.0)
        assert abs(score - 0.5) < 0.01
