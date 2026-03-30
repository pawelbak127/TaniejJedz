from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.dev",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ─────────────────────────────────────────────────
    app_env: str = "development"
    app_debug: bool = False
    app_secret_key: str = "change-me"

    # ── Database ────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://taniejjedz:localdevpassword@localhost:5432/taniejjedz"
    database_url_sync: str = "postgresql://taniejjedz:localdevpassword@localhost:5432/taniejjedz"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # ── Redis ───────────────────────────────────────────────
    redis_url: str = "redis://:localdevpassword@localhost:6379/0"

    # ── Meilisearch ─────────────────────────────────────────
    meili_url: str = "http://localhost:7700"
    meili_master_key: str = "localdevmasterkey"

    # ── Nominatim (geocoding) ──────────────────────────────
    nominatim_url: str = "http://localhost:8080"

    # ── CORS ────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # ── Rate Limiting ───────────────────────────────────────
    rate_limit_enabled: bool = True
    rate_limit_search: str = "15/minute"
    rate_limit_compare: str = "20/minute"
    rate_limit_redirect: str = "30/minute"
    rate_limit_feedback: str = "5/minute"

    # ── Cities (launch config) ──────────────────────────────
    default_city_slug: str = "warszawa"
    launch_cities: list[dict[str, Any]] = [
        {
            "name": "Warszawa",
            "slug": "warszawa",
            "center_lat": 52.2297,
            "center_lng": 21.0122,
            "radius_km": 15,
        },
    ]

    # ── Epic 3: Scraper infrastructure ──────────────────────

    # Bright Data residential proxy
    proxy_enabled: bool = False  # True in production, False = direct requests
    proxy_host: str = "brd.superproxy.io"
    proxy_port: int = 22225
    proxy_username: str = ""
    proxy_password: str = ""
    proxy_zone: str = "residential_pl"
    proxy_country: str = "pl"

    # Daily request budgets per platform
    budget_wolt_daily: int = 5000
    budget_pyszne_daily: int = 5000
    budget_glovo_daily: int = 5000
    budget_ubereats_daily: int = 5000
    budget_alert_threshold: float = 0.90  # alert at 90%

    # Circuit breaker
    cb_failure_threshold: int = 5
    cb_cooldown_seconds: int = 120

    # Scraper HTTP timeouts
    scraper_timeout_realtime: float = 8.0   # hard 8s for user-facing path
    scraper_timeout_background: float = 30.0  # Dramatiq background jobs
    scraper_max_retries: int = 2

    # Session / cookie TTL (seconds)
    session_cookie_ttl: int = 3600

    # Platform API URLs
    wolt_search_url: str = "https://restaurant-api.wolt.com/v1/pages/restaurants"
    wolt_menu_url: str = "https://consumer-api.wolt.com/consumer-api/venue-content-api/v3/web/venue-content/slug"
    pyszne_search_url: str = "https://rest.api.eu-central-1.production.jet-external.com/discovery/pl/restaurants/enriched"
    pyszne_menu_base_url: str = "https://www.pyszne.pl/menu"

    # Orchestrator
    orchestrator_platforms: list[str] = ["wolt", "pyszne", "glovo", "ubereats"]
    orchestrator_timeout: float = 8.0        # per-platform hard limit
    warm_cache_top_n: int = 50               # top N restaurants per city to warm
    warm_cache_interval_minutes: int = 30
    nightly_crawl_hour: int = 3              # 3:00 AM CET

    # ── Epic 4: Data Pipeline ───────────────────────────────

    # Persistence
    persist_enabled: bool = True             # Enable DB writes from crawl jobs

    # Entity matching thresholds (Sprint 4.2-4.3)
    match_auto_threshold: float = 0.85       # ≥ 0.85 → auto-match
    match_review_threshold: float = 0.60     # 0.60-0.85 → entity_review_queue
    # < 0.60 → create new canonical_restaurant

    # Matching weights
    match_weight_name: float = 0.30
    match_weight_distance: float = 0.25
    match_weight_menu_overlap: float = 0.25
    match_weight_phone: float = 0.20

    # Geospatial blocking radius (meters)
    match_geo_radius_m: int = 300

    # Trigram pre-filter threshold
    match_trgm_threshold: float = 0.3

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
