"""Response shape for the documents API. No `DocumentCreate` — creation is a file
upload (multipart), not a JSON body, so FastAPI's `UploadFile` param covers it.
`owner_id` is deliberately absent here — never expose it over HTTP."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.modules.documents.models import DocumentStatus
from app.shared.datetime import UtcDatetime
from app.shared.language import DEFAULT_LANGUAGE


class DocumentRead(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    filename: str
    content_type: str
    status: DocumentStatus
    summary: str | None
    created_at: UtcDatetime


class DocumentPresignRequest(BaseModel):
    """Ask for a presigned direct-to-R2 upload URL. Carries only metadata (never the
    bytes) — the file itself goes straight from the browser to R2, so a large file
    never has to traverse the backend function (bypassing Vercel's ~4.5 MB body cap).
    `content_type` must be one StudyMate can parse. The uploader's UI locale is sent
    later, at confirm (where the row is actually created), not here."""

    filename: str
    content_type: str


class DocumentPresignResponse(BaseModel):
    """The presigned upload URL plus the ids the client needs to `PUT` the file and then
    call confirm. `object_key` is returned for transparency/debugging; the confirm step
    re-derives it server-side from `owner_id`+`document_id`+`filename` and never trusts a
    client-supplied key."""

    document_id: uuid.UUID
    object_key: str
    upload_url: str


class DocumentConfirmRequest(BaseModel):
    """Sent after the browser's direct `PUT` to R2 succeeds. The same metadata as the
    presign request — used to re-derive the object key, enforce the size limit (via a
    HEAD on the uploaded object), and create the `Document` row. Creating the row here
    (not at presign) means an abandoned/failed upload never leaves a stuck `pending`
    row."""

    filename: str
    content_type: str
    language: str = DEFAULT_LANGUAGE
