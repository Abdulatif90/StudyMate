"""Tests for app.core.auth — Clerk JWT verification against a local RSA key.

No network calls: we generate a throwaway RSA keypair, sign a token
ourselves, and hand `decode_clerk_token` a fake JWKS client, so this never
needs Clerk's real JWKS endpoint.
"""

from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.core import auth

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_ISSUER = "https://test.clerk.accounts.dev"


def _make_token(**claims) -> str:
    return jwt.encode(claims, _private_key, algorithm="RS256", headers={"kid": "test-key"})


class _FakeJwksClient:
    def get_signing_key_from_kid(self, kid: str):
        assert kid == "test-key"
        return SimpleNamespace(key=_public_key)


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(clerk_issuer=_ISSUER))


def test_decode_clerk_token_returns_claims_for_valid_token():
    token = _make_token(sub="user_123", iss=_ISSUER)
    claims = auth.decode_clerk_token(token, _FakeJwksClient())
    assert claims["sub"] == "user_123"


def test_decode_clerk_token_rejects_wrong_issuer():
    token = _make_token(sub="user_123", iss="https://someone-else.clerk.accounts.dev")
    with pytest.raises(jwt.InvalidIssuerError):
        auth.decode_clerk_token(token, _FakeJwksClient())


def test_get_current_user_id_returns_sub_for_valid_token():
    token = _make_token(sub="user_123", iss=_ISSUER)
    credentials = SimpleNamespace(credentials=token)
    user_id = auth.get_current_user_id(credentials=credentials, jwks_client=_FakeJwksClient())
    assert user_id == "user_123"


def test_get_current_user_id_rejects_missing_credentials():
    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user_id(credentials=None, jwks_client=_FakeJwksClient())
    assert exc_info.value.status_code == 401


def test_get_current_user_id_rejects_invalid_token():
    token = _make_token(sub="user_123", iss="https://wrong-issuer")
    credentials = SimpleNamespace(credentials=token)
    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user_id(credentials=credentials, jwks_client=_FakeJwksClient())
    assert exc_info.value.status_code == 401
