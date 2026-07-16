"""Response shape for the documents API. No `DocumentCreate` — creation is a file
upload (multipart), not a JSON body, so FastAPI's `UploadFile` param covers it.
`owner_id` is deliberately absent here — never expose it over HTTP."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.modules.documents.models import DocumentStatus


class DocumentRead(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    filename: str
    content_type: str
    status: DocumentStatus
    summary: str | None
    created_at: datetime
