"""inspection feishu per workshop

Revision ID: b4e2f8a1c7d3
Revises: a3d8f2c6e1b9
Create Date: 2026-10-12

设备巡检飞书镜像按车间隔离：配置表、巡检记录、设备档案、同步状态
四张表增加 workshop_code（存量回填 201-1，即当前已配置的 201一车间）；
唯一约束改为「未删除行内按车间唯一」的部分唯一索引。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b4e2f8a1c7d3"
down_revision = "a3d8f2c6e1b9"
branch_labels = None
depends_on = None

_WORKSHOP_CODE = "201-1"

# (表, 旧唯一约束名)
_LEGACY_UNIQUES = [
    ("inspection_feishu_records", "uq_inspection_feishu_records_source_record"),
    ("inspection_feishu_devices", "uq_inspection_feishu_devices_record"),
    ("inspection_feishu_sync_state", "uq_inspection_feishu_sync_state_key"),
]


def _add_workshop_column(table: str) -> None:
    op.add_column(
        table,
        sa.Column(
            "workshop_code",
            sa.String(length=10),
            nullable=False,
            server_default=_WORKSHOP_CODE,
            comment="车间代码（如 101-1 / 201-1）",
        ),
        schema="equipment",
    )


def upgrade() -> None:
    for table, unique_name in _LEGACY_UNIQUES:
        op.drop_constraint(unique_name, table, schema="equipment", type_="unique")
    for table in (
        "inspection_feishu_config",
        "inspection_feishu_records",
        "inspection_feishu_devices",
        "inspection_feishu_sync_state",
    ):
        _add_workshop_column(table)

    op.create_index(
        "uq_inspection_feishu_config_workshop",
        "inspection_feishu_config",
        ["workshop_code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="equipment",
    )
    op.create_index(
        "uq_inspection_feishu_records_source_record",
        "inspection_feishu_records",
        ["workshop_code", "source", "record_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="equipment",
    )
    op.create_index(
        "uq_inspection_feishu_devices_record",
        "inspection_feishu_devices",
        ["workshop_code", "record_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="equipment",
    )
    op.create_index(
        "uq_inspection_feishu_sync_state_ws_table",
        "inspection_feishu_sync_state",
        ["workshop_code", "table_key"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="equipment",
    )
    # 查询路径：页面按车间 + 来源 + 日期过滤
    op.create_index(
        "ix_inspection_feishu_records_ws_source_date",
        "inspection_feishu_records",
        ["workshop_code", "source", "record_date"],
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inspection_feishu_records_ws_source_date",
        table_name="inspection_feishu_records", schema="equipment",
    )
    op.drop_index(
        "uq_inspection_feishu_sync_state_ws_table",
        table_name="inspection_feishu_sync_state", schema="equipment",
    )
    op.drop_index(
        "uq_inspection_feishu_devices_record",
        table_name="inspection_feishu_devices", schema="equipment",
    )
    op.drop_index(
        "uq_inspection_feishu_records_source_record",
        table_name="inspection_feishu_records", schema="equipment",
    )
    op.drop_index(
        "uq_inspection_feishu_config_workshop",
        table_name="inspection_feishu_config", schema="equipment",
    )
    for table in (
        "inspection_feishu_config",
        "inspection_feishu_records",
        "inspection_feishu_devices",
        "inspection_feishu_sync_state",
    ):
        op.drop_column(table, "workshop_code", schema="equipment")
    op.create_unique_constraint(
        "uq_inspection_feishu_sync_state_key",
        "inspection_feishu_sync_state",
        ["table_key", "is_deleted"],
        schema="equipment",
    )
    op.create_unique_constraint(
        "uq_inspection_feishu_devices_record",
        "inspection_feishu_devices",
        ["record_id", "is_deleted"],
        schema="equipment",
    )
    op.create_unique_constraint(
        "uq_inspection_feishu_records_source_record",
        "inspection_feishu_records",
        ["source", "record_id", "is_deleted"],
        schema="equipment",
    )
