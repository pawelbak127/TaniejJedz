"""
MenuMatcher — cross-platform menu item entity resolution.

Matches platform_menu_items (canonical_menu_item_id=NULL) to
canonical_menu_items, or creates new canonicals when no match found.

Algorithm:
  1. Find canonical_restaurants with menu items on 2+ platforms
  2. For each: seed platform (most items) → create canonical_menu_items
  3. Other platforms → fuzzy match by normalized name + size label
  4. Decision:
     ≥ 0.80 + same size → auto-match
     ≥ 0.80 + diff size → new canonical (same dish, different size)
     < 0.80 → new canonical

Usage:
    async with get_async_session() as session:
        matcher = MenuMatcher(session)
        stats = await matcher.match_all()
        await session.commit()
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.entity_resolution.normalizers import normalize_dish_name
from app.models.menu import CanonicalMenuItem, MenuCategory, PlatformMenuItem
from app.models.restaurant import CanonicalRestaurant, PlatformRestaurant

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════

MENU_MATCH_THRESHOLD = 0.80  # ≥ 0.80 normalized name similarity → auto-match
MENU_EXACT_BONUS = 0.10      # bonus for exact (not fuzzy) name match
SIZE_MISMATCH_BLOCKS = True   # different size_label → always new canonical


def _normalize_size(label: str | None) -> str | None:
    """Normalize size label for comparison: strip spaces, comma→dot, lowercase."""
    if label is None:
        return None
    s = label.strip().lower()
    s = s.replace(" ", "").replace(",", ".")
    return s


# ══════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════


@dataclass
class MenuMatchStats:
    """Aggregate statistics for menu matching run."""
    restaurants_processed: int = 0
    seed_items_created: int = 0      # canonical_menu_items from seed platform
    auto_matched: int = 0            # items matched to existing canonical
    new_canonical: int = 0           # new canonical created (no match)
    already_linked: int = 0          # already had canonical_menu_item_id
    errors: int = 0
    categories_created: int = 0

    @property
    def total_linked(self) -> int:
        return self.seed_items_created + self.auto_matched

    def __repr__(self) -> str:
        return (
            f"MenuMatchStats(restaurants={self.restaurants_processed}, "
            f"seed={self.seed_items_created}, auto={self.auto_matched}, "
            f"new={self.new_canonical}, already={self.already_linked}, "
            f"categories={self.categories_created}, err={self.errors})"
        )

    def merge(self, other: MenuMatchStats) -> None:
        self.restaurants_processed += other.restaurants_processed
        self.seed_items_created += other.seed_items_created
        self.auto_matched += other.auto_matched
        self.new_canonical += other.new_canonical
        self.already_linked += other.already_linked
        self.errors += other.errors
        self.categories_created += other.categories_created


@dataclass
class NormalizedItem:
    """Platform menu item with pre-computed normalized name."""
    pmi_id: uuid.UUID
    platform_item_id: str
    platform_name: str
    price_grosz: int
    category_name: str | None
    base_name: str          # from normalize_dish_name()
    size_label: str | None  # from normalize_dish_name()
    canonical_menu_item_id: uuid.UUID | None = None


# ══════════════════════════════════════════════════════════════
# MATCHER
# ══════════════════════════════════════════════════════════════


class MenuMatcher:
    """
    Cross-platform menu item matcher.

    For each canonical_restaurant with menus on 2+ platforms:
    1. Seed: platform with most items → creates canonical_menu_items
    2. Match: other platforms' items → fuzzy match against seed canonicals
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def match_all(self) -> MenuMatchStats:
        """
        Match menu items across all multi-platform restaurants.

        Returns aggregate stats.
        """
        # Find canonical_restaurants with menu items on 2+ platforms
        candidates = await self._find_multi_platform_restaurants()

        if not candidates:
            logger.info("menu_match: no multi-platform restaurants with menus")
            return MenuMatchStats()

        logger.info(
            "menu_match START: %d restaurants with menus on 2+ platforms",
            len(candidates),
        )

        total_stats = MenuMatchStats()

        for canonical_id, canonical_name, platform_count in candidates:
            try:
                stats = await self._match_restaurant(canonical_id, canonical_name)
                total_stats.merge(stats)
            except Exception:
                total_stats.errors += 1
                logger.exception(
                    "menu_match error: canonical=%s name=%s",
                    canonical_id, canonical_name,
                )

            # Flush every 10 restaurants to avoid huge transaction
            if total_stats.restaurants_processed % 10 == 0:
                await self._session.flush()

        logger.info("menu_match DONE: %s", total_stats)
        return total_stats

    async def match_restaurant(
        self, canonical_restaurant_id: uuid.UUID,
    ) -> MenuMatchStats:
        """Match menu items for a single canonical restaurant (public API)."""
        return await self._match_restaurant(canonical_restaurant_id, "")

    # ══════════════════════════════════════════════════════════
    # CORE MATCHING
    # ══════════════════════════════════════════════════════════

    async def _match_restaurant(
        self,
        canonical_id: uuid.UUID,
        canonical_name: str,
    ) -> MenuMatchStats:
        """Match all menu items for one canonical restaurant."""
        stats = MenuMatchStats()
        stats.restaurants_processed = 1

        # Get all platform_menu_items grouped by platform
        items_by_platform = await self._get_items_by_platform(canonical_id)

        if len(items_by_platform) < 2:
            return stats  # Need 2+ platforms

        # Pick seed platform (most items)
        seed_platform = max(items_by_platform, key=lambda p: len(items_by_platform[p]))
        seed_items = items_by_platform[seed_platform]

        logger.debug(
            "menu_match %s: seed=%s (%d items), matching %d other platforms",
            canonical_name[:30], seed_platform, len(seed_items),
            len(items_by_platform) - 1,
        )

        # Create categories from seed platform
        category_map = await self._ensure_categories(
            canonical_id, seed_items, stats
        )

        # Step 1: Seed platform → create canonical_menu_items
        canonical_items = await self._seed_canonical_items(
            canonical_id, seed_items, category_map, stats,
        )

        # Step 2: Other platforms → match against canonical items
        for platform, items in items_by_platform.items():
            if platform == seed_platform:
                continue
            await self._match_platform_items(
                canonical_id, items, canonical_items, category_map, stats,
            )

        return stats

    async def _seed_canonical_items(
        self,
        canonical_id: uuid.UUID,
        seed_items: list[NormalizedItem],
        category_map: dict[str, uuid.UUID],
        stats: MenuMatchStats,
    ) -> list[dict]:
        """Create canonical_menu_items from seed platform items."""
        canonical_items: list[dict] = []

        for item in seed_items:
            # Skip if already linked
            if item.canonical_menu_item_id is not None:
                stats.already_linked += 1
                # Still add to canonical_items for matching
                canonical_items.append({
                    "id": item.canonical_menu_item_id,
                    "base_name": item.base_name,
                    "size_label": item.size_label,
                    "name": item.platform_name,
                })
                continue

            # Create canonical_menu_item
            category_id = category_map.get(item.category_name) if item.category_name else None

            cmi = CanonicalMenuItem(
                canonical_restaurant_id=canonical_id,
                category_id=category_id,
                name=item.platform_name,
                normalized_name=item.base_name,
                description=None,
                size_label=item.size_label,
            )
            self._session.add(cmi)
            await self._session.flush()

            # Link platform_menu_item → canonical
            await self._link_pmi(item.pmi_id, cmi.id, 1.0)

            canonical_items.append({
                "id": cmi.id,
                "base_name": item.base_name,
                "size_label": item.size_label,
                "name": item.platform_name,
            })
            stats.seed_items_created += 1

        return canonical_items

    async def _match_platform_items(
        self,
        canonical_id: uuid.UUID,
        items: list[NormalizedItem],
        canonical_items: list[dict],
        category_map: dict[str, uuid.UUID],
        stats: MenuMatchStats,
    ) -> None:
        """Match a platform's items against existing canonical_menu_items."""
        for item in items:
            # Skip if already linked
            if item.canonical_menu_item_id is not None:
                stats.already_linked += 1
                continue

            # Find best match
            best_match, best_score = self._find_best_match(item, canonical_items)

            if best_match is not None and best_score >= MENU_MATCH_THRESHOLD:
                # Auto-match
                await self._link_pmi(item.pmi_id, best_match["id"], best_score)
                stats.auto_matched += 1
            else:
                # No match → create new canonical
                category_id = (
                    category_map.get(item.category_name)
                    if item.category_name else None
                )
                cmi = CanonicalMenuItem(
                    canonical_restaurant_id=canonical_id,
                    category_id=category_id,
                    name=item.platform_name,
                    normalized_name=item.base_name,
                    description=None,
                    size_label=item.size_label,
                )
                self._session.add(cmi)
                await self._session.flush()

                await self._link_pmi(item.pmi_id, cmi.id, 1.0)

                # Add to canonical_items so subsequent platforms can match
                canonical_items.append({
                    "id": cmi.id,
                    "base_name": item.base_name,
                    "size_label": item.size_label,
                    "name": item.platform_name,
                })
                stats.new_canonical += 1

    # ══════════════════════════════════════════════════════════
    # MATCHING LOGIC
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _find_best_match(
        item: NormalizedItem,
        canonical_items: list[dict],
    ) -> tuple[dict | None, float]:
        """
        Find the best matching canonical_menu_item for a platform item.

        Uses normalized base_name similarity (rapidfuzz token_set_ratio).
        Size label must match (after normalization) or both be None.

        Returns (best_match_dict, score) or (None, 0.0).
        """
        if not item.base_name or not canonical_items:
            return None, 0.0

        best: dict | None = None
        best_score: float = 0.0

        for canonical in canonical_items:
            # Size label gate: must match exactly (after normalization)
            if SIZE_MISMATCH_BLOCKS:
                if _normalize_size(item.size_label) != _normalize_size(canonical.get("size_label")):
                    continue

            # Name similarity
            c_name = canonical.get("base_name", "")
            if not c_name:
                continue

            score = fuzz.token_set_ratio(
                item.base_name, c_name
            ) / 100.0  # rapidfuzz returns 0-100

            # Exact match bonus
            if item.base_name == c_name:
                score = min(1.0, score + MENU_EXACT_BONUS)

            if score > best_score:
                best_score = score
                best = canonical

        return best, best_score

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    async def _find_multi_platform_restaurants(
        self,
    ) -> list[tuple[uuid.UUID, str, int]]:
        """
        Find canonical_restaurants with menu items on 2+ platforms.

        Returns list of (canonical_id, name, platform_count).
        """
        result = await self._session.execute(text("""
            SELECT cr.id, cr.name, COUNT(DISTINCT pr.platform) as platform_count
            FROM canonical_restaurants cr
            JOIN platform_restaurants pr ON pr.canonical_restaurant_id = cr.id
            JOIN platform_menu_items pmi ON pmi.platform_restaurant_id = pr.id
            WHERE pmi.is_available = true
            GROUP BY cr.id, cr.name
            HAVING COUNT(DISTINCT pr.platform) >= 2
            ORDER BY platform_count DESC, cr.name
        """))
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def _get_items_by_platform(
        self,
        canonical_id: uuid.UUID,
    ) -> dict[str, list[NormalizedItem]]:
        """Get all platform_menu_items for a canonical restaurant, grouped by platform."""
        result = await self._session.execute(
            select(
                PlatformMenuItem.id,
                PlatformMenuItem.platform_item_id,
                PlatformMenuItem.platform_name,
                PlatformMenuItem.price_grosz,
                PlatformMenuItem.canonical_menu_item_id,
                PlatformRestaurant.platform,
            )
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
            .order_by(PlatformRestaurant.platform, PlatformMenuItem.platform_name)
        )

        items_by_platform: dict[str, list[NormalizedItem]] = {}
        for row in result.all():
            pmi_id, item_id, name, price, cmi_id, platform = row
            base_name, size_label = normalize_dish_name(name)

            ni = NormalizedItem(
                pmi_id=pmi_id,
                platform_item_id=item_id,
                platform_name=name,
                price_grosz=price,
                category_name=None,  # filled below if available
                base_name=base_name,
                size_label=size_label,
                canonical_menu_item_id=cmi_id,
            )
            items_by_platform.setdefault(platform, []).append(ni)

        return items_by_platform

    async def _ensure_categories(
        self,
        canonical_id: uuid.UUID,
        seed_items: list[NormalizedItem],
        stats: MenuMatchStats,
    ) -> dict[str, uuid.UUID]:
        """
        Create MenuCategory entries for unique category names.

        Returns mapping: category_name → category_id.
        """
        # Get unique category names from seed items
        # Note: category_name on NormalizedItem is None because persistor
        # doesn't store it on platform_menu_items. We'll use the category
        # from platform_metadata or skip category assignment.
        # For now return empty — categories are optional in the schema.
        return {}

    async def _link_pmi(
        self,
        pmi_id: uuid.UUID,
        canonical_menu_item_id: uuid.UUID,
        confidence: float,
    ) -> None:
        """Link a platform_menu_item to its canonical_menu_item."""
        await self._session.execute(
            PlatformMenuItem.__table__.update()
            .where(PlatformMenuItem.id == pmi_id)
            .values(
                canonical_menu_item_id=canonical_menu_item_id,
                match_confidence=confidence,
            )
        )
