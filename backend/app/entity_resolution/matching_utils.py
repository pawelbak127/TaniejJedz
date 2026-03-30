"""
Matching utilities for entity resolution.

Pure functions used by RestaurantMatcher and MenuMatcher:
  - haversine_distance(lat1, lng1, lat2, lng2) → meters
  - jaccard_menu_overlap(items_a, items_b) → 0.0-1.0
  - phones_match(phone_a, phone_b) → bool
  - name_similarity(name_a, name_b) → 0.0-1.0

All functions are stateless and testable without DB.
"""

from __future__ import annotations

import math
import re


# Earth radius in meters
_EARTH_RADIUS_M = 6_371_000


def haversine_distance(
    lat1: float, lng1: float,
    lat2: float, lng2: float,
) -> float:
    """
    Calculate distance between two points in meters using Haversine formula.

    Returns float meters. Returns inf if any coordinate is 0.0 (missing).
    """
    if lat1 == 0.0 or lng1 == 0.0 or lat2 == 0.0 or lng2 == 0.0:
        return float("inf")

    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return _EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def name_similarity(name_a: str, name_b: str) -> float:
    """
    Fuzzy name similarity using rapidfuzz token_sort_ratio.

    Both inputs should be pre-normalized (lowercase, no diacritics, sorted tokens).
    Returns 0.0–1.0.
    """
    if not name_a or not name_b:
        return 0.0
    try:
        from rapidfuzz import fuzz
        return fuzz.token_sort_ratio(name_a, name_b) / 100.0
    except ImportError:
        # Fallback: simple set overlap (Jaccard on tokens)
        set_a = set(name_a.split())
        set_b = set(name_b.split())
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0


def jaccard_menu_overlap(
    items_a: list[str],
    items_b: list[str],
) -> float:
    """
    Jaccard similarity of two menu item name lists.

    Inputs should be normalized item names (lowercase, no diacritics).
    Returns 0.0–1.0. Returns 0.5 (neutral) if either list is empty.
    """
    if not items_a or not items_b:
        return 0.5  # neutral — don't penalize missing menu data

    set_a = set(items_a)
    set_b = set(items_b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def phones_match(phone_a: str | None, phone_b: str | None) -> bool:
    """
    Check if two phone numbers match by comparing last 9 digits.

    Strips all non-digit characters, then compares the last 9 digits.
    Handles Polish formats: +48 123 456 789, 123-456-789, etc.
    Returns False if either phone is None/empty.
    """
    if not phone_a or not phone_b:
        return False

    digits_a = re.sub(r"\D", "", phone_a)
    digits_b = re.sub(r"\D", "", phone_b)

    if len(digits_a) < 9 or len(digits_b) < 9:
        return False

    return digits_a[-9:] == digits_b[-9:]


def distance_score(distance_m: float, max_radius_m: float = 300.0) -> float:
    """
    Convert distance in meters to a 0.0–1.0 score.

    0m → 1.0, max_radius → 0.0. Linear decay.
    Beyond max_radius → 0.0.
    """
    if distance_m >= max_radius_m or distance_m == float("inf"):
        return 0.0
    return 1.0 - (distance_m / max_radius_m)
