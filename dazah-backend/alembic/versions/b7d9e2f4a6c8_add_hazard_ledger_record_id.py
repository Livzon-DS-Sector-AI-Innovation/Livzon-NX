"""add safety.hazard_reports.ledger_record_id for company ledger projection

隐患随手拍登记（旧隐患登记/AI 识别/三级复核流程）后把记录汇总写入公司
隐患总台账（飞书多维表格，由「隐患随手拍」镜像页展示）。本列保存写入后的
总台账 record_id，作为后续进度同步（整改回复/复核关闭回写）的幂等锚点；
不复用已被旧隐患流程表占用的 feishu_record_id。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7d9e2f4a6c8"
down_revision: str | None = "c9d400000060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hazard_reports",
        sa.Column(
            "ledger_record_id",
            sa.String(length=64),
            nullable=True,
            comment="公司隐患总台账（隐患随手拍页）飞书记录 ID，汇总写入锚点",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column("hazard_reports", "ledger_record_id", schema="safety")
