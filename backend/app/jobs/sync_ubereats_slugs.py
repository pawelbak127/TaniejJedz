"""
UberEats sitemap discovery — background job v2.

Changes from v1:
  - City classification from slug keywords (districts, landmarks, city names)
  - Per-city Redis keys: scraper:ubereats:known_stores:{city_slug}
  - Unclassified stores in separate key (for future enrichment via getStoreV1)

Redis keys:
    scraper:ubereats:known_stores:{city_slug}  →  JSON list of {slug, uuid, locale}
    scraper:ubereats:known_stores:_unclassified →  stores without city info
    scraper:ubereats:sitemap_meta               →  JSON metadata

Usage:
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
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)

UBEREATS_BASE = "https://www.ubereats.com"
ROBOTS_URL = f"{UBEREATS_BASE}/robots.txt"
_FETCH_CONCURRENCY = 5

# ═══════════════════════════════════════════════════════════════
# Regexes
# ═══════════════════════════════════════════════════════════════

_PL_STORE_RE = re.compile(
    r"https://www\.ubereats\.com/(pl(?:-en)?)/store/"
    r"([^/\s<]+)"
    r"/([A-Za-z0-9_\-]+)"
)

_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")
_ROBOTS_SITEMAP_RE = re.compile(r"^Sitemap:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
_SITEMAP_CHILD_RE = re.compile(r"<loc>\s*(https://[^<]+?)\s*</loc>")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TaniejJedz/1.0; food-price-comparison)",
    "Accept": "*/*",
}

# ═══════════════════════════════════════════════════════════════
# City classification from slug keywords
# ═══════════════════════════════════════════════════════════════

# Each city has: city_slug → list of keywords found in UberEats slugs
# Includes city names, districts, landmarks, shopping malls
_CITY_KEYWORDS: dict[str, list[str]] = {
    "warszawa": [
        "warszawa", "warsaw",
        # Districts
        "mokotow", "mokotów", "wola", "praga", "ursynow", "ursynów",
        "bemowo", "wilanow", "wilanów", "bielany", "ochota",
        "zoliborz", "żoliborz", "targowek", "targówek", "wlochy", "włochy",
        "ursus", "rembertow", "rembertów", "wesola", "wesoła",
        "bialoleka", "białołęka", "wawer", "srodmiescie", "śródmieście",
        "kabaty", "natolin", "stegny", "sadyba",
        # Landmarks / malls
        "mlociny", "młociny", "arkadia", "zlote-tarasy", "złote-tarasy",
        "galeria-mokotow", "blue-city", "westfield", "reduta",
        "marszalkowska", "marszałkowska", "nowy-swiat", "nowy-świat",
        "aleje-jerozolimskie", "plac-bankowy", "plac-zbawiciela",
        # Suburbs commonly in Warsaw UberEats
        "janki", "lomianki", "łomianki", "piaseczno", "pruszkow", "pruszków",
        "legionowo", "marki", "zabki", "ząbki", "piastow", "piastów",
        "grodzisk-mazowiecki",
    ],
    "krakow": [
        "krakow", "kraków", "cracow",
        "kazimierz", "nowa-huta", "podgorze", "podgórze", "krowodrza",
        "bronowice", "debniki", "dębniki", "zwierzyniec", "pradnik",
        "galeria-krakowska", "bonarka", "ruczaj",
        "wieliczka", "niepolomice", "niepołomice", "skawina",
    ],
    "wroclaw": [
        "wroclaw", "wrocław",
        "krzyki", "fabryczna", "psie-pole", "srodmiescie",
        "galeria-dominikanska", "dominikanski", "dominikański",
        "wroclavia", "magnolia",
        "olesnica", "oleśnica", "olawa", "oława",
    ],
    "gdansk": [
        "gdansk", "gdańsk", "gdynia", "sopot",
        "wrzeszcz", "oliwa", "przymorze", "zaspa", "morena",
        "letnica", "galeria-baltycka", "bałtycka",
        "rumia", "reda", "pruszcz-gdanski",
    ],
    "poznan": [
        "poznan", "poznań",
        "jezyce", "jeżyce", "wilda", "grunwald", "rataje",
        "stary-browar", "posnania", "avenida",
        "swarzedz", "lubon", "luboń",
    ],
    "lodz": [
        "lodz", "łódź", "łodz",
        "baluty", "bałuty", "polesie", "srodmiescie", "widzew", "gorna", "górna",
        "manufaktura", "galeria-lodzka", "łódzka",
        "pabianice", "zgierz", "aleksandrow",
    ],
    "katowice": [
        "katowice", "katowic",
        "silesia-city", "galeria-katowicka", "3-stawy",
        # Silesian conurbation
        "sosnowiec", "gliwice", "zabrze", "bytom", "tychy",
        "chorzow", "chorzów", "siemianowice", "dabrowa-gornicza",
        "dąbrowa-górnicza", "ruda-slaska", "ruda-śląska",
        "myslowice", "mysłowice", "jaworzno", "mikolow", "mikołów",
    ],
    "lublin": [
        "lublin",
        "swidnik", "świdnik", "leczna", "łęczna",
        "galeria-olimp", "tarasy-zamkowe",
    ],
    "szczecin": [
        "szczecin",
        "galeria-kaskada", "galaxy",
        "prawobrzeze", "prawobrzeże", "police", "stargard",
    ],
    "bialystok": [
        "bialystok", "białystok",
        "galeria-jurowiecka", "alfa-centrum",
    ],
    "rzeszow": [
        "rzeszow", "rzeszów",
        "galeria-rzeszow", "millenium-hall",
    ],
    "bydgoszcz": [
        "bydgoszcz",
        "galeria-focus", "zielone-arkady",
    ],
    "torun": [
        "torun", "toruń",
    ],
    "kielce": [
        "kielce",
        "galeria-echo", "galeria-korona",
    ],
    "olsztyn": [
        "olsztyn",
        "galeria-warminska", "warmińska",
    ],
    "opole": ["opole"],
    "zielona-gora": ["zielona-gora", "zielona-góra"],
    "gorzow-wielkopolski": ["gorzow", "gorzów"],
    "koszalin": ["koszalin"],
    "radom": ["radom"],
    "plock": ["plock", "płock"],
    "elblag": ["elblag", "elbląg"],
    "tarnow": ["tarnow", "tarnów"],
    "kalisz": ["kalisz"],
    "legnica": ["legnica"],
    "slupsk": ["slupsk", "słupsk"],
    "rybnik": ["rybnik"],
    "czestochowa": ["czestochowa", "częstochowa"],
    "siedlce": ["siedlce"],
    "inowroclaw": ["inowroclaw", "inowrocław"],
    "ostroleka": ["ostroleka", "ostrołęka"],
    "pila": ["pila", "piła"],
    "suwalki": ["suwalki", "suwałki"],
    "konin": ["konin"],
    "kolobrzeg": ["kolobrzeg", "kołobrzeg"],
    "nowy-sacz": ["nowy-sacz", "nowy-sącz"],
    "grudziadz": ["grudziadz", "grudziądz"],
    "jelenia-gora": ["jelenia-gora", "jelenia-góra"],
    "leszno": ["leszno"],
    "lomza": ["lomza", "łomża"],
    "walbrzych": ["walbrzych", "wałbrzych"],
    "oswiecim": ["oswiecim", "oświęcim"],
    "malbork": ["malbork"],
    "sanok": ["sanok"],
    "tczew": ["tczew"],
    "kutno": ["kutno"],
    "swidnica": ["swidnica", "świdnica"],
    "starachowice": ["starachowice"],
    "belchatow": ["belchatow", "bełchatów"],
    "boleslawiec": ["boleslawiec", "bolesławiec"],
}


def _classify_city(slug: str) -> str | None:
    """Classify a store slug to a city_slug based on keyword matching.

    Returns city_slug or None if unclassifiable.
    """
    slug_lower = slug.lower()
    # Exact match on city name at end of slug: "kfc-warszawa" → warszawa
    # or as a component: "pizza-hut-mokotow" → warszawa
    for city_slug, keywords in _CITY_KEYWORDS.items():
        for kw in keywords:
            if kw in slug_lower:
                return city_slug
    return None


# ═══════════════════════════════════════════════════════════════
# Non-food filtering
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
# Fetch
# ═══════════════════════════════════════════════════════════════

async def _fetch_gz(client: httpx.AsyncClient, url: str) -> bytes | None:
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


def _extract_stores_from_xml(xml_text: str) -> list[dict]:
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


# ═══════════════════════════════════════════════════════════════
# Core sync
# ═══════════════════════════════════════════════════════════════

async def sync_ubereats_slugs(redis_client) -> dict[str, int]:
    """Main sync: fetch sitemaps → classify by city → save per-city Redis keys.

    Returns dict of {city_slug: count}.
    """
    start = time.monotonic()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        headers=_HEADERS,
    ) as client:
        # Step 1: robots.txt
        robots_data = await _fetch_gz(client, ROBOTS_URL)
        if not robots_data:
            logger.error("Failed to fetch robots.txt")
            return {}

        robots_text = robots_data.decode("utf-8", errors="replace")
        sitemap_urls = _ROBOTS_SITEMAP_RE.findall(robots_text)
        logger.info("Found %d Sitemap directives", len(sitemap_urls))

        # Step 2: Expand index
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
                all_store_sitemaps.extend(u for u in children if "store" in u)

        all_store_sitemaps = list(dict.fromkeys(all_store_sitemaps))
        logger.info("Total store sitemaps: %d", len(all_store_sitemaps))

        # Step 3: Fetch all sitemaps
        semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)
        all_stores: list[dict] = []

        async def scan_one(url: str) -> list[dict]:
            async with semaphore:
                data = await _fetch_gz(client, url)
                if not data:
                    return []
                return _extract_stores_from_xml(data.decode("utf-8", errors="replace"))

        tasks = [scan_one(u) for u in all_store_sitemaps]
        results = await asyncio.gather(*tasks)
        for stores in results:
            all_stores.extend(stores)

    # Step 4: Deduplicate + filter + classify
    seen: set[str] = set()
    city_stores: dict[str, list[dict]] = defaultdict(list)
    skipped_non_food = 0
    classified = 0
    unclassified_count = 0

    for s in all_stores:
        if s["uuid"] in seen:
            continue
        seen.add(s["uuid"])

        if _is_non_food_slug(s["slug"]):
            skipped_non_food += 1
            continue

        city = _classify_city(s["slug"])
        if city:
            city_stores[city].append(s)
            classified += 1
        else:
            city_stores["_unclassified"].append(s)
            unclassified_count += 1

    # Step 5: Save to Redis — per-city keys
    per_city: dict[str, int] = {}

    # Clean up old keys first
    old_keys = []
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match="scraper:ubereats:known_stores:*", count=100)
        old_keys.extend(keys)
        if cursor == 0:
            break
    if old_keys:
        await redis_client.delete(*old_keys)

    for city_slug, stores in sorted(city_stores.items()):
        redis_key = f"scraper:ubereats:known_stores:{city_slug}"
        await redis_client.set(redis_key, json.dumps(stores))
        per_city[city_slug] = len(stores)
        logger.info("Redis SET %s → %d stores", redis_key, len(stores))

    # Also keep a flat "all stores" key for backward compat
    all_unique = []
    for stores in city_stores.values():
        all_unique.extend(stores)
    await redis_client.set("scraper:ubereats:known_stores", json.dumps(all_unique))

    # Metadata
    total = classified + unclassified_count
    meta = {
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "total_stores": total,
        "classified": classified,
        "unclassified": unclassified_count,
        "skipped_non_food": skipped_non_food,
        "sitemaps_scanned": len(all_store_sitemaps),
        "cities": len([c for c in per_city if c != "_unclassified"]),
        "duration_seconds": round(time.monotonic() - start, 2),
        "per_city": per_city,
    }
    await redis_client.set("scraper:ubereats:sitemap_meta", json.dumps(meta))

    elapsed = time.monotonic() - start
    logger.info(
        "UberEats sync complete: %d stores (%d classified → %d cities, %d unclassified) in %.1fs",
        total, classified, len([c for c in per_city if c != "_unclassified"]),
        unclassified_count, elapsed,
    )

    return per_city


# ═══════════════════════════════════════════════════════════════
# Redis connection (standalone)
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


async def _run_standalone():
    print("=" * 60)
    print("  UBEREATS SITEMAP SYNC v2 — with city classification")
    print("=" * 60)
    print()

    try:
        redis = await _connect_redis()
        print("  ✓ Connected to Redis")
    except Exception as e:
        print(f"  ✗ Redis connection failed: {e}")
        print('  Fix: $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"')
        return

    print()

    try:
        result = await sync_ubereats_slugs(redis)

        print(f"\n{'='*60}")
        print("  SYNC COMPLETE")
        print(f"{'='*60}")

        meta_raw = await redis.get("scraper:ubereats:sitemap_meta")
        if meta_raw:
            meta = json.loads(meta_raw)
            total = meta["total_stores"]
            classified = meta["classified"]
            unclassified = meta["unclassified"]
            pct = 100 * classified / max(1, total)

            print(f"  Total stores:      {total}")
            print(f"  Classified:        {classified} ({pct:.0f}%)")
            print(f"  Unclassified:      {unclassified}")
            print(f"  Cities:            {meta['cities']}")
            print(f"  Duration:          {meta['duration_seconds']}s")
            print(f"  Non-food skipped:  {meta['skipped_non_food']}")

        # Top cities
        classified_cities = {k: v for k, v in sorted(result.items(), key=lambda x: -x[1]) if k != "_unclassified"}
        print(f"\n  Top cities:")
        for city, count in list(classified_cities.items())[:15]:
            print(f"    {city:<25} {count:>5} stores")
        if len(classified_cities) > 15:
            print(f"    ... and {len(classified_cities) - 15} more cities")

        # Sample Warsaw
        waw_raw = await redis.get("scraper:ubereats:known_stores:warszawa")
        if waw_raw:
            waw = json.loads(waw_raw)
            kfc = [s for s in waw if "kfc" in s["slug"].lower()]
            print(f"\n  Warszawa: {len(waw)} stores, {len(kfc)} KFC")
            for s in kfc[:5]:
                print(f"    • {s['slug']} → {s['uuid']}")

    finally:
        await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(_run_standalone())
