# Epic 3 Hotfix v4 — UberEats Sitemap Sync

## Co jest w paczce

```
patch-v4/
├── app/
│   ├── jobs/
│   │   └── sync_ubereats_slugs.py     # NOWY: UberEats sitemap sync job
│   └── scraper/
│       └── adapters/
│           └── ubereats.py             # ZMODYFIKOWANY: sitemap-based search
└── tests/
    └── test_ubereats_sitemap.py        # Testy sync joba + adaptera
```

**UWAGA**: Ten patch nie zawiera plików Glovo — te zostały dostarczone w v3.

## Deployment

```powershell
cd C:\Projects\TaniejJedz\backend
# Rozpakuj — nadpisze ubereats.py!
```

## Testowanie

```powershell
# 1. Testy jednostkowe (bez Redis/sieci)
pytest tests/test_ubereats_sitemap.py -v

# 2. UberEats sitemap sync (wymaga Redis + sieć, ~2-3 min)
python -m app.jobs.sync_ubereats_slugs

# 3. Weryfikacja Redis
redis-cli -a localdevpassword
> GET scraper:ubereats:sitemap_meta
> STRLEN scraper:ubereats:known_stores
```

## Oczekiwany output sync

```
============================================================
  UBEREATS SITEMAP SYNC — standalone runner
============================================================
  Connecting to: redis://:*****@localhost:6379/0
  ✓ Connected to Redis

  ...scanning 114 sitemaps...

============================================================
  SYNC COMPLETE
============================================================
  Total unique stores: ~11,998
  Duration: ~150s
  Sitemaps scanned: 114
```

## Podsumowanie coverage po obu syncach

| Platforma | Przed | Po | Mnożnik |
|-----------|------:|---:|--------:|
| Glovo     |    50 | 13,867 | 277× |
| UberEats  |    43 | 11,998 | 279× |
| Wolt      |   630 | 630    | (bez zmian) |
| Pyszne    |   556 | 556    | (bez zmian) |
| **TOTAL** | 1,279 | **27,051** | **21×** |
