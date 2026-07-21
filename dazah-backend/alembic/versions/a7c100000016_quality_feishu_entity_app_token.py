"""add quality feishu entity app token

Revision ID: a7c100000016
Revises: a7c100000015
Create Date: 2026-07-03 23:58:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000016"
down_revision: str | None = "a7c100000015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCHEMA_NAME = "quality"


def upgrade() -> None:
    op.add_column(
        "quality_feishu_entity_settings",
        sa.Column("app_token", sa.String(length=100), nullable=True),
        schema=SCHEMA_NAME,
    )
    op.alter_column(
        "quality_feishu_app_settings",
        "app_token",
        existing_type=sa.String(length=100),
        nullable=True,
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    op.alter_column(
        "quality_feishu_app_settings",
        "app_token",
        existing_type=sa.String(length=100),
        nullable=False,
        schema=SCHEMA_NAME,
    )
    op.drop_column(
        "quality_feishu_entity_settings",
        "app_token",
        schema=SCHEMA_NAME,
    )