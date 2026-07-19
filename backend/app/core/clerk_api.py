"""Clerk **Backend API** client — the ONE place the backend calls Clerk's REST API.

Until now this backend never called Clerk's API: `app.core.auth` only *verifies* the
session JWT against Clerk's JWKS, and `app.core.org` only reads claims out of an
already-verified token (ADR #9 — "we only read JWT claims"). The assignment-submission
roster diff is a deliberate, flagged expansion of that design: to show a teacher *who
has not submitted*, we must enumerate an org's members, and Clerk — not our DB — owns
membership. All Clerk-REST specifics (base URL, auth header, pagination, JSON shape) are
isolated here so the rest of the app is unaffected and, when unconfigured, unbroken.

Verified contract (Clerk Backend API OpenAPI spec `bapi/2024-10-01.yml`,
raw.githubusercontent.com/clerk/openapi-specs/main/bapi/2024-10-01.yml, operationId
`ListOrganizationMemberships`):
  - GET  https://api.clerk.com/v1/organizations/{organization_id}/memberships
  - Auth: `Authorization: Bearer <CLERK_SECRET_KEY>` (bearerAuth, `sk_<env>_<value>`).
  - Pagination: `limit` (1–500, default 10) + `offset` (default 0).
  - Response `OrganizationMemberships`: `{ "data": OrganizationMembership[],
    "total_count": int }` (both required).
  - Each `OrganizationMembership.public_user_data.user_id` (string, required) is the
    member's Clerk user id — the value we diff against submission `owner_id`s.

Missing `CLERK_SECRET_KEY` is a deployment gap, not a crash: `_secret_key()` raises
`ClerkConfigError` at the point of use — the same loud-failure-at-use pattern as
`embedding.py`/`llm.py`/`r2_client.py`/`inngest_client.py`. The roster endpoint
translates that to a clean 503 rather than leaking a 500.
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings

# Backend API base — the spec's single declared server.
_BASE_URL = "https://api.clerk.com/v1"
# Per-page size. The spec allows 1–500; 100 keeps each response small while making the
# common (small class/org) case a single request. Pagination below handles any size.
_PAGE_LIMIT = 100
_TIMEOUT_SECONDS = 10.0


class ClerkConfigError(RuntimeError):
    """Raised when `CLERK_SECRET_KEY` isn't configured — the roster feature is env-gated
    and simply unavailable until the key is set. Surfaced by the router as a 503, never a
    500 (a missing key is a configuration gap, not an internal fault)."""


class ClerkAPIError(RuntimeError):
    """Raised when Clerk returns a non-2xx response — an upstream failure distinct from a
    missing key (bad/expired secret, org not found, Clerk outage). Surfaced as a 502."""


def _secret_key() -> str:
    key = get_settings().clerk_secret_key
    if not key:
        raise ClerkConfigError(
            "CLERK_SECRET_KEY is not set. Add it to backend/.env — see backend/.env.example. "
            "The assignment roster needs Clerk's Backend API to enumerate org members."
        )
    return key


def list_organization_member_ids(org_id: str) -> list[str]:
    """Return the Clerk user ids of every member of `org_id`, following pagination.

    Calls `GET /v1/organizations/{org_id}/memberships` with a Bearer secret key, walking
    `offset` in pages of `_PAGE_LIMIT` until every membership (per `total_count`) is read.
    Extracts `public_user_data.user_id` from each membership. Missing key →
    `ClerkConfigError`; a non-2xx response → `ClerkAPIError`. Order follows Clerk's default
    (creation date); the caller diffs by set membership, so order is not relied upon.
    """
    headers = {"Authorization": f"Bearer {_secret_key()}"}
    user_ids: list[str] = []
    offset = 0

    with httpx.Client(base_url=_BASE_URL, timeout=_TIMEOUT_SECONDS) as client:
        while True:
            response = client.get(
                f"/organizations/{org_id}/memberships",
                headers=headers,
                params={"limit": _PAGE_LIMIT, "offset": offset},
            )
            if response.status_code != 200:
                raise ClerkAPIError(
                    f"Clerk memberships call failed for org {org_id}: HTTP {response.status_code}"
                )

            body = response.json()
            data = body.get("data") or []
            for membership in data:
                public_user_data = membership.get("public_user_data") or {}
                user_id = public_user_data.get("user_id")
                if user_id:
                    user_ids.append(user_id)

            # Advance by what we actually received and stop once we've read the whole set
            # (or Clerk returned an empty page — the belt-and-braces guard against an
            # inconsistent total_count that would otherwise loop forever).
            offset += len(data)
            total_count = body.get("total_count", 0)
            if not data or offset >= total_count:
                break

    return user_ids
