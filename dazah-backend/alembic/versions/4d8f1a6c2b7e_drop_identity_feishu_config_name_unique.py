"""drop identity feishu config name unique

Revision ID: 4d8f1a6c2b7e
Revises: 7c4f2a9b1d6e
Create Date: 2026-07-03 00:00:01.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "4d8f1a6c2b7e"
down_revision: str | None = "7c4f2a9b1d6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_identity_feishu_configs_name",
        "feishu_configs",
        schema="identity",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_identity_feishu_configs_name",
        "feishu_configs",
        ["config_name"],
        schema="identity",
    )
