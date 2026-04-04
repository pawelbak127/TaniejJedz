"""
UberEats sitemap discovery — background job.

Fetches UberEats store sitemaps (public, from robots.txt), extracts all
Polish store URLs with base64 UUIDs, and saves to Redis.

Redis keys:
    scraper:ubereats:known_stores   →  JSON list of {slug, uuid, locale}
    scraper:ubereats:sitemap_meta   →  JSON {last_sync, total_stores, duration}

URL pattern:
    https://www.ubereats.com/pl/store/{slug}/{base64_uuid}
    https://www.ubereats.com/pl-en/store/{slug}/{base64_uuid}

Usage (PowerShell, from backend/):
    python -m app.jobs.sync_ubereats_slugs
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════

UBEREATS_BASE = "https://www.ubereats.com"
ROBOTS_URL = f"{UBEREATS_BASE}/robots.txt"

# Concurrency for sitemap fetches
_FETCH_CONCURRENCY = 5

# ═══════════════════════════════════════════════════════════════
# Regexes
# ═══════════════════════════════════════════════════════════════

# Polish store URL: /pl/store/{slug}/{base64_uuid} or /pl-en/store/...
_PL_STORE_RE = re.compile(
    r"https://www\.ubereats\.com/(pl(?:-en)?)/store/"
    r"([^/\s<]+)"            # slug (URL-encoded)
    r"/([A-Za-z0-9_\-]+)"   # base64 UUID
)

_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")
_ROBOTS_SITEMAP_RE = re.compile(r"^Sitemap:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
_SITEMAP_CHILD_RE = re.compile(r"<loc>\s*(https://[^<]+?)\s*</loc>")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TaniejJedz/1.0; food-price-comparison)",
    "Accept": "*/*",
}

# ═══════════════════════════════════════════════════════════════
# Non-food filtering (adapted from Glovo)
# ═══════════════════════════════════════════════════════════════

_NON_FOOD_KEYWORDS = [
    "apteczka", "apteka", "pharmacy",
    "biedronka", "rossmann", "hebe", "stokrotka",
    "carrefour", "auchan", "lidl", "kaufland",
    "zabka", "żabka", "lewiatan",
    "mediamarkt", "empik", "decathlon",
    "pepco", "action", "tedi",
    "zooplus", "maxi-zoo", "kakadu",
]


def _is_non_food_slug(slug: str) -> bool:
    slug_lower = slug.lower()
    return any(kw in slug_lower for kw in _NON_FOOD_KEYWORDS)


# ═══════════════════════════════════════════════════════════════
# Fetch utilities
# ═══════════════════════════════════════════════════════════════

async def _fetch_gz(client: httpx.AsyncClient, url: str) -> bytes | None:
    """Fetch URL, decompress gzip if needed."""
    try:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code != 200:
            return None
        content = resp.content
        if url.endswith(".gz"):
            content = gzip.decompress(content)
        return content
    except Exception as e:
        logger.debug("Fetch failed %s: %s", url, e)
        return None


# ═══════════════════════════════════════════════════════════════
# Core sync
# ═══════════════════════════════════════════════════════════════

def _extract_stores_from_xml(xml_text: str) -> list[dict]:
    """Extract Polish store {slug, uuid, locale} from sitemap XML."""
    stores = []
    for loc_match in _LOC_RE.finditer(xml_text):
        url = loc_match.group(1).strip()
        m = _PL_STORE_RE.match(url)
        if not m:
            continue
        locale = m.group(1)
        slug_raw = m.group(2)
        uuid = m.group(3)
        try:
            slug = unquote(slug_raw)
        except Exception:
            slug = slug_raw
        stores.append({"slug": slug, "uuid": uuid, "locale": locale})
    return stores


async def sync_ubereats_slugs(redis_client) -> int:
    """Main sync: fetch sitemaps → extract Polish stores → save to Redis.

    Returns total unique stores saved.
    """
    start = time.monotonic()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        headers=_HEADERS,
    ) as client:

        # Step 1: Get sitemap list from robots.txt
        robots_data = await _fetch_gz(client, ROBOTS_URL)
        if not robots_data:
            logger.error("Failed to fetch robots.txt")
            return 0

        robots_text = robots_data.decode("utf-8", errors="replace")
        sitemap_urls = _ROBOTS_SITEMAP_RE.findall(robots_text)
        logger.info("Found %d Sitemap directives in robots.txt", len(sitemap_urls))

        # Step 2: Expand sitemap index to get all store sitemaps
        index_urls = [u for u in sitemap_urls if "index" in u]
        store_urls = [u for u in sitemap_urls if "store" in u and "index" not in u]

        all_store_sitemaps = list(store_urls)
        for idx_url in index_urls:
            idx_data = await _fetch_gz(client, idx_url)
            if not idx_data:
                continue
            idx_text = idx_data.decode("utf-8", errors="replace")
            if "<sitemapindex" in idx_text:
                children = _SITEMAP_CHILD_RE.findall(idx_text)
                child_stores = [u for u in children if "store" in u]
                all_store_sitemaps.extend(child_stores)

        all_store_sitemaps = list(dict.fromkeys(all_store_sitemaps))
        logger.info("Total store sitemaps to scan: %d", len(all_store_sitemaps))

        # Step 3: Fetch and parse all sitemaps concurrently
        semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)
        all_stores: list[dict] = []

        async def scan_one(url: str) -> list[dict]:
            async with semaphore:
                data = await _fetch_gz(client, url)
                if not data:
                    return []
                text = data.decode("utf-8", errors="replace")
                return _extract_stores_from_xml(text)

        tasks = [scan_one(u) for u in all_store_sitemaps]
        results = await asyncio.gather(*tasks)

        for stores in results:
            all_stores.extend(stores)

    # Step 4: Deduplicate by UUID
    seen: set[str] = set()
    unique: list[dict] = []
    skipped_non_food = 0

    for s in all_stores:
        if s["uuid"] in seen:
            continue
        seen.add(s["uuid"])
        if _is_non_food_slug(s["slug"]):
            skipped_non_food += 1
            continue
        unique.append(s)

    # Step 5: Save to Redis
    # Single key with all stores (they don't have city info in the URL)
    await redis_client.set(
        "scraper:ubereats:known_stores",
        json.dumps(unique),
    )

    meta = {
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "total_stores": len(unique),
        "total_raw": len(all_stores),
        "skipped_non_food": skipped_non_food,
        "sitemaps_scanned": len(all_store_sitemaps),
        "duration_seconds": round(time.monotonic() - start, 2),
    }
    await redis_client.set("scraper:ubereats:sitemap_meta", json.dumps(meta))

    elapsed = time.monotonic() - start
    logger.info(
        "UberEats sitemap sync complete: %d unique stores in %.1fs "
        "(raw: %d, non-food skipped: %d, sitemaps: %d)",
        len(unique), elapsed, len(all_stores),
        skipped_non_food, len(all_store_sitemaps),
    )

    return len(unique)


# ═══════════════════════════════════════════════════════════════
# Redis connection (standalone) — same pattern as Glovo sync
# ═══════════════════════════════════════════════════════════════

def _get_redis_url() -> str:
    url = os.environ.get("REDIS_URL")
    if not url:
        try:
            from app.config import get_settings
            settings = get_settings()
            url = str(getattr(settings, "REDIS_URL", "") or getattr(settings, "redis_url", ""))
        except Exception:
            pass
    if not url:
        url = "redis://:localdevpassword@localhost:6379/0"
    url = re.sub(r"@redis:", "@localhost:", url)
    return url


async def _connect_redis():
    from redis.asyncio import Redis
    url = _get_redis_url()
    safe_url = re.sub(r"://:[^@]+@", "://:*****@", url)
    print(f"  Connecting to: {safe_url}")
    redis = Redis.from_url(url, decode_responses=True)
    await redis.ping()
    return redis


# ═══════════════════════════════════════════════════════════════
# Standalone runner
# ═══════════════════════════════════════════════════════════════

async def _run_standalone():
    print("=" * 60)
    print("  UBEREATS SITEMAP SYNC — standalone runner")
    print("=" * 60)
    print()

    try:
        redis = await _connect_redis()
        print("  ✓ Connected to Redis")
    except Exception as e:
        print(f"  ✗ Redis connection failed: {e}")
        print()
        print("  Quick fix (PowerShell):")
        print('    $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"')
        return

    print()

    try:
        total = await sync_ubereats_slugs(redis)

        print(f"\n{'='*60}")
        print("  SYNC COMPLETE")
        print(f"{'='*60}")
        print(f"  Total unique stores: {total}")

        meta_raw = await redis.get("scraper:ubereats:sitemap_meta")
        if meta_raw:
            meta = json.loads(meta_raw)
            print(f"  Duration: {meta['duration_seconds']}s")
            print(f"  Sitemaps scanned: {meta['sitemaps_scanned']}")
            print(f"  Non-food skipped: {meta['skipped_non_food']}")

        # Show sample
        raw = await redis.get("scraper:ubereats:known_stores")
        if raw:
            stores = json.loads(raw)
            print(f"\n  Sample stores (first 15 of {len(stores)}):")
            print(f"  {'SLUG':<45} {'UUID':<25}")
            print(f"  {'─'*45} {'─'*25}")
            for s in stores[:15]:
                slug_display = s["slug"][:43]
                uuid_display = s["uuid"][:23]
                print(f"  {slug_display:<45} {uuid_display:<25}")

    finally:
        await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(_run_standalone())
