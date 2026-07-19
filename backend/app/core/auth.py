"""Clerk authentication: verifies the JWT Clerk attaches to each request.

Clerk signs session tokens with RS256; the public keys are published at a
JWKS (JSON Web Key Set) URL. We fetch them (cached by `PyJWKClient`), verify
the JWT's signature and issuer, and trust its `sub` claim as the user id.
"""

from __future__ import annotations

from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import get_settings
from app.core.org import OrgContext, extract_org_context, is_teacher_role

_bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_jwks_client() -> PyJWKClient:
    """Build (once) the client that fetches + caches Clerk's public keys."""
    settings = get_settings()
    if not settings.clerk_jwks_url:
        raise RuntimeError(
            "CLERK_JWKS_URL is not set. Add it to backend/.env — see backend/.env.example."
        )
    return PyJWKClient(settings.clerk_jwks_url)


def decode_clerk_token(token: str, jwks_client: PyJWKClient) -> dict:
    """Verify a Clerk-issued JWT and return its claims.

    Raises `jwt.PyJWTError` (or a subclass) on any failure — expired,
    wrong signature, wrong issuer. Callers turn that into an HTTP 401.
    """
    settings = get_settings()
    signing_key = jwks_client.get_signing_key(jwt.get_unverified_header(token)["kid"])
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=settings.clerk_issuer,
        options={"verify_aud": False},
    )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    jwks_client: PyJWKClient = Depends(get_jwks_client),
) -> str:
    """FastAPI dependency: the authenticated caller's Clerk user id.

    Use as `user_id: str = Depends(get_current_user_id)` on any route that
    needs a signed-in user — every tenant-scoped query filters by this id.
    """
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        claims = decode_clerk_token(credentials.credentials, jwks_client)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    return claims["sub"]


def get_org_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    jwks_client: PyJWKClient = Depends(get_jwks_client),
) -> OrgContext:
    """FastAPI dependency: the caller's active Clerk organization context.

    Reads org id/role from the SAME JWKS-verified session token as
    `get_current_user_id` (no second verification path, no unverified token) and
    returns an `OrgContext`. A user with no active organization (personal
    workspace, or Organizations not enabled on the instance) yields
    `OrgContext(None, None)` — a valid state, not a 401. Auth failures
    (missing/invalid token) still raise 401, exactly as `get_current_user_id` does.

    Foundation for Phase 5: nothing is org-scoped by this yet — the next increment
    (content org-scoping) builds on this dependency.
    """
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        claims = decode_clerk_token(credentials.credentials, jwks_client)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    return extract_org_context(claims)


def require_teacher(org: OrgContext = Depends(get_org_context)) -> OrgContext:
    """FastAPI guard dependency: caller must hold the teacher/admin org role.

    Raises 403 when there is no active organization or the active role isn't the
    teacher/admin one (see `app.core.org.is_teacher_role`). A thin capability check
    only — no content is protected by it this increment; it's the guard the next
    increment (teacher-only actions) will attach to routes.
    """
    if not is_teacher_role(org.org_role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Requires an organization teacher/admin role",
        )
    return org
