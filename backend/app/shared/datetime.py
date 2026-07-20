"""A single, DRY datetime serializer for the API's JSON output boundary.

Why this exists: models store timestamps as `datetime.now(UTC)` (tz-aware UTC), but the
DB columns are `TIMESTAMP WITHOUT TIME ZONE`, so values round-trip **naive**. A naive
datetime serializes with no timezone marker (e.g. `"2026-07-20T13:00:00"`), and the
frontend's `new Date(str)` then reads a tz-less string as *local* time — shifting every
timestamp by the viewer's UTC offset ("Overdue" on a fresh assignment, wrong quiz times).

`UtcDatetime` fixes that at the OUTPUT boundary only: a naive value is assumed to be UTC
(which it is — everything is written with `datetime.now(UTC)`) and re-tagged, so the JSON
always carries an explicit UTC marker (`+00:00` / `Z`). Server-side datetime *comparison*
logic (SM-2 scheduling, billing day math) keeps using the stored values untouched — this
only changes how a datetime is rendered into JSON. Using an annotated type instead of a
DB migration keeps the columns as-is (no Alembic migration needed).

Apply it to every `datetime` field in a Read/response schema:

    from app.shared.datetime import UtcDatetime

    class FooRead(BaseModel):
        created_at: UtcDatetime
        due_at: UtcDatetime | None = None
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def _to_utc_isoformat(dt: datetime) -> str:
    """Emit `dt` as an ISO-8601 string carrying an explicit UTC offset.

    A naive datetime is assumed to be UTC (all stored values are written as
    `datetime.now(UTC)` but round-trip naive); an already-aware datetime is left in its
    own zone. Either way the result has an unambiguous timezone marker, so the frontend
    never misreads it as local time.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


#: A `datetime` that always serializes to JSON with an explicit UTC/timezone offset.
#: Behaves exactly like `datetime` for validation and Python-side use; only the
#: JSON-output representation changes.
UtcDatetime = Annotated[datetime, PlainSerializer(_to_utc_isoformat, return_type=str)]
