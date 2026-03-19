# Sprint 3.1 — Scraper Infrastructure — MANIFEST

## Status: ✅ COMPLETE (55/55 tests passing) — v2 after code review

## Review Fixes Applied (v1 → v2)

| Issue | Before (v1) | After (v2) |
|-------|-------------|------------|
| Settings naming | `PROXY_HOST`, `BUDGET_WOLT_DAILY` etc. (UPPERCASE) | `proxy_host`, `budget_wolt_daily` (lowercase, matching Epic 2) |
| Config class | Custom `model_config = {"env_file": ".env"}` | `SettingsConfigDict(env_file=".env.dev", case_sensitive=False)` |
| `@lru_cache` | `@lru_cache()` (with parens) | `@lru_cache` (no parens, matching Epic 2) |
| Redis import | `import redis.asyncio as aioredis` + `aioredis.Redis` | `from redis.asyncio import Redis` (matching Epic 2) |
| Config completeness | Only scraper fields | Full Epic 2 config + scraper delta appended |
| Cache path assumption | Created `app/services/cache_service.py` stub | Removed — real is `app/cache/cache_service.py` (CacheService class) |
| Test conftest | Missing `cache_clear` autouse | Added autouse `_clear_settings_cache` fixture |

## New Files (Sprint 3.1 delta)

### Core Scraper Infrastructure
| File | LOC | Purpose |
|------|-----|---------|
| `app/scraper/__init__.py` | 25 | Package exports |
| `app/scraper/proxy_manager.py` | 105 | Bright Data residential proxy rotation (rotating + sticky sessions) |
| `app/scraper/fingerprint.py` | 195 | 54 Polish-locale User-Agents, `build_headers()` with Sec-CH-UA/Sec-Fetch, `human_delay()` |
| `app/scraper/budget_manager.py` | 155 | Daily caps per platform, Redis atomic counters, 3 priority tiers, 90% alert |
| `app/scraper/session_manager.py` | 140 | Per-platform cookie jars serialised to Redis, TTL, list/touch/delete |
| `app/scraper/circuit_breaker.py` | 165 | CLOSED→OPEN→HALF_OPEN state machine in Redis, 5 failures/120s cooldown |
| `app/scraper/base_adapter.py` | 145 | Abstract base for platform adapters — wires proxy+budget+CB+sessions+httpx |
| `app/scraper/adapters/__init__.py` | 5 | Adapters package placeholder |

### Modified Files (Epic 2 → Epic 3)
| File | Changes |
|------|---------|
| `app/config.py` | Full Epic 2 config preserved + 12 new scraper fields: `proxy_*`, `budget_*`, `cb_*`, `scraper_timeout_*`, `session_cookie_ttl` |

### Tests
| File | Tests | Coverage |
|------|-------|----------|
| `test_proxy_manager.py` | 5 | Rotating vs sticky, URL format, Bright Data params |
| `test_fingerprint.py` | 11 | 50+ UAs, multi-browser, mobile/desktop, Sec headers, locale, delay bounds |
| `test_budget_manager.py` | 11 | Tier thresholds (LOW@70%, NORMAL@90%, CRITICAL=never), alert callback, isolation |
| `test_session_manager.py` | 10 | Save/load/delete cookies, platform isolation, corrupt data resilience |
| `test_circuit_breaker.py` | 11 | State transitions, half-open probe, platform isolation, force open/close |
| `test_base_adapter.py` | 2 | CB blocks fetch, budget blocks fetch |
| **Total** | **55** | |

## Architecture Decisions

1. **Redis everywhere** — all shared state (budgets, circuit breakers, sessions) lives in Redis
   so multiple Dramatiq workers share consistent state. Uses existing `REDIS_URL` from config.
2. **Priority tiers** — LOW rejected at 70% budget, NORMAL at 90%, CRITICAL never rejected.
   This lets canary/health probes always execute even when budget is tight.
3. **Circuit breaker in Redis** — CLOSED→OPEN (5 failures, 120s cooldown)→HALF_OPEN (1 probe).
   Per-platform isolation: Wolt outage doesn't block Pyszne.
4. **Proxy URL format** — Bright Data `session-{id}` param for per-request rotation.
   Sticky sessions via reusable session ID for multi-step auth flows.
5. **Fingerprint realism** — Sec-CH-UA, Sec-Fetch-*, DNT for Firefox, triangular-distribution
   human delays, Polish Accept-Language variants.

## Verification

```bash
cd taniejjedz
pip install -r requirements-scraper.txt --break-system-packages
python -m pytest app/scraper/tests/ -v
# Expected: 55 passed
```

## Integration Points with Epic 2

| Epic 2 Component | How Sprint 3.1 Integrates |
|------------------|--------------------------|
| `app/config.py` (Settings) | Scraper fields appended, same `SettingsConfigDict` + lowercase convention |
| `app/cache/cache_service.py` (CacheService) | Sprint 3.4 orchestrator will use existing `get_menu()`, `set_menu()` etc. |
| `app/cache/keys.py` (CacheKeys, CacheTTL) | Adapters will use existing key builders for cache writes |
| `app/dependencies.py` (RedisClient) | Adapters accept `Redis` via DI — same `from redis.asyncio import Redis` |
| `app/jobs/__init__.py` (Dramatiq broker) | Sprint 3.4 jobs will register on same broker via `dramatiq.actor` |
| `app/jobs/compare_worker.py` | Sprint 3.4 replaces `_generate_mock_result()` with real adapter calls |
| `app/models/restaurant.py` (PlatformRestaurant) | Adapters normalize to existing model fields |
| `app/models/menu.py` (PlatformMenuItem) | Menu adapter data maps to existing columns |
| `app/models/modifier.py` (ModifierGroup/Option) | Modifier tree from adapters maps to existing FK structure |
| `app/schemas/menu.py` (MenuResponse) | Adapter output normalises to existing Pydantic schemas |

## Next: Sprint 3.2 (Wolt Adapter)
- `app/scraper/adapters/wolt.py` — search_restaurants, get_menu, get_delivery_fee, get_operating_hours, get_promotions
- Wolt-specific Pydantic response schemas
- Normalisation to unified PlatformRestaurant / PlatformMenu
- Contract tests with fixture JSON
