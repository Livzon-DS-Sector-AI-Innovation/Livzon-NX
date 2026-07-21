"""add quality feishu field mappings

Revision ID: a7c100000017
Revises: a7c100000016
Create Date: 2026-07-04 00:18:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000017"
down_revision: str | None = "a7c100000016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "quality"


def upgrade() -> None:
    op.add_column(
        "quality_feishu_entity_settings",
        sa.Column("field_mappings", sa.JSON(), nullable=True),
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    op.drop_column(
        "quality_feishu_entity_settings",
        "field_mappings",
        schema=SCHEMA_NAME,
    )