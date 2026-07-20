"""add active_subject_id to telegram_links (Phase 7 — Telegram own-materials answering)

Revision ID: c1d2e3f4a5b6
Revises: 06650625fb97
Create Date: 2026-07-20 15:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy  # noqa: F401 — used when autogenerate emits pgvector column types
import sqlalchemy as sa
import sqlmodel  # noqa: F401 — used when autogenerate emits SQLModel column types

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "06650625fb97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable, no FK constraint on purpose (plain-column style; a subject delete must not
    # need to know about telegram_links — a dangling value is handled at read time).
    op.add_column(
        "telegram_links",
        sa.Column("active_subject_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("telegram_links", "active_subject_id")
