"""Tests for app.core.r2_client — the R2/S3 storage wrapper.

Offline tests mock boto3 / patch settings (no network). One live test round-trips a
real object through real R2 — marked `live` (deselected by default; run with
`pytest -m live`) and guarded with `skipif` on R2 not being configured, so
`pytest -m live` still skips cleanly where there's no R2.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from app.core import r2_client
from app.core.config import get_settings


def _clear_client_cache():
    r2_client._get_client.cache_clear()


def test_build_object_key_is_owner_scoped():
    document_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    key = r2_client.build_object_key("user_abc", document_id, "notes.txt")
    assert key == "user_abc/11111111-1111-1111-1111-111111111111/notes.txt"


def test_build_object_key_differs_by_owner():
    document_id = uuid.uuid4()
    a = r2_client.build_object_key("owner_a", document_id, "f.txt")
    b = r2_client.build_object_key("owner_b", document_id, "f.txt")
    # same document_id + filename must not collide across owners
    assert a != b
    assert a.startswith("owner_a/")
    assert b.startswith("owner_b/")


@pytest.mark.parametrize(
    "settings_kwargs",
    [
        {
            "r2_account_id": None,
            "r2_access_key_id": "k",
            "r2_secret_access_key": "s",
            "r2_bucket_name": "b",
        },
        {
            "r2_account_id": "a",
            "r2_access_key_id": None,
            "r2_secret_access_key": "s",
            "r2_bucket_name": "b",
        },
        {
            "r2_account_id": "a",
            "r2_access_key_id": "k",
            "r2_secret_access_key": None,
            "r2_bucket_name": "b",
        },
        {
            "r2_account_id": "a",
            "r2_access_key_id": "k",
            "r2_secret_access_key": "s",
            "r2_bucket_name": None,
        },
    ],
)
def test_get_client_raises_when_any_credential_missing(monkeypatch, settings_kwargs):
    _clear_client_cache()
    monkeypatch.setattr(r2_client, "get_settings", lambda: SimpleNamespace(**settings_kwargs))
    with pytest.raises(r2_client.R2ConfigError):
        r2_client._get_client()
    _clear_client_cache()


def test_put_get_delete_call_boto3_with_bucket_and_key(monkeypatch):
    _clear_client_cache()
    fake_body = SimpleNamespace(read=lambda: b"hello")
    fake_client = SimpleNamespace(
        put_object=lambda **kw: kw,
        get_object=lambda **kw: {"Body": fake_body},
        delete_object=lambda **kw: kw,
    )
    calls = {}
    fake_client.put_object = lambda **kw: calls.setdefault("put", kw)
    fake_client.delete_object = lambda **kw: calls.setdefault("delete", kw)
    monkeypatch.setattr(r2_client, "_get_client", lambda: fake_client)
    monkeypatch.setattr(
        r2_client, "get_settings", lambda: SimpleNamespace(r2_bucket_name="my-bucket")
    )

    r2_client.put_object("owner/doc/f.txt", b"hello", "text/plain")
    assert calls["put"]["Bucket"] == "my-bucket"
    assert calls["put"]["Key"] == "owner/doc/f.txt"
    assert calls["put"]["Body"] == b"hello"
    assert calls["put"]["ContentType"] == "text/plain"

    assert r2_client.get_object("owner/doc/f.txt") == b"hello"

    r2_client.delete_object("owner/doc/f.txt")
    assert calls["delete"]["Bucket"] == "my-bucket"
    assert calls["delete"]["Key"] == "owner/doc/f.txt"


_HAS_R2 = all(
    (
        get_settings().r2_account_id,
        get_settings().r2_access_key_id,
        get_settings().r2_secret_access_key,
        get_settings().r2_bucket_name,
    )
)


@pytest.mark.live
@pytest.mark.skipif(not _HAS_R2, reason="requires real R2 credentials in .env")
def test_r2_round_trip_against_real_bucket():
    _clear_client_cache()
    key = f"__test__/{uuid.uuid4()}/roundtrip.txt"
    payload = b"StudyMate R2 round-trip test payload"
    try:
        r2_client.put_object(key, payload, "text/plain")
        assert r2_client.get_object(key) == payload
    finally:
        r2_client.delete_object(key)
        # confirm it's gone — a subsequent get should now raise NoSuchKey
        with pytest.raises(ClientError):
            r2_client.get_object(key)
    _clear_client_cache()
