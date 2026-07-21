"""add quality change action plans

Revision ID: a7c100000004
Revises: a7c100000003
Create Date: 2026-06-30 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000004"
down_revision: str | None = "a7c100000003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")
    if not inspector.has_table("quality_change_action_plans", schema="quality"):
        op.create_table(
            "quality_change_action_plans",
            sa.Column("change_id", sa.Uuid(), nullable=True),
            sa.Column("change_code", sa.String(length=100), nullable=False),
            sa.Column("project_name", sa.String(length=255), nullable=False),
            sa.Column("related_work", sa.Text(), nullable=True),
            sa.Column("owner_name", sa.String(length=100), nullable=True),
            sa.Column("owner_user_id", sa.String(length=100), nullable=True),
            sa.Column("director_name", sa.String(length=100), nullable=True),
            sa.Column("director_user_id", sa.String(length=100), nullable=True),
            sa.Column("deadline_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(length=100), nullable=True),
            sa.Column("delay_flag", sa.String(length=100), nullable=True),
            sa.Column("delayed_deadline_date", sa.Date(), nullable=True),
            sa.Column("feishu_record_id", sa.String(length=100), nullable=True),
            sa.Column(
                "sync_status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("sync_error", sa.Text(), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.PrimaryKeyConstraint("id"),
            schema="quality",
        )
    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes("quality_change_action_plans", schema="quality")
    }
    if "ix_quality_change_action_plans_change_code" not in existing_indexes:
        op.create_index(
            "ix_quality_change_action_plans_change_code",
            "quality_change_action_plans",
            ["change_code"],
            unique=False,
            schema="quality",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("quality_change_action_plans", schema="quality"):
        existing_indexes = {
            index["name"]
            for index in inspector.get_indexes("quality_change_action_plans", schema="quality")
        }
        if "ix_quality_change_action_plans_change_code" in existing_indexes:
            op.drop_index(
                "ix_quality_change_action_plans_change_code",
                table_name="quality_change_action_plans",
                schema="quality",
            )
        op.drop_table("quality_change_action_plans", schema="quality")