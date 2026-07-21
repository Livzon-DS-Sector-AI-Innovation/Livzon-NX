"""add identity feishu user tokens

Revision ID: b6e4d2f9a1c3
Revises: a7c100000020
Create Date: 2026-07-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b6e4d2f9a1c3"
down_revision: str | None = "a7c100000020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")
    op.create_table(
        "feishu_user_tokens",
        sa.Column(
            "local_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="本地平台用户 ID",
        ),
        sa.Column(
            "app_id",
            sa.String(length=128),
            nullable=False,
            comment="飞书自建应用 App ID",
        ),
        sa.Column(
            "feishu_open_id",
            sa.String(length=128),
            nullable=True,
            comment="飞书 open_id",
        ),
        sa.Column(
            "feishu_user_id",
            sa.String(length=128),
            nullable=True,
            comment="飞书 user_id",
        ),
        sa.Column(
            "feishu_union_id",
            sa.String(length=128),
            nullable=True,
            comment="飞书 union_id",
        ),
        sa.Column(
            "tenant_key",
            sa.String(length=128),
            nullable=True,
            comment="飞书租户标识",
        ),
        sa.Column(
            "encrypted_user_access_token",
            sa.Text(),
            nullable=False,
            comment="加密后的 user_access_token",
        ),
        sa.Column(
            "encrypted_refresh_token",
            sa.Text(),
            nullable=True,
            comment="加密后的 refresh_token",
        ),
        sa.Column(
            "token_type",
            sa.String(length=32),
            nullable=True,
            comment="Token 类型",
        ),
        sa.Column("scope", sa.Text(), nullable=True, comment="授权范围"),
        sa.Column(
            "access_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="user_access_token 过期时间",
        ),
        sa.Column(
            "refresh_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="refresh_token 过期时间",
        ),
        sa.Column(
            "last_refreshed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近刷新时间",
        ),
        sa.Column("last_error", sa.Text(), nullable=True, comment="最近刷新错误"),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
            comment="active/revoked/error",
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "local_user_id",
            "app_id",
            name="uq_identity_feishu_user_tokens_user_app",
        ),
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_user_tokens_app_id"),
        "feishu_user_tokens",
        ["app_id"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_user_tokens_feishu_open_id"),
        "feishu_user_tokens",
        ["feishu_open_id"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_user_tokens_feishu_user_id"),
        "feishu_user_tokens",
        ["feishu_user_id"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_user_tokens_local_user_id"),
        "feishu_user_tokens",
        ["local_user_id"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_user_tokens_status"),
        "feishu_user_tokens",
        ["status"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_user_tokens_tenant_key"),
        "feishu_user_tokens",
        ["tenant_key"],
        unique=False,
        schema="identity",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_identity_feishu_user_tokens_tenant_key"),
        table_name="feishu_user_tokens",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_user_tokens_status"),
        table_name="feishu_user_tokens",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_user_tokens_local_user_id"),
        table_name="feishu_user_tokens",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_user_tokens_feishu_user_id"),
        table_name="feishu_user_tokens",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_user_tokens_feishu_open_id"),
        table_name="feishu_user_tokens",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_user_tokens_app_id"),
        table_name="feishu_user_tokens",
        schema="identity",
    )
    op.drop_table("feishu_user_tokens", schema="identity")
