"""
Cross-platform comparison — Wolt vs Pyszne vs Glovo.

Same location (Warszawa centrum), then tries to find and compare
the same restaurant (KFC) across all 3 platforms.

Usage:
  cd backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python -m app.scraper.tests.manual_test_cross_platform
"""

import asyncio
import sys
import time
from collections import defaultdict

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.orchestrator import ScraperOrchestrator
from app.scraper.quality_scorer import score_menu

LAT, LNG = 52.2297, 21.0122

# Known slugs for KFC across platforms — override if auto-discovery fails
KFC_SLUGS_FALLBACK = {
    "pyszne": "kfc-waw",
    "glovo": "kfc-waw",
}


def _find_kfc_slugs(result) -> dict[str, str]:
    """Auto-discover KFC slugs from search results."""
    slugs = {}
    for platform, restaurants in result.restaurants.items():
        kfc = next(
            (r for r in restaurants if "kfc" in r.name.lower() and r.is_online),
            next((r for r in restaurants if "kfc" in r.name.lower()), None),
        )
        if kfc:
            slugs[platform] = kfc.platform_slug
    # Merge with fallbacks for platforms without search (Glovo)
    for platform, slug in KFC_SLUGS_FALLBACK.items():
        if platform not in slugs:
            slugs[platform] = slug
    return slugs


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    orch = ScraperOrchestrator(redis)

    # ═══════════════════════════════════════════════════════
    # PART 1: Parallel search — all platforms, same location
    # ═══════════════════════════════════════════════════════

    print("=" * 70)
    print("CROSS-PLATFORM SEARCH — Warszawa centrum")
    print(f"Location: {LAT}, {LNG}")
    print("=" * 70)

    start = time.monotonic()
    result = await orch.search_all(LAT, LNG, 5.0)
    total_ms = (time.monotonic() - start) * 1000

    for platform in ["wolt", "pyszne", "glovo"]:
        restaurants = result.restaurants.get(platform, [])
        error = result.errors.get(platform)
        cached = platform in result.from_cache
        elapsed = result.timings.get(platform, 0)

        if error:
            print(f"\n  [{platform.upper():7s}] ✗ ERROR: {error[:80]}")
        else:
            status = "CACHE" if cached else f"{elapsed:.0f}ms"
            online = sum(1 for r in restaurants if r.is_online)
            print(f"\n  [{platform.upper():7s}] {len(restaurants):3d} restaurants ({online} online) [{status}]")
            for r in restaurants[:3]:
                icon = "✓" if r.is_online else "✗"
                fee = f"{r.delivery_fee.fee_grosz / 100:.2f}zł" if r.delivery_fee else "?"
                print(f"    {icon} {r.platform_name[:40]:40s} fee={fee}")
            if len(restaurants) > 3:
                print(f"    ... +{len(restaurants) - 3}")

    total = len(result.all_restaurants)
    print(f"\n  {'─' * 50}")
    print(f"  TOTAL: {total} restaurants across {len(result.restaurants)} platforms ({total_ms:.0f}ms)")

    # ═══════════════════════════════════════════════════════
    # PART 2: Find common restaurant names across platforms
    # ═══════════════════════════════════════════════════════

    print(f"\n{'=' * 70}")
    print("COMMON RESTAURANTS — appearing on multiple platforms")
    print("=" * 70)

    # Normalize names for matching
    name_to_platforms: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for platform, restaurants in result.restaurants.items():
        for r in restaurants:
            # Simple normalization for matching
            key = r.name.lower().strip().split(" - ")[0].split(" (")[0].strip()
            name_to_platforms[key].append((platform, r.platform_slug, r.name))

    multi_platform = {
        k: v for k, v in name_to_platforms.items()
        if len(v) >= 2 and len(set(p for p, _, _ in v)) >= 2
    }

    if multi_platform:
        for name, entries in sorted(multi_platform.items(), key=lambda x: -len(x[1]))[:10]:
            platforms_str = ", ".join(f"{p}:{slug}" for p, slug, _ in entries)
            print(f"  {entries[0][2]:40s} → {platforms_str}")
        print(f"\n  Found {len(multi_platform)} restaurants on 2+ platforms")
    else:
        print("  No exact name matches found (names may differ between platforms)")

    # ═══════════════════════════════════════════════════════
    # PART 3: KFC menu comparison across platforms
    # ═══════════════════════════════════════════════════════

    print(f"\n{'=' * 70}")
    print("KFC MENU COMPARISON — same restaurant, 3 platforms")
    print("=" * 70)

    # Try known KFC slugs — auto-discover from search results
    active_slugs = _find_kfc_slugs(result)

    if not active_slugs:
        print("  KFC not found on any platform. Skipping menu comparison.")
        await redis.aclose()
        return

    print(f"  Slugs: {active_slugs}")

    start = time.monotonic()
    menu_result = await orch.get_menu_all(active_slugs)
    menu_ms = (time.monotonic() - start) * 1000

    # Per-platform summary
    platform_items: dict[str, dict] = {}  # platform → {name: item}
    for platform in ["wolt", "pyszne", "glovo"]:
        items = menu_result.menus.get(platform, [])
        error = menu_result.errors.get(platform)
        cached = platform in menu_result.from_cache
        elapsed = menu_result.timings.get(platform, 0)

        if error:
            print(f"\n  [{platform.upper():7s}] ✗ {error[:80]}")
            continue

        status = "CACHE" if cached else f"{elapsed:.0f}ms"
        available = sum(1 for i in items if i.is_available)
        with_mods = sum(1 for i in items if i.modifier_groups)

        # Quality
        report = score_menu(items, platform, active_slugs.get(platform, ""))

        print(f"\n  [{platform.upper():7s}] {len(items):3d} items ({available} avail, {with_mods} with mods) [{status}]")
        print(f"            Quality: {report.score:.3f} [{report.status.upper()}]")

        # Build lookup
        lookup = {}
        for item in items:
            lookup[item.platform_name.lower().strip()] = item
        platform_items[platform] = lookup

        # Top 5 by price
        sorted_items = sorted(items, key=lambda i: -i.price_grosz)[:5]
        print(f"            Top 5 by price:")
        for item in sorted_items:
            mods = f" ({len(item.modifier_groups)} mod)" if item.modifier_groups else ""
            print(f"              {item.platform_name[:45]:45s} {item.price_grosz / 100:7.2f} zł{mods}")

    print(f"\n  {'─' * 50}")
    print(f"  Menu fetch: {menu_ms:.0f}ms total")

    # ═══════════════════════════════════════════════════════
    # PART 4: Price comparison — same items across platforms
    # ═══════════════════════════════════════════════════════

    if len(platform_items) >= 2:
        print(f"\n{'=' * 70}")
        print("PRICE COMPARISON — same items across platforms")
        print("=" * 70)

        # Find items with similar names across platforms
        all_names: set[str] = set()
        for lookup in platform_items.values():
            all_names.update(lookup.keys())

        compared = 0
        for name in sorted(all_names):
            prices = {}
            for platform, lookup in platform_items.items():
                item = lookup.get(name)
                if item and item.price_grosz > 0:
                    prices[platform] = item.price_grosz

            if len(prices) >= 2:
                compared += 1
                if compared > 20:
                    print(f"  ... (showing first 20 of more matches)")
                    break

                # Find cheapest
                cheapest = min(prices, key=prices.get)
                most_expensive = max(prices, key=prices.get)
                diff = prices[most_expensive] - prices[cheapest]
                diff_pct = (diff / prices[cheapest] * 100) if prices[cheapest] > 0 else 0

                price_str = " | ".join(
                    f"{p}: {v / 100:.2f}zł{'*' if p == cheapest else ''}"
                    for p, v in sorted(prices.items())
                )

                marker = ""
                if diff_pct > 10:
                    marker = f" ⚠ {diff_pct:.0f}% diff"
                elif diff_pct > 0:
                    marker = f" ({diff_pct:.0f}% diff)"

                display_name = name[:35]
                print(f"  {display_name:35s} {price_str}{marker}")

        if compared == 0:
            print("  No exact name matches found between platforms.")
            print("  (Names often differ: 'Cheeseburger' vs 'Burger Cheeseburger')")

            # Fuzzy match attempt
            print(f"\n  Fuzzy matches (substring):")
            fuzzy_count = 0
            for name in sorted(all_names):
                if len(name) < 5:
                    continue
                matches = {}
                for platform, lookup in platform_items.items():
                    for item_name, item in lookup.items():
                        if name in item_name or item_name in name:
                            if platform not in matches:
                                matches[platform] = (item_name, item.price_grosz)
                if len(matches) >= 2:
                    fuzzy_count += 1
                    if fuzzy_count > 15:
                        break
                    parts = " | ".join(
                        f"{p}: {n[:25]}={v / 100:.2f}zł"
                        for p, (n, v) in sorted(matches.items())
                    )
                    print(f"    {parts}")

    # ═══════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    for platform in ["wolt", "pyszne", "glovo"]:
        r_count = len(result.restaurants.get(platform, []))
        m_count = len(menu_result.menus.get(platform, []))
        r_err = "✗" if platform in result.errors else "✓"
        m_err = "✗" if platform in menu_result.errors else "✓"
        print(f"  {platform:7s}: search {r_err} ({r_count:3d} rest) | menu {m_err} ({m_count:3d} items)")

    print(f"\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
