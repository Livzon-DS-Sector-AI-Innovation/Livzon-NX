"""add change action plan reminder fields

Revision ID: a7c100000005
Revises: a7c100000004
Create Date: 2026-07-01 13:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000005"
down_revision: str | None = "a7c100000004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"]
        for column in inspector.get_columns(
            "quality_change_action_plans",
            schema="quality",
        )
    }

    if "reminder_enabled" not in columns:
        op.add_column(
            "quality_change_action_plans",
            sa.Column(
                "reminder_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            schema="quality",
        )
    if "reminder_status" not in columns:
        op.add_column(
            "quality_change_action_plans",
            sa.Column(
                "reminder_status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
            schema="quality",
        )
    if "last_reminded_at" not in columns:
        op.add_column(
            "quality_change_action_plans",
            sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True),
            schema="quality",
        )
    if "reminder_confirmed_at" not in columns:
        op.add_column(
            "quality_change_action_plans",
            sa.Column(
                "reminder_confirmed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            schema="quality",
        )
    if "reminder_confirmed_by" not in columns:
        op.add_column(
            "quality_change_action_plans",
            sa.Column("reminder_confirmed_by", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "reminder_message_id" not in columns:
        op.add_column(
            "quality_change_action_plans",
            sa.Column("reminder_message_id", sa.String(length=100), nullable=True),
            schema="quality",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"]
        for column in inspector.get_columns(
            "quality_change_action_plans",
            schema="quality",
        )
    }

    for column_name in (
        "reminder_message_id",
        "reminder_confirmed_by",
        "reminder_confirmed_at",
        "last_reminded_at",
        "reminder_status",
        "reminder_enabled",
    ):
        if column_name in columns:
            op.drop_column(
                "quality_change_action_plans",
                column_name,
                schema="quality",
            )