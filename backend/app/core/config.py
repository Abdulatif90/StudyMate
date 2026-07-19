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
    # Clerk *Backend API* secret key (sk_...). Distinct from the JWKS/issuer above:
    # auth only *verifies JWT claims* (no Clerk API call), but the assignment roster diff
    # must *enumerate* an org's members, which only Clerk can answer. Optional/env-gated so
    # the app/tests boot without it; app/core/clerk_api.py raises a clear error at point of
    # use, and the roster endpoint returns 503 (not 500) until it's set.
    clerk_secret_key: str | None = None
    cohere_api_key: str | None = None
    anthropic_api_key: str | None = None
    # Inngest (async document processing). Optional so the app/tests boot without
    # them; the event-send path raises a clear error at point of use if unset (see
    # app/core/inngest_client.py).
    inngest_event_key: str | None = None
    inngest_signing_key: str | None = None

    # Cloudflare R2 (S3-compatible file storage for uploaded documents). Optional so
    # the app/tests boot without them; app/core/r2_client.py raises at point of use.
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None

    # Polar (billing/payments). Optional so the app/tests boot without them;
    # app/core/polar_client.py raises at point of use.
    polar_access_token: str | None = None
    polar_webhook_secret: str | None = None
    # "sandbox" or "production" — drives which API base URL the SDK targets.
    # Defaults to sandbox so a misconfigured deploy can never accidentally charge a
    # real card; production is an explicit opt-in.
    polar_server: str = "sandbox"

    # Product -> plan mapping, by **product id** rather than product name.
    # Ids are stable and opaque; a name is a mutable dashboard label, and renaming a
    # product would silently break entitlement mapping (this org's own products were
    # already named inconsistently — "FREE"/"PRO"/"Business"). Ids also keep the
    # webhook's hot path local: mapping by name would need an extra Polar API call per
    # event, adding latency and a new failure mode to a path that must be cheap and
    # reliable. No id for Free on purpose: Free is the *absence* of a paid plan (see
    # billing/models.UserPlan), so it is never sold and never checked out.
    polar_product_id_pro: str | None = None
    polar_product_id_business: str | None = None

    # Error monitoring (Sentry). Optional so the app/tests boot without it —
    # app/core/sentry.py's init_sentry() is a no-op when unset, never a crash (a missing
    # DSN means "no observability", not a startup failure).
    sentry_dsn: str | None = None

    # Comma-separated (not JSON) so a plain `.env` value like
    # `CORS_ORIGINS=http://localhost:3000,https://app.example.com` just works —
    # pydantic-settings expects JSON for genuine list-typed fields, which is more
    # friction than this needs for something this simple.
    cors_origins: str = "http://localhost:3000"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a single, cached Settings instance (built once, reused everywhere)."""
    return Settings()
