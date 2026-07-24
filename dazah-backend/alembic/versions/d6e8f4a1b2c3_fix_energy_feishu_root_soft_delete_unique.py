"""fix energy Feishu root soft-delete uniqueness

Revision ID: d6e8f4a1b2c3
Revises: c4f7a2d9e631
Create Date: 2026-07-23 14:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6e8f4a1b2c3"
down_revision: str | None = "c4f7a2d9e631"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_energy_feishu_source_root",
        "feishu_source_roots",
        schema="energy",
        type_="unique",
    )
    op.create_index(
        "uq_energy_feishu_source_root_active",
        "feishu_source_roots",
        ["config_id", "source_type", "root_token"],
        unique=True,
        schema="energy",
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_energy_feishu_source_root_active",
        table_name="feishu_source_roots",
        schema="energy",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_unique_constraint(
        "uq_energy_feishu_source_root",
        "feishu_source_roots",
        ["config_id", "source_type", "root_token", "is_deleted"],
        schema="energy",
    )
