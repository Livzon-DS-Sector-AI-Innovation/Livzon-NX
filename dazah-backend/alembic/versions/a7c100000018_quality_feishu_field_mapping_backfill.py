"""backfill quality feishu field mappings

Revision ID: a7c100000018
Revises: a7c100000017
Create Date: 2026-07-04 00:35:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000018"
down_revision: str | None = "a7c100000017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE quality.quality_feishu_entity_settings "
        "SET field_mappings = '[]'::json "
        "WHERE field_mappings IS NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE quality.quality_feishu_entity_settings "
        "SET field_mappings = NULL "
        "WHERE field_mappings = '[]'::json"
    )