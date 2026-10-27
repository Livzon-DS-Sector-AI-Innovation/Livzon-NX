"""regulation_no optional

安全操作规程编号改为可选：
- ``safety.operation_regulations.regulation_no`` 取消 NOT NULL，
  批量导入/标准化生成的记录编号留空，由文控或车间编号时再填写；
- 局部唯一索引（is_deleted = false）对 NULL 不生效，多条无编号记录可共存。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f2a7c9e4b5d3"
down_revision: str | None = "c3e8b1a4f7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "operation_regulations",
        "regulation_no",
        existing_type="VARCHAR(64)",
        nullable=True,
        comment="操规编号（可为空，由文控/车间编号时填写）",
        schema="safety",
    )


def downgrade() -> None:
    # 回滚前要求所有记录都有编号，否则 NOT NULL 约束无法建立
    op.alter_column(
        "operation_regulations",
        "regulation_no",
        existing_type="VARCHAR(64)",
        nullable=False,
        comment="操规编号",
        schema="safety",
    )
