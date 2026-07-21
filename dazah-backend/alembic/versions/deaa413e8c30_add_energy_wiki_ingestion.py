"""add_energy_wiki_ingestion

Revision ID: deaa413e8c30
Revises: b272bca6fada
Create Date: 2026-07-13 11:34:07.064732
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "deaa413e8c30"
down_revision: str | None = "b272bca6fada"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS energy")

    op.create_table(
        "feishu_configs",
        sa.Column(
            "config_name", sa.String(length=128), nullable=False, comment="配置名称"
        ),
        sa.Column(
            "app_id", sa.String(length=128), nullable=False, comment="飞书 App ID"
        ),
        sa.Column(
            "encrypted_app_secret",
            sa.String(length=1024),
            nullable=False,
            comment="加密后的飞书 App Secret",
        ),
        sa.Column(
            "root_wiki_url", sa.Text(), nullable=False, comment="月度表父 Wiki 根链接"
        ),
        sa.Column(
            "root_wiki_token",
            sa.String(length=256),
            nullable=True,
            comment="解析后的 Wiki 根节点 token",
        ),
        sa.Column("timezone", sa.String(length=64), nullable=False, comment="同步时区"),
        sa.Column(
            "daily_sync_time",
            sa.String(length=5),
            nullable=False,
            comment="每日同步时间 HH:MM",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="是否启用",
        ),
        sa.Column(
            "last_successful_sync_date",
            sa.Date(),
            nullable=True,
            comment="最近成功同步的本地日期",
        ),
        sa.Column(
            "sync_status", sa.String(length=32), nullable=False, comment="最近同步状态"
        ),
        sa.Column("sync_error", sa.Text(), nullable=True, comment="最近同步错误"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema="energy",
    )
    op.create_index(
        "ix_energy_feishu_configs_active",
        "feishu_configs",
        ["is_active"],
        schema="energy",
    )

    op.create_table(
        "wiki_documents",
        sa.Column("config_id", sa.Uuid(), nullable=False),
        sa.Column("wiki_node_token", sa.String(length=256), nullable=False),
        sa.Column("parent_node_token", sa.String(length=256), nullable=True),
        sa.Column("space_id", sa.String(length=128), nullable=True),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("document_token", sa.String(length=256), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column(
            "node_path",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("period_month", sa.Date(), nullable=True, comment="所属月份首日"),
        sa.Column(
            "classification_status",
            sa.String(length=32),
            nullable=False,
            comment="monthly/unclassified",
        ),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "config_id",
            "wiki_node_token",
            "is_deleted",
            name="uq_energy_wiki_document_node",
        ),
        schema="energy",
    )
    op.create_index(
        "ix_energy_wiki_documents_period",
        "wiki_documents",
        ["config_id", "period_month"],
        schema="energy",
    )

    op.create_table(
        "workbook_sheets",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("external_sheet_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("sheet_index", sa.Integer(), nullable=False),
        sa.Column(
            "grid_properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("header_row", sa.Integer(), nullable=False),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("schema_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "mapping_status",
            sa.String(length=32),
            nullable=False,
            comment="unmapped/mapped/needs_mapping",
        ),
        sa.Column("latest_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("latest_content_hash", sa.String(length=64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "external_sheet_id",
            "is_deleted",
            name="uq_energy_workbook_sheet",
        ),
        schema="energy",
    )
    op.create_index(
        "ix_energy_workbook_sheets_document",
        "workbook_sheets",
        ["document_id"],
        schema="energy",
    )
    op.create_index(
        "ix_energy_workbook_sheets_schema",
        "workbook_sheets",
        ["schema_hash"],
        schema="energy",
    )

    op.create_table(
        "sync_runs",
        sa.Column("config_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("sheet_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_count", sa.Integer(), nullable=False),
        sa.Column("fact_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("lock_owner", sa.String(length=128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_energy_sync_run_idempotency"),
        schema="energy",
    )
    op.create_index(
        "ix_energy_sync_runs_config_started",
        "sync_runs",
        ["config_id", "started_at"],
        schema="energy",
    )
    op.create_index(
        "ix_energy_sync_runs_status", "sync_runs", ["status"], schema="energy"
    )

    op.create_table(
        "sheet_snapshots",
        sa.Column("sheet_id", sa.Uuid(), nullable=False),
        sa.Column("sync_run_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_number", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "header_values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sheet_id", "snapshot_number", name="uq_energy_sheet_snapshot_number"
        ),
        schema="energy",
    )
    op.create_index(
        "ix_energy_sheet_snapshots_sheet_captured",
        "sheet_snapshots",
        ["sheet_id", "captured_at"],
        schema="energy",
    )

    op.create_table(
        "snapshot_rows",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column(
            "values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id", "row_index", name="uq_energy_snapshot_row_index"
        ),
        schema="energy",
    )
    op.create_index(
        "ix_energy_snapshot_rows_snapshot",
        "snapshot_rows",
        ["snapshot_id", "row_index"],
        schema="energy",
    )

    op.create_table(
        "sheet_mappings",
        sa.Column("sheet_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("schema_hash", sa.String(length=64), nullable=True),
        sa.Column("header_row", sa.Integer(), nullable=False),
        sa.Column("date_column", sa.String(length=256), nullable=True),
        sa.Column("date_format", sa.String(length=128), nullable=True),
        sa.Column(
            "dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("validation_error", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sheet_id", "version", name="uq_energy_sheet_mapping_version"
        ),
        schema="energy",
    )
    op.create_index(
        "ix_energy_sheet_mappings_sheet_current",
        "sheet_mappings",
        ["sheet_id", "is_current"],
        schema="energy",
    )

    op.create_table(
        "metric_facts",
        sa.Column("mapping_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_version", sa.Integer(), nullable=False),
        sa.Column("sheet_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(length=256), nullable=False),
        sa.Column("source_row_index", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("energy_type", sa.String(length=128), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("meter_key", sa.String(length=256), nullable=True),
        sa.Column("value_semantics", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mapping_id",
            "snapshot_id",
            "metric_key",
            "source_row_index",
            name="uq_energy_metric_fact_source",
        ),
        schema="energy",
    )
    op.create_index(
        "ix_energy_metric_facts_observed",
        "metric_facts",
        ["observed_at", "energy_type", "unit"],
        schema="energy",
    )
    op.create_index(
        "ix_energy_metric_facts_sheet_snapshot",
        "metric_facts",
        ["sheet_id", "snapshot_id"],
        schema="energy",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_energy_metric_facts_sheet_snapshot",
        table_name="metric_facts",
        schema="energy",
    )
    op.drop_index(
        "ix_energy_metric_facts_observed", table_name="metric_facts", schema="energy"
    )
    op.drop_table("metric_facts", schema="energy")
    op.drop_index(
        "ix_energy_sheet_mappings_sheet_current",
        table_name="sheet_mappings",
        schema="energy",
    )
    op.drop_table("sheet_mappings", schema="energy")
    op.drop_index(
        "ix_energy_snapshot_rows_snapshot", table_name="snapshot_rows", schema="energy"
    )
    op.drop_table("snapshot_rows", schema="energy")
    op.drop_index(
        "ix_energy_sheet_snapshots_sheet_captured",
        table_name="sheet_snapshots",
        schema="energy",
    )
    op.drop_table("sheet_snapshots", schema="energy")
    op.drop_index("ix_energy_sync_runs_status", table_name="sync_runs", schema="energy")
    op.drop_index(
        "ix_energy_sync_runs_config_started", table_name="sync_runs", schema="energy"
    )
    op.drop_table("sync_runs", schema="energy")
    op.drop_index(
        "ix_energy_workbook_sheets_schema",
        table_name="workbook_sheets",
        schema="energy",
    )
    op.drop_index(
        "ix_energy_workbook_sheets_document",
        table_name="workbook_sheets",
        schema="energy",
    )
    op.drop_table("workbook_sheets", schema="energy")
    op.drop_index(
        "ix_energy_wiki_documents_period", table_name="wiki_documents", schema="energy"
    )
    op.drop_table("wiki_documents", schema="energy")
    op.drop_index(
        "ix_energy_feishu_configs_active", table_name="feishu_configs", schema="energy"
    )
    op.drop_table("feishu_configs", schema="energy")


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
    ]
