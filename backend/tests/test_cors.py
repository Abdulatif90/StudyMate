"""Tests for CORS: the frontend (localhost:3000) can call the API cross-origin;
an arbitrary origin can't."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app

client = TestClient(app)


def test_cors_origin_list_splits_comma_separated_string():
    settings = Settings(cors_origins="http://localhost:3000, https://app.example.com")
    assert settings.cors_origin_list == ["http://localhost:3000", "https://app.example.com"]


def test_allowed_origin_gets_cors_header():
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_disallowed_origin_gets_no_cors_header():
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers
