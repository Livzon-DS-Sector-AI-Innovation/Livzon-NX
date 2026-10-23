"""add safety fire equipment inspection tables

「灭火器及消防栓点检」：飞书多维表格（各车间子表）经页面镜像同步后，投影为
结构化消防器材台账并支持扫码点检：
- ``safety.fire_equipment``：器材台账（镜像投影，含编号/部门/位置与最近点检状态）；
- ``safety.fire_inspection_records``：点检记录（检查项快照 + 结论 + 异常处理）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e3a7c5d9b1f4"
down_revision: str | None = "c9d400000062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fire_equipment",
        sa.Column("page_key", sa.String(length=160), nullable=False,
                  comment="来源镜像页标识"),
        sa.Column("table_id", sa.String(length=64), nullable=False,
                  comment="来源飞书子表 table_id"),
        sa.Column("record_id", sa.String(length=64), nullable=False,
                  comment="来源飞书记录 record_id"),
        sa.Column("tab_name", sa.String(length=120), nullable=False,
                  server_default="", comment="来源子表页签名（车间）"),
        sa.Column("equipment_type", sa.String(length=20), nullable=False,
                  server_default="extinguisher",
                  comment="器材类型: extinguisher=灭火器 / hydrant=消防栓"),
        sa.Column("equipment_no", sa.String(length=100), nullable=False,
                  server_default="",
                  comment="器材编号（如 灭火器编号/消防栓编号 列值）"),
        sa.Column("department", sa.String(length=200), nullable=False,
                  server_default="", comment="归属部门/车间"),
        sa.Column("location", sa.String(length=200), nullable=False,
                  server_default="", comment="存放位置"),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, comment="镜像解码后的全部字段值"),
        sa.Column("search_text", sa.Text(), nullable=False, server_default="",
                  comment="关键字搜索文本（编号/部门/位置/子表名）"),
        sa.Column("last_inspected_at", sa.DateTime(timezone=True), nullable=True,
                  comment="最近一次点检时间"),
        sa.Column("last_inspection_result", sa.String(length=20), nullable=True,
                  comment="最近一次点检结论: pass=合格 / fail=不合格"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()"), comment="该行最近投影同步时间"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="safety",
    )
    op.create_index(
        "uq_safety_fire_equipment_source_record",
        "fire_equipment",
        ["table_id", "record_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="safety",
    )
    op.create_index(
        "ix_safety_fire_equipment_page",
        "fire_equipment",
        ["page_key", "is_deleted"],
        schema="safety",
    )

    op.create_table(
        "fire_inspection_records",
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=False,
                  comment="器材 id（safety.fire_equipment）"),
        sa.Column("equipment_type", sa.String(length=20), nullable=False,
                  comment="器材类型快照: extinguisher/hydrant"),
        sa.Column("equipment_no", sa.String(length=100), nullable=False,
                  server_default="", comment="器材编号快照"),
        sa.Column("department", sa.String(length=200), nullable=False,
                  server_default="", comment="归属部门快照"),
        sa.Column("location", sa.String(length=200), nullable=False,
                  server_default="", comment="存放位置快照"),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False,
                  comment="检查项快照 [{key, label, result: ok/fail, remark}]"),
        sa.Column("result", sa.String(length=20), nullable=False,
                  comment="点检结论: pass=全部合格 / fail=存在不合格项"),
        sa.Column("failed_items", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True, comment="不合格项 [{key, label}]"),
        sa.Column("abnormal_action", sa.Text(), nullable=True,
                  comment="异常处理措施"),
        sa.Column("inspector_id", postgresql.UUID(as_uuid=True), nullable=True,
                  comment="点检人用户 id"),
        sa.Column("inspector_name", sa.String(length=100), nullable=False,
                  server_default="", comment="点检人姓名"),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False,
                  comment="点检时间"),
        sa.Column("source", sa.String(length=20), nullable=False,
                  server_default="web", comment="提交来源: scan=扫码页 / web=网页端"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.ForeignKeyConstraint(
            ["equipment_id"], ["safety.fire_equipment.id"]
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="safety",
    )
    op.create_index(
        "ix_safety_fire_inspections_equipment",
        "fire_inspection_records",
        ["equipment_id", "inspected_at"],
        schema="safety",
    )
    op.create_index(
        "ix_safety_fire_inspections_inspected_at",
        "fire_inspection_records",
        ["inspected_at"],
        schema="safety",
    )


def downgrade() -> None:
    op.drop_index("ix_safety_fire_inspections_inspected_at",
                  table_name="fire_inspection_records", schema="safety")
    op.drop_index("ix_safety_fire_inspections_equipment",
                  table_name="fire_inspection_records", schema="safety")
    op.drop_table("fire_inspection_records", schema="safety")
    op.drop_index("ix_safety_fire_equipment_page",
                  table_name="fire_equipment", schema="safety")
    op.drop_index("uq_safety_fire_equipment_source_record",
                  table_name="fire_equipment", schema="safety")
    op.drop_table("fire_equipment", schema="safety")
