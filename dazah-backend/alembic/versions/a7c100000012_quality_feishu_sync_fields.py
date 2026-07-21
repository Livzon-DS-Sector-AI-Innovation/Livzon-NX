"""add quality feishu sync fields

Revision ID: a7c100000012
Revises: a7c100000011
Create Date: 2026-07-03 17:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000012"
down_revision: str | None = "a7c100000011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_sync_columns(table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns(table_name, schema="quality")
    }

    if "feishu_base_table_id" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column("feishu_base_table_id", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "feishu_base_record_id" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column("feishu_base_record_id", sa.String(length=100), nullable=True),
            schema="quality",
        )
    if "feishu_sync_status" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "feishu_sync_status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
            schema="quality",
        )
    if "feishu_last_sync_error" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column("feishu_last_sync_error", sa.Text(), nullable=True),
            schema="quality",
        )
    if "feishu_synced_at" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column("feishu_synced_at", sa.DateTime(timezone=True), nullable=True),
            schema="quality",
        )

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name, schema="quality")
        if constraint.get("name")
    }
    constraint_name = f"uq_q_{table_name}_fbr"
    if (
        "feishu_base_record_id" in {
            column["name"]
            for column in inspector.get_columns(table_name, schema="quality")
        }
        and constraint_name not in unique_constraints
    ):
        op.create_unique_constraint(
            constraint_name,
            table_name,
            ["feishu_base_record_id"],
            schema="quality",
        )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")
    _add_sync_columns("deviations")
    _add_sync_columns("capas")
    _add_sync_columns("deviation_investigation_push_records")
    _add_sync_columns("capa_plan_tracks")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in (
        "capa_plan_tracks",
        "deviation_investigation_push_records",
        "capas",
        "deviations",
    ):
        unique_constraints = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints(table_name, schema="quality")
            if constraint.get("name")
        }
        constraint_name = f"uq_q_{table_name}_fbr"
        if constraint_name in unique_constraints:
            op.drop_constraint(
                constraint_name,
                table_name,
                schema="quality",
                type_="unique",
            )

        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name, schema="quality")
        }
        for column_name in (
            "feishu_synced_at",
            "feishu_last_sync_error",
            "feishu_sync_status",
            "feishu_base_record_id",
            "feishu_base_table_id",
        ):
            if column_name in existing_columns:
                op.drop_column(table_name, column_name, schema="quality")