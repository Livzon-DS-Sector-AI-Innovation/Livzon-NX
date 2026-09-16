"""Add explicit workshop ownership without guessing historical assignments."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000039"
down_revision: str | None = "c9d400000038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "batches",
        sa.Column(
            "workshop_code",
            sa.String(32),
            nullable=True,
            comment="所属车间编码；空值表示待确认",
        ),
        schema="production",
    )
    op.create_index(
        "ix_production_batches_workshop_code",
        "batches",
        ["workshop_code"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_production_batches_workshop_code", table_name="batches", schema="production"
    )
    op.drop_column("batches", "workshop_code", schema="production")
