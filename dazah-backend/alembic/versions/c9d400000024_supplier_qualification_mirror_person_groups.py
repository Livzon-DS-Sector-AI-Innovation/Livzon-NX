"""add supplier_qualification_records person/groups mirror columns

供应商资质镜像表补充负责人成员对象与群组展示列：
- responsible_users：飞书「负责人」成员字段原始对象 [{id(ou_), name}]，
  供本地编辑多选后按 ou_ 写回飞书，也便于后续按 open_id 关联头像；
- groups：飞书「群组」群聊字段 [{id(oc_), name, avatar_url}]，
  GroupChat 类型不支持 API 写入，仅镜像展示。
两列均可空，回拉映射兜底写 None。

Revision ID: c9d400000024
Revises: c9d400000023
Create Date: 2026-09-09 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000024"
down_revision: str | None = "b7c9e1f4a6d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "supplier_qualification_records",
        sa.Column(
            "responsible_users",
            sa.JSON(),
            nullable=True,
            comment="负责人飞书成员对象列表 [{id, name}]（写回飞书用）",
        ),
        schema="quality",
    )
    op.add_column(
        "supplier_qualification_records",
        sa.Column(
            "groups",
            sa.JSON(),
            nullable=True,
            comment="群组飞书群聊对象列表 [{id, name, avatar_url}]（只读展示）",
        ),
        schema="quality",
    )


def downgrade() -> None:
    op.drop_column("supplier_qualification_records", "groups", schema="quality")
    op.drop_column(
        "supplier_qualification_records", "responsible_users", schema="quality"
    )
