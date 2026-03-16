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
    launch_cities: list[dict[str, Any]] = [
        {
            "name": "Warszawa",
            "slug": "warszawa",
            "center_lat": 52.2297,
            "center_lng": 21.0122,
            "radius_km": 15,
        },
    ]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
