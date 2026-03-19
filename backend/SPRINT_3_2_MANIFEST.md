# Sprint 3.2 — Wolt Adapter — MANIFEST

## Status: ✅ COMPLETE (106/106 tests — 58 Sprint 3.1 + 48 Sprint 3.2)

## New Files

| File | LOC | Purpose |
|------|-----|---------|
| `app/scraper/schemas/__init__.py` | 7 | Package init |
| `app/scraper/schemas/normalized.py` | 119 | Platform-agnostic output schemas mapping to DB models |
| `app/scraper/schemas/wolt.py` | 206 | Raw Wolt API response Pydantic models |
| `app/scraper/adapters/wolt.py` | 447 | Full Wolt adapter: search, menu, delivery, hours, promos |
| `app/scraper/tests/fixtures/wolt_discovery.json` | 118 | Wolt search/discovery API fixture (3 venues, 2 sections) |
| `app/scraper/tests/fixtures/wolt_venue.json` | 208 | Wolt venue+menu fixture (2 categories, 5 items, modifiers, hours, promos) |
| `app/scraper/tests/test_wolt_contract.py` | 495 | 48 contract tests — parsing + normalisation |

## Modified Files

| File | Changes |
|------|---------|
| `app/scraper/base_adapter.py` | Abstract methods now return typed `Normalized*` schemas; added normalized imports |
| `app/scraper/adapters/__init__.py` | Exports `WoltAdapter` |
| `app/scraper/tests/test_base_adapter.py` | `_DummyAdapter` returns typed values |

## Architecture

### Wolt API endpoints modelled

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/v1/pages/restaurants?lat=...&lon=...` | `search_restaurants()` | `list[NormalizedRestaurant]` (no menu) |
| `/v4/venues/slug/{slug}` | `get_menu()` | `list[NormalizedMenuItem]` with modifier groups |
| `/v4/venues/slug/{slug}` | `get_delivery_fee()` | `NormalizedDeliveryFee` |
| `/v4/venues/slug/{slug}` | `get_operating_hours()` | `list[NormalizedHours]` |
| `/v4/venues/slug/{slug}` | `get_promotions()` | `list[NormalizedPromotion]` |
| `/v4/venues/slug/{slug}` | `get_full_venue()` | `NormalizedRestaurant` with ALL data (1 HTTP call) |

### Normalisation mapping

| Wolt field | Normalised field | Notes |
|------------|-----------------|-------|
| `location.coordinates[lon, lat]` | `latitude, longitude` | GeoJSON order swapped |
| `rating.score` (0-100) | `rating_score` (0-10) | Divided by 10 |
| `baseprice` (grosz) | `price_grosz` | Direct 1:1 |
| `options[].type: "single_choice"` + `min_selections: 1` | `group_type: "required"` | Mapped |
| `options[].type: "multi_choice"` + `min_selections: 0` | `group_type: "optional"` | Mapped |
| `opening_times[].times[].opening_time: "24:00"` | `close_time: 23:59` | Edge case handled |

### Contract test coverage (48 tests)

| Group | Tests | Verifies |
|-------|-------|----------|
| Discovery parsing | 8 | JSON→schema, dedup across sections, all fields |
| Discovery normalisation | 6 | GeoJSON swap, rating scale, URL building, offline flag |
| Venue+menu parsing | 10 | Categories, items, modifiers, options, hours, delivery, promos |
| Menu normalisation | 8 | Price, modifiers required/optional, disabled items, diacritics |
| Hours normalisation | 4 | Day mapping, time parsing, edge cases (24:00) |
| Delivery fee | 1 | Full fee structure from venue |
| Promotions | 3 | Type mapping, percentage vs free_delivery |
| Full venue | 3 | Combined output, item counts, coordinates |
| Edge cases | 5 | Empty responses, missing fields, dual option keys, closed days |

## Verification

```bash
cd backend
python -m pytest app/scraper/tests/ -v
# Expected: 106 passed
```
