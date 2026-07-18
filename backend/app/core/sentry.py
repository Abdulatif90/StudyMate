"""Sentry error monitoring — optional, env-gated on `Settings.sentry_dsn`.

Inverts this codebase's usual "raise a clear error at point of use" pattern (see
db.py/embedding.py/llm.py/r2_client.py/polar_client.py) on purpose: observability itself
must never become a new way for the app to fail to boot, so a missing DSN means Sentry is
simply off, not a `RuntimeError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sentry_sdk

from app.core.config import get_settings


def _build_before_send(
    ignored_exceptions: Sequence[type[BaseException]],
) -> Any:
    """A `before_send` hook that drops events whose exception is one of
    `ignored_exceptions` — used to keep expected, already-handled errors (e.g. a plan
    limit hit, which main.py turns into a normal 402) out of Sentry, so they don't spam
    an issue stream meant for genuine unexpected failures."""

    def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
        exc_info = hint.get("exc_info")
        if exc_info is not None and isinstance(exc_info[1], tuple(ignored_exceptions)):
            return None
        return event

    return before_send


def init_sentry(ignored_exceptions: Sequence[type[BaseException]] = ()) -> None:
    """Initialize Sentry if `SENTRY_DSN` is set; a no-op otherwise.

    `ignored_exceptions` lets the caller (main.py) name application exceptions that
    already have a dedicated, expected-outcome handler (e.g. `PlanLimitExceededError` ->
    402) — kept generic here rather than importing a specific domain exception, so
    app/core stays free of a dependency on app/modules.
    """
    settings = get_settings()
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        before_send=_build_before_send(ignored_exceptions),
    )
