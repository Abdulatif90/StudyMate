"""Request/response shapes for the subjects API — kept separate from `models.Subject`
so the DB schema (owner_id, table structure) is never accidentally exposed over HTTP."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SubjectRead(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
