"""Subject — a student's top-level container for uploaded materials.

`owner_id` is the Clerk user id (JWT `sub` claim); every query in
`service.py` filters by it, so one student never sees another's subjects.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Subject(SQLModel, table=True):
    __tablename__ = "subjects"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: str = Field(index=True)
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
