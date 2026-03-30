"""
Tests for entity_resolution.restaurant_matcher — Sprint 4.3.

Structural and contract tests. Full integration requires PostgreSQL
with PostGIS extensions (see README for verification steps).
"""

from __future__ import annotations

import os
import uuid
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.entity_resolution.restaurant_matcher import (
    MatchResult,
    MatchStats,
    RestaurantMatcher,
    ScoredCandidate,
)


@pytest.fixture(autouse=True)
def _clear_settings():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ══════════════════════════════════════════════════════════════
# MatchResult
# ══════════════════════════════════════════════════════════════


class TestMatchResult:

    def test_auto_match(self):
        r = MatchResult(
            platform_restaurant_id=uuid.uuid4(),
            decision="auto_match",
            canonical_restaurant_id=uuid.uuid4(),
            confidence=0.92,
        )
        assert r.decision == "auto_match"
        assert r.confidence == 0.92

    def test_review(self):
        r = MatchResult(
            platform_restaurant_id=uuid.uuid4(),
            decision="review",
            confidence=0.72,
        )
        assert r.decision == "review"

    def test_new_canonical(self):
        r = MatchResult(
            platform_restaurant_id=uuid.uuid4(),
            decision="new_canonical",
        )
        assert r.canonical_restaurant_id is None
        assert r.confidence == 0.0

    def test_skipped(self):
        r = MatchResult(
            platform_restaurant_id=uuid.uuid4(),
            decision="skipped",
            match_details={"reason": "no_coordinates"},
        )
        assert r.match_details["reason"] == "no_coordinates"


# ══════════════════════════════════════════════════════════════
# MatchStats
# ══════════════════════════════════════════════════════════════


class TestMatchStats:

    def test_initial_zeros(self):
        s = MatchStats()
        assert s.auto_matched == 0
        assert s.review_queue == 0
        assert s.new_canonical == 0
        assert s.total_processed == 0

    def test_total_processed(self):
        s = MatchStats(auto_matched=10, review_queue=5, new_canonical=3)
        assert s.total_processed == 18

    def test_merge(self):
        a = MatchStats(auto_matched=10, review_queue=5, new_canonical=3, errors=1)
        b = MatchStats(auto_matched=7, review_queue=2, new_canonical=1, skipped_no_coords=4)
        a.merge(b)
        assert a.auto_matched == 17
        assert a.review_queue == 7
        assert a.new_canonical == 4
        assert a.errors == 1
        assert a.skipped_no_coords == 4

    def test_repr(self):
        s = MatchStats(auto_matched=5)
        assert "auto=5" in repr(s)


# ══════════════════════════════════════════════════════════════
# ScoredCandidate
# ══════════════════════════════════════════════════════════════


class TestScoredCandidate:

    def test_fields(self):
        c = ScoredCandidate(
            canonical_id=uuid.uuid4(),
            canonical_name="KFC Floriańska",
            normalized_name="florianska kfc",
            latitude=52.23,
            longitude=21.01,
            phone=None,
            total_score=0.92,
            name_score=0.95,
            distance_score=0.88,
            menu_score=0.5,
            phone_score=0.5,
            distance_m=35.0,
        )
        assert c.total_score == 0.92
        assert c.distance_m == 35.0

    def test_default_scores(self):
        c = ScoredCandidate(
            canonical_id=uuid.uuid4(),
            canonical_name="Test",
            normalized_name="test",
            latitude=0.0,
            longitude=0.0,
            phone=None,
        )
        assert c.total_score == 0.0
        assert c.name_score == 0.0


# ══════════════════════════════════════════════════════════════
# SCORING CONTRACT
# ══════════════════════════════════════════════════════════════


class TestScoringContract:
    """Verify scoring weights and thresholds from config."""

    def test_weights_sum_to_one(self):
        from app.config import get_settings
        s = get_settings()
        total = (
            s.match_weight_name
            + s.match_weight_distance
            + s.match_weight_menu_overlap
            + s.match_weight_phone
        )
        assert abs(total - 1.0) < 0.001

    def test_auto_threshold(self):
        from app.config import get_settings
        assert get_settings().match_auto_threshold == 0.85

    def test_review_threshold(self):
        from app.config import get_settings
        assert get_settings().match_review_threshold == 0.60

    def test_auto_above_review(self):
        from app.config import get_settings
        s = get_settings()
        assert s.match_auto_threshold > s.match_review_threshold

    def test_perfect_score_auto_matches(self):
        """All components at 1.0 → total = 1.0 → auto_match."""
        from app.config import get_settings
        s = get_settings()
        score = (
            s.match_weight_name * 1.0
            + s.match_weight_distance * 1.0
            + s.match_weight_menu_overlap * 1.0
            + s.match_weight_phone * 1.0
        )
        assert score >= s.match_auto_threshold

    def test_name_only_match_goes_to_review_or_auto(self):
        """High name + good distance, no menu/phone → weights redistributed to name+distance.
        With redistribution: name=0.545, distance=0.455.
        Score = 0.545*1.0 + 0.455*0.5 = 0.773 → review zone.
        """
        from app.config import get_settings
        s = get_settings()
        # With redistribution, effective weights are name=0.545, dist=0.455
        name_w = s.match_weight_name / (s.match_weight_name + s.match_weight_distance)
        dist_w = s.match_weight_distance / (s.match_weight_name + s.match_weight_distance)
        score = name_w * 1.0 + dist_w * 0.5  # perfect name, moderate distance
        assert s.match_review_threshold <= score

    def test_perfect_name_and_distance_auto_matches(self):
        """With weight redistribution, perfect name + distance → auto_match."""
        from app.config import get_settings
        s = get_settings()
        name_w = s.match_weight_name / (s.match_weight_name + s.match_weight_distance)
        dist_w = s.match_weight_distance / (s.match_weight_name + s.match_weight_distance)
        score = name_w * 1.0 + dist_w * 1.0
        assert score >= s.match_auto_threshold

    def test_low_scores_create_new(self):
        """Low name + far distance → below review threshold → new canonical."""
        from app.config import get_settings
        s = get_settings()
        score = (
            s.match_weight_name * 0.2
            + s.match_weight_distance * 0.1
            + s.match_weight_menu_overlap * 0.5
            + s.match_weight_phone * 0.5
        )
        assert score < s.match_review_threshold


# ══════════════════════════════════════════════════════════════
# MATCHER STRUCTURE
# ══════════════════════════════════════════════════════════════


class TestMatcherStructure:

    def test_platform_order(self):
        """Default platform order should exist."""
        assert RestaurantMatcher.PLATFORM_ORDER == ["wolt", "pyszne", "glovo", "ubereats"]

    def test_has_match_all_platforms(self):
        assert hasattr(RestaurantMatcher, "match_all_platforms")

    def test_has_find_candidates(self):
        assert hasattr(RestaurantMatcher, "_find_candidates")

    def test_has_score_candidate(self):
        assert hasattr(RestaurantMatcher, "_score_candidate")

    def test_has_create_canonicals(self):
        assert hasattr(RestaurantMatcher, "_create_canonicals_from_platform")

    def test_has_match_platform(self):
        assert hasattr(RestaurantMatcher, "_match_platform")

    def test_find_candidates_uses_postigs(self):
        """_find_candidates must use earth_box/ll_to_earth for PostGIS blocking."""
        import inspect
        source = inspect.getsource(RestaurantMatcher._find_candidates)
        assert "earth_box" in source
        assert "ll_to_earth" in source
        assert "earth_distance" in source

    def test_score_uses_all_weights(self):
        """_score_candidate must use all 4 weight components."""
        import inspect
        source = inspect.getsource(RestaurantMatcher._score_candidate)
        assert "match_weight_name" in source
        assert "match_weight_distance" in source
        assert "match_weight_menu_overlap" in source
        assert "match_weight_phone" in source

    def test_match_one_uses_thresholds(self):
        """_match_one must check auto_threshold and review_threshold."""
        import inspect
        source = inspect.getsource(RestaurantMatcher._match_one)
        assert "match_auto_threshold" in source
        assert "match_review_threshold" in source

    def test_first_platform_creates_canonicals(self):
        """match_all_platforms must create canonicals for first platform."""
        import inspect
        source = inspect.getsource(RestaurantMatcher.match_all_platforms)
        assert "_create_canonicals_from_platform" in source

    def test_skips_no_coords(self):
        """_match_one must skip restaurants without coordinates."""
        import inspect
        source = inspect.getsource(RestaurantMatcher._match_one)
        assert "skipped" in source
        assert "no_coordinates" in source

    def test_writes_entity_review_queue(self):
        """Review decisions must INSERT into entity_review_queue."""
        import inspect
        source = inspect.getsource(RestaurantMatcher._match_platform)
        assert "EntityReviewQueue" in source

    def test_dynamic_platform_ordering(self):
        """Platform order should be determined dynamically by count."""
        import inspect
        source = inspect.getsource(RestaurantMatcher.match_all_platforms)
        assert "_get_platform_order" in source
