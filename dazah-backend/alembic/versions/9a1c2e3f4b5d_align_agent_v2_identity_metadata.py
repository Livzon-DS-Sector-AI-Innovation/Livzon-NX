"""align Agent V2 identity metadata with SQLAlchemy models

Revision ID: 9a1c2e3f4b5d
Revises: 4e7b9c1d2f30
Create Date: 2026-07-31 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9a1c2e3f4b5d"
down_revision: str | None = "4e7b9c1d2f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_identity_external_identity_bindings_local_user_id",
        "external_identity_bindings",
        ["local_user_id"],
        unique=False,
        schema="identity",
    )
    op.alter_column(
        "feishu_configs",
        "tenant_id",
        existing_type=sa.String(length=128),
        comment="Gateway 可信租户标识",
        existing_nullable=False,
        existing_server_default="default",
        schema="identity",
    )
    op.alter_column(
        "feishu_configs",
        "gateway_enabled",
        existing_type=sa.Boolean(),
        comment="是否启用 Hermes Feishu Gateway",
        existing_nullable=False,
        existing_server_default=sa.text("true"),
        schema="identity",
    )
    op.alter_column(
        "feishu_configs",
        "config_version",
        existing_type=sa.Integer(),
        comment="Gateway 配置单调递增版本",
        existing_nullable=False,
        existing_server_default="1",
        schema="identity",
    )


def downgrade() -> None:
    op.alter_column(
        "feishu_configs",
        "config_version",
        existing_type=sa.Integer(),
        comment=None,
        existing_nullable=False,
        existing_server_default="1",
        schema="identity",
    )
    op.alter_column(
        "feishu_configs",
        "gateway_enabled",
        existing_type=sa.Boolean(),
        comment=None,
        existing_nullable=False,
        existing_server_default=sa.text("true"),
        schema="identity",
    )
    op.alter_column(
        "feishu_configs",
        "tenant_id",
        existing_type=sa.String(length=128),
        comment=None,
        existing_nullable=False,
        existing_server_default="default",
        schema="identity",
    )
    op.drop_index(
        "ix_identity_external_identity_bindings_local_user_id",
        table_name="external_identity_bindings",
        schema="identity",
    )
