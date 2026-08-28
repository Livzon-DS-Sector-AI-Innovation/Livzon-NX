"""repair missing production Feishu read mirror tables

Some existing databases reached the migration head while only the quality
read-mirror tables were present.  This additive repair creates the production
tables when they are absent and leaves existing tables and rows untouched.

Revision ID: c1e7f4a9b2d6
Revises: b5f4c8d1a2e3
Create Date: 2026-08-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c1e7f4a9b2d6"
down_revision: str | None = "b5f4c8d1a2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_columns() -> list[sa.Column]:
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


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name, schema="production")


def _create_missing_tables() -> None:
    if not _table_exists("feishu_read_source_roots"):
        op.create_table(
            "feishu_read_source_roots",
            sa.Column("config_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("source_type", sa.String(16), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("root_token", sa.String(256), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column(
                "discovery_status",
                sa.String(32),
                server_default="pending",
                nullable=False,
            ),
            sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("discovery_error", sa.Text(), nullable=True),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "config_id",
                "source_type",
                "root_token",
                "is_deleted",
                name="uq_production_feishu_read_source_root",
            ),
            schema="production",
        )
        op.create_index(
            "ix_production_feishu_read_roots_config",
            "feishu_read_source_roots",
            ["config_id", "is_active"],
            schema="production",
        )

    if not _table_exists("feishu_read_resources"):
        op.create_table(
            "feishu_read_resources",
            sa.Column("source_root_id", sa.Uuid(), nullable=False),
            sa.Column("app_token", sa.String(256), nullable=False),
            sa.Column("table_id", sa.String(256), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column(
                "source_path",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("schema_hash", sa.String(64), nullable=True),
            sa.Column("active_mirror_version", sa.Uuid(), nullable=True),
            sa.Column(
                "last_complete_sync_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column(
                "sync_status", sa.String(32), server_default="pending", nullable=False
            ),
            sa.Column("sync_error", sa.Text(), nullable=True),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "app_token",
                "table_id",
                "is_deleted",
                name="uq_production_feishu_read_resource",
            ),
            schema="production",
        )
        op.create_index(
            "ix_production_feishu_read_resources_root",
            "feishu_read_resources",
            ["source_root_id"],
            schema="production",
        )

    if not _table_exists("feishu_read_fields"):
        op.create_table(
            "feishu_read_fields",
            sa.Column("resource_id", sa.Uuid(), nullable=False),
            sa.Column("field_id", sa.String(256), nullable=False),
            sa.Column("field_name", sa.String(255), nullable=False),
            sa.Column("field_type", sa.String(64), nullable=False),
            sa.Column(
                "property",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "resource_id",
                "field_id",
                "is_deleted",
                name="uq_production_feishu_read_field",
            ),
            schema="production",
        )
        op.create_index(
            "ix_production_feishu_read_fields_resource",
            "feishu_read_fields",
            ["resource_id", "sort_order"],
            schema="production",
        )

    if not _table_exists("feishu_read_records"):
        op.create_table(
            "feishu_read_records",
            sa.Column("resource_id", sa.Uuid(), nullable=False),
            sa.Column("record_id", sa.String(256), nullable=False),
            sa.Column("mirror_version", sa.Uuid(), nullable=False),
            sa.Column(
                "raw_fields",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "normalized_fields",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("search_text", sa.Text(), server_default="", nullable=False),
            sa.Column("source_created_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "source_modified_time", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "resource_id",
                "record_id",
                "mirror_version",
                name="uq_production_feishu_read_record_version",
            ),
            schema="production",
        )
        op.create_index(
            "ix_production_feishu_read_records_page",
            "feishu_read_records",
            ["resource_id", "mirror_version", "record_id"],
            schema="production",
        )

    if not _table_exists("feishu_read_page_bindings"):
        op.create_table(
            "feishu_read_page_bindings",
            sa.Column("page_key", sa.String(255), nullable=False),
            sa.Column("resource_id", sa.Uuid(), nullable=False),
            sa.Column("tab_name", sa.String(255), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column(
                "is_default", sa.Boolean(), server_default="false", nullable=False
            ),
            sa.Column(
                "is_enabled", sa.Boolean(), server_default="true", nullable=False
            ),
            sa.Column(
                "visible_field_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "page_key",
                "resource_id",
                "is_deleted",
                name="uq_production_feishu_read_page_binding",
            ),
            schema="production",
        )
        op.create_index(
            "ix_production_feishu_read_bindings_page",
            "feishu_read_page_bindings",
            ["page_key", "sort_order"],
            schema="production",
        )

    if not _table_exists("feishu_read_sync_runs"):
        op.create_table(
            "feishu_read_sync_runs",
            sa.Column("resource_id", sa.Uuid(), nullable=False),
            sa.Column("mirror_version", sa.Uuid(), nullable=False),
            sa.Column(
                "status", sa.String(32), server_default="running", nullable=False
            ),
            sa.Column("expected_count", sa.Integer(), nullable=True),
            sa.Column("actual_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            schema="production",
        )
        op.create_index(
            "ix_production_feishu_read_runs_resource",
            "feishu_read_sync_runs",
            ["resource_id", "started_at"],
            schema="production",
        )


def upgrade() -> None:
    _create_missing_tables()


def downgrade() -> None:
    # This is a repair migration.  It intentionally does not drop tables or
    # data that may have existed before the repair was applied.
    pass
