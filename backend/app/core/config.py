"""Application settings, loaded from environment variables (and a local .env).

We use `pydantic-settings`: it reads env vars, validates their types, and gives
us one typed `Settings` object instead of scattered `os.getenv(...)` calls.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Where to read values from, and ignore any env vars we don't declare.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    debug: bool = False

    # Filled in once Neon/Clerk accounts exist (see backend/.env.example).
    # Optional here so the app/tests can still boot before they're set;
    # code that needs them raises a clear error at the point of use instead.
    database_url: str | None = None
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    """Return a single, cached Settings instance (built once, reused everywhere)."""
    return Settings()
