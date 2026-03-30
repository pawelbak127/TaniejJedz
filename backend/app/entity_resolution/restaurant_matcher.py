"""
RestaurantMatcher — cross-platform restaurant entity resolution.

Matches platform_restaurants (canonical_restaurant_id=NULL) to existing
canonical_restaurants, or creates new canonicals when no match is found.

Algorithm:
  1. Process platforms in order of coverage (most restaurants first)
  2. First platform → creates canonical_restaurants for all its entries
  3. Subsequent platforms → for each unmatched restaurant:
     a. PostGIS blocking: find canonicals within 300m
     b. Trigram pre-filter: pg_trgm similarity > 0.3 on normalized_name
     c. Weighted scoring: name(0.30) + distance(0.25) + menu_overlap(0.25) + phone(0.20)
     d. Decision:
        ≥ 0.85 → auto-match (link platform_restaurant to canonical)
        0.60–0.85 → entity_review_queue (human review)
        < 0.60 → create new canonical_restaurant

Usage:
    async with get_async_session() as session:
        matcher = RestaurantMatcher(session)
        stats = await matcher.match_all_platforms("warszawa")
        await session.commit()
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, and_, text, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.entity_resolution.matching_utils import (
    distance_score,
    haversine_distance,
    jaccard_menu_overlap,
    name_similarity,
    phones_match,
)
from app.entity_resolution.normalizers import normalize_restaurant_name
from app.models.city import City
from app.models.feedback import EntityReviewQueue
from app.models.menu import PlatformMenuItem
from app.models.restaurant import CanonicalRestaurant, PlatformRestaurant

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════


@dataclass
class MatchResult:
    """Result of matching a single platform_restaurant."""
    platform_restaurant_id: uuid.UUID
    decision: str  # "auto_match" | "review" | "new_canonical"
    canonical_restaurant_id: uuid.UUID | None = None
    confidence: float = 0.0
    match_details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchStats:
    """Aggregate statistics for a matching run."""
    auto_matched: int = 0
    review_queue: int = 0
    new_canonical: int = 0
    skipped_no_coords: int = 0
    errors: int = 0

    @property
    def total_processed(self) -> int:
        return self.auto_matched + self.review_queue + self.new_canonical

    def __repr__(self) -> str:
        return (
            f"MatchStats(auto={self.auto_matched}, review={self.review_queue}, "
            f"new={self.new_canonical}, skipped={self.skipped_no_coords}, err={self.errors})"
        )

    def merge(self, other: MatchStats) -> None:
        self.auto_matched += other.auto_matched
        self.review_queue += other.review_queue
        self.new_canonical += other.new_canonical
        self.skipped_no_coords += other.skipped_no_coords
        self.errors += other.errors


@dataclass
class ScoredCandidate:
    """A canonical_restaurant candidate with match score breakdown."""
    canonical_id: uuid.UUID
    canonical_name: str
    normalized_name: str
    latitude: float
    longitude: float
    phone: str | None
    total_score: float = 0.0
    name_score: float = 0.0
    distance_score: float = 0.0
    menu_score: float = 0.0
    phone_score: float = 0.0
    distance_m: float = 0.0


# ══════════════════════════════════════════════════════════════
# MATCHER
# ══════════════════════════════════════════════════════════════


class RestaurantMatcher:
    """
    Cross-platform restaurant entity matcher.

    Processes platforms in order of coverage (most → least) to build
    the canonical set progressively.
    """

    # Platform processing order — most coverage first
    PLATFORM_ORDER = ["wolt", "pyszne", "glovo", "ubereats"]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()

    async def match_all_platforms(self, city_slug: str) -> MatchStats:
        """
        Run matching for all platforms in a city.

        1. Determine platform order by count of unmatched restaurants
        2. First platform → create canonicals
        3. Remaining platforms → match against existing canonicals
        """
        city_id = await self._get_city_id(city_slug)
        if city_id is None:
            logger.error("match_all_platforms: city '%s' not found", city_slug)
            return MatchStats()

        # Count unmatched per platform, order by most coverage
        platform_order = await self._get_platform_order()
        if not platform_order:
            logger.info("match_all_platforms: no unmatched restaurants")
            return MatchStats()

        logger.info(
            "match_all_platforms START city=%s platforms=%s",
            city_slug,
            [(p, c) for p, c in platform_order],
        )

        total_stats = MatchStats()

        for idx, (platform, count) in enumerate(platform_order):
            if count == 0:
                continue

            unmatched = await self._get_unmatched(platform)
            if not unmatched:
                continue

            if idx == 0:
                # First platform (most coverage) → create canonicals
                logger.info(
                    "match: %s (first, %d restaurants) → creating canonicals",
                    platform, len(unmatched),
                )
                stats = await self._create_canonicals_from_platform(
                    unmatched, city_id
                )
            else:
                # Subsequent platforms → match against existing canonicals
                logger.info(
                    "match: %s (%d restaurants) → matching against %d canonicals",
                    platform, len(unmatched),
                    await self._count_canonicals(city_id),
                )
                stats = await self._match_platform(unmatched, city_id)

            total_stats.merge(stats)
            await self._session.flush()

            logger.info("match: %s done — %s", platform, stats)

        logger.info("match_all_platforms DONE city=%s — %s", city_slug, total_stats)
        return total_stats

    # ══════════════════════════════════════════════════════════
    # FIRST PLATFORM → CREATE CANONICALS
    # ══════════════════════════════════════════════════════════

    async def _create_canonicals_from_platform(
        self,
        platform_restaurants: list[PlatformRestaurant],
        city_id: uuid.UUID,
    ) -> MatchStats:
        """
        First platform: create canonical_restaurant for each, link FK.

        These canonicals form the base set that subsequent platforms match against.
        """
        stats = MatchStats()

        for pr in platform_restaurants:
            try:
                meta = pr.platform_metadata or {}
                normalized = meta.get("normalized_name", "")
                if not normalized:
                    normalized = normalize_restaurant_name(pr.platform_name)

                canonical = CanonicalRestaurant(
                    city_id=city_id,
                    name=pr.platform_name,
                    normalized_name=normalized,
                    address_street=meta.get("address_street"),
                    address_city=meta.get("address_city"),
                    latitude=pr.latitude or 0.0,
                    longitude=pr.longitude or 0.0,
                    cuisine_tags=meta.get("cuisine_tags", []),
                    image_url=meta.get("image_url"),
                    data_quality_score=0.0,
                    is_active=True,
                )
                self._session.add(canonical)
                await self._session.flush()

                # Link platform_restaurant → canonical
                pr.canonical_restaurant_id = canonical.id
                pr.match_confidence = 1.0

                stats.new_canonical += 1

            except Exception:
                stats.errors += 1
                logger.exception(
                    "create_canonical error: pr_id=%s name=%s",
                    pr.id, pr.platform_name,
                )

        return stats

    # ══════════════════════════════════════════════════════════
    # SUBSEQUENT PLATFORMS → MATCH
    # ══════════════════════════════════════════════════════════

    async def _match_platform(
        self,
        platform_restaurants: list[PlatformRestaurant],
        city_id: uuid.UUID,
    ) -> MatchStats:
        """Match a platform's restaurants against existing canonicals."""
        stats = MatchStats()
        auto_threshold = self._settings.match_auto_threshold
        review_threshold = self._settings.match_review_threshold

        for pr in platform_restaurants:
            try:
                result = await self._match_one(pr, city_id)

                if result.decision == "auto_match":
                    pr.canonical_restaurant_id = result.canonical_restaurant_id
                    pr.match_confidence = result.confidence
                    stats.auto_matched += 1

                elif result.decision == "review":
                    # Insert into entity_review_queue
                    review = EntityReviewQueue(
                        platform_restaurant_id=pr.id,
                        candidate_canonical_id=result.canonical_restaurant_id,
                        confidence_score=result.confidence,
                        status="pending",
                        match_details=result.match_details,
                    )
                    self._session.add(review)
                    stats.review_queue += 1

                elif result.decision == "new_canonical":
                    canonical_id = await self._create_new_canonical(pr, city_id)
                    pr.canonical_restaurant_id = canonical_id
                    pr.match_confidence = 1.0
                    stats.new_canonical += 1

                elif result.decision == "skipped":
                    stats.skipped_no_coords += 1

            except Exception:
                stats.errors += 1
                logger.exception(
                    "match_one error: pr_id=%s name=%s",
                    pr.id, pr.platform_name,
                )

        return stats

    async def _match_one(
        self,
        pr: PlatformRestaurant,
        city_id: uuid.UUID,
    ) -> MatchResult:
        """Match a single platform_restaurant against canonicals."""
        # Sanity check: skip if no coordinates
        if not pr.latitude or not pr.longitude:
            return MatchResult(
                platform_restaurant_id=pr.id,
                decision="skipped",
                match_details={"reason": "no_coordinates"},
            )

        meta = pr.platform_metadata or {}
        pr_normalized = meta.get("normalized_name", "")
        if not pr_normalized:
            pr_normalized = normalize_restaurant_name(pr.platform_name)

        # Find candidates via PostGIS + trigram
        candidates = await self._find_candidates(
            pr.latitude, pr.longitude, pr_normalized, city_id
        )

        if not candidates:
            return MatchResult(
                platform_restaurant_id=pr.id,
                decision="new_canonical",
                match_details={"reason": "no_candidates_in_radius"},
            )

        # Score each candidate
        pr_menu_names = await self._get_menu_names(pr.id)
        pr_phone = meta.get("phone")

        best: ScoredCandidate | None = None
        for candidate in candidates:
            candidate = await self._score_candidate(
                pr_normalized, pr.latitude, pr.longitude,
                pr_menu_names, pr_phone, candidate,
            )
            if best is None or candidate.total_score > best.total_score:
                best = candidate

        if best is None:
            return MatchResult(
                platform_restaurant_id=pr.id,
                decision="new_canonical",
                match_details={"reason": "no_scored_candidates"},
            )

        # Decision based on thresholds
        auto_threshold = self._settings.match_auto_threshold
        review_threshold = self._settings.match_review_threshold

        details = {
            "candidate_name": best.canonical_name,
            "total_score": round(best.total_score, 4),
            "name_score": round(best.name_score, 4),
            "distance_score": round(best.distance_score, 4),
            "distance_m": round(best.distance_m, 1),
            "menu_score": round(best.menu_score, 4),
            "phone_score": round(best.phone_score, 4),
        }

        if best.total_score >= auto_threshold:
            return MatchResult(
                platform_restaurant_id=pr.id,
                decision="auto_match",
                canonical_restaurant_id=best.canonical_id,
                confidence=best.total_score,
                match_details=details,
            )
        elif best.total_score >= review_threshold:
            return MatchResult(
                platform_restaurant_id=pr.id,
                decision="review",
                canonical_restaurant_id=best.canonical_id,
                confidence=best.total_score,
                match_details=details,
            )
        else:
            details["reason"] = "below_review_threshold"
            return MatchResult(
                platform_restaurant_id=pr.id,
                decision="new_canonical",
                match_details=details,
            )

    # ══════════════════════════════════════════════════════════
    # CANDIDATE FINDING (PostGIS + trigram)
    # ══════════════════════════════════════════════════════════

    async def _find_candidates(
        self,
        lat: float,
        lng: float,
        normalized_name: str,
        city_id: uuid.UUID,
    ) -> list[ScoredCandidate]:
        """
        Find canonical_restaurant candidates using PostGIS blocking + trigram.

        1. earth_box + ll_to_earth → GiST index scan, 300m radius
        2. pg_trgm similarity > 0.3 on normalized_name
        3. Return as ScoredCandidate (scores not yet calculated)
        """
        radius_m = self._settings.match_geo_radius_m
        trgm_threshold = self._settings.match_trgm_threshold

        # PostGIS + trigram query
        stmt = text("""
            SELECT 
                id, name, normalized_name, latitude, longitude, phone,
                earth_distance(
                    ll_to_earth(:lat, :lng),
                    ll_to_earth(latitude, longitude)
                ) AS distance_m
            FROM canonical_restaurants
            WHERE city_id = :city_id
              AND is_active = true
              AND latitude != 0 AND longitude != 0
              AND earth_box(ll_to_earth(:lat, :lng), :radius) @> ll_to_earth(latitude, longitude)
              AND earth_distance(ll_to_earth(:lat, :lng), ll_to_earth(latitude, longitude)) < :radius
            ORDER BY distance_m ASC
            LIMIT 20
        """)

        result = await self._session.execute(
            stmt,
            {
                "lat": lat,
                "lng": lng,
                "city_id": city_id,
                "radius": radius_m,
            },
        )
        rows = result.fetchall()

        candidates = []
        for row in rows:
            # Apply trigram filter in Python (more flexible than SQL for JSONB)
            candidate_normalized = row.normalized_name or ""
            if normalized_name and candidate_normalized:
                sim = name_similarity(normalized_name, candidate_normalized)
                if sim < trgm_threshold:
                    continue

            candidates.append(ScoredCandidate(
                canonical_id=row.id,
                canonical_name=row.name,
                normalized_name=candidate_normalized,
                latitude=row.latitude,
                longitude=row.longitude,
                phone=row.phone,
                distance_m=row.distance_m,
            ))

        return candidates

    # ══════════════════════════════════════════════════════════
    # SCORING
    # ══════════════════════════════════════════════════════════

    async def _score_candidate(
        self,
        pr_normalized: str,
        pr_lat: float,
        pr_lng: float,
        pr_menu_names: list[str],
        pr_phone: str | None,
        candidate: ScoredCandidate,
    ) -> ScoredCandidate:
        """
        Score a candidate match using weighted components.

        Base weights from config: name(0.30) + distance(0.25) + menu(0.25) + phone(0.20).

        When menu or phone data is unavailable, their weights are redistributed
        proportionally to name + distance. Without this, max achievable score
        with neutral(0.5) components would be 0.775 — never reaching auto_threshold(0.85).
        """
        w = self._settings

        # Name similarity (rapidfuzz token_sort_ratio)
        candidate.name_score = name_similarity(pr_normalized, candidate.normalized_name)

        # Distance score (0m → 1.0, 300m → 0.0)
        candidate.distance_score = distance_score(
            candidate.distance_m, float(w.match_geo_radius_m)
        )

        # Menu overlap (Jaccard on normalized item names)
        canonical_menu_names = await self._get_canonical_menu_names(candidate.canonical_id)
        has_menu = bool(pr_menu_names) and bool(canonical_menu_names)
        candidate.menu_score = jaccard_menu_overlap(pr_menu_names, canonical_menu_names)

        # Phone match
        has_phone = bool(pr_phone) and bool(candidate.phone)
        if has_phone:
            candidate.phone_score = 1.0 if phones_match(pr_phone, candidate.phone) else 0.0
        else:
            candidate.phone_score = 0.5

        # Weight redistribution: exclude unavailable components, renormalize
        wt_name = w.match_weight_name
        wt_dist = w.match_weight_distance
        wt_menu = w.match_weight_menu_overlap if has_menu else 0.0
        wt_phone = w.match_weight_phone if has_phone else 0.0

        total_weight = wt_name + wt_dist + wt_menu + wt_phone
        if total_weight > 0:
            wt_name /= total_weight
            wt_dist /= total_weight
            wt_menu /= total_weight
            wt_phone /= total_weight

        candidate.total_score = (
            wt_name * candidate.name_score
            + wt_dist * candidate.distance_score
            + wt_menu * candidate.menu_score
            + wt_phone * candidate.phone_score
        )

        return candidate

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    async def _create_new_canonical(
        self,
        pr: PlatformRestaurant,
        city_id: uuid.UUID,
    ) -> uuid.UUID:
        """Create a new canonical_restaurant from platform data."""
        meta = pr.platform_metadata or {}
        normalized = meta.get("normalized_name", "")
        if not normalized:
            normalized = normalize_restaurant_name(pr.platform_name)

        canonical = CanonicalRestaurant(
            city_id=city_id,
            name=pr.platform_name,
            normalized_name=normalized,
            address_street=meta.get("address_street"),
            address_city=meta.get("address_city"),
            latitude=pr.latitude or 0.0,
            longitude=pr.longitude or 0.0,
            cuisine_tags=meta.get("cuisine_tags", []),
            image_url=meta.get("image_url"),
            data_quality_score=0.0,
            is_active=True,
        )
        self._session.add(canonical)
        await self._session.flush()
        return canonical.id

    async def _get_unmatched(self, platform: str) -> list[PlatformRestaurant]:
        """Get all platform_restaurants with canonical_restaurant_id IS NULL."""
        result = await self._session.execute(
            select(PlatformRestaurant).where(
                and_(
                    PlatformRestaurant.platform == platform,
                    PlatformRestaurant.canonical_restaurant_id.is_(None),
                    PlatformRestaurant.is_active.is_(True),
                )
            )
        )
        return list(result.scalars().all())

    async def _get_platform_order(self) -> list[tuple[str, int]]:
        """Get platforms ordered by unmatched count (most first)."""
        result = await self._session.execute(
            select(
                PlatformRestaurant.platform,
                func.count(PlatformRestaurant.id),
            )
            .where(
                and_(
                    PlatformRestaurant.canonical_restaurant_id.is_(None),
                    PlatformRestaurant.is_active.is_(True),
                )
            )
            .group_by(PlatformRestaurant.platform)
            .order_by(func.count(PlatformRestaurant.id).desc())
        )
        return [(row[0], row[1]) for row in result.all()]

    async def _count_canonicals(self, city_id: uuid.UUID) -> int:
        """Count canonical_restaurants in a city."""
        result = await self._session.execute(
            select(func.count(CanonicalRestaurant.id)).where(
                and_(
                    CanonicalRestaurant.city_id == city_id,
                    CanonicalRestaurant.is_active.is_(True),
                )
            )
        )
        return result.scalar() or 0

    async def _get_city_id(self, city_slug: str) -> uuid.UUID | None:
        """Get city ID by slug."""
        result = await self._session.execute(
            select(City.id).where(City.slug == city_slug)
        )
        return result.scalar_one_or_none()

    async def _get_menu_names(self, platform_restaurant_id: uuid.UUID) -> list[str]:
        """Get normalized menu item names for a platform restaurant."""
        from app.entity_resolution.normalizers import normalize_dish_name

        result = await self._session.execute(
            select(PlatformMenuItem.platform_name).where(
                and_(
                    PlatformMenuItem.platform_restaurant_id == platform_restaurant_id,
                    PlatformMenuItem.is_available.is_(True),
                )
            )
        )
        names = []
        for (name,) in result.all():
            base, _ = normalize_dish_name(name)
            if base:
                names.append(base)
        return names

    async def _get_canonical_menu_names(
        self, canonical_id: uuid.UUID,
    ) -> list[str]:
        """Get normalized menu item names via canonical's linked platform restaurants."""
        from app.entity_resolution.normalizers import normalize_dish_name

        # Get menu items from ALL platform_restaurants linked to this canonical
        result = await self._session.execute(
            select(PlatformMenuItem.platform_name)
            .join(
                PlatformRestaurant,
                PlatformMenuItem.platform_restaurant_id == PlatformRestaurant.id,
            )
            .where(
                and_(
                    PlatformRestaurant.canonical_restaurant_id == canonical_id,
                    PlatformMenuItem.is_available.is_(True),
                )
            )
        )
        names = []
        for (name,) in result.all():
            base, _ = normalize_dish_name(name)
            if base:
                names.append(base)
        return names
