"""add quality feishu sync metadata fields

Revision ID: a7c100000013
Revises: a7c100000012
Create Date: 2026-07-03 20:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000013"
down_revision: str | None = "a7c100000012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_metadata_columns(table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns(table_name, schema="quality")
    }

    if "feishu_last_sync_direction" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "feishu_last_sync_direction", sa.String(length=20), nullable=True
            ),
            schema="quality",
        )
    if "feishu_source_updated_at" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "feishu_source_updated_at", sa.DateTime(timezone=True), nullable=True
            ),
            schema="quality",
        )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")
    _add_metadata_columns("deviations")
    _add_metadata_columns("capas")
    _add_metadata_columns("deviation_investigation_push_records")
    _add_metadata_columns("capa_plan_tracks")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in (
        "capa_plan_tracks",
        "deviation_investigation_push_records",
        "capas",
        "deviations",
    ):
        existing_columns = {
            column["name"]
            for column in inspector.get_columns(table_name, schema="quality")
        }
        for column_name in ("feishu_source_updated_at", "feishu_last_sync_direction"):
            if column_name in existing_columns:
                op.drop_column(table_name, column_name, schema="quality")
