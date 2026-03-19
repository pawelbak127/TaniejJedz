"""
Quality Scorer — scores scrape results for data quality.

Scoring dimensions (0.0–1.0 each, weighted average):
  1. Completeness  (0.40) — name, price, description present
  2. Price range   (0.30) — price > 100 gr (>1 zł) AND < 100_000 gr (<1000 zł)
  3. Modifier tree (0.20) — groups have min/max, options have names and prices ≥ 0
  4. Availability  (0.10) — at least some items are available

Thresholds:
  score < 0.6 → REJECT (keep old cached data, fire alert)
  score < 0.8 → ACCEPT with WARNING
  score ≥ 0.8 → ACCEPT

Used by:
  - Orchestrator (optional quality gate before caching)
  - Canary job (validate sample scrapes)
  - Nightly crawl (log quality per restaurant)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.scraper.schemas.normalized import NormalizedMenuItem

logger = logging.getLogger(__name__)

# Thresholds
REJECT_THRESHOLD = 0.6
WARNING_THRESHOLD = 0.8

# Weights
W_COMPLETENESS = 0.40
W_PRICE_RANGE = 0.30
W_MODIFIERS = 0.20
W_AVAILABILITY = 0.10

# Price sanity bounds (grosz)
MIN_PRICE_GROSZ = 100       # 1.00 zł
MAX_PRICE_GROSZ = 100_000   # 1000.00 zł


@dataclass
class QualityReport:
    """Detailed quality report for a scrape."""
    platform: str
    slug: str
    total_items: int = 0
    score: float = 0.0
    completeness: float = 0.0
    price_range: float = 0.0
    modifier_quality: float = 0.0
    availability: float = 0.0
    status: str = "pending"  # "accept" | "warning" | "reject"
    issues: list[str] = field(default_factory=list)

    @property
    def is_accepted(self) -> bool:
        return self.status in ("accept", "warning")


def score_menu(
    items: list[NormalizedMenuItem],
    platform: str = "",
    slug: str = "",
) -> QualityReport:
    """
    Score a list of menu items for data quality.

    Returns QualityReport with overall score and per-dimension breakdown.
    """
    report = QualityReport(platform=platform, slug=slug, total_items=len(items))

    if not items:
        report.score = 0.0
        report.status = "reject"
        report.issues.append("empty menu (0 items)")
        return report

    # ── 1. Completeness (name + price present) ─────────────
    complete_count = 0
    for item in items:
        has_name = bool(item.platform_name and item.platform_name.strip())
        has_price = item.price_grosz > 0
        if has_name and has_price:
            complete_count += 1
        else:
            if not has_name:
                report.issues.append(f"item {item.platform_item_id}: missing name")
            if not has_price:
                report.issues.append(f"item {item.platform_item_id} ({item.platform_name}): price=0")

    report.completeness = complete_count / len(items)

    # ── 2. Price range validity ────────────────────────────
    priced_items = [i for i in items if i.price_grosz > 0]
    if not priced_items:
        report.price_range = 0.0
        report.issues.append("no items with price > 0")
    else:
        valid_price_count = sum(
            1 for i in priced_items
            if MIN_PRICE_GROSZ <= i.price_grosz <= MAX_PRICE_GROSZ
        )
        report.price_range = valid_price_count / len(priced_items)

        # Report outliers
        for i in priced_items:
            if i.price_grosz < MIN_PRICE_GROSZ:
                report.issues.append(
                    f"item {i.platform_name}: price {i.price_grosz}gr < {MIN_PRICE_GROSZ}gr"
                )
            elif i.price_grosz > MAX_PRICE_GROSZ:
                report.issues.append(
                    f"item {i.platform_name}: price {i.price_grosz}gr > {MAX_PRICE_GROSZ}gr"
                )

    # ── 3. Modifier tree quality ───────────────────────────
    items_with_mods = [i for i in items if i.modifier_groups]
    if not items_with_mods:
        # No modifiers at all — neutral (some menus legitimately have none)
        report.modifier_quality = 0.8
    else:
        valid_groups = 0
        total_groups = 0
        for item in items_with_mods:
            for mg in item.modifier_groups:
                total_groups += 1
                has_name = bool(mg.name and mg.name.strip())
                has_options = len(mg.options) > 0
                valid_min_max = mg.min_selections >= 0 and mg.max_selections >= mg.min_selections
                options_valid = all(
                    bool(o.name) and o.price_grosz >= 0
                    for o in mg.options
                )
                if has_name and has_options and valid_min_max and options_valid:
                    valid_groups += 1
                else:
                    if not has_name:
                        report.issues.append(f"modifier group: missing name")
                    if not has_options:
                        report.issues.append(f"modifier group {mg.name}: no options")
                    if not valid_min_max:
                        report.issues.append(
                            f"modifier group {mg.name}: invalid min={mg.min_selections}/max={mg.max_selections}"
                        )

        report.modifier_quality = valid_groups / total_groups if total_groups else 0.8

    # ── 4. Availability ────────────────────────────────────
    available_count = sum(1 for i in items if i.is_available)
    report.availability = available_count / len(items)

    if report.availability == 0.0:
        report.issues.append("all items unavailable")

    # ── Weighted score ─────────────────────────────────────
    report.score = (
        W_COMPLETENESS * report.completeness
        + W_PRICE_RANGE * report.price_range
        + W_MODIFIERS * report.modifier_quality
        + W_AVAILABILITY * report.availability
    )
    report.score = round(report.score, 4)

    # ── Threshold decision ─────────────────────────────────
    if report.score < REJECT_THRESHOLD:
        report.status = "reject"
    elif report.score < WARNING_THRESHOLD:
        report.status = "warning"
    else:
        report.status = "accept"

    # Cap issues list
    if len(report.issues) > 20:
        trimmed = len(report.issues) - 20
        report.issues = report.issues[:20]
        report.issues.append(f"... and {trimmed} more issues")

    logger.info(
        "quality score %s/%s: %.3f (%s) — items=%d complete=%.2f price=%.2f mods=%.2f avail=%.2f",
        platform, slug, report.score, report.status,
        len(items), report.completeness, report.price_range,
        report.modifier_quality, report.availability,
    )

    return report
