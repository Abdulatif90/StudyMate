"""Polar (payments) client — one SDK client, built once and shared.

Same "build once + fail loudly at point of use" pattern as `r2_client.py` /
`inngest_client.py` / `embedding.py`: missing credentials is a *deployment* mistake, so
`get_client()` raises `PolarConfigError` naming exactly which vars are missing rather
than failing obscurely deep inside the SDK.

**This module is deliberately Polar-only.** It knows nothing about `Plan`/`UserPlan` —
the product-id -> plan mapping lives in `billing/service.py`, which owns the domain.
Keeping the layering that way (core = infrastructure, modules = domain) is why
`app/core` never imports `app/modules`.

**Secrets never leave here** (CLAUDE.md rule 5): the access token and webhook secret are
read from settings and handed to the SDK. They are never logged, never returned in a
response, and never included in an exception message — the errors below name the *env
var*, never its value.
"""

from __future__ import annotations

from functools import lru_cache

from polar_sdk import Polar
from polar_sdk.webhooks import (
    WebhookUnknownTypeError as SDKWebhookUnknownTypeError,
)
from polar_sdk.webhooks import (
    WebhookVerificationError as SDKWebhookVerificationError,
)
from polar_sdk.webhooks import (
    validate_event,
)

from app.core.config import get_settings

# Re-exported so callers can catch these without importing the SDK themselves.
WebhookVerificationError = SDKWebhookVerificationError
#: Raised by `validate_event` when the signature is VALID but the event type is one this
#: SDK version doesn't know (e.g. Polar shipped a new event). Not a security failure —
#: the payload is authentic — so the caller ignores it rather than rejecting it.
WebhookUnknownTypeError = SDKWebhookUnknownTypeError

_VALID_SERVERS = {"sandbox", "production"}


class PolarConfigError(RuntimeError):
    """Raised when Polar isn't fully configured."""


@lru_cache
def get_client() -> Polar:
    settings = get_settings()
    if not settings.polar_access_token:
        raise PolarConfigError(
            "Polar is not configured — missing POLAR_ACCESS_TOKEN. "
            "Add it to backend/.env — see backend/.env.example."
        )
    if settings.polar_server not in _VALID_SERVERS:
        raise PolarConfigError(
            f"POLAR_SERVER must be one of {sorted(_VALID_SERVERS)}, got {settings.polar_server!r}."
        )
    # `server` selects the SDK's own base URL ("sandbox" -> https://sandbox-api.polar.sh,
    # "production" -> https://api.polar.sh), so no URL is hardcoded here.
    return Polar(access_token=settings.polar_access_token, server=settings.polar_server)


def get_webhook_secret() -> str:
    """The webhook signing secret, or raise.

    **Never falls back to "unset -> accept".** An unverified webhook is an entitlement
    bypass: anyone who can POST to the endpoint could put themselves on Business for
    free. A missing secret is a misconfiguration and fails loudly, exactly like every
    other missing credential in this codebase.
    """
    secret = get_settings().polar_webhook_secret
    if not secret:
        raise PolarConfigError(
            "Polar webhooks are not configured — missing POLAR_WEBHOOK_SECRET. "
            "Add it to backend/.env — see backend/.env.example."
        )
    return secret


def verify_webhook(body: bytes, headers: dict[str, str]) -> object:
    """Verify a webhook's signature against POLAR_WEBHOOK_SECRET and return the parsed
    event. Raises `WebhookVerificationError` if the signature/timestamp doesn't check
    out, `PolarConfigError` if no secret is configured.

    `body` MUST be the **raw** request bytes. The signature covers those exact bytes, so
    re-serializing parsed JSON (different key order/spacing) would produce a different
    payload and fail verification.

    The SDK's `validate_event` base64-encodes the secret and delegates to the Standard
    Webhooks verifier, which compares signatures in constant time (`hmac.compare_digest`)
    and rejects stale timestamps — i.e. replay protection comes for free, and we don't
    hand-roll any crypto here.
    """
    return validate_event(body, headers, get_webhook_secret())
