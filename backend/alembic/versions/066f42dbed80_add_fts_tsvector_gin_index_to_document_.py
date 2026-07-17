"""add FTS tsvector + GIN index to document_chunks

Revision ID: 066f42dbed80
Revises: 5ffe4bd447ff
Create Date: 2026-07-17 10:46:09.667942

"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy  # noqa: F401 — used when autogenerate emits pgvector column types
import sqlmodel  # noqa: F401 — used when autogenerate emits SQLModel column types

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "066f42dbed80"
down_revision: str | Sequence[str] | None = "5ffe4bd447ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Adds the lexical (full-text search) half of hybrid retrieval, in Postgres — NOT in
    Python (DECISIONS.md #4 explicitly avoids rebuilding relevance per query).

    - `text_search_vector` is a GENERATED ... STORED column, so Postgres computes the
      tsvector once per row on write (and, on this ALTER, for every EXISTING row too —
      no separate backfill needed). Regenerated automatically whenever `text` changes.
    - `to_tsvector('simple', text)` uses the `simple` config on purpose: the app is
      multilingual, and `simple` does no language-specific stemming or stopword removal,
      so it won't mangle non-English terms the way `english` would. The two-arg form
      with an explicit config is IMMUTABLE (required for a generated column) — the
      one-arg `to_tsvector(text)` depends on a session GUC and is only STABLE, so it
      can't be used here.
    - The GIN index is what makes the `@@` match a single indexed lookup rather than a
      per-query scan (the anti-pattern DECISIONS.md #4 calls out).

    Managed here in raw SQL (not on the SQLModel `DocumentChunk`) so the SQLite test
    engine — which has no tsvector type or `to_tsvector` — can still `create_all`. See
    `alembic/env.py`'s `include_object`, which keeps autogenerate from ever proposing to
    drop this Postgres-only column/index just because the ORM model doesn't declare it.
    """
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN text_search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_text_search_vector "
        "ON document_chunks USING GIN (text_search_vector)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_text_search_vector")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS text_search_vector")
