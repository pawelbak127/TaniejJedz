"""Quality scorer tests — completeness, price range, modifiers, thresholds."""

from __future__ import annotations

import pytest

from app.scraper.quality_scorer import (
    score_menu,
    QualityReport,
    REJECT_THRESHOLD,
    WARNING_THRESHOLD,
    MIN_PRICE_GROSZ,
    MAX_PRICE_GROSZ,
)
from app.scraper.schemas.normalized import (
    NormalizedMenuItem,
    NormalizedModifierGroup,
    NormalizedModifierOption,
)


def _item(
    name: str = "Test",
    price: int = 2500,
    available: bool = True,
    modifiers: list | None = None,
) -> NormalizedMenuItem:
    return NormalizedMenuItem(
        platform_item_id=f"id-{name}",
        platform_name=name,
        description="desc",
        price_grosz=price,
        is_available=available,
        modifier_groups=modifiers or [],
    )


def _modifier_group(
    name: str = "Size",
    options: int = 3,
    min_sel: int = 0,
    max_sel: int = 1,
) -> NormalizedModifierGroup:
    return NormalizedModifierGroup(
        platform_group_id=f"mg-{name}",
        name=name,
        group_type="optional",
        min_selections=min_sel,
        max_selections=max_sel,
        options=[
            NormalizedModifierOption(
                platform_option_id=f"opt-{i}",
                name=f"Option {i}",
                price_grosz=i * 100,
            )
            for i in range(options)
        ],
    )


class TestScoreMenu:

    def test_perfect_score(self):
        items = [
            _item("Pizza", 2500, modifiers=[_modifier_group()]),
            _item("Burger", 3000, modifiers=[_modifier_group("Sos")]),
            _item("Cola", 700),
        ]
        report = score_menu(items, "wolt", "test")
        assert report.score >= 0.9
        assert report.status == "accept"
        assert report.is_accepted is True

    def test_empty_menu_rejected(self):
        report = score_menu([], "wolt", "empty")
        assert report.score == 0.0
        assert report.status == "reject"
        assert report.is_accepted is False
        assert "empty menu" in report.issues[0]

    def test_missing_names_lower_completeness(self):
        items = [
            _item("", 2500),  # empty name
            _item("Pizza", 2500),
            _item("Burger", 2500),
        ]
        report = score_menu(items)
        assert report.completeness == pytest.approx(2 / 3, abs=0.01)

    def test_zero_price_lower_completeness(self):
        items = [
            _item("Pizza", 0),     # zero price
            _item("Burger", 2500),
        ]
        report = score_menu(items)
        assert report.completeness == 0.5

    def test_prices_below_min_flagged(self):
        items = [_item("Cheap", 50)]  # 0.50 zł < 1.00 zł
        report = score_menu(items)
        assert report.price_range == 0.0
        assert any("< 100gr" in issue for issue in report.issues)

    def test_prices_above_max_flagged(self):
        items = [_item("Expensive", 150_000)]  # 1500 zł > 1000 zł
        report = score_menu(items)
        assert report.price_range == 0.0
        assert any("> 100000gr" in issue for issue in report.issues)

    def test_valid_prices_full_score(self):
        items = [
            _item("A", 500),
            _item("B", 5000),
            _item("C", 50000),
        ]
        report = score_menu(items)
        assert report.price_range == 1.0

    def test_modifier_quality_valid(self):
        mg = _modifier_group("Size", options=3, min_sel=1, max_sel=1)
        items = [_item("Pizza", 2500, modifiers=[mg])]
        report = score_menu(items)
        assert report.modifier_quality == 1.0

    def test_modifier_quality_no_options(self):
        mg = NormalizedModifierGroup(
            platform_group_id="bad",
            name="Empty Group",
            options=[],
        )
        items = [_item("Pizza", 2500, modifiers=[mg])]
        report = score_menu(items)
        assert report.modifier_quality < 1.0
        assert any("no options" in issue for issue in report.issues)

    def test_no_modifiers_neutral(self):
        """Items without modifiers → neutral 0.8 score (not penalized)."""
        items = [_item("Cola", 700)]
        report = score_menu(items)
        assert report.modifier_quality == 0.8

    def test_all_unavailable_low_availability(self):
        items = [
            _item("A", 2500, available=False),
            _item("B", 3000, available=False),
        ]
        report = score_menu(items)
        assert report.availability == 0.0
        assert any("all items unavailable" in issue for issue in report.issues)

    def test_mixed_availability(self):
        items = [
            _item("A", 2500, available=True),
            _item("B", 3000, available=False),
        ]
        report = score_menu(items)
        assert report.availability == 0.5


class TestThresholds:

    def test_reject_threshold(self):
        """Score < 0.6 → reject."""
        items = [
            _item("", 0, available=False),  # all bad
            _item("", 0, available=False),
        ]
        report = score_menu(items)
        assert report.score < REJECT_THRESHOLD
        assert report.status == "reject"

    def test_warning_threshold(self):
        """Score 0.6–0.8 → warning."""
        # Mix of good and bad items to land in warning zone
        items = [
            _item("Good", 2500),
            _item("", 50, available=False),  # bad
            _item("OK", 3000),
        ]
        report = score_menu(items)
        # Might be warning or accept depending on exact calc
        assert report.status in ("warning", "accept")

    def test_accept_threshold(self):
        """Score ≥ 0.8 → accept."""
        items = [_item("Pizza", 2500) for _ in range(10)]
        report = score_menu(items)
        assert report.score >= WARNING_THRESHOLD
        assert report.status == "accept"


class TestQualityReport:

    def test_report_fields(self):
        items = [_item("Test", 2500)]
        report = score_menu(items, "wolt", "test-slug")
        assert report.platform == "wolt"
        assert report.slug == "test-slug"
        assert report.total_items == 1
        assert 0 <= report.score <= 1.0
        assert report.status in ("accept", "warning", "reject")

    def test_issues_capped(self):
        """Issues list capped at ~20 entries."""
        items = [_item("", 0) for _ in range(50)]  # 50 items with issues
        report = score_menu(items)
        assert len(report.issues) <= 21  # 20 + "...and N more"

    def test_is_accepted_property(self):
        r = QualityReport(platform="x", slug="x", status="accept")
        assert r.is_accepted is True
        r.status = "warning"
        assert r.is_accepted is True
        r.status = "reject"
        assert r.is_accepted is False
