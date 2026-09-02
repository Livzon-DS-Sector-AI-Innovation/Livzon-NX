"""hr training expand content fields

- training_ledgers: training_date/training_subject 改为 nullable;
  training_content VARCHAR(512)->VARCHAR(4096)
- training_evaluations: training_content VARCHAR(512)->VARCHAR(4096)
- plan_tracking_records: training_content VARCHAR(512)->VARCHAR(4096)
- esg_training_records: training_name VARCHAR(512)->VARCHAR(4096)

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema = "hr"

    # ─ training_ledgers ──
    op.alter_column(
        "training_ledgers",
        "training_date",
        existing_type=sa.Date(),
        nullable=True,
        schema=schema,
    )
    op.alter_column(
        "training_ledgers",
        "training_subject",
        existing_type=sa.String(256),
        nullable=True,
        schema=schema,
    )
    op.alter_column(
        "training_ledgers",
        "training_content",
        existing_type=sa.String(512),
        type_=sa.String(4096),
        existing_nullable=True,
        schema=schema,
    )

    # ─ training_evaluations ──
    op.alter_column(
        "training_evaluations",
        "training_content",
        existing_type=sa.String(512),
        type_=sa.String(4096),
        existing_nullable=True,
        schema=schema,
    )

    # ── plan_tracking_records ──
    op.alter_column(
        "plan_tracking_records",
        "training_content",
        existing_type=sa.String(512),
        type_=sa.String(4096),
        existing_nullable=True,
        schema=schema,
    )

    # ── esg_training_records ──
    op.alter_column(
        "esg_training_records",
        "training_name",
        existing_type=sa.String(512),
        type_=sa.String(4096),
        existing_nullable=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = "hr"

    op.alter_column(
        "esg_training_records",
        "training_name",
        existing_type=sa.String(4096),
        type_=sa.String(512),
        existing_nullable=False,
        schema=schema,
    )
    op.alter_column(
        "plan_tracking_records",
        "training_content",
        existing_type=sa.String(4096),
        type_=sa.String(512),
        existing_nullable=True,
        schema=schema,
    )
    op.alter_column(
        "training_evaluations",
        "training_content",
        existing_type=sa.String(4096),
        type_=sa.String(512),
        existing_nullable=True,
        schema=schema,
    )
    op.alter_column(
        "training_ledgers",
        "training_content",
        existing_type=sa.String(4096),
        type_=sa.String(512),
        existing_nullable=True,
        schema=schema,
    )
    op.alter_column(
        "training_ledgers",
        "training_subject",
        existing_type=sa.String(256),
        nullable=False,
        schema=schema,
    )
    op.alter_column(
        "training_ledgers",
        "training_date",
        existing_type=sa.Date(),
        nullable=False,
        schema=schema,
    )
