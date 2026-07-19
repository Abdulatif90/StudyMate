"""add org_plans table + Plan.TEAM (Phase 5 team billing)

Revision ID: 6c9f0c767feb
Revises: b2c3d4e5f6a7
Create Date: 2026-07-20 06:10:56.044443

"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy  # noqa: F401 — used when autogenerate emits pgvector column types
import sqlalchemy as sa
import sqlmodel  # noqa: F401 — used when autogenerate emits SQLModel column types
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c9f0c767feb"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The `plan` Postgres enum already exists (created with user_plans, migration
    # 48c8dee79a2c) with only free/pro/business. Adding Plan.TEAM means the EXISTING type
    # must gain the `team` value — a plain `CREATE TYPE` inside create_table below would
    # fail because the type already exists, and skipping it would leave the type without
    # `team`. So extend the existing type first (idempotent), then create org_plans
    # referencing it with create_type=False (do NOT re-emit CREATE TYPE). Since PG 12,
    # ALTER TYPE ... ADD VALUE is allowed inside a transaction as long as the new value
    # isn't *used* in the same transaction — we only reference the type here, never insert
    # `team`, so alembic's transactional DDL is fine.
    op.execute("ALTER TYPE plan ADD VALUE IF NOT EXISTS 'team'")

    # Reference the EXISTING `plan` type — `create_type=False` on postgresql.ENUM (the
    # canonical "reference, don't create" form; the generic sa.Enum ignores the flag inside
    # create_table and re-emits CREATE TYPE, which fails since the type already exists).
    plan_enum = postgresql.ENUM(name="plan", create_type=False)

    op.create_table(
        "org_plans",
        sa.Column("org_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("plan", plan_enum, nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("org_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("org_plans")

    # The `team` enum value is deliberately NOT removed: Postgres can't drop a single enum
    # value, and `user_plans` still uses the same `plan` type. The `plan` type itself is
    # also kept (user_plans depends on it). Dropping org_plans is enough to reverse this
    # migration; a re-upgrade's ADD VALUE IF NOT EXISTS is a no-op when `team` is present.
