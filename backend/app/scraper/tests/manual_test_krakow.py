"""
Cross-platform comparison — Kraków.

Finds the nearest restaurant to given coordinates across all 4 platforms,
then compares menu prices item-by-item.

Usage:
  cd backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python -m app.scraper.tests.manual_test_krakow
"""

import asyncio
import math
import time
from collections import defaultdict

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.orchestrator import ScraperOrchestrator
from app.scraper.adapters.ubereats import UberEatsAdapter
from app.scraper.quality_scorer import score_menu

# Kraków Rynek Główny
LAT, LNG = 50.0614, 19.9372


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in km between two points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_nearest(restaurants, lat, lng, min_name_len=3):
    """Find restaurant closest to coordinates (with valid location)."""
    best = None
    best_dist = float("inf")
    for r in restaurants:
        if r.latitude == 0.0 and r.longitude == 0.0:
            continue
        dist = _haversine_km(lat, lng, r.latitude, r.longitude)
        if dist < best_dist:
            best_dist = dist
            best = r
    return best, best_dist


def _normalize_name(name: str) -> str:
    """Normalize for cross-platform matching."""
    import unicodedata
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [" - kraków", " kraków", " krakow", " - krakow"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    # Remove diacritics
    nfkd = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Remove non-alphanumeric (keep spaces)
    name = "".join(c for c in name if c.isalnum() or c == " ")
    return name.strip()


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    orch = ScraperOrchestrator(redis)

    # ═══════════════════════════════════════════════════════
    # PART 1: Search all platforms — Kraków
    # ═══════════════════════════════════════════════════════

    print("=" * 70)
    print("KRAKÓW — CROSS-PLATFORM SEARCH")
    print(f"Location: {LAT}, {LNG} (Rynek Główny)")
    print("=" * 70)

    start = time.monotonic()
    result = await orch.search_all(LAT, LNG, 5.0)
    total_ms = (time.monotonic() - start) * 1000

    for platform in ["wolt", "pyszne", "glovo", "ubereats"]:
        restaurants = result.restaurants.get(platform, [])
        error = result.errors.get(platform)
        elapsed = result.timings.get(platform, 0)
        cached = platform in result.from_cache

        if error:
            print(f"\n  [{platform.upper():9s}] ✗ ERROR: {str(error)[:80]}")
        else:
            status = "CACHE" if cached else f"{elapsed:.0f}ms"
            online = sum(1 for r in restaurants if r.is_online)
            print(f"\n  [{platform.upper():9s}] {len(restaurants):4d} restaurants ({online} online) [{status}]")

    total = len(result.all_restaurants)
    print(f"\n  {'─' * 55}")
    print(f"  TOTAL: {total} restaurants ({total_ms:.0f}ms)")

    # ═══════════════════════════════════════════════════════
    # PART 2: Find nearest restaurant to Rynek
    # ═══════════════════════════════════════════════════════

    print(f"\n{'=' * 70}")
    print("NEAREST RESTAURANT TO RYNEK GŁÓWNY")
    print("=" * 70)

    # Find nearest per platform (only those with coordinates)
    nearest_per_platform: dict[str, tuple] = {}
    for platform in ["wolt", "pyszne"]:  # Only these have coordinates
        restaurants = result.restaurants.get(platform, [])
        if not restaurants:
            continue
        nearest, dist = _find_nearest(restaurants, LAT, LNG)
        if nearest:
            nearest_per_platform[platform] = (nearest, dist)
            print(f"  [{platform.upper():9s}] {nearest.platform_name[:45]:45s} ({dist:.2f} km)")

    # Pick the overall nearest
    if not nearest_per_platform:
        print("  No restaurants with coordinates found.")
        await redis.aclose()
        return

    overall_platform, (target, target_dist) = min(
        nearest_per_platform.items(), key=lambda x: x[1][1]
    )
    target_name = target.name
    target_norm = _normalize_name(target_name)

    print(f"\n  → TARGET: {target_name} on {overall_platform} ({target_dist:.2f} km)")
    print(f"    Normalized: '{target_norm}'")

    # ═══════════════════════════════════════════════════════
    # PART 3: Find same restaurant on other platforms
    # ═══════════════════════════════════════════════════════

    print(f"\n{'=' * 70}")
    print(f"FINDING '{target_name}' ON ALL PLATFORMS")
    print("=" * 70)

    # Build name index for fuzzy matching
    matched_slugs: dict[str, str] = {}  # platform → slug/uuid

    for platform, restaurants in result.restaurants.items():
        best_match = None
        best_score = 0

        for r in restaurants:
            r_norm = _normalize_name(r.name)

            # Exact match
            if r_norm == target_norm:
                best_match = r
                best_score = 100
                break

            # Contains match
            if target_norm in r_norm or r_norm in target_norm:
                score = 80
                if score > best_score:
                    best_match = r
                    best_score = score
                    continue

            # Word overlap
            target_words = set(target_norm.split())
            r_words = set(r_norm.split())
            if target_words and r_words:
                overlap = len(target_words & r_words)
                total_words = max(len(target_words), len(r_words))
                score = int(overlap / total_words * 70)
                if score > best_score and score >= 40:
                    best_match = r
                    best_score = score

        if best_match:
            matched_slugs[platform] = best_match.platform_slug or best_match.platform_restaurant_id
            match_type = "exact" if best_score == 100 else f"fuzzy ({best_score}%)"
            print(f"  [{platform.upper():9s}] ✓ {best_match.name[:45]:45s} [{match_type}]")
            print(f"             slug: {matched_slugs[platform]}")
        else:
            print(f"  [{platform.upper():9s}] ✗ not found")

    # Also try Uber Eats direct search for target name
    if "ubereats" not in matched_slugs:
        try:
            ue_adapter = UberEatsAdapter(redis)
            suggestions = await ue_adapter._search_suggestions(target_name)
            for s in suggestions:
                s_norm = _normalize_name(s.title)
                if target_norm in s_norm or s_norm in target_norm:
                    matched_slugs["ubereats"] = s.uuid
                    print(f"  [UBEREATS  ] ✓ {s.title[:45]:45s} [suggestion match]")
                    print(f"             uuid: {s.uuid}")
                    break
        except Exception as exc:
            print(f"  [UBEREATS  ] ✗ suggestion search failed: {exc}")

    if len(matched_slugs) < 2:
        print(f"\n  Found on only {len(matched_slugs)} platform(s). Need 2+ for comparison.")

        # Fallback: pick a well-known chain
        print(f"\n  FALLBACK: Looking for KFC / McDonald's / Burger King...")
        chains = ["kfc", "mcdonald", "burger king"]
        for chain in chains:
            chain_slugs: dict[str, str] = {}
            for platform, restaurants in result.restaurants.items():
                match = next((r for r in restaurants if chain in r.name.lower() and r.is_online), None)
                if match:
                    chain_slugs[platform] = match.platform_slug or match.platform_restaurant_id
                    print(f"    [{platform.upper():9s}] {match.name[:45]:45s} slug={chain_slugs[platform]}")

            if len(chain_slugs) >= 2:
                matched_slugs = chain_slugs
                target_name = chain.upper()
                print(f"\n  → Using {target_name} ({len(matched_slugs)} platforms)")
                break

    if len(matched_slugs) < 2:
        print("\n  Cannot find any restaurant on 2+ platforms. Aborting.")
        await redis.aclose()
        return

    # ═══════════════════════════════════════════════════════
    # PART 4: Fetch menus and compare
    # ═══════════════════════════════════════════════════════

    print(f"\n{'=' * 70}")
    print(f"MENU COMPARISON: {target_name}")
    print("=" * 70)

    start = time.monotonic()
    menu_result = await orch.get_menu_all(matched_slugs)

    # Also fetch Uber Eats menu directly if matched
    if "ubereats" in matched_slugs and "ubereats" not in menu_result.menus:
        try:
            ue_adapter = UberEatsAdapter(redis)
            ue_items = await ue_adapter.get_menu(matched_slugs["ubereats"])
            menu_result.menus["ubereats"] = ue_items
            menu_result.timings["ubereats"] = 0
        except Exception as exc:
            menu_result.errors["ubereats"] = str(exc)

    menu_ms = (time.monotonic() - start) * 1000

    platform_items: dict[str, dict[str, tuple]] = {}  # platform → {norm_name: (name, price)}

    for platform in ["wolt", "pyszne", "glovo", "ubereats"]:
        items = menu_result.menus.get(platform, [])
        error = menu_result.errors.get(platform)
        elapsed = menu_result.timings.get(platform, 0)

        if error:
            print(f"\n  [{platform.upper():9s}] ✗ {str(error)[:80]}")
            continue
        if not items:
            continue

        report = score_menu(items, platform, matched_slugs.get(platform, ""))
        avail = sum(1 for i in items if i.is_available)
        mods = sum(1 for i in items if i.modifier_groups)

        print(f"\n  [{platform.upper():9s}] {len(items):3d} items ({avail} avail, {mods} mods)")
        print(f"             Quality: {report.score:.3f} [{report.status.upper()}] | {elapsed:.0f}ms")

        # Build lookup
        lookup = {}
        for item in items:
            norm = _normalize_name(item.platform_name)
            if norm and item.price_grosz > 0:
                lookup[norm] = (item.platform_name, item.price_grosz)
        platform_items[platform] = lookup

    print(f"\n  Menu fetch: {menu_ms:.0f}ms")

    # ═══════════════════════════════════════════════════════
    # PART 5: Price comparison
    # ═══════════════════════════════════════════════════════

    if len(platform_items) >= 2:
        print(f"\n{'=' * 70}")
        print("PRICE COMPARISON")
        print("=" * 70)

        all_names: set[str] = set()
        for lookup in platform_items.values():
            all_names.update(lookup.keys())

        # Collect matches
        comparisons = []
        for norm_name in sorted(all_names):
            prices = {}
            display_name = norm_name
            for platform, lookup in platform_items.items():
                if norm_name in lookup:
                    orig_name, price = lookup[norm_name]
                    prices[platform] = price
                    display_name = orig_name

            if len(prices) >= 2:
                cheapest_platform = min(prices, key=prices.get)
                most_expensive = max(prices, key=prices.get)
                diff = prices[most_expensive] - prices[cheapest_platform]
                diff_pct = (diff / prices[cheapest_platform] * 100) if prices[cheapest_platform] > 0 else 0
                comparisons.append((display_name, prices, cheapest_platform, diff_pct))

        # Sort by price difference (biggest savings first)
        comparisons.sort(key=lambda x: -x[3])

        if comparisons:
            # Summary stats
            total_savings = 0
            for _, prices, cheapest, _ in comparisons:
                most_exp = max(prices.values())
                total_savings += most_exp - prices[cheapest]

            print(f"\n  Matched items: {len(comparisons)}")
            print(f"  Total potential savings: {total_savings / 100:.2f} zł")
            print(f"  (if you always pick the cheapest platform per item)\n")

            # Header
            platforms = sorted(platform_items.keys())
            header = f"  {'Pozycja':40s}"
            for p in platforms:
                header += f" {p:>10s}"
            header += "     diff"
            print(header)
            print(f"  {'─' * (42 + 11 * len(platforms) + 10)}")

            for display_name, prices, cheapest, diff_pct in comparisons[:30]:
                row = f"  {display_name[:40]:40s}"
                for p in platforms:
                    if p in prices:
                        price_str = f"{prices[p] / 100:.2f}"
                        marker = "*" if p == cheapest and len(prices) > 1 and diff_pct > 0 else " "
                        row += f" {price_str:>9s}{marker}"
                    else:
                        row += f" {'—':>10s}"

                if diff_pct > 10:
                    row += f"  ⚠ {diff_pct:.0f}%"
                elif diff_pct > 0:
                    row += f"    {diff_pct:.0f}%"

                print(row)

            if len(comparisons) > 30:
                print(f"  ... +{len(comparisons) - 30} more items")

            # Platform ranking
            print(f"\n  {'─' * 55}")
            print(f"  PLATFORM RANKING (cheapest wins):")
            wins: dict[str, int] = defaultdict(int)
            for _, prices, cheapest, diff_pct in comparisons:
                if diff_pct > 0:
                    wins[cheapest] += 1

            for platform, count in sorted(wins.items(), key=lambda x: -x[1]):
                pct = count / len(comparisons) * 100
                print(f"    {platform:10s}: cheapest on {count:3d}/{len(comparisons)} items ({pct:.0f}%)")

        else:
            print("\n  No exact name matches between platforms.")
            print("  Names often differ: 'Cheeseburger' vs 'Burger Cheeseburger'")

    # ═══════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    for platform in ["wolt", "pyszne", "glovo", "ubereats"]:
        r_count = len(result.restaurants.get(platform, []))
        m_count = len(menu_result.menus.get(platform, []))
        r_ok = "✓" if platform not in result.errors else "✗"
        m_ok = "✓" if platform not in menu_result.errors and m_count > 0 else "✗"
        slug = matched_slugs.get(platform, "—")
        print(f"  {platform:9s}: search {r_ok} ({r_count:4d}) | menu {m_ok} ({m_count:3d}) | slug: {slug}")

    print(f"\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
