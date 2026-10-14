"""add safety.page_feishu_configs.workshop_aliases

仪表盘按车间聚合需要把自由文本里的别名归一到规范车间名（如 DR车间/DR提炼/
霉酚酸提炼 都算 201二车间）。映射存配置行，由「安全飞书设置」页维护，
避免把车间别名写死在代码里。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8a2c6d4b0f7"
down_revision: str | None = "c5d7e9a1b3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "workshop_aliases",
            sa.JSON(),
            nullable=True,
            comment="车间别名归一映射（{别名: 规范车间名}），供仪表盘按车间聚合使用",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column("page_feishu_configs", "workshop_aliases", schema="safety")
