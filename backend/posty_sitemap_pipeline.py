"""
Post-Sitemap Fix: Re-crawl → Re-match → Menu Crawl

Run from: C:\Projects\TaniejJedz\backend
Prereqs:
  - Docker (postgres, redis) running
  - Sitemap sync already done (sync_glovo_slugs, sync_ubereats_slugs)
  - $env:DATABASE_URL and $env:REDIS_URL set

Usage:
  python post_sitemap_pipeline.py
"""

import asyncio
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def step1_recrawl():
    """Re-crawl all 4 platforms (sitemap-powered Glovo/UberEats)."""
    from app.jobs.crawl_restaurants import _crawl_city_async

    logger.info("=" * 60)
    logger.info("STEP 1: Re-crawl restaurants (all platforms)")
    logger.info("=" * 60)

    start = time.monotonic()
    result = await _crawl_city_async(
        "warszawa", 52.2297, 21.0122, 15.0,
        ["wolt", "pyszne", "glovo", "ubereats"],
    )
    elapsed = time.monotonic() - start

    for platform, data in result.get("platforms", {}).items():
        count = data.get("count", 0)
        error = data.get("error")
        status = f"ERROR: {error}" if error else "OK"
        logger.info(f"  {platform:12s}: {count:>5d} restaurants  [{status}]")

    persisted = result.get("persisted", {})
    for platform, stats in persisted.items():
        if isinstance(stats, dict) and "inserted" in stats:
            logger.info(
                f"  {platform:12s}: +{stats['inserted']} new, "
                f"~{stats['updated']} updated, {stats.get('fees', 0)} fees"
            )

    logger.info(f"  Elapsed: {elapsed:.1f}s")
    return result


async def step2_verify_db():
    """Verify DB state after re-crawl."""
    from app.jobs.db import get_async_session
    from sqlalchemy import text

    logger.info("=" * 60)
    logger.info("STEP 2: Verify DB state")
    logger.info("=" * 60)

    async with get_async_session() as session:
        # Per-platform counts
        rows = await session.execute(text(
            "SELECT platform, COUNT(*) as cnt "
            "FROM platform_restaurants GROUP BY platform ORDER BY cnt DESC"
        ))
        for row in rows:
            logger.info(f"  {row[0]:12s}: {row[1]:>5d} platform_restaurants")

        # Unmatched count
        row = await session.execute(text(
            "SELECT COUNT(*) FROM platform_restaurants "
            "WHERE canonical_restaurant_id IS NULL"
        ))
        unmatched = row.scalar()
        logger.info(f"  Unmatched (canonical_id IS NULL): {unmatched}")

        # Lat/lng coverage
        row = await session.execute(text(
            "SELECT platform, "
            "COUNT(*) FILTER (WHERE latitude IS NOT NULL) as with_coords, "
            "COUNT(*) as total "
            "FROM platform_restaurants GROUP BY platform ORDER BY total DESC"
        ))
        for r in row:
            pct = (r[1] / r[2] * 100) if r[2] > 0 else 0
            logger.info(f"  {r[0]:12s}: {r[1]}/{r[2]} have coordinates ({pct:.0f}%)")


async def step3_rematch():
    """Re-run restaurant matcher on new data."""
    from app.jobs.db import get_async_session
    from app.entity_resolution.restaurant_matcher import RestaurantMatcher

    logger.info("=" * 60)
    logger.info("STEP 3: Re-match restaurants")
    logger.info("=" * 60)

    start = time.monotonic()
    async with get_async_session() as session:
        matcher = RestaurantMatcher(session)
        stats = await matcher.match_all_platforms("warszawa")
        await session.commit()

    elapsed = time.monotonic() - start
    logger.info(f"  Result: {stats}")
    logger.info(f"  Elapsed: {elapsed:.1f}s")
    return stats


async def step4_verify_matches():
    """Verify match results."""
    from app.jobs.db import get_async_session
    from sqlalchemy import text

    logger.info("=" * 60)
    logger.info("STEP 4: Verify match results")
    logger.info("=" * 60)

    async with get_async_session() as session:
        rows = await session.execute(text(
            "SELECT platform, "
            "COUNT(*) as total, "
            "COUNT(canonical_restaurant_id) as matched, "
            "COUNT(*) FILTER (WHERE canonical_restaurant_id IS NULL) as unmatched "
            "FROM platform_restaurants GROUP BY platform ORDER BY total DESC"
        ))
        for r in rows:
            logger.info(
                f"  {r[0]:12s}: {r[2]:>5d} matched / {r[3]:>5d} unmatched "
                f"(total {r[1]})"
            )

        # Cross-platform matches (non-wolt matched to wolt canonicals)
        row = await session.execute(text("""
            SELECT pr.platform, COUNT(DISTINCT pr.canonical_restaurant_id)
            FROM platform_restaurants pr
            WHERE pr.canonical_restaurant_id IS NOT NULL
              AND pr.platform != 'wolt'
            GROUP BY pr.platform
        """))
        for r in row:
            logger.info(f"  {r[0]:12s}: {r[1]} matched to canonicals")

        # Review queue
        row = await session.execute(text(
            "SELECT COUNT(*) FROM entity_review_queue WHERE status = 'pending'"
        ))
        pending = row.scalar()
        logger.info(f"  Entity review queue: {pending} pending")

        # Canonical count
        row = await session.execute(text(
            "SELECT COUNT(*) FROM canonical_restaurants"
        ))
        logger.info(f"  Total canonical_restaurants: {row.scalar()}")


async def step5_crawl_sample_menus():
    """Crawl menus for a sample of matched restaurants (top 20 cross-platform)."""
    from app.jobs.db import get_async_session
    from app.jobs.crawl_menus import _crawl_menu_async
    from sqlalchemy import text

    logger.info("=" * 60)
    logger.info("STEP 5: Crawl menus for matched restaurants (sample)")
    logger.info("=" * 60)

    # Find restaurants matched on 2+ platforms (most valuable for comparison)
    async with get_async_session() as session:
        rows = await session.execute(text("""
            SELECT pr.platform, pr.platform_restaurant_id, pr.platform_slug,
                   pr.platform_name, cr.name as canonical_name
            FROM platform_restaurants pr
            JOIN canonical_restaurants cr ON pr.canonical_restaurant_id = cr.id
            WHERE pr.canonical_restaurant_id IN (
                SELECT canonical_restaurant_id
                FROM platform_restaurants
                WHERE canonical_restaurant_id IS NOT NULL
                GROUP BY canonical_restaurant_id
                HAVING COUNT(DISTINCT platform) >= 2
            )
            ORDER BY cr.name, pr.platform
            LIMIT 60
        """))
        to_crawl = [(r[0], r[1], r[2], r[3], r[4]) for r in rows]

    if not to_crawl:
        logger.warning("  No cross-platform matched restaurants found!")
        return

    logger.info(f"  Found {len(to_crawl)} platform entries to crawl menus for")

    # Group by canonical for display
    by_canonical = {}
    for platform, pid, slug, pname, cname in to_crawl:
        by_canonical.setdefault(cname, []).append((platform, slug or pid))

    for cname, entries in list(by_canonical.items())[:5]:
        platforms = ", ".join(f"{p}:{s[:20]}" for p, s in entries)
        logger.info(f"  {cname}: {platforms}")
    if len(by_canonical) > 5:
        logger.info(f"  ... and {len(by_canonical) - 5} more")

    # Crawl menus (use slug for wolt/pyszne/glovo, UUID for ubereats)
    success = 0
    failed = 0
    for platform, pid, slug, pname, cname in to_crawl:
        menu_slug = slug or pid
        try:
            result = await _crawl_menu_async(platform, menu_slug)
            items = result.get("items_count", 0)
            if items > 0:
                success += 1
                logger.info(f"  OK: {platform}/{pname[:30]} → {items} items")
            else:
                failed += 1
                logger.debug(f"  EMPTY: {platform}/{pname[:30]} → 0 items")
        except Exception as e:
            failed += 1
            logger.debug(f"  FAIL: {platform}/{menu_slug[:30]} → {e}")

    logger.info(f"  Menu crawl: {success} OK, {failed} failed/empty")


async def step6_menu_stats():
    """Show menu item counts per platform."""
    from app.jobs.db import get_async_session
    from sqlalchemy import text

    logger.info("=" * 60)
    logger.info("STEP 6: Menu item stats")
    logger.info("=" * 60)

    async with get_async_session() as session:
        rows = await session.execute(text("""
            SELECT pr.platform, COUNT(pmi.id) as items
            FROM platform_menu_items pmi
            JOIN platform_restaurants pr ON pmi.platform_restaurant_id = pr.id
            GROUP BY pr.platform
            ORDER BY items DESC
        """))
        for r in rows:
            logger.info(f"  {r[0]:12s}: {r[1]:>6d} menu items")

        # Cross-platform restaurants with menus on 2+ platforms
        row = await session.execute(text("""
            SELECT COUNT(DISTINCT canonical_restaurant_id)
            FROM platform_restaurants pr
            WHERE pr.canonical_restaurant_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM platform_menu_items pmi
                  WHERE pmi.platform_restaurant_id = pr.id
              )
            GROUP BY canonical_restaurant_id
            HAVING COUNT(DISTINCT pr.platform) >= 2
        """))
        multi = len(row.all()) if row else 0
        logger.info(f"  Restaurants with menus on 2+ platforms: {multi}")


async def main():
    logger.info("Post-Sitemap Pipeline: Re-crawl → Re-match → Menu Crawl")
    logger.info("")

    await step1_recrawl()
    await step2_verify_db()
    await step3_rematch()
    await step4_verify_matches()
    await step5_crawl_sample_menus()
    await step6_menu_stats()

    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE — Ready for Sprint 4.5 (Menu Item Matching)")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())