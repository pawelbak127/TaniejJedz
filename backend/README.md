# Sprint 4.3 — Restaurant Matcher — Wdrożenie

**Zawiera także Sprint 4.2** (normalizers, geocoding, persistor update).
Jeśli masz już Sprint 4.2 — ten ZIP go nadpisze tymi samymi plikami.

## Krok 1: Rozpakuj

```powershell
cd C:\Projects\TaniejJedz\backend
Expand-Archive -Path sprint_4_3.zip -DestinationPath . -Force
```

Nowe pliki (Sprint 4.3):
- `app/entity_resolution/matching_utils.py` — haversine, name_similarity, Jaccard, phones_match
- `app/entity_resolution/restaurant_matcher.py` — RestaurantMatcher z PostGIS + rapidfuzz
- `app/entity_resolution/tests/test_matching_utils.py`
- `app/entity_resolution/tests/test_restaurant_matcher.py`

Z Sprint 4.2 (niezmienione):
- `app/entity_resolution/normalizers.py`, `geocoding.py`
- `app/services/persistor.py` (z normalized_name w metadata)

---

## Krok 2: Zależności

```powershell
pip install rapidfuzz unidecode
```

---

## Krok 3: Testy (bez Dockera)

```powershell
python -m pytest app/entity_resolution/tests/ -v
```

Oczekiwane: **148 passed, 1 skipped**

---

## Krok 4: Test integracyjny (z Dockerem)

```powershell
# Upewnij się że masz dane z crawla (Sprint 4.1)
$env:DATABASE_URL="postgresql+asyncpg://taniejjedz:localdevpassword@localhost:5432/taniejjedz"
$env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"

# Uruchom matching
python -c "
import asyncio
from app.jobs.db import get_async_session
from app.entity_resolution.restaurant_matcher import RestaurantMatcher

async def run():
    async with get_async_session() as session:
        matcher = RestaurantMatcher(session)
        stats = await matcher.match_all_platforms('warszawa')
        await session.commit()
        print(stats)

asyncio.run(run())
"
```

Oczekiwany output:
```
MatchStats(auto=N, review=M, new=K, skipped=S, err=0)
```

Gdzie:
- `new` ≈ 1378 (Wolt — pierwszy, tworzy canonicals)
- `auto` > 200 (Pyszne restaurants matched to Wolt canonicals)
- `review` = kilkadziesiąt (medium-confidence matches)
- `skipped` ≈ 50 (Glovo bez koordynatów)

---

## Krok 5: Weryfikacja w DB

```sql
-- Ile canonical_restaurants powstało?
SELECT COUNT(*) FROM canonical_restaurants;

-- Ile platform_restaurants ma match?
SELECT 
  COUNT(*) FILTER (WHERE canonical_restaurant_id IS NOT NULL) AS matched,
  COUNT(*) FILTER (WHERE canonical_restaurant_id IS NULL) AS unmatched
FROM platform_restaurants;

-- Breakdown per platform
SELECT 
  platform,
  COUNT(*) AS total,
  COUNT(canonical_restaurant_id) AS matched,
  ROUND(AVG(match_confidence)::numeric, 3) AS avg_confidence
FROM platform_restaurants
GROUP BY platform
ORDER BY total DESC;

-- Losowe auto-matchy (confidence ≥ 0.85)
SELECT 
  cr.name AS canonical,
  pr.platform,
  pr.platform_name,
  pr.match_confidence
FROM platform_restaurants pr
JOIN canonical_restaurants cr ON pr.canonical_restaurant_id = cr.id
WHERE pr.match_confidence >= 0.85
  AND pr.platform != 'wolt'
ORDER BY RANDOM()
LIMIT 10;

-- Entity review queue
SELECT COUNT(*), status FROM entity_review_queue GROUP BY status;

-- Przykładowe review items
SELECT 
  pr.platform_name,
  cr.name AS candidate,
  erq.confidence_score,
  erq.match_details
FROM entity_review_queue erq
JOIN platform_restaurants pr ON erq.platform_restaurant_id = pr.id
LEFT JOIN canonical_restaurants cr ON erq.candidate_canonical_id = cr.id
WHERE erq.status = 'pending'
LIMIT 5;
```

---

## Jak działa matching

```
1. Wolt (1378 restauracji)
   → Wszystkie stają się canonical_restaurants
   → canonical_restaurant_id = nowe canonical.id
   → match_confidence = 1.0

2. Pyszne (578 restauracji)
   → Dla każdej z lat/lng:
     a. PostGIS: znajdź canonicals w promieniu 300m
     b. Trigram: odfiltruj similarity < 0.3
     c. Score: name(0.30) + distance(0.25) + menu(0.25) + phone(0.20)
     d. ≥ 0.85 → auto_match (link do canonical)
     e. 0.60–0.85 → entity_review_queue (czeka na admina)
     f. < 0.60 → nowy canonical_restaurant

3. Glovo (50) → jak Pyszne, ale ~50 skipped (brak koordynatów)

4. UberEats (42) → jak Pyszne
```

---

## Co dalej

- **Sprint 4.4** (opcjonalny): Cross-reference discovery — uzupełnij Glovo/UberEats coverage
- **Sprint 4.5**: Menu item matching — link platform_menu_items do canonical_menu_items
