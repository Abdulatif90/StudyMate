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
    # NULL for a private subject; the Clerk org id for an org-owned (read-shared) one.
    # The frontend uses this to badge a subject "Shared" and to decide whether to show
    # write actions (a member of the owning org who isn't a teacher can't write) — the
    # backend 403 is the real guard, this is the UX signal. `owner_id` is deliberately
    # NOT exposed (never was) — it isn't needed client-side and shouldn't leak.
    org_id: str | None = None
    created_at: datetime
