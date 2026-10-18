"""multi-table tabs for safety page mirror (sub_tables + mirror table_id)

「隐患台账」等镜像页需要像飞书 Base 一样展示多张子表（2024-2026 公司级
检查、上级部门检查、事业部检查、不符合项、观察项），且仪表盘跨子表聚合：
- ``page_feishu_configs`` 加 ``sub_tables`` JSON（附加页签清单）；
- ``page_table_mirror_records`` 加 ``table_id`` 列并把唯一索引升级为
  ``(page_key, table_id, record_id)``，存量行按各页主绑定表回填。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9f1a5e3b8d2"
down_revision: str | None = "b7d9e2f4a6c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "sub_tables",
            sa.JSON(),
            nullable=True,
            comment=(
                "附加子表页签 [{table_id, tab_name, hidden_field_names}]；"
                "主绑定（table_id 列）是第一个页签，本列表是其余页签"
            ),
        ),
        schema="safety",
    )
    op.add_column(
        "page_table_mirror_records",
        sa.Column(
            "table_id",
            sa.String(length=64),
            nullable=True,
            server_default="",
            comment="所属飞书子表 table_id（多页签页面区分数据来源）",
        ),
        schema="safety",
    )
    # 存量镜像行回填为其页面主绑定的 table_id（无绑定的页面填空串）
    op.execute(
        """
        UPDATE safety.page_table_mirror_records AS m
        SET table_id = COALESCE(
            (SELECT c.table_id FROM safety.page_feishu_configs AS c
             WHERE c.page_key = m.page_key AND c.is_deleted = false
             ORDER BY c.updated_at DESC LIMIT 1),
            '')
        WHERE m.table_id IS NULL OR m.table_id = ''
        """
    )
    op.alter_column(
        "page_table_mirror_records",
        "table_id",
        nullable=False,
        schema="safety",
    )
    op.drop_index(
        "uq_safety_page_table_mirror_records_page_record",
        table_name="page_table_mirror_records",
        schema="safety",
    )
    op.create_index(
        "uq_safety_page_table_mirror_records_page_table_record",
        "page_table_mirror_records",
        ["page_key", "table_id", "record_id"],
        unique=True,
        schema="safety",
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_safety_page_table_mirror_records_page_table_record",
        table_name="page_table_mirror_records",
        schema="safety",
    )
    op.create_index(
        "uq_safety_page_table_mirror_records_page_record",
        "page_table_mirror_records",
        ["page_key", "record_id"],
        unique=True,
        schema="safety",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_column("page_table_mirror_records", "table_id", schema="safety")
    op.drop_column("page_feishu_configs", "sub_tables", schema="safety")
