"""add page permission matrix

Revision ID: d2f8a4c6e1b3
Revises: c1e7f4a9b2d6
Create Date: 2026-08-28 00:00:00.000000
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d2f8a4c6e1b3"
down_revision: str | None = "c1e7f4a9b2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
    ]


def _grant_columns() -> list[sa.Column]:
    return [
        sa.Column("page_key", sa.String(length=255), nullable=False),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "sensitive_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "scope_type",
            sa.String(length=32),
            server_default="department_tree",
            nullable=False,
        ),
        sa.Column(
            "department_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column(
            "grant_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="角色页面授权单调递增版本",
        ),
        schema="identity",
    )
    op.create_table(
        "role_page_grants",
        *_base_columns(),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        *_grant_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "role_id", "page_key", name="uq_identity_role_page_grants_role_page"
        ),
        schema="identity",
        comment="角色页面权限基线",
    )
    op.create_index(
        "ix_identity_role_page_grants_role",
        "role_page_grants",
        ["role_id"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_role_page_grants_page",
        "role_page_grants",
        ["page_key"],
        schema="identity",
    )
    op.create_table(
        "user_page_grants",
        *_base_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        *_grant_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "page_key", name="uq_identity_user_page_grants_user_page"
        ),
        schema="identity",
        comment="用户页面权限精确覆盖",
    )
    op.create_index(
        "ix_identity_user_page_grants_user",
        "user_page_grants",
        ["user_id"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_user_page_grants_page",
        "user_page_grants",
        ["page_key"],
        schema="identity",
    )
    op.create_table(
        "permission_module_rollouts",
        *_base_columns(),
        sa.Column("module_code", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="legacy", nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("last_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "status IN ('legacy', 'draft', 'enforced')",
            name="ck_identity_permission_module_rollouts_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "module_code", name="uq_identity_permission_module_rollouts_module"
        ),
        schema="identity",
        comment="页面权限模块发布状态",
    )
    for module_code in ("hr", "warehouse", "quality", "procurement"):
        op.execute(
            sa.text(
                "INSERT INTO identity.permission_module_rollouts "
                "(id, module_code, status, version, is_deleted) "
                "VALUES (:id, :module_code, 'draft', 0, false)"
            ).bindparams(
                sa.bindparam("id", value=uuid.uuid4(), type_=sa.Uuid()),
                sa.bindparam(
                    "module_code", value=module_code, type_=sa.String(length=64)
                ),
            )
        )


def downgrade() -> None:
    op.drop_table("permission_module_rollouts", schema="identity")
    op.drop_index(
        "ix_identity_user_page_grants_page",
        table_name="user_page_grants",
        schema="identity",
    )
    op.drop_index(
        "ix_identity_user_page_grants_user",
        table_name="user_page_grants",
        schema="identity",
    )
    op.drop_table("user_page_grants", schema="identity")
    op.drop_index(
        "ix_identity_role_page_grants_page",
        table_name="role_page_grants",
        schema="identity",
    )
    op.drop_index(
        "ix_identity_role_page_grants_role",
        table_name="role_page_grants",
        schema="identity",
    )
    op.drop_table("role_page_grants", schema="identity")
    op.drop_column("roles", "grant_version", schema="identity")
