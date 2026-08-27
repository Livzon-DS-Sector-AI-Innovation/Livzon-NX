"""add quality import/export fields to CAPA and Deviation

Revision ID: a7c100000001
Revises: f1a2b3c4d5e6
Create Date: 2026-06-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000001"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CAPA table: add department and affected_product
    op.add_column(
        "capas",
        sa.Column("department", sa.String(255), nullable=True),
        schema="quality",
    )
    op.add_column(
        "capas",
        sa.Column("affected_product", sa.String(255), nullable=True),
        schema="quality",
    )

    # Deviation table: add new fields
    op.add_column(
        "deviations",
        sa.Column("has_occurred_before", sa.Boolean(), nullable=True),
        schema="quality",
    )
    op.add_column(
        "deviations",
        sa.Column("material_disposition", sa.Text(), nullable=True),
        schema="quality",
    )
    op.add_column(
        "deviations",
        sa.Column("corrective_actions", sa.Text(), nullable=True),
        schema="quality",
    )
    op.add_column(
        "deviations",
        sa.Column("root_cause_analysis", sa.Text(), nullable=True),
        schema="quality",
    )
    op.add_column(
        "deviations",
        sa.Column(
            "investigation_completed_at", sa.DateTime(timezone=True), nullable=True
        ),
        schema="quality",
    )


def downgrade() -> None:
    # Deviation table: drop new fields
    op.drop_column("deviations", "investigation_completed_at", schema="quality")
    op.drop_column("deviations", "root_cause_analysis", schema="quality")
    op.drop_column("deviations", "corrective_actions", schema="quality")
    op.drop_column("deviations", "material_disposition", schema="quality")
    op.drop_column("deviations", "has_occurred_before", schema="quality")

    # CAPA table: drop new fields
    op.drop_column("capas", "affected_product", schema="quality")
    op.drop_column("capas", "department", schema="quality")
