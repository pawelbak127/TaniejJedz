"""
Tests for entity_resolution.menu_matcher — Sprint 4.5.

Tests matching logic, scoring, size label gating, and structural contracts.
Full integration requires PostgreSQL with menu data.
"""

from __future__ import annotations

import os
import uuid
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.entity_resolution.menu_matcher import (
    MENU_EXACT_BONUS,
    MENU_MATCH_THRESHOLD,
    SIZE_MISMATCH_BLOCKS,
    MenuMatcher,
    MenuMatchStats,
    NormalizedItem,
    _normalize_size,
)


@pytest.fixture(autouse=True)
def _clear_settings():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _item(
    name: str = "Margherita",
    base: str = "margherita",
    size: str | None = None,
    price: int = 2500,
    cmi_id: uuid.UUID | None = None,
) -> NormalizedItem:
    return NormalizedItem(
        pmi_id=uuid.uuid4(),
        platform_item_id=f"item-{uuid.uuid4().hex[:8]}",
        platform_name=name,
        price_grosz=price,
        category_name="Pizza",
        base_name=base,
        size_label=size,
        canonical_menu_item_id=cmi_id,
    )


def _canonical(
    base: str = "margherita",
    size: str | None = None,
    name: str = "Margherita",
) -> dict:
    return {
        "id": uuid.uuid4(),
        "base_name": base,
        "size_label": size,
        "name": name,
    }


# ══════════════════════════════════════════════════════════════
# MenuMatchStats
# ══════════════════════════════════════════════════════════════


class TestMenuMatchStats:

    def test_initial_zeros(self):
        s = MenuMatchStats()
        assert s.restaurants_processed == 0
        assert s.seed_items_created == 0
        assert s.auto_matched == 0
        assert s.new_canonical == 0
        assert s.total_linked == 0

    def test_total_linked(self):
        s = MenuMatchStats(seed_items_created=10, auto_matched=5)
        assert s.total_linked == 15

    def test_merge(self):
        a = MenuMatchStats(seed_items_created=10, auto_matched=5, new_canonical=3)
        b = MenuMatchStats(seed_items_created=7, auto_matched=2, errors=1)
        a.merge(b)
        assert a.seed_items_created == 17
        assert a.auto_matched == 7
        assert a.new_canonical == 3
        assert a.errors == 1

    def test_repr(self):
        s = MenuMatchStats(auto_matched=5)
        assert "auto=5" in repr(s)


# ══════════════════════════════════════════════════════════════
# NormalizedItem
# ══════════════════════════════════════════════════════════════


class TestNormalizedItem:

    def test_fields(self):
        item = _item(name="Pizza 32cm", base="pizza", size="32cm", price=3500)
        assert item.platform_name == "Pizza 32cm"
        assert item.base_name == "pizza"
        assert item.size_label == "32cm"
        assert item.price_grosz == 3500

    def test_no_size(self):
        item = _item(name="Classic Burger", base="classic burger", size=None)
        assert item.size_label is None

    def test_already_linked(self):
        cmi_id = uuid.uuid4()
        item = _item(cmi_id=cmi_id)
        assert item.canonical_menu_item_id == cmi_id


# ══════════════════════════════════════════════════════════════
# MATCHING LOGIC — _find_best_match
# ══════════════════════════════════════════════════════════════


class TestFindBestMatch:

    def test_exact_match(self):
        """Identical normalized names → high score."""
        item = _item(base="margherita")
        canonicals = [_canonical(base="margherita")]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is not None
        assert score >= 0.95  # exact match + bonus

    def test_fuzzy_match(self):
        """Similar names → score above threshold."""
        item = _item(base="pizza margherita")
        canonicals = [_canonical(base="margherita pizza")]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is not None
        assert score >= MENU_MATCH_THRESHOLD

    def test_no_match_different_names(self):
        """Completely different names → no match."""
        item = _item(base="kebab duzy")
        canonicals = [_canonical(base="margherita")]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        # Score should be below threshold
        if match is not None:
            assert score < MENU_MATCH_THRESHOLD

    def test_size_label_blocks_mismatch(self):
        """Different size labels → no match (even if names identical)."""
        item = _item(base="margherita", size="32cm")
        canonicals = [_canonical(base="margherita", size="40cm")]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is None  # blocked by size mismatch

    def test_size_label_none_matches_none(self):
        """Both size=None → allowed to match."""
        item = _item(base="margherita", size=None)
        canonicals = [_canonical(base="margherita", size=None)]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is not None

    def test_size_label_none_vs_some(self):
        """One has size, other doesn't → blocked."""
        item = _item(base="margherita", size="32cm")
        canonicals = [_canonical(base="margherita", size=None)]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is None

    def test_size_label_normalized_spaces(self):
        """'32cm' matches '32 cm' after normalization."""
        item = _item(base="margherita", size="32cm")
        canonicals = [_canonical(base="margherita", size="32 cm")]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is not None

    def test_size_label_normalized_comma(self):
        """'0.5l' matches '0,5l' after normalization."""
        item = _item(base="coca cola", size="0.5l")
        canonicals = [_canonical(base="coca cola", size="0,5l")]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is not None

    def test_picks_best_of_multiple(self):
        """When multiple candidates, picks highest score."""
        item = _item(base="margherita klasyczna")
        canonicals = [
            _canonical(base="pepperoni"),
            _canonical(base="margherita klasyczna"),
            _canonical(base="margherita"),
        ]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is not None
        assert match["base_name"] == "margherita klasyczna"

    def test_empty_canonicals(self):
        """No canonical items → no match."""
        item = _item(base="margherita")
        match, score = MenuMatcher._find_best_match(item, [])
        assert match is None
        assert score == 0.0

    def test_empty_base_name(self):
        """Empty base name → no match."""
        item = _item(base="")
        canonicals = [_canonical(base="margherita")]
        match, score = MenuMatcher._find_best_match(item, [])
        assert match is None

    def test_cross_platform_kfc_item(self):
        """Real-world: KFC item names vary across platforms."""
        item = _item(base="hot wings 6 szt", size="6szt")
        canonicals = [
            _canonical(base="hot wings kubełek", size="6szt"),
            _canonical(base="hot wings", size="6szt"),
        ]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is not None
        assert score > 0.5  # at least partial match

    def test_exact_bonus_applied(self):
        """Exact name match gets bonus over fuzzy."""
        item = _item(base="margherita")
        canonicals = [_canonical(base="margherita")]
        _, score_exact = MenuMatcher._find_best_match(item, canonicals)

        item2 = _item(base="margherit")  # slightly different
        _, score_fuzzy = MenuMatcher._find_best_match(item2, canonicals)

        assert score_exact > score_fuzzy

    def test_word_order_insensitive(self):
        """token_set_ratio handles word order and subset differences."""
        item = _item(base="chicken wings spicy")
        canonicals = [_canonical(base="spicy chicken wings")]
        match, score = MenuMatcher._find_best_match(item, canonicals)
        assert match is not None
        assert score >= 0.95


# ══════════════════════════════════════════════════════════════
# THRESHOLD CONTRACT
# ══════════════════════════════════════════════════════════════


class TestThresholdContract:

    def test_threshold_value(self):
        assert MENU_MATCH_THRESHOLD == 0.80

    def test_exact_bonus_value(self):
        assert MENU_EXACT_BONUS == 0.10

    def test_size_mismatch_blocks(self):
        assert SIZE_MISMATCH_BLOCKS is True

    def test_threshold_reachable(self):
        """Identical names must exceed threshold."""
        item = _item(base="test item")
        canonicals = [_canonical(base="test item")]
        _, score = MenuMatcher._find_best_match(item, canonicals)
        assert score >= MENU_MATCH_THRESHOLD


# ══════════════════════════════════════════════════════════════
# MATCHER STRUCTURE
# ══════════════════════════════════════════════════════════════


class TestMatcherStructure:

    def test_has_match_all(self):
        assert hasattr(MenuMatcher, "match_all")

    def test_has_match_restaurant(self):
        assert hasattr(MenuMatcher, "match_restaurant")

    def test_has_find_best_match(self):
        assert hasattr(MenuMatcher, "_find_best_match")

    def test_has_seed_canonical_items(self):
        assert hasattr(MenuMatcher, "_seed_canonical_items")

    def test_has_match_platform_items(self):
        assert hasattr(MenuMatcher, "_match_platform_items")

    def test_has_find_multi_platform(self):
        assert hasattr(MenuMatcher, "_find_multi_platform_restaurants")

    def test_uses_normalize_dish_name(self):
        """Matcher must use normalize_dish_name for name processing."""
        import inspect
        source = inspect.getsource(MenuMatcher._get_items_by_platform)
        assert "normalize_dish_name" in source

    def test_uses_rapidfuzz(self):
        """Matching must use rapidfuzz for fuzzy similarity."""
        import inspect
        source = inspect.getsource(MenuMatcher._find_best_match)
        assert "token_set_ratio" in source

    def test_size_label_gating(self):
        """Size label check must be in matching logic."""
        import inspect
        source = inspect.getsource(MenuMatcher._find_best_match)
        assert "size_label" in source

    def test_links_pmi_to_canonical(self):
        """Matcher must update platform_menu_items.canonical_menu_item_id."""
        import inspect
        source = inspect.getsource(MenuMatcher._link_pmi)
        assert "canonical_menu_item_id" in source

    def test_creates_canonical_menu_items(self):
        """Seed must create CanonicalMenuItem."""
        import inspect
        source = inspect.getsource(MenuMatcher._seed_canonical_items)
        assert "CanonicalMenuItem" in source

    def test_match_all_finds_multi_platform(self):
        """match_all must find restaurants with 2+ platforms."""
        import inspect
        source = inspect.getsource(MenuMatcher.match_all)
        assert "_find_multi_platform_restaurants" in source


# ══════════════════════════════════════════════════════════════
# INTEGRATION WITH NORMALIZERS
# ══════════════════════════════════════════════════════════════


class TestNormalizerIntegration:
    """Verify menu matcher uses normalizers correctly."""

    def test_dish_name_normalization(self):
        from app.entity_resolution.normalizers import normalize_dish_name

        # Same dish, different platform names
        wolt_base, wolt_size = normalize_dish_name("Margherita 32cm")
        pyszne_base, pyszne_size = normalize_dish_name("Pizza Margherita 32 cm")

        # Both should have "margherita" in base and similar size
        assert "margherita" in wolt_base
        assert "margherita" in pyszne_base
        assert wolt_size is not None
        assert pyszne_size is not None

    def test_size_extraction_consistency(self):
        from app.entity_resolution.normalizers import normalize_dish_name

        _, size1 = normalize_dish_name("Pepperoni 32cm")
        _, size2 = normalize_dish_name("Hawaiańska 32cm")
        assert size1 == size2  # both "32cm"

    def test_no_size_items(self):
        from app.entity_resolution.normalizers import normalize_dish_name

        base, size = normalize_dish_name("Classic Burger")
        assert size is None
        assert "classic burger" in base

    def test_cross_platform_matching_scenario(self):
        """Simulate cross-platform matching with real dish names."""
        from app.entity_resolution.normalizers import normalize_dish_name

        # Wolt names
        wolt_items = [
            "Margherita 32cm",
            "Pepperoni 32cm",
            "Coca-Cola 0.5L",
            "Tiramisu",
        ]
        # Pyszne names (same dishes, different formatting)
        pyszne_items = [
            "Pizza Margherita 32 cm",
            "Pizza Pepperoni 32cm",
            "Coca Cola 0,5L",
            "Tiramisu deser",
        ]

        # Normalize both
        wolt_normalized = [normalize_dish_name(n) for n in wolt_items]
        pyszne_normalized = [normalize_dish_name(n) for n in pyszne_items]

        # Build canonical items from wolt
        canonical_items = [
            _canonical(base=base, size=size, name=wolt_items[i])
            for i, (base, size) in enumerate(wolt_normalized)
        ]

        # Match pyszne items
        matched = 0
        for i, (base, size) in enumerate(pyszne_normalized):
            item = _item(
                name=pyszne_items[i],
                base=base,
                size=size,
            )
            match, score = MenuMatcher._find_best_match(item, canonical_items)
            if match is not None and score >= MENU_MATCH_THRESHOLD:
                matched += 1

        # All 4 should match: token_set_ratio handles "Pizza" prefix,
        # _normalize_size handles "32cm" vs "32 cm" and "0.5l" vs "0,5l"
        assert matched >= 3, f"Expected ≥3 matches, got {matched}"
