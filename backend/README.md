# Hotfix 2 — UberEats UUID Decode Fix

## Odkrycie

Sitemap UberEats zawiera UUID-y w formacie **base64url** (22 znaki):
```
skuqnuRLTnWC8PipFYCYfg
```

API `getStoreV1` oczekuje **hex UUID** (36 znaków):
```
b24baa9e-e44b-4e75-82f0-f8a91580987e
```

Konwersja: `base64.urlsafe_b64decode(b64url + padding)` → `uuid.UUID(bytes=...)` → hex string.

**Wynik testu P0**: 10/10 UUID-ów z sitemapy zwraca sukces po decode — koordynaty + menu (60-211 items).

## Pliki

```
app/scraper/adapters/ubereats.py     # ZMODYFIKOWANY — decode_ubereats_uuid() + _ensure_hex_uuid()
app/jobs/enrich_ubereats.py          # NOWY — batch enrichment (koordynaty + menu validation)
diag/diag_uuid_decode.py             # Skrypt diagnostyczny P0
tests/test_ubereats_uuid_decode.py   # Testy decode
```

## Testowanie

```powershell
# 1. Testy jednostkowe
pytest tests/test_ubereats_uuid_decode.py -v

# 2. Enrichment Warszawa (~787 stores, ~13 min at 1 req/s)
python -m app.jobs.enrich_ubereats

# 3. Enrichment innego miasta
$env:ENRICH_CITY="krakow"
python -m app.jobs.enrich_ubereats
```

## Zmiany w adapterze

Jedyna zmiana behawioralna: `_search_from_sitemap()` teraz dekoduje base64url→hex UUID przed zapisaniem do `platform_slug`. Reszta kodu (suggestions, normalizacja, schemas) bez zmian.

`_ensure_hex_uuid()` w `get_menu()`, `get_store_info()`, `get_delivery_fee()` automatycznie dekoduje jeśli dostanie base64url — safety net.
