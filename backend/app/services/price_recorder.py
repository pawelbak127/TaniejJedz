"""
PriceRecorder — snapshot current prices into price_history (partitioned by month).

Records the current price_grosz for each platform_menu_item belonging to
a platform_restaurant. Called after persist_menu() to track price changes.

Usage:
    async with session_factory() as session:
        recorder = PriceRecorder(session)
        count = await recorder.record_prices(platform_restaurant_id)
        await session.commit()
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu import PlatformMenuItem

logger = logging.getLogger(__name__)


class PriceRecorder:
    """Records price snapshots to price_history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_prices(
        self,
        platform_restaurant_id: uuid.UUID,
    ) -> int:
        """
        Snapshot all current prices for a platform restaurant into price_history.

        Uses raw SQL INSERT for the partitioned table (SQLAlchemy ORM
        doesn't natively handle partition routing for tables with composite PKs
        defined in raw SQL).

        Returns: number of price records inserted.
        """
        # Get all active platform_menu_items for this restaurant
        result = await self._session.execute(
            select(PlatformMenuItem.id, PlatformMenuItem.price_grosz).where(
                PlatformMenuItem.platform_restaurant_id == platform_restaurant_id,
                PlatformMenuItem.is_available.is_(True),
                PlatformMenuItem.price_grosz > 0,
            )
        )
        items = result.all()

        if not items:
            return 0

        now = datetime.now(timezone.utc)
        count = 0

        for pmi_id, price_grosz in items:
            try:
                await self._session.execute(
                    text("""
                        INSERT INTO price_history (id, platform_menu_item_id, price_grosz, recorded_at)
                        VALUES (uuid_generate_v4(), :pmi_id, :price, :ts)
                    """),
                    {"pmi_id": pmi_id, "price": price_grosz, "ts": now},
                )
                count += 1
            except Exception:
                logger.warning(
                    "price_history insert failed: pmi_id=%s price=%d",
                    pmi_id, price_grosz,
                    exc_info=True,
                )

        logger.info(
            "record_prices: pr_id=%s recorded=%d items",
            str(platform_restaurant_id)[:12], count,
        )
        return count

    async def record_single_price(
        self,
        platform_menu_item_id: uuid.UUID,
        price_grosz: int,
    ) -> None:
        """Record a single price snapshot."""
        now = datetime.now(timezone.utc)
        await self._session.execute(
            text("""
                INSERT INTO price_history (id, platform_menu_item_id, price_grosz, recorded_at)
                VALUES (uuid_generate_v4(), :pmi_id, :price, :ts)
            """),
            {"pmi_id": platform_menu_item_id, "price": price_grosz, "ts": now},
        )
