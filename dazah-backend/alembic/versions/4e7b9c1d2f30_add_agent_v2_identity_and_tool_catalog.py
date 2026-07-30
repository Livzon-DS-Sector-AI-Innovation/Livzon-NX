"""add Agent V2 external identity bindings and tool catalog

Revision ID: 4e7b9c1d2f30
Revises: fbffa92623e9
Create Date: 2026-07-30 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4e7b9c1d2f30"
down_revision: str | None = "fbffa92623e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.add_column(
        "feishu_configs",
        sa.Column(
            "tenant_id",
            sa.String(length=128),
            server_default="default",
            nullable=False,
        ),
        schema="identity",
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "gateway_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        schema="identity",
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "config_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        schema="identity",
    )
    op.drop_column(
        "feishu_configs",
        "card_callback_verification_token",
        schema="identity",
    )
    op.drop_column(
        "feishu_configs",
        "encrypted_card_callback_encrypt_key",
        schema="identity",
    )
    op.drop_table("feishu_card_actions", schema="identity")
    op.create_table(
        "external_identity_bindings",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("app_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("external_user_id", sa.String(length=128), nullable=True),
        sa.Column("external_open_id", sa.String(length=128), nullable=True),
        sa.Column("external_union_id", sa.String(length=128), nullable=True),
        sa.Column(
            "local_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "binding_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *_base_columns(),
        sa.CheckConstraint(
            "external_user_id IS NOT NULL OR external_open_id IS NOT NULL "
            "OR external_union_id IS NOT NULL",
            name="ck_identity_external_bindings_identifier",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "platform",
            "app_fingerprint",
            "external_user_id",
            name="uq_identity_external_bindings_user_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "platform",
            "app_fingerprint",
            "external_open_id",
            name="uq_identity_external_bindings_open_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "platform",
            "app_fingerprint",
            "external_union_id",
            name="uq_identity_external_bindings_union_id",
        ),
        schema="identity",
        comment="外部应用身份到本地可信主体的绑定事实",
    )
    op.create_index(
        "ix_identity_external_bindings_local_user_id",
        "external_identity_bindings",
        ["local_user_id"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_external_bindings_local_status",
        "external_identity_bindings",
        ["local_user_id", "status"],
        schema="identity",
    )
    op.execute(
        """
        INSERT INTO identity.external_identity_bindings (
            id, tenant_id, platform, app_fingerprint,
            external_user_id, external_open_id, external_union_id,
            local_user_id, status, binding_metadata,
            created_at, updated_at, is_deleted
        )
        SELECT
            md5(u.id::text || ':' || c.app_id)::uuid,
            c.tenant_id,
            'feishu',
            c.app_id,
            u.feishu_user_id,
            u.feishu_open_id,
            u.feishu_union_id,
            u.id,
            CASE WHEN u.status = 'active' THEN 'active' ELSE 'disabled' END,
            '{"migration_source":"identity.users"}'::jsonb,
            now(), now(), false
        FROM identity.users AS u
        CROSS JOIN LATERAL (
            SELECT app_id, tenant_id
            FROM identity.feishu_configs
            WHERE is_active = true AND is_deleted = false
            ORDER BY updated_at DESC
            LIMIT 1
        ) AS c
        WHERE u.is_deleted = false
          AND (
              u.feishu_user_id IS NOT NULL
              OR u.feishu_open_id IS NOT NULL
              OR u.feishu_union_id IS NOT NULL
          )
        """
    )

    op.create_table(
        "agent_tool_catalog",
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=True),
        sa.Column("capability_version", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("write", sa.Boolean(), nullable=False),
        sa.Column("confirmation_required", sa.Boolean(), nullable=False),
        sa.Column(
            "admin_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("permission_key", sa.String(length=120), nullable=True),
        sa.Column(
            "input_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "output_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("idempotent", sa.Boolean(), nullable=False),
        sa.Column("metadata_hash", sa.String(length=64), nullable=False),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation", name="uq_core_agent_tool_catalog_operation"
        ),
        schema="core",
        comment="Agent 工具目录运行时事实源",
    )
    op.create_index(
        "ix_core_agent_tool_catalog_module_status",
        "agent_tool_catalog",
        ["module", "status"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_agent_tool_catalog_module_status",
        table_name="agent_tool_catalog",
        schema="core",
    )
    op.drop_table("agent_tool_catalog", schema="core")
    op.drop_index(
        "ix_identity_external_bindings_local_status",
        table_name="external_identity_bindings",
        schema="identity",
    )
    op.drop_index(
        "ix_identity_external_bindings_local_user_id",
        table_name="external_identity_bindings",
        schema="identity",
    )
    op.drop_table("external_identity_bindings", schema="identity")
    op.create_table(
        "feishu_card_actions",
        sa.Column("message_id", sa.String(length=128), nullable=True),
        sa.Column("card_id", sa.String(length=128), nullable=True),
        sa.Column(
            "local_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("recipient_open_id", sa.String(length=128), nullable=True),
        sa.Column(
            "business_ref",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("action_key", sa.String(length=64), nullable=False),
        sa.Column("action_label", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("clicked_open_id", sa.String(length=128), nullable=True),
        sa.Column(
            "callback_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema="identity",
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "encrypted_card_callback_encrypt_key",
            sa.String(length=1024),
            nullable=True,
        ),
        schema="identity",
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "card_callback_verification_token",
            sa.String(length=512),
            nullable=True,
        ),
        schema="identity",
    )
    op.drop_column("feishu_configs", "config_version", schema="identity")
    op.drop_column("feishu_configs", "gateway_enabled", schema="identity")
    op.drop_column("feishu_configs", "tenant_id", schema="identity")
