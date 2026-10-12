"""create inspection feishu mirror tables

Revision ID: f1c7e9a3d4b6
Revises: e9a4c7d1f5b8
Create Date: 2026-10-10

设备巡检飞书多维表格镜像：巡检记录（今日+历史）、巡检设备
清单、同步状态三张表。平台自持只读副本，录入在飞书。
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f1c7e9a3d4b6"
down_revision = "e9a4c7d1f5b8"
branch_labels = None
depends_on = None

_CHECK_COLUMNS = [
    "am_clean", "am_lubrication", "am_fastening", "am_sealing",
    "am_vibration", "am_sound", "am_surface",
    "pm_clean", "pm_lubrication", "pm_fastening", "pm_sealing",
    "pm_vibration", "pm_sound", "pm_surface",
]


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(),
            server_default=sa.text("false"), nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "inspection_feishu_records",
        *_base_columns(),
        sa.Column("source", sa.String(length=20), nullable=False, comment="来源表"),
        sa.Column(
            "record_id", sa.String(length=64), nullable=False, comment="飞书记录ID"
        ),
        sa.Column("record_date", sa.Date(), nullable=True, comment="巡检日期"),
        sa.Column("equipment_name", sa.String(length=200), nullable=True),
        sa.Column("equipment_no", sa.String(length=100), nullable=True),
        *[
            sa.Column(name, sa.String(length=8), nullable=True)
            for name in _CHECK_COLUMNS
        ],
        sa.Column("anomaly_note", sa.Text(), nullable=True),
        sa.Column("process_status", sa.String(length=20), nullable=True),
        sa.Column(
            "has_abnormal", sa.Boolean(),
            server_default=sa.text("false"), nullable=False,
        ),
        sa.Column("raw_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source", "record_id", "is_deleted",
                            name="uq_inspection_feishu_records_source_record"),
        schema="equipment",
    )
    op.create_index(
        "ix_inspection_feishu_records_date",
        "inspection_feishu_records",
        ["record_date"],
        schema="equipment",
    )
    op.create_index(
        "ix_inspection_feishu_records_source_date",
        "inspection_feishu_records",
        ["source", "record_date"],
        schema="equipment",
    )
    op.create_index(
        "ix_inspection_feishu_records_equipment_no",
        "inspection_feishu_records",
        ["equipment_no"],
        schema="equipment",
    )

    op.create_table(
        "inspection_feishu_devices",
        *_base_columns(),
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column("equipment_name", sa.String(length=200), nullable=True),
        sa.Column("equipment_no", sa.String(length=100), nullable=True),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("record_id", "is_deleted",
                            name="uq_inspection_feishu_devices_record"),
        schema="equipment",
    )

    op.create_table(
        "inspection_feishu_sync_state",
        *_base_columns(),
        sa.Column("table_key", sa.String(length=20), nullable=False),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("table_key", "is_deleted",
                            name="uq_inspection_feishu_sync_state_key"),
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_table("inspection_feishu_sync_state", schema="equipment")
    op.drop_table("inspection_feishu_devices", schema="equipment")
    op.drop_index("ix_inspection_feishu_records_equipment_no",
                  table_name="inspection_feishu_records", schema="equipment")
    op.drop_index("ix_inspection_feishu_records_source_date",
                  table_name="inspection_feishu_records", schema="equipment")
    op.drop_index("ix_inspection_feishu_records_date",
                  table_name="inspection_feishu_records", schema="equipment")
    op.drop_table("inspection_feishu_records", schema="equipment")
