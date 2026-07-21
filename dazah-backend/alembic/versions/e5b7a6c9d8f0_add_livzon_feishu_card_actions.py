"""add livzon feishu card actions

Revision ID: e5b7a6c9d8f0
Revises: 4d8f1a6c2b7e
Create Date: 2026-07-03 00:00:02.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5b7a6c9d8f0"
down_revision: str | None = "4d8f1a6c2b7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")
    op.add_column(
        "feishu_configs",
        sa.Column(
            "card_callback_verification_token",
            sa.String(length=512),
            nullable=True,
            comment="飞书卡片回调 Verification Token",
        ),
        schema="identity",
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "encrypted_card_callback_encrypt_key",
            sa.String(length=1024),
            nullable=True,
            comment="加密后的飞书卡片回调 Encrypt Key",
        ),
        schema="identity",
    )
    op.create_table(
        "feishu_card_actions",
        sa.Column(
            "message_id",
            sa.String(length=128),
            nullable=True,
            comment="飞书消息 ID",
        ),
        sa.Column(
            "card_id",
            sa.String(length=128),
            nullable=True,
            comment="飞书卡片 ID",
        ),
        sa.Column(
            "local_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="本地收件人用户 ID",
        ),
        sa.Column(
            "recipient_open_id",
            sa.String(length=128),
            nullable=True,
            comment="收件人 open_id",
        ),
        sa.Column(
            "business_ref",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="业务引用摘要",
        ),
        sa.Column(
            "action_key",
            sa.String(length=64),
            nullable=False,
            comment="动作 key",
        ),
        sa.Column(
            "action_label",
            sa.String(length=100),
            nullable=False,
            comment="动作展示名称",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
            comment="pending/processed/expired/rejected",
        ),
        sa.Column(
            "clicked_open_id",
            sa.String(length=128),
            nullable=True,
            comment="点击人 open_id",
        ),
        sa.Column(
            "callback_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="回调摘要，不保存完整敏感 payload",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="动作过期时间",
        ),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="处理时间",
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
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_card_actions_action_key"),
        "feishu_card_actions",
        ["action_key"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_card_actions_card_id"),
        "feishu_card_actions",
        ["card_id"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_card_actions_local_user_id"),
        "feishu_card_actions",
        ["local_user_id"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_card_actions_message_id"),
        "feishu_card_actions",
        ["message_id"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_card_actions_recipient_open_id"),
        "feishu_card_actions",
        ["recipient_open_id"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        op.f("ix_identity_feishu_card_actions_status"),
        "feishu_card_actions",
        ["status"],
        unique=False,
        schema="identity",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_identity_feishu_card_actions_status"),
        table_name="feishu_card_actions",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_card_actions_recipient_open_id"),
        table_name="feishu_card_actions",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_card_actions_message_id"),
        table_name="feishu_card_actions",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_card_actions_local_user_id"),
        table_name="feishu_card_actions",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_card_actions_card_id"),
        table_name="feishu_card_actions",
        schema="identity",
    )
    op.drop_index(
        op.f("ix_identity_feishu_card_actions_action_key"),
        table_name="feishu_card_actions",
        schema="identity",
    )
    op.drop_table("feishu_card_actions", schema="identity")
    op.drop_column(
        "feishu_configs",
        "encrypted_card_callback_encrypt_key",
        schema="identity",
    )
    op.drop_column(
        "feishu_configs",
        "card_callback_verification_token",
        schema="identity",
    )
