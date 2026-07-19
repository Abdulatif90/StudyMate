"""Subject — a student's top-level container for uploaded materials.

`owner_id` is the Clerk user id (JWT `sub` claim). A subject is either:

- **Private** (`org_id is None`): scoped to `owner_id` exactly as it always has been —
  one student never sees another's private subjects.
- **Org-owned / read-shared** (`org_id` set to a Clerk organization id, Phase 5
  increment 2): still `owner_id`-owned, but readable by any member whose *active*
  organization is that org, and writable by that org's teachers/admins (or the owner).

Authorization for both cases lives in `service.py` (`can_read_subject` /
`can_write_subject` and the `require_readable_subject` / `require_writable_subject`
pair) — the single source of truth every read/write path routes through.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Subject(SQLModel, table=True):
    __tablename__ = "subjects"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: str = Field(index=True)
    # NULL = private to owner_id (unchanged legacy behavior). Set = the Clerk org id
    # that read-shares this subject with its members. Indexed because listing an org's
    # subjects filters on it on the hot path.
    org_id: str | None = Field(default=None, index=True)
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
