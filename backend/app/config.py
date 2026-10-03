"""Application configuration with strict validation and secure defaults."""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Orion Banking settings loaded from environment (or .env).

    All secrets MUST come from env in production — defaults are only
    safe enough to bootstrap local development with SQLite.
    """

    # ── App ──────────────────────────────────────────────────────
    app_name: str = "Orion Banking API"
    env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Database ──────────────────────────────────────────────────
    # Default to SQLite for zero-config local dev. Production MUST override.
    database_url: str = "sqlite:///./orion_banking.db"

    # ── Security ─────────────────────────────────────────────────
    # If SECRET_KEY is not provided in env, we generate a stable random one
    # for the lifetime of this process (tokens will not survive restart).
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # PIN policy
    pin_min_length: int = 4
    pin_max_length: int = 6

    # CORS — comma-separated list of allowed origins
    cors_allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    # Rate limiting (per-IP) — requests per minute on auth endpoints
    auth_rate_limit_per_minute: int = 10
    api_rate_limit_per_minute: int = 60

    @field_validator("secret_key")
    @classmethod
    def _warn_insecure_secret(cls, v: str) -> str:
        if v == "change-me-in-production":
            raise ValueError(
                "SECRET_KEY='change-me-in-production' is forbidden. "
                "Set a strong value in your .env file (e.g. `openssl rand -hex 32`)."
            )
        return v

    @field_validator("database_url")
    @classmethod
    def _warn_sqlite_in_prod(cls, v: str, info) -> str:
        if info.data.get("env") == "prod" and v.startswith("sqlite"):
            raise ValueError("SQLite must not be used in production env=prod.")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_test(self) -> bool:
        return self.env == "dev" and self.database_url.startswith("sqlite")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — single source of truth."""
    return Settings()


# Module-level alias used across the codebase
settings = get_settings()
