"""
UberEats enrichment job — batch fetch store details via getStoreV1.

Fetches coordinates, real store name, and validates menu availability
for all UberEats stores from sitemap that don't yet have coordinates.

Requires: sitemap sync already run (scraper:ubereats:known_stores:* in Redis)

Usage: python -m app.jobs.enrich_ubereats

Redis output:
    scraper:ubereats:enriched:{city_slug}  →  JSON list of enriched stores
    scraper:ubereats:enrich_meta           →  stats
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
import uuid as uuid_module
from collections import defaultdict
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_UBEREATS_BASE = "https://www.ubereats.com"
_CONCURRENCY = 3       # parallel API requests
_DELAY = 1.0           # seconds between requests (rate limit)
_TIMEOUT = 10.0


def decode_ubereats_uuid(b64url: str) -> str:
    """Convert base64url UUID to hex format for API."""
    padding = "=" * (4 - (len(b64url) % 4)) if len(b64url) % 4 != 0 else ""
    raw_bytes = base64.urlsafe_b64decode(b64url + padding)
    if len(raw_bytes) != 16:
        raise ValueError(f"Expected 16 bytes, got {len(raw_bytes)}")
    return str(uuid_module.UUID(bytes=raw_bytes))


async def fetch_store_details(
    client: httpx.AsyncClient,
    hex_uuid: str,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """Fetch store details from getStoreV1. Returns enriched data or None."""
    async with semaphore:
        try:
            resp = await client.post(
                f"{_UBEREATS_BASE}/_p/api/getStoreV1?localeCode=pl-en",
                json={
                    "storeUuid": hex_uuid,
                    "diningMode": "DELIVERY",
                    "time": {"asap": True},
                },
                headers={
                    "x-csrf-token": "x",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Origin": _UBEREATS_BASE,
                    "Referer": f"{_UBEREATS_BASE}/",
                },
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            if data.get("status") != "success":
                return None

            store = data.get("data", {})
            loc = store.get("location", {})
            catalog = store.get("catalogSectionsMap", {})

            # Count menu items
            menu_count = 0
            if isinstance(catalog, dict):
                for entries in catalog.values():
                    if isinstance(entries, list):
                        for entry in entries:
                            sip = entry.get("payload", {}).get("standardItemsPayload", {})
                            menu_count += len(sip.get("catalogItems", []))

            return {
                "hex_uuid": hex_uuid,
                "title": store.get("title", ""),
                "slug": store.get("slug", ""),
                "latitude": loc.get("latitude", 0.0),
                "longitude": loc.get("longitude", 0.0),
                "address": loc.get("streetAddress", ""),
                "city": loc.get("city", ""),
                "is_open": store.get("isOpen", False),
                "menu_items": menu_count,
                "cuisine": store.get("cuisineList", []),
            }

        except Exception as e:
            logger.debug("enrich failed for %s: %s", hex_uuid[:12], e)
            return None
        finally:
            await asyncio.sleep(_DELAY)


async def enrich_city(redis_client, city_slug: str) -> dict:
    """Enrich all stores for a city. Returns stats dict."""
    redis_key = f"scraper:ubereats:known_stores:{city_slug}"
    raw = await redis_client.get(redis_key)
    if not raw:
        return {"city": city_slug, "total": 0, "enriched": 0, "failed": 0, "stale": 0}

    stores = json.loads(raw)
    total = len(stores)
    enriched = []
    failed = 0
    stale = 0
    decode_err = 0

    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_TIMEOUT),
        follow_redirects=True,
    ) as client:

        for i, store in enumerate(stores):
            b64url = store.get("uuid", "")
            if not b64url:
                continue

            try:
                hex_uuid = decode_ubereats_uuid(b64url)
            except Exception:
                decode_err += 1
                continue

            result = await fetch_store_details(client, hex_uuid, semaphore)

            if result:
                result["b64url"] = b64url
                result["slug_sitemap"] = store.get("slug", "")
                enriched.append(result)
            else:
                stale += 1

            if (i + 1) % 50 == 0:
                logger.info(
                    "enrich %s: %d/%d done (%d enriched, %d stale)",
                    city_slug, i + 1, total, len(enriched), stale,
                )

    # Save enriched data
    if enriched:
        out_key = f"scraper:ubereats:enriched:{city_slug}"
        await redis_client.set(out_key, json.dumps(enriched))
        logger.info("Redis SET %s → %d enriched stores", out_key, len(enriched))

    stats = {
        "city": city_slug,
        "total": total,
        "enriched": len(enriched),
        "stale": stale,
        "decode_errors": decode_err,
        "with_menu": sum(1 for s in enriched if s["menu_items"] > 0),
        "with_coords": sum(1 for s in enriched if s["latitude"] != 0),
    }
    return stats


# ═══════════════════════════════════════════════════════════════
# Standalone runner
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
    return re.sub(r"@redis:", "@localhost:", url)


async def _run_standalone():
    from redis.asyncio import Redis

    print("=" * 60)
    print("  UBEREATS ENRICHMENT — batch getStoreV1 fetch")
    print("=" * 60)

    redis = Redis.from_url(_get_redis_url(), decode_responses=True)
    try:
        await redis.ping()
        print("  ✓ Redis connected")
    except Exception as e:
        print(f"  ✗ Redis: {e}")
        return

    # Find all city keys
    cursor = 0
    city_keys = []
    while True:
        cursor, keys = await redis.scan(cursor, match="scraper:ubereats:known_stores:*", count=100)
        city_keys.extend(keys)
        if cursor == 0:
            break

    cities = [k.split(":")[-1] for k in city_keys if not k.endswith(":_unclassified")]
    cities.sort()

    # For standalone test, only do warszawa (or specify via env)
    target = os.environ.get("ENRICH_CITY", "warszawa")
    if target != "all":
        cities = [c for c in cities if c == target]

    if not cities:
        print(f"  No data for city '{target}'. Available: {', '.join(cities[:10])}")
        await redis.aclose()
        return

    print(f"  Cities to enrich: {cities}")
    print(f"  Concurrency: {_CONCURRENCY}, delay: {_DELAY}s")
    print()

    start = time.monotonic()
    all_stats = []

    for city in cities:
        print(f"  Enriching {city}...")
        stats = await enrich_city(redis, city)
        all_stats.append(stats)
        print(f"    Total: {stats['total']}, enriched: {stats['enriched']}, "
              f"stale: {stats['stale']}, menu: {stats['with_menu']}, "
              f"coords: {stats['with_coords']}")

    elapsed = time.monotonic() - start

    # Save metadata
    meta = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(elapsed, 1),
        "cities": all_stats,
    }
    await redis.set("scraper:ubereats:enrich_meta", json.dumps(meta))

    # Summary
    total_enriched = sum(s["enriched"] for s in all_stats)
    total_stale = sum(s["stale"] for s in all_stats)
    total_menu = sum(s["with_menu"] for s in all_stats)

    print(f"\n{'='*60}")
    print(f"  COMPLETE in {elapsed:.0f}s")
    print(f"  Enriched: {total_enriched}")
    print(f"  Stale/removed: {total_stale}")
    print(f"  With menu: {total_menu}")
    print(f"{'='*60}")

    # Show sample
    waw_raw = await redis.get("scraper:ubereats:enriched:warszawa")
    if waw_raw:
        waw = json.loads(waw_raw)
        print(f"\n  Sample enriched Warsaw stores (first 5):")
        for s in waw[:5]:
            print(f"    {s['title']:<35} {s['latitude']:.4f}, {s['longitude']:.4f}  ({s['menu_items']} items)")

    await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(_run_standalone())
