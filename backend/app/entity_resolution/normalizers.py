"""
Name normalizers for entity resolution.

Two main functions:
  normalize_restaurant_name(name) → normalized string for matching
  normalize_dish_name(name) → (base_name, size_label)

Uses spaCy pl_core_news_md for Polish lemmatization when available.
Falls back to diacritics removal + stop words + lowercasing when not.

The fallback is sufficient for fuzzy matching (rapidfuzz token_sort_ratio
handles most variation). spaCy adds ~5% accuracy on edge cases like
"Pizzerii" → "pizzeria" lemmatization.

Install spaCy model (recommended for production):
    pip install spacy
    python -m spacy download pl_core_news_md
"""

from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from typing import Callable

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# STOP WORDS — removed from restaurant names before matching
# ══════════════════════════════════════════════════════════════

RESTAURANT_STOP_WORDS: frozenset[str] = frozenset({
    # Business types
    "restauracja", "restaurant", "pizzeria", "bar", "bistro",
    "pub", "cafe", "kawiarnia", "cukiernia", "grill",
    "kebab", "kuchnia", "kitchen", "food", "foods",
    "house", "place", "lounge", "express", "studio",
    "trattoria", "osteria", "taverna", "gastro",
    # Polish prepositions/articles (common in names)
    "pod", "u", "na", "w", "z", "do", "i", "oraz",
    # Flavor words
    "smaki", "smak", "taste", "flavour",
    # Generic suffixes
    "delivery", "online", "order", "zamow",
})

# Size patterns for dish name parsing
_SIZE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Explicit cm: "32cm", "32 cm"
    (re.compile(r'\b(\d{2,3}\s*cm)\b', re.IGNORECASE), "cm"),
    # Polish sizes: "mała", "średnia", "duża", "mega"
    (re.compile(r'\b(mala|mała|srednia|średnia|duza|duża|mega|xxl|xl|family)\b', re.IGNORECASE), "size_word"),
    # Piece count: "12szt", "12 szt", "6 pieces"
    (re.compile(r'\b(\d+\s*(?:szt|pieces?|pcs|sztuk))\b', re.IGNORECASE), "pieces"),
    # Volume: "0.5L", "330ml", "500 ml"
    (re.compile(r'\b(\d+(?:[.,]\d+)?\s*(?:ml|l|cl))\b', re.IGNORECASE), "volume"),
    # Weight: "200g", "1kg"
    (re.compile(r'\b(\d+(?:[.,]\d+)?\s*(?:g|kg))\b', re.IGNORECASE), "weight"),
    # Generic number+unit at end: "x3", "2x"
    (re.compile(r'\b(\d+\s*x|x\s*\d+)\b', re.IGNORECASE), "multiplier"),
]

# City suffixes commonly appended to restaurant names on platforms
_CITY_SUFFIXES: list[str] = [
    "warszawa", "krakow", "kraków", "wroclaw", "wrocław",
    "poznan", "poznań", "gdansk", "gdańsk", "lodz", "łódź",
    "katowice", "lublin", "bialystok", "białystok", "rzeszow", "rzeszów",
    "szczecin", "kielce", "torun", "toruń",
    # Short forms used by Glovo
    "waw", "kra", "wro", "poz", "gdn", "ldz", "ktw", "lub",
]


# ══════════════════════════════════════════════════════════════
# spaCy INTEGRATION (optional)
# ══════════════════════════════════════════════════════════════

_spacy_nlp = None
_spacy_available: bool | None = None


def _get_spacy_nlp():
    """Lazy-load spaCy Polish model. Returns None if unavailable."""
    global _spacy_nlp, _spacy_available

    if _spacy_available is False:
        return None
    if _spacy_nlp is not None:
        return _spacy_nlp

    try:
        import spacy
        _spacy_nlp = spacy.load("pl_core_news_md", disable=["ner", "parser"])
        _spacy_available = True
        logger.info("spaCy pl_core_news_md loaded — lemmatization enabled")
        return _spacy_nlp
    except (ImportError, OSError):
        _spacy_available = False
        logger.info(
            "spaCy pl_core_news_md not available — using fallback normalization. "
            "For better accuracy: pip install spacy && python -m spacy download pl_core_news_md"
        )
        return None


def spacy_available() -> bool:
    """Check if spaCy Polish model is loaded."""
    _get_spacy_nlp()
    return _spacy_available is True


def _lemmatize_spacy(text: str) -> str:
    """Lemmatize Polish text using spaCy."""
    nlp = _get_spacy_nlp()
    if nlp is None:
        return text
    doc = nlp(text)
    return " ".join(token.lemma_.lower() for token in doc if not token.is_punct)


# ══════════════════════════════════════════════════════════════
# CORE NORMALIZATION FUNCTIONS
# ══════════════════════════════════════════════════════════════

def remove_diacritics(text: str) -> str:
    """Remove Polish diacritics: ą→a, ć→c, ę→e, ł→l, ń→n, ó→o, ś→s, ź→z, ż→z.

    Note: ł/Ł requires explicit mapping — NFKD decomposition doesn't handle it
    because ł is not a base letter + combining mark in Unicode.
    """
    # Explicit ł/Ł mapping (not decomposable by NFKD)
    text = text.replace("ł", "l").replace("Ł", "L")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _strip_city_suffix(name: str) -> str:
    """Remove trailing city name from restaurant name.

    "KFC Floriańska Kraków" → "KFC Floriańska"
    "Pizza Hut - Warszawa" → "Pizza Hut"
    """
    # Remove after dash/comma: "Name - City", "Name, City"
    for sep in [" - ", " – ", ", "]:
        if sep in name:
            parts = name.rsplit(sep, 1)
            tail = parts[1].strip().lower()
            tail_ascii = remove_diacritics(tail)
            if tail_ascii in _CITY_SUFFIXES or tail in _CITY_SUFFIXES:
                name = parts[0].strip()

    # Remove trailing city word
    words = name.split()
    if len(words) >= 2:
        last = words[-1].lower()
        last_ascii = remove_diacritics(last)
        if last_ascii in _CITY_SUFFIXES or last in _CITY_SUFFIXES:
            words = words[:-1]
            name = " ".join(words)

    return name.strip()


def _remove_stop_words(tokens: list[str]) -> list[str]:
    """Remove restaurant stop words from token list."""
    return [t for t in tokens if t not in RESTAURANT_STOP_WORDS and len(t) > 1]


def normalize_restaurant_name(name: str) -> str:
    """
    Normalize restaurant name for cross-platform matching.

    Pipeline:
      1. Strip city suffix ("KFC Kraków" → "KFC")
      2. Lowercase
      3. Remove diacritics (ą→a, ł→l)
      4. Lemmatize via spaCy (optional: "pizzerii" → "pizzeria")
      5. Remove stop words (restauracja, bar, pod, u, na...)
      6. Sort tokens alphabetically (for token_sort_ratio stability)

    Examples:
      "Pizzeria Roma pod Wieżą"  → "roma wieza"
      "KFC Floriańska"           → "florianska kfc"
      "Restauracja Sushi Master" → "master sushi"
      "Bar Kebab u Ali"          → "ali"
      "Burger King - Warszawa"   → "burger king"

    Returns empty string if name normalizes to nothing (all stop words).
    """
    if not name or not name.strip():
        return ""

    # 1. Strip city suffix
    cleaned = _strip_city_suffix(name)

    # 2. Lowercase
    cleaned = cleaned.lower().strip()

    # 3. Remove diacritics
    cleaned = remove_diacritics(cleaned)

    # 4. Lemmatize (spaCy if available)
    nlp = _get_spacy_nlp()
    if nlp is not None:
        doc = nlp(cleaned)
        tokens = [
            remove_diacritics(token.lemma_.lower())
            for token in doc
            if not token.is_punct and not token.is_space
        ]
    else:
        # Fallback: split on non-alphanumeric
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        tokens = cleaned.split()

    # 5. Remove stop words
    tokens = _remove_stop_words(tokens)

    # 6. Sort alphabetically (stabilizes token_sort_ratio)
    tokens.sort()

    return " ".join(tokens)


def normalize_dish_name(name: str) -> tuple[str, str | None]:
    """
    Extract base dish name and size label from a menu item name.

    Splits size/quantity indicators from the dish name so items like
    "Margherita 32cm" and "Margherita 40cm" can be recognized as
    the same dish in different sizes.

    Pipeline:
      1. Extract size label (32cm, duża, 12szt, 0.5L, 200g)
      2. Remove extracted label from name
      3. Lowercase + remove diacritics
      4. Strip excess whitespace

    Examples:
      "Margherita 32cm"          → ("margherita", "32cm")
      "Pizza Pepperoni duża"     → ("pizza pepperoni", "duża")
      "Coca-Cola 0.5L"           → ("coca-cola", "0.5l")
      "Nuggetsy 12szt"           → ("nuggetsy", "12szt")
      "Zestaw Sake 16szt"       → ("zestaw sake", "16szt")
      "Classic Burger"           → ("classic burger", None)

    Returns:
      (base_name, size_label) — size_label is None if no size found.
    """
    if not name or not name.strip():
        return ("", None)

    size_label: str | None = None
    working = name.strip()

    # Try each size pattern, take first match
    for pattern, _ in _SIZE_PATTERNS:
        match = pattern.search(working)
        if match:
            size_label = match.group(1).strip().lower()
            # Remove the size label from the name
            working = working[:match.start()] + working[match.end():]
            break

    # Normalize the base name
    base = working.lower().strip()
    base = remove_diacritics(base)
    # Collapse whitespace
    base = re.sub(r'\s+', ' ', base).strip()
    # Remove trailing/leading punctuation
    base = re.sub(r'^[\s\-–,]+|[\s\-–,]+$', '', base)

    return (base, size_label)


# ══════════════════════════════════════════════════════════════
# BATCH NORMALIZATION (for persistor integration)
# ══════════════════════════════════════════════════════════════

def normalize_restaurant_names_batch(
    names: list[str],
) -> list[str]:
    """Normalize a batch of restaurant names. Efficient with spaCy pipe."""
    nlp = _get_spacy_nlp()

    if nlp is not None and len(names) > 10:
        # Use spaCy pipe for batch processing (much faster than one-by-one)
        cleaned = []
        for name in names:
            c = _strip_city_suffix(name).lower().strip()
            c = remove_diacritics(c)
            cleaned.append(c)

        results = []
        for doc in nlp.pipe(cleaned, batch_size=64):
            tokens = [
                remove_diacritics(token.lemma_.lower())
                for token in doc
                if not token.is_punct and not token.is_space
            ]
            tokens = _remove_stop_words(tokens)
            tokens.sort()
            results.append(" ".join(tokens))
        return results

    # Fallback: one-by-one
    return [normalize_restaurant_name(name) for name in names]
