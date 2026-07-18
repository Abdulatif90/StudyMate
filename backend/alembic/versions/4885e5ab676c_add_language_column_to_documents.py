"""add language column to documents

Revision ID: 4885e5ab676c
Revises: 48c8dee79a2c
Create Date: 2026-07-19 04:08:10.853240

"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy  # noqa: F401 — used when autogenerate emits pgvector column types
import sqlalchemy as sa
import sqlmodel  # noqa: F401 — used when autogenerate emits SQLModel column types

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4885e5ab676c"
down_revision: str | Sequence[str] | None = "48c8dee79a2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default backfills existing rows (English, same as the Python-side
    # default in Document.language) so this NOT NULL column can land on a table that
    # already has data; dropped right after so future inserts must go through the
    # model's Python-side default instead of relying on the DB default.
    op.add_column(
        "documents",
        sa.Column(
            "language", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="en"
        ),
    )
    op.alter_column("documents", "language", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("documents", "language")
