"""Persist the Feishu CAPA plan department independently of the CAPA ledger."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000054"
down_revision: str | None = "c9d400000053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "capa_plan_tracks",
        sa.Column("department", sa.String(length=255), nullable=True),
        schema="quality",
    )


def downgrade() -> None:
    op.drop_column("capa_plan_tracks", "department", schema="quality")
