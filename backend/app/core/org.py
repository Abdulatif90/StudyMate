"""Organization context + role logic for Clerk Organizations (Phase 5).

Orgs, memberships, roles, and invitations are owned by **Clerk Organizations**
(Clerk's native feature), not by our own DB tables — see docs/DECISIONS.md. Our
backend never stores org data; it only reads the *active organization* out of the
same Clerk session JWT it already verifies for auth (`app.core.auth`).

This module is pure (no FastAPI, no I/O): it extracts org claims from an
already-verified claim dict and maps a Clerk org role to our teacher/student
capability. The FastAPI dependencies that feed it a verified token live in
`app.core.auth` (`get_org_context`, `require_teacher`).
"""

from __future__ import annotations

from dataclasses import dataclass

# Our two capability levels. Clerk's *default* org roles are `org:admin` and
# `org:member` (confirmed against the installed @clerk/* SDK's own type docs, and
# Clerk's docs). We map the admin-tier role -> "teacher" and everything else ->
# "student". `org:teacher`/`org:student` are also honored in case a custom role set
# is configured on the instance later — but nothing here assumes they exist.
TEACHER = "teacher"
STUDENT = "student"

# Role keys that grant the teacher/admin capability. Kept as a set so a custom
# `org:teacher` role maps correctly if the instance ever adds one, without changing
# the default `org:admin`->teacher behavior.
_TEACHER_ROLE_KEYS = frozenset({"org:admin", "org:teacher"})


@dataclass(frozen=True)
class OrgContext:
    """The caller's active-organization context, read from the verified JWT.

    Both fields are `None` when the user has no active organization (personal
    workspace) — a valid, non-error state, not a failure. When an org is active,
    `org_role` is the raw Clerk role key (e.g. `org:admin`), mapped to a capability
    via `org_capability`.
    """

    org_id: str | None = None
    org_role: str | None = None


def extract_org_context(claims: dict) -> OrgContext:
    """Pull active-organization context out of an already-verified Clerk JWT.

    Handles BOTH session-token claim shapes Clerk issues, since which one an
    instance emits depends on its (dashboard-configured) session-token version:

    - **v1** (the long-standing default): flat top-level `org_id` / `org_role`
      claims, present ONLY when the session has an active organization.
    - **v2** (`"v": 2`, newer): a nested `o` object — `o.id` (org id), `o.rol`
      (role). Preferred when present, mirroring Clerk's own SDK, which reads the
      nested object first and falls back to the flat claims.

    No org claims at all (personal workspace / Organizations not enabled) -> both
    `None`. This never trusts an unverified token: callers pass claims that already
    came out of `decode_clerk_token`'s JWKS-verified path.
    """
    nested = claims.get("o")
    if isinstance(nested, dict):
        org_id = nested.get("id")
        org_role = nested.get("rol")
    else:
        org_id = claims.get("org_id")
        org_role = claims.get("org_role")

    return OrgContext(
        org_id=org_id if isinstance(org_id, str) and org_id else None,
        org_role=org_role if isinstance(org_role, str) and org_role else None,
    )


def is_teacher_role(role: str | None) -> bool:
    """Whether a Clerk org role key grants the teacher/admin capability."""
    return role is not None and role in _TEACHER_ROLE_KEYS


def org_capability(role: str | None) -> str:
    """Map a Clerk org role key to our capability: `TEACHER` or `STUDENT`.

    Anything that isn't an explicit teacher/admin role (including `org:member`,
    an unknown custom role, or `None` for no active org) is `STUDENT` — the safe
    default, since teacher is the privileged capability.
    """
    return TEACHER if is_teacher_role(role) else STUDENT
