"""add fermentation source uniqueness

Revision ID: 45c37377e9a2
Revises: 1dedd1302f7e
Create Date: 2026-07-15 13:50:00.033912
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "45c37377e9a2"
down_revision: str | None = "1dedd1302f7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_fermentation_source_record",
        "fermentation_records",
        ["source", "source_record_id"],
        schema="production",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_fermentation_source_record",
        "fermentation_records",
        schema="production",
        type_="unique",
    )
