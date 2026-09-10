"""add quality_feishu_entity_settings feishu_form_url column

验证主计划各年度台账新增「飞书多维表单分享链接」：
新增记录改为打开对应年度的飞书表单（表单可写群组等开放接口不支持的字段），
2024/2025/2026 由代码预填默认表单，2027/2028 预留、后续在
质量管理-设置-飞书设置中粘贴表单链接即可关联。

Revision ID: c9d400000025
Revises: a7c8d9e0f1b2
Create Date: 2026-09-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000025"
down_revision: str | None = "a7c8d9e0f1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quality_feishu_entity_settings",
        sa.Column(
            "feishu_form_url",
            sa.String(length=512),
            nullable=True,
            comment="飞书多维表单分享链接（新增记录改为打开表单录入）",
        ),
        schema="quality",
    )


def downgrade() -> None:
    op.drop_column(
        "quality_feishu_entity_settings",
        "feishu_form_url",
        schema="quality",
    )
