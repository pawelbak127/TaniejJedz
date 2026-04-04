"""
Glovo sitemap discovery — background job.

Fetches Glovo's public sitemaps (robots.txt allows), extracts all Polish
store slugs, maps transliterated city names to our city_slug format,
filters out non-food stores, and saves clean slug lists to Redis.

Redis keys:
    scraper:glovo:known_slugs:{city_slug}  →  JSON list of slugs
    scraper:glovo:sitemap_meta               →  JSON {last_sync, total_slugs, per_city}

Usage (PowerShell, from backend/):
    python -m app.jobs.sync_glovo_slugs

    # Or with explicit Redis URL:
    $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
    python -m app.jobs.sync_glovo_slugs
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Sitemap URLs — from recon (April 2026)
# ═══════════════════════════════════════════════════════════════

SITEMAP_INDEX_URL = "https://glovoapp.com/sitemap-index.xml"

_POLISH_SITEMAP_FILES = [
    "https://glovoapp.com/sitemap-p.xml",
    "https://glovoapp.com/sitemap-o.xml",
    "https://glovoapp.com/sitemap-a.xml",
]

# ═══════════════════════════════════════════════════════════════
# Transliterated city name → our city_slug mapping
# ═══════════════════════════════════════════════════════════════

_TRANSLITERATED_CITY_MAP: dict[str, str] = {
    # ── Original 24 cities (sitemap-p.xml transliterations) ──────────
    "varshava": "warszawa",
    "vrotslav": "wroclaw",
    "krakiv": "krakow",
    "katovitse": "katowice",
    "shchetsin": "szczecin",
    "lyublin": "lublin",
    "bidgoshch": "bydgoszcz",
    "bilostok": "bialystok",
    "zheshuv": "rzeszow",
    "ryashiv": "rzeszow",
    "olshtin": "olsztyn",
    "sosnovets": "sosnowiec",
    "glivitse": "gliwice",
    "chenstohova": "czestochowa",
    "keltse": "kielce",
    "zelyona-gura": "zielona-gora",
    "zelena-gura": "zielona-gora",
    "belsko-byala": "bielsko-biala",
    "vlotslavek": "wloclawek",

    # ── sitemap-o.xml alternative transliterations (discovered live) ─
    "krakov": "krakow",             # 1212 — vs "krakiv" in sitemap-p
    "bydgoshch": "bydgoszcz",       # 233  — vs "bidgoshch"
    "belostok": "bialystok",        # 200  — vs "bilostok"
    "olshtyn": "olsztyn",           # 189  — vs "olshtin"

    # ── NEW cities: 50+ stores (from live unknown_cities log) ────────
    "koshalin": "koszalin",         # 176
    "koszalin": "koszalin",
    "plotsk": "plock",              # 172
    "plock": "plock",
    "elblong": "elblag",            # 168
    "elblag": "elblag",
    "kolobzheg": "kolobrzeg",       # 114
    "kolobrzeg": "kolobrzeg",
    "kalish": "kalisz",             # 112
    "kalisz": "kalisz",
    "chehovitse-dzedzitse": "czechowice-dziedzice",  # 110
    "czechowice-dziedzice": "czechowice-dziedzice",
    "legnitsa": "legnica",          # 100
    "legnica": "legnica",
    "slupsk": "slupsk",             # 97
    "raciborz": "raciborz",         # 96
    "pila": "pila",                 # 91
    "gozhuv-velikopolskiy": "gorzow-wielkopolski",   # 90
    "gorzow-wielkopolski": "gorzow-wielkopolski",
    "gozhuv-velkopolski": "gorzow-wielkopolski",
    "ribnik": "rybnik",             # 88
    "rybnik": "rybnik",
    "belhatuv": "belchatow",        # 88
    "belchatow": "belchatow",
    "grodzisk-mazovetskiy": "grodzisk-mazowiecki",   # 87
    "grodzisk-mazowiecki": "grodzisk-mazowiecki",
    "tarnuv": "tarnow",             # 87
    "tarnow": "tarnow",
    "valbzhih": "walbrzych",        # 86
    "walbrzych": "walbrzych",
    "bitom": "bytom",               # 83
    "bytom": "bytom",
    "suvalki": "suwalki",           # 83
    "suwalki": "suwalki",
    "inovrotslav": "inowroclaw",    # 81
    "inowroclaw": "inowroclaw",
    "tomashuv-mazovetskiy": "tomaszow-mazowiecki",   # 81
    "tomaszow-mazowiecki": "tomaszow-mazowiecki",
    "nowy-targ": "nowy-targ",       # 81
    "osventsim": "oswiecim",        # 80
    "oswiecim": "oswiecim",
    "tihi": "tychy",                # 79
    "tyhy": "tychy",
    "tychy": "tychy",
    "lomzha": "lomza",              # 78
    "lomza": "lomza",
    "lyubin": "lubin",              # 78
    "lubin": "lubin",
    "tchev": "tczew",               # 77
    "tczew": "tczew",
    "boleslavets": "boleslawiec",   # 74
    "boleslawiec": "boleslawiec",
    "chrzanow": "chrzanow",         # 73
    "jastrzebie-zdroj": "jastrzebie-zdroj",  # 69
    "sanok": "sanok",               # 69
    "sedltse": "siedlce",           # 69
    "siedlce": "siedlce",
    "starahovitse": "starachowice", # 68
    "starachowice": "starachowice",
    "starogard-gdanskiy": "starogard-gdanski",  # 67
    "starogard-gdanski": "starogard-gdanski",
    "konin": "konin",               # 66
    "swinoujscie": "swinoujscie",   # 66
    "leshno": "leszno",             # 66
    "leszno": "leszno",
    "cieszyn": "cieszyn",           # 66
    "kutno": "kutno",               # 65
    "pyotrkuv-tribunalskiy": "piotrkow-trybunalski",  # 63
    "pyotrkuv-trybunalskiy": "piotrkow-trybunalski",
    "piotrkow-trybunalski": "piotrkow-trybunalski",
    "kostsezhina": "koscierzyna",   # 62
    "koscierzyna": "koscierzyna",
    "ostrovets-sventokshiskiy": "ostrowiec-swietokrzyski",  # 62
    "ostrowiec-swietokrzyski": "ostrowiec-swietokrzyski",
    "malbork": "malbork",           # 61
    "wodzislaw-slaski": "wodzislaw-slaski",  # 59
    "kedzierzyn-kozle": "kedzierzyn-kozle",  # 58
    "olkusz": "olkusz",             # 58
    "lyubon": "lubon",              # 58
    "lubon": "lubon",
    "noviy-sonch": "nowy-sacz",     # 54
    "novy-sonch": "nowy-sacz",
    "nowy-sacz": "nowy-sacz",
    "olava": "olawa",               # 54
    "olawa": "olawa",
    "skernevitse": "skierniewice",  # 52
    "skierniewice": "skierniewice",
    "stargard": "stargard",         # 51
    "tsehanuv": "ciechanow",        # 51
    "ciechanow": "ciechanow",
    "tarnobzheg": "tarnobrzeg",     # 51
    "tarnobrzeg": "tarnobrzeg",
    "olesnitsa": "olesnica",        # 50
    "olesnica": "olesnica",

    # ── NEW cities: 30-49 stores ─────────────────────────────────────
    "pyastuv": "piastow",           # 49
    "piastow": "piastow",
    "chojnice": "chojnice",         # 48
    "grudzondz": "grudziadz",       # 48
    "grudzyondz": "grudziadz",
    "grudziadz": "grudziadz",
    "ostrolenka": "ostroleka",      # 48
    "ostroleka": "ostroleka",
    "elenya-gura": "jelenia-gora",  # 48
    "yelenya-gura": "jelenia-gora", # 47
    "jelenia-gora": "jelenia-gora",
    "swidnica": "swidnica",         # 47
    "zdunska-wola": "zdunska-wola", # 45
    "gnyezno": "gniezno",           # 44
    "gnezno": "gniezno",
    "gniezno": "gniezno",
    "nowa-sol": "nowa-sol",         # 44
    "pravoberizhzhya": "prawobrzeze",  # 44 (Szczecin district)
    "pravoberezhe": "prawobrzeze",
    "prawobrzeze": "prawobrzeze",
    "skarzhisko-kamenna": "skarzysko-kamienna",  # 44
    "skarzysko-kamienna": "skarzysko-kamienna",
    "ostruda": "ostroda",           # 44
    "ostroda": "ostroda",
    "melets": "mielec",             # 43
    "mielec": "mielec",
    "elk": "elk",                   # 43
    "krotoshin": "krotoszyn",       # 43
    "krotoszyn": "krotoszyn",
    "ostruv-velikopolskiy": "ostrow-wielkopolski",   # 42
    "ostruv-velkopolskiy": "ostrow-wielkopolski",
    "ostrow-wielkopolski": "ostrow-wielkopolski",
    "klodzko": "klodzko",           # 41
    "sieradz": "sieradz",           # 41
    "slubice": "slubice",           # 40
    "jarocin": "jarocin",           # 39
    "mlava": "mlawa",               # 38
    "mlawa": "mlawa",
    "lomianki": "lomianki",         # 38
    "srem": "srem",                 # 38
    "chelm": "chelm",               # 38
    "jaroslaw": "jaroslaw",         # 37
    "dembitsya": "debica",          # 37
    "dembitsa": "debica",
    "debica": "debica",
    "zhory": "zory",                # 36
    "zhori": "zory",
    "zory": "zory",
    "polkovitse": "polkowice",      # 36
    "polkowice": "polkowice",
    "shchetsinek": "szczecinek",    # 36
    "szczecinek": "szczecinek",
    "zawiercie": "zawiercie",       # 33
    "lubliniec": "lubliniec",       # 33
    "minsk-mazovetskiy": "minsk-mazowiecki",  # 33
    "minsk-mazovetski": "minsk-mazowiecki",
    "minsk-mazowiecki": "minsk-mazowiecki",
    "kostrzyn-nad-odra": "kostrzyn-nad-odra",  # 31
    "lyebork": "lebork",            # 31
    "lembork": "lebork",
    "lebork": "lebork",
    "nisa": "nysa",                 # 31
    "nysa": "nysa",
    "gloguv": "glogow",             # 30
    "glogov": "glogow",
    "glogow": "glogow",
    "lowicz": "lowicz",             # 30
    "okolice-lodzi": "lodz",        # 30 (Łódź suburbs → map to Łódź)
    "yavozhno": "jaworzno",         # 30
    "jaworzno": "jaworzno",

    # ── NEW cities: 10-29 stores ─────────────────────────────────────
    "wagrowiec": "wagrowiec",       # 29
    "kolo": "kolo",                 # 29
    "kelchuv": "kielczow",          # 28
    "kielczow": "kielczow",
    "mikoluv": "mikolow",           # 28
    "mikolow": "mikolow",
    "peremishl": "przemysl",        # 27
    "pshemysl": "przemysl",
    "przemysl": "przemysl",
    "korosno": "krosno",            # 27
    "krosno": "krosno",
    "plonsk": "plonsk",             # 26
    "sohachev": "sochaczew",        # 26
    "sochaczew": "sochaczew",
    "swiecie": "swiecie",           # 26
    "walcz": "walcz",               # 24
    "dzierzoniow": "dzierzoniow",   # 24
    "turek": "turek",               # 24
    "zamosts": "zamosc",            # 24
    "zamostya": "zamosc",
    "zamosc": "zamosc",
    "pulavi": "pulawy",             # 24
    "pulawy": "pulawy",
    "bila-pidlyaska": "biala-podlaska",  # 24
    "byala-podlyaska": "biala-podlaska",
    "biala-podlaska": "biala-podlaska",
    "ilawa": "ilawa",               # 23
    "andrychow": "andrychow",       # 22
    "mragowo": "mragowo",           # 21
    "kvidzin": "kwidzyn",           # 21
    "kvidzyn": "kwidzyn",
    "kwidzyn": "kwidzyn",
    "zhivets": "zywiec",            # 21
    "zywiec": "zywiec",
    "naklo-nad-notecia": "naklo-nad-notecia",  # 20
    "krapkowice": "krapkowice",     # 20
    "tarnovski-guri": "tarnowskie-gory",  # 20
    "tarnovske-gury": "tarnowskie-gory",
    "tarnowskie-gory": "tarnowskie-gory",
    "vzhesnya": "wrzesnia",         # 20
    "wrzesnia": "wrzesnia",
    "zhary": "zary",                # 20
    "zhari": "zary",
    "zary": "zary",
    "noviy-dvir-mazovetskiy": "nowy-dwor-mazowiecki",  # 19
    "novy-dvur-mazovetski": "nowy-dwor-mazowiecki",
    "nowy-dwor-mazowiecki": "nowy-dwor-mazowiecki",
    "swiebodzin": "swiebodzin",     # 17
    "lukiv": "lukow",               # 17
    "lukuv": "lukow",
    "lukow": "lukow",
    "vyshuv": "wyszkow",            # 16
    "vishkuv": "wyszkow",
    "vyszkuv": "wyszkow",
    "wyszkow": "wyszkow",
    "krasnystaw": "krasnystaw",     # 16
    "sroda-wielkopolska": "sroda-wielkopolska",  # 16
    "brodnitsya": "brodnica",       # 15
    "brodnitsa": "brodnica",
    "brodnica": "brodnica",
    "pultusk": "pultusk",           # 15
    "avgustiv": "augustow",         # 14
    "avgustov": "augustow",
    "augustow": "augustow",
    "zambrow": "zambrow",           # 14
    "gdinya": "gdynia",             # 14
    "gdynya": "gdynia",
    "gdynia": "gdynia",
    "sulechow": "sulechow",         # 14
    "swidnik": "swidnik",           # 14
    "krasnik": "krasnik",           # 28
    "zgozhelets": "zgorzelec",      # 13
    "zgorzelec": "zgorzelec",
    "rumiya": "rumia",              # 11
    "rumya": "rumia",
    "rumia": "rumia",
    "biale-blota": "biale-blota",   # 10
    "krzeszowice": "krzeszowice",   # 10
    "lantsut": "lancut",            # 10
    "lancut": "lancut",
    "politse": "police",            # 10
    "police": "police",
    "putsk": "puck",                # 10
    "puck": "puck",
    "shchitno": "szczytno",         # 10
    "szczytno": "szczytno",
    "krakow-okolice": "krakow",     # 18 (Kraków suburbs)

    # ── Direct Polish matches (original 24 + all new cities) ─────────
    "warszawa": "warszawa",
    "krakow": "krakow",
    "wroclaw": "wroclaw",
    "gdansk": "gdansk",
    "poznan": "poznan",
    "lodz": "lodz",
    "katowice": "katowice",
    "szczecin": "szczecin",
    "lublin": "lublin",
    "bydgoszcz": "bydgoszcz",
    "bialystok": "bialystok",
    "rzeszow": "rzeszow",
    "olsztyn": "olsztyn",
    "sosnowiec": "sosnowiec",
    "gliwice": "gliwice",
    "czestochowa": "czestochowa",
    "kielce": "kielce",
    "torun": "torun",
    "zielona-gora": "zielona-gora",
    "bielsko-biala": "bielsko-biala",
    "opole": "opole",
    "wloclawek": "wloclawek",
    "zakopane": "zakopane",
    "radom": "radom",
}

_CITY_SLUG_TO_CODE: dict[str, str] = {
    # Major cities (original 24)
    "warszawa": "WAW", "krakow": "KRA", "wroclaw": "WRO",
    "poznan": "POZ", "gdansk": "GDN", "lodz": "LDZ",
    "katowice": "KTW", "lublin": "LUB", "bialystok": "BIA",
    "rzeszow": "RZE", "szczecin": "SZZ", "kielce": "KIE",
    "torun": "TOR", "bydgoszcz": "BDG", "olsztyn": "OLS",
    "sosnowiec": "SOS", "gliwice": "GLI", "czestochowa": "CZE",
    "zielona-gora": "ZGO", "bielsko-biala": "BBI", "opole": "OPO",
    "wloclawek": "WLO", "zakopane": "ZAK", "radom": "RAD",
    # New cities (from sitemap discovery)
    "koszalin": "KOS", "plock": "PLO", "elblag": "ELB",
    "kolobrzeg": "KOL", "kalisz": "KAL", "legnica": "LEG",
    "slupsk": "SLU", "raciborz": "RAC", "pila": "PIL",
    "gorzow-wielkopolski": "GOR", "rybnik": "RYB", "belchatow": "BEL",
    "grodzisk-mazowiecki": "GRM", "tarnow": "TAR", "walbrzych": "WAL",
    "bytom": "BYT", "suwalki": "SUW", "inowroclaw": "INO",
    "tomaszow-mazowiecki": "TOM", "nowy-targ": "NTA", "oswiecim": "OSW",
    "tychy": "TYC", "lomza": "LOM", "lubin": "LUB2",
    "tczew": "TCZ", "boleslawiec": "BOL", "chrzanow": "CHR",
    "jastrzebie-zdroj": "JAS", "sanok": "SAN", "siedlce": "SIE",
    "starachowice": "STA", "starogard-gdanski": "STG", "konin": "KON",
    "swinoujscie": "SWI", "leszno": "LES", "cieszyn": "CIE",
    "kutno": "KUT", "piotrkow-trybunalski": "PIO", "koscierzyna": "KSC",
    "ostrowiec-swietokrzyski": "OSS", "malbork": "MAL",
    "wodzislaw-slaski": "WOD", "kedzierzyn-kozle": "KED", "olkusz": "OLK",
    "lubon": "LBN", "nowy-sacz": "NSA", "olawa": "OLA",
    "skierniewice": "SKI", "stargard": "SRG", "ciechanow": "CIH",
    "tarnobrzeg": "TBR", "olesnica": "OLE", "piastow": "PIA",
    "chojnice": "CHO", "grudziadz": "GRU", "ostroleka": "OST",
    "jelenia-gora": "JEL", "swidnica": "SWD", "zdunska-wola": "ZDU",
    "gniezno": "GNI", "nowa-sol": "NOS", "prawobrzeze": "PRB",
    "skarzysko-kamienna": "SKA", "ostroda": "OSD", "mielec": "MIE",
    "elk": "ELK", "krotoszyn": "KRO", "ostrow-wielkopolski": "OSR",
    "klodzko": "KLO", "sieradz": "SIR", "slubice": "SLB",
    "jarocin": "JAR", "mlawa": "MLA", "lomianki": "LMK",
    "srem": "SRM", "chelm": "CHE", "jaroslaw": "JRL",
    "debica": "DEB", "zory": "ZOR", "polkowice": "PLK",
    "szczecinek": "SCN", "zawiercie": "ZAW", "lubliniec": "LBL",
    "minsk-mazowiecki": "MIM", "kostrzyn-nad-odra": "KNO",
    "lebork": "LEB", "nysa": "NYS", "glogow": "GLG",
    "lowicz": "LOW", "jaworzno": "JAW", "czechowice-dziedzice": "CZD",
    "gdynia": "GDY", "przemysl": "PRZ", "zamosc": "ZAM",
    "pulawy": "PUL", "biala-podlaska": "BPO", "brodnica": "BRO",
    "augustow": "AUG", "kwidzyn": "KWI", "zywiec": "ZYW",
    "tarnowskie-gory": "TGO", "wrzesnia": "WRZ", "zary": "ZAR",
    "nowy-dwor-mazowiecki": "NDM", "lukow": "LUK", "wyszkow": "WYS",
    "zgorzelec": "ZGR", "rumia": "RUM", "krosno": "KRS",
    "wagrowiec": "WAG", "kolo": "KOO", "kielczow": "KLC",
    "mikolow": "MIK", "krasnik": "KRA2",
    "krasnystaw": "KRS2", "sroda-wielkopolska": "SRW",
    "pultusk": "PUU", "zambrow": "ZBR", "sulechow": "SUL",
    "swidnik": "SWN", "swiecie": "SWC", "walcz": "WAC",
    "dzierzoniow": "DZI", "turek": "TUR", "ilawa": "ILA",
    "andrychow": "AND", "mragowo": "MRA", "plonsk": "PLN",
    "sochaczew": "SOC", "lancut": "LAN", "police": "POL",
    "puck": "PUC", "szczytno": "SZC",
    "naklo-nad-notecia": "NAK", "krapkowice": "KRP",
    "biale-blota": "BBL", "krzeszowice": "KRZ",
    "swiebodzin": "SWB",
}

# ═══════════════════════════════════════════════════════════════
# Non-food slug filtering
# ═══════════════════════════════════════════════════════════════

_NON_FOOD_KEYWORDS = [
    "apteczka", "apteka", "pharmacy",
    "biedronka", "rossmann", "hebe", "stokrotka",
    "carrefour", "auchan", "lidl", "kaufland",
    "zabka", "żabka", "lewiatan", "dino-market",
    "intermarche", "netto", "polomarket", "polo-market",
    "delikatesy", "spolem", "freshmarket", "fresh-market",
    "a-kwiaty", "kwiaciarnia", "florist",
    "mediamarkt", "media-markt", "empik", "decathlon",
    "pepco", "action", "tedi",
    "zooplus", "maxi-zoo", "kakadu",
    "alkohole", "duzy-ben", "specjaly",
]


def _is_non_food_slug(slug: str) -> bool:
    slug_lower = slug.lower()
    return any(kw in slug_lower for kw in _NON_FOOD_KEYWORDS)


# ═══════════════════════════════════════════════════════════════
# URL parsing
# ═══════════════════════════════════════════════════════════════

_SITEMAP_URL_RE = re.compile(
    r"https://glovoapp\.com/pl/(?:ru|uk|pl)/([^/]+)/([^/]+)/?"
)

_LOC_RE = re.compile(r"<loc>\s*(https://glovoapp\.com/pl/[^<]+?)\s*</loc>")

_SITEMAP_HREF_RE = re.compile(r"<loc>\s*(https://glovoapp\.com/sitemap[^<]+?)\s*</loc>")


def _parse_sitemap_urls(xml_content: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for loc_match in _LOC_RE.finditer(xml_content):
        url = loc_match.group(1).strip().rstrip("/")
        url_match = _SITEMAP_URL_RE.match(url)
        if not url_match:
            continue

        city_raw = url_match.group(1)
        slug = url_match.group(2)

        if slug.startswith("categories"):
            continue

        key = (city_raw, slug)
        if key not in seen:
            seen.add(key)
            pairs.append((city_raw, slug))

    return pairs


def _resolve_city(transliterated: str) -> str | None:
    return _TRANSLITERATED_CITY_MAP.get(transliterated.lower())


# ═══════════════════════════════════════════════════════════════
# Core sync logic
# ═══════════════════════════════════════════════════════════════

async def fetch_sitemap(client: httpx.AsyncClient, url: str) -> str:
    logger.info("Fetching sitemap: %s", url)
    resp = await client.get(url, follow_redirects=True)
    resp.raise_for_status()
    logger.info("Fetched %s — %d bytes", url, len(resp.text))
    return resp.text


async def sync_glovo_slugs(redis_client) -> dict[str, int]:
    """Main sync function — fetch sitemaps, parse, filter, save to Redis."""
    start = time.monotonic()
    city_slugs: dict[str, set[str]] = defaultdict(set)
    unknown_cities: dict[str, int] = defaultdict(int)
    total_urls = 0
    skipped_non_food = 0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; TaniejJedz/1.0; food-price-comparison)",
            "Accept": "application/xml, text/xml, */*",
        },
    ) as client:
        tasks = [fetch_sitemap(client, url) for url in _POLISH_SITEMAP_FILES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for url, result in zip(_POLISH_SITEMAP_FILES, results):
        if isinstance(result, Exception):
            logger.error("Failed to fetch %s: %s", url, result)
            continue

        pairs = _parse_sitemap_urls(result)
        total_urls += len(pairs)
        logger.info("Parsed %s → %d store URLs", url, len(pairs))

        for transliterated_city, slug in pairs:
            city_slug = _resolve_city(transliterated_city)
            if city_slug is None:
                unknown_cities[transliterated_city] += 1
                continue

            if _is_non_food_slug(slug):
                skipped_non_food += 1
                continue

            city_slugs[city_slug].add(slug)

    # Save to Redis
    total_saved = 0
    per_city: dict[str, int] = {}

    for city_slug, slugs in sorted(city_slugs.items()):
        slug_list = sorted(slugs)
        redis_key = f"scraper:glovo:known_slugs:{city_slug}"
        await redis_client.set(redis_key, json.dumps(slug_list))
        count = len(slug_list)
        per_city[city_slug] = count
        total_saved += count
        logger.info("Redis SET %s → %d slugs", redis_key, count)

    meta = {
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "total_slugs": total_saved,
        "total_urls_parsed": total_urls,
        "skipped_non_food": skipped_non_food,
        "unknown_cities": dict(unknown_cities),
        "per_city": per_city,
        "duration_seconds": round(time.monotonic() - start, 2),
    }
    await redis_client.set("scraper:glovo:sitemap_meta", json.dumps(meta))

    elapsed = time.monotonic() - start
    logger.info(
        "Glovo sitemap sync complete: %d slugs across %d cities in %.1fs "
        "(parsed %d URLs, skipped %d non-food, %d unknown cities)",
        total_saved, len(per_city), elapsed,
        total_urls, skipped_non_food, len(unknown_cities),
    )

    if unknown_cities:
        top_unknown = sorted(unknown_cities.items(), key=lambda x: -x[1])[:10]
        logger.warning("Top unknown transliterated cities: %s", top_unknown)

    return per_city


# ═══════════════════════════════════════════════════════════════
# Dramatiq task wrapper (production)
# ═══════════════════════════════════════════════════════════════

try:
    import dramatiq
    from app.core.redis import get_redis_pool

    @dramatiq.actor(max_retries=3, min_backoff=60_000)
    def sync_glovo_slugs_task():
        loop = asyncio.new_event_loop()
        try:
            redis = loop.run_until_complete(get_redis_pool())
            result = loop.run_until_complete(sync_glovo_slugs(redis))
            logger.info("Dramatiq task result: %s", result)
        finally:
            loop.close()

except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════
# Redis connection (standalone)
# ═══════════════════════════════════════════════════════════════

def _get_redis_url() -> str:
    """Read Redis URL — env var → pydantic settings → fallback.

    Auto-replaces Docker hostname 'redis' with 'localhost' when running
    standalone on Windows (outside Docker Compose network).
    """
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

    # Fix Docker Compose hostname → localhost for standalone runs
    # .env.dev typically has redis://:pass@redis:6379/0 (Docker service name)
    # but when running Python directly on Windows, we need localhost
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
    print("  GLOVO SITEMAP SYNC — standalone runner")
    print("=" * 60)
    print()

    try:
        redis = await _connect_redis()
        print("  ✓ Connected to Redis")
    except Exception as e:
        print(f"  ✗ Redis connection failed: {e}")
        print()
        print("  Make sure Redis is running on localhost:6379")
        print("  Your .env.dev has 'redis' as hostname (Docker service name)")
        print("  but standalone scripts need localhost.")
        print()
        print("  Quick fix (PowerShell):")
        print('    $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"')
        return

    print()

    try:
        result = await sync_glovo_slugs(redis)
        print(f"\n{'='*60}")
        print("  SYNC COMPLETE")
        print(f"{'='*60}")
        total = sum(result.values())
        print(f"  Total slugs: {total}")
        print(f"  Cities: {len(result)}")
        print(f"\n  Per city:")
        for city, count in sorted(result.items(), key=lambda x: -x[1]):
            code = _CITY_SLUG_TO_CODE.get(city, "???")
            print(f"    {city:20s} ({code}) → {count:>5d} restaurants")

        meta_raw = await redis.get("scraper:glovo:sitemap_meta")
        if meta_raw:
            meta = json.loads(meta_raw)
            print(f"\n  Duration: {meta['duration_seconds']}s")
            print(f"  Non-food skipped: {meta['skipped_non_food']}")
            if meta.get("unknown_cities"):
                print(f"  Unknown cities: {meta['unknown_cities']}")

        waw_raw = await redis.get("scraper:glovo:known_slugs:warszawa")
        if waw_raw:
            waw_slugs = json.loads(waw_raw)
            print(f"\n  Sample Warszawa slugs (first 10 of {len(waw_slugs)}):")
            for s in waw_slugs[:10]:
                print(f"    • {s}")

    finally:
        await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(_run_standalone())
