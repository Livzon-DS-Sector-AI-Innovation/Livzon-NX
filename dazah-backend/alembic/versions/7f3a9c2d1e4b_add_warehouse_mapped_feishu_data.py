"""add warehouse mapped Feishu data platform

Revision ID: 7f3a9c2d1e4b
Revises: 45c37377e9a2
Create Date: 2026-07-21 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7f3a9c2d1e4b"
down_revision: str | None = "45c37377e9a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS warehouse")
    op.add_column(
        "feishu_configs",
        sa.Column("timezone", sa.String(64), server_default="Asia/Shanghai", nullable=False),
        schema="warehouse",
    )
    op.add_column(
        "feishu_configs",
        sa.Column("daily_sync_time", sa.String(5), server_default="02:00", nullable=False),
        schema="warehouse",
    )
    op.add_column("feishu_tables", sa.Column("source_root_id", sa.Uuid(), nullable=True), schema="warehouse")
    op.add_column(
        "feishu_tables",
        sa.Column("source_path", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        schema="warehouse",
    )
    op.add_column("feishu_tables", sa.Column("schema_hash", sa.String(64), nullable=True), schema="warehouse")
    op.add_column("feishu_tables", sa.Column("active_mirror_version", sa.String(64), nullable=True), schema="warehouse")
    op.add_column(
        "feishu_fields",
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        schema="warehouse",
    )
    op.add_column(
        "feishu_records",
        sa.Column("normalized_fields", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        schema="warehouse",
    )
    op.add_column("feishu_records", sa.Column("source_revision", sa.Integer(), nullable=True), schema="warehouse")
    op.add_column("feishu_records", sa.Column("mirror_version", sa.String(64), nullable=True), schema="warehouse")
    op.add_column(
        "feishu_records",
        sa.Column("is_source_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        schema="warehouse",
    )

    op.create_table(
        "feishu_source_roots",
        sa.Column("config_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("root_token", sa.String(256), nullable=False),
        sa.Column("business_domain", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("discovery_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("discovery_error", sa.Text(), nullable=True),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.UniqueConstraint("config_id", "root_token", "is_deleted", name="uq_warehouse_feishu_root"),
        schema="warehouse",
    )
    op.create_index("ix_warehouse_feishu_roots_active", "feishu_source_roots", ["config_id", "is_active"], schema="warehouse")

    op.create_table(
        "feishu_page_bindings",
        sa.Column("page_key", sa.String(128), nullable=False),
        sa.Column("table_pk", sa.Uuid(), nullable=False),
        sa.Column("tab_label", sa.String(255), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("visible_field_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("default_sort", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("history_mode", sa.String(32), server_default="current_mirror", nullable=False),
        sa.Column("status", sa.String(16), server_default="published", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_base_columns(),
        sa.UniqueConstraint("page_key", "table_pk", "is_deleted", name="uq_warehouse_page_table_binding"),
        schema="warehouse",
    )
    op.create_index("ix_warehouse_page_bindings_page", "feishu_page_bindings", ["page_key", "is_enabled"], schema="warehouse")

    op.create_table(
        "feishu_data_sync_runs",
        sa.Column("table_pk", sa.Uuid(), nullable=False),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("mirror_version", sa.String(64), nullable=False),
        sa.Column("start_revision", sa.Integer(), nullable=True),
        sa.Column("end_revision", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("received_count", sa.Integer(), nullable=False),
        sa.Column("unique_count", sa.Integer(), nullable=False),
        sa.Column("expected_total", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_base_columns(),
        schema="warehouse",
    )
    op.create_index("ix_warehouse_data_sync_runs_table", "feishu_data_sync_runs", ["table_pk", "started_at"], schema="warehouse")

    op.create_table(
        "feishu_record_snapshots",
        sa.Column("table_pk", sa.Uuid(), nullable=False),
        sa.Column("mirror_version", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(128), nullable=False),
        sa.Column("fields", postgresql.JSONB(), nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *_base_columns(),
        sa.UniqueConstraint("table_pk", "mirror_version", "record_id", name="uq_warehouse_record_snapshot"),
        schema="warehouse",
    )
    op.create_index("ix_warehouse_record_snapshots_table", "feishu_record_snapshots", ["table_pk", "captured_at"], schema="warehouse")

    op.create_table(
        "feishu_analysis_profiles",
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("resource_ids", postgresql.JSONB(), nullable=False),
        sa.Column("analysis_goal", sa.Text(), nullable=False),
        sa.Column("input_field_ids", postgresql.JSONB(), nullable=False),
        sa.Column("time_field_id", sa.String(128), nullable=True),
        sa.Column("metric_field_ids", postgresql.JSONB(), nullable=False),
        sa.Column("dimension_field_ids", postgresql.JSONB(), nullable=False),
        sa.Column("quality_rules", postgresql.JSONB(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=False),
        sa.Column("max_raw_rows", sa.Integer(), nullable=False),
        sa.Column("auto_run", sa.Boolean(), nullable=False),
        sa.Column("allow_sensitive_fields", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("published_prompt_version_id", sa.Uuid(), nullable=True),
        *_base_columns(),
        schema="warehouse",
    )
    op.create_index("ix_warehouse_analysis_profiles_active", "feishu_analysis_profiles", ["is_active", "auto_run"], schema="warehouse")

    op.create_table(
        "feishu_prompt_versions",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("business_context", sa.Text(), nullable=True),
        sa.Column("focus_points", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.UniqueConstraint("profile_id", "version", name="uq_warehouse_prompt_version"),
        schema="warehouse",
    )

    op.create_table(
        "feishu_analysis_runs",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("source_versions", postgresql.JSONB(), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_base_columns(),
        schema="warehouse",
    )
    op.create_index("ix_warehouse_analysis_runs_profile", "feishu_analysis_runs", ["profile_id", "started_at"], schema="warehouse")

    op.create_table(
        "feishu_analysis_results",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("risks", postgresql.JSONB(), nullable=False),
        sa.Column("trends", postgresql.JSONB(), nullable=False),
        sa.Column("feasibility", postgresql.JSONB(), nullable=False),
        sa.Column("recommendations", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("llm_output", postgresql.JSONB(), nullable=True),
        *_base_columns(),
        sa.UniqueConstraint("run_id", name="uq_warehouse_analysis_result_run"),
        schema="warehouse",
    )


def downgrade() -> None:
    op.drop_table("feishu_analysis_results", schema="warehouse")
    op.drop_index("ix_warehouse_analysis_runs_profile", table_name="feishu_analysis_runs", schema="warehouse")
    op.drop_table("feishu_analysis_runs", schema="warehouse")
    op.drop_table("feishu_prompt_versions", schema="warehouse")
    op.drop_index("ix_warehouse_analysis_profiles_active", table_name="feishu_analysis_profiles", schema="warehouse")
    op.drop_table("feishu_analysis_profiles", schema="warehouse")
    op.drop_index("ix_warehouse_record_snapshots_table", table_name="feishu_record_snapshots", schema="warehouse")
    op.drop_table("feishu_record_snapshots", schema="warehouse")
    op.drop_index("ix_warehouse_data_sync_runs_table", table_name="feishu_data_sync_runs", schema="warehouse")
    op.drop_table("feishu_data_sync_runs", schema="warehouse")
    op.drop_index("ix_warehouse_page_bindings_page", table_name="feishu_page_bindings", schema="warehouse")
    op.drop_table("feishu_page_bindings", schema="warehouse")
    op.drop_index("ix_warehouse_feishu_roots_active", table_name="feishu_source_roots", schema="warehouse")
    op.drop_table("feishu_source_roots", schema="warehouse")
    op.drop_column("feishu_records", "is_source_deleted", schema="warehouse")
    op.drop_column("feishu_records", "mirror_version", schema="warehouse")
    op.drop_column("feishu_records", "source_revision", schema="warehouse")
    op.drop_column("feishu_records", "normalized_fields", schema="warehouse")
    op.drop_column("feishu_fields", "display_order", schema="warehouse")
    op.drop_column("feishu_tables", "active_mirror_version", schema="warehouse")
    op.drop_column("feishu_tables", "schema_hash", schema="warehouse")
    op.drop_column("feishu_tables", "source_path", schema="warehouse")
    op.drop_column("feishu_tables", "source_root_id", schema="warehouse")
    op.drop_column("feishu_configs", "daily_sync_time", schema="warehouse")
    op.drop_column("feishu_configs", "timezone", schema="warehouse")
