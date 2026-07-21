"""initial platform schemas

Revision ID: 20260529_0001
Revises:
Create Date: 2026-05-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260529_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUSINESS_SCHEMAS = (
    "production",
    "equipment",
    "safety",
    "environment",
    "energy",
    "warehouse",
    "procurement",
    "administration",
    "hr",
    "research",
    "registration",
    "quality",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    for schema in BUSINESS_SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    op.create_table(
        "users",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("employee_no", sa.String(length=64), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("mobile", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("feishu_user_id", sa.String(length=128), nullable=True),
        sa.Column("feishu_open_id", sa.String(length=128), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=True),
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
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_no", name="uq_identity_users_employee_no"),
        sa.UniqueConstraint("feishu_user_id", name="uq_identity_users_feishu_user_id"),
        schema="identity",
    )

    op.create_table(
        "logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=True),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=100), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="audit",
    )
    op.create_index(
        "idx_audit_logs_created_at",
        "logs",
        ["created_at"],
        unique=False,
        schema="audit",
    )
    op.create_index(
        "idx_audit_logs_request_id",
        "logs",
        ["request_id"],
        unique=False,
        schema="audit",
    )
    op.create_index(
        "idx_audit_logs_resource",
        "logs",
        ["resource_type", "resource_id"],
        unique=False,
        schema="audit",
    )
    op.create_index(
        "idx_audit_logs_user_id",
        "logs",
        ["user_id"],
        unique=False,
        schema="audit",
    )


def downgrade() -> None:
    op.drop_index("idx_audit_logs_user_id", table_name="logs", schema="audit")
    op.drop_index("idx_audit_logs_resource", table_name="logs", schema="audit")
    op.drop_index("idx_audit_logs_request_id", table_name="logs", schema="audit")
    op.drop_index("idx_audit_logs_created_at", table_name="logs", schema="audit")
    op.drop_table("logs", schema="audit")
    op.drop_table("users", schema="identity")
    for schema in reversed(BUSINESS_SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema}")
    op.execute("DROP SCHEMA IF EXISTS audit")
    op.execute("DROP SCHEMA IF EXISTS identity")
