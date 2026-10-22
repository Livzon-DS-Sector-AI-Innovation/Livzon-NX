"""fire inspection writeback columns

点检记录写回飞书多维表格：
- ``safety.page_feishu_configs`` 加 ``writeback_table_id``（点检记录回写子表，
  灭火器/消防栓点检页专用，与器材台账同 Base）；
- ``safety.fire_inspection_records`` 加 ``feishu_record_id``（回写锚点，
  NULL 表示待回写，同步循环自动补写）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b6f2d8a4c1e7"
down_revision: str | None = "e3a7c5d9b1f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "writeback_table_id",
            sa.String(length=100),
            nullable=True,
            comment="点检记录回写子表 table_id（灭火器/消防栓点检页专用，同一 Base）",
        ),
        schema="safety",
    )
    op.add_column(
        "fire_inspection_records",
        sa.Column(
            "feishu_record_id",
            sa.String(length=64),
            nullable=True,
            comment="回写飞书点检记录表的 record_id（NULL=待回写）",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column(
        "fire_inspection_records", "feishu_record_id", schema="safety"
    )
    op.drop_column("page_feishu_configs", "writeback_table_id", schema="safety")
