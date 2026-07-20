"""Cloudflare R2 (S3-compatible) file storage for uploaded documents.

One boto3 S3 client, built once and shared — same "build once" pattern as
`inngest_client.py`. R2 speaks the S3 API at
`https://<account_id>.r2.cloudflarestorage.com`.

Missing R2 credentials is a deployment mistake: `_get_client()` raises a bare
`RuntimeError` at the point of use (same pattern as db.py/embedding.py/llm.py/
inngest_client) rather than failing obscurely deep inside boto3.

Keys are owner-scoped (`build_object_key`) so one owner's document can never resolve
to another owner's object — but callers must still verify DB-level ownership before
touching R2 (the key is derived from ids the caller already owns; it isn't itself an
authorization check).
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class R2ConfigError(RuntimeError):
    """Raised when R2 credentials aren't fully configured."""


@lru_cache
def _get_client() -> S3Client:
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("R2_ACCOUNT_ID", settings.r2_account_id),
            ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
            ("R2_BUCKET_NAME", settings.r2_bucket_name),
        )
        if not value
    ]
    if missing:
        raise R2ConfigError(
            f"R2 storage is not configured — missing {', '.join(missing)}. "
            "Add them to backend/.env — see backend/.env.example."
        )
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        # R2 only supports the "auto" region; the signer still needs *a* region set.
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def _bucket() -> str:
    # Presence already enforced by _get_client(); read it back for the API calls.
    return get_settings().r2_bucket_name  # type: ignore[return-value]


def build_object_key(owner_id: str, document_id: uuid.UUID, filename: str) -> str:
    """Owner-scoped object key: `{owner_id}/{document_id}/{filename}`. The owner_id
    prefix keeps one tenant's objects namespaced from another's; document_id makes the
    key unique per upload even for a repeated filename."""
    return f"{owner_id}/{document_id}/{filename}"


def put_object(key: str, data: bytes, content_type: str) -> None:
    _get_client().put_object(Bucket=_bucket(), Key=key, Body=data, ContentType=content_type)


def get_object(key: str) -> bytes:
    response = _get_client().get_object(Bucket=_bucket(), Key=key)
    return response["Body"].read()


def generate_presigned_put_url(key: str, content_type: str, expires_in: int) -> str:
    """A short-lived presigned S3/R2 `PutObject` URL the browser can `PUT` a file to
    directly — bypassing the backend function entirely (and thus Vercel's ~4.5 MB
    serverless request-body cap; see docs/DEPLOYMENT.md §8 / RELEASE_CHECKLIST.md).

    The URL is signed for this exact `key` and `ContentType`, so the PUT MUST send a
    matching `Content-Type` header or R2 rejects the signature. `key` is owner-scoped
    (`build_object_key`), so a URL minted for one owner can never target another's
    namespace. Size is NOT enforceable on a presigned PUT — the caller (confirm step)
    re-checks the real object size via `head_object_size` afterward.
    """
    return _get_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": _bucket(), "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )


def head_object_size(key: str) -> int | None:
    """The object's size in bytes via a `HEAD`, or `None` if it doesn't exist. Used by
    the confirm step to prove a presigned upload actually landed and to enforce the
    size limit the presigned PUT itself couldn't. A genuine 404/NoSuchKey is the
    expected "not uploaded" signal (→ `None`); any other error propagates (a real
    infra/credentials problem should fail loudly, not masquerade as 'not uploaded')."""
    try:
        response = _get_client().head_object(Bucket=_bucket(), Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise
    return response["ContentLength"]


def delete_object(key: str) -> None:
    # S3/R2 DeleteObject is idempotent — deleting a missing key is a no-op, not an error.
    _get_client().delete_object(Bucket=_bucket(), Key=key)
