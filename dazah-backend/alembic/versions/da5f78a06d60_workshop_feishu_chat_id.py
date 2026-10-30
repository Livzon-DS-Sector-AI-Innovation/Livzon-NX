"""workshops add feishu repair chat id

Revision ID: da5f78a06d60
Revises: a7c3e5f1b8d2
Create Date: 2026-10-29

车间各自的维修群：派单卡片按工单所属车间路由到对应群；
未配置的车间回落全局默认群（FEISHU_EQUIPMENT_CHAT_ID）。
"""

import sqlalchemy as sa

from alembic import op

revision = "da5f78a06d60"
down_revision = "a7c3e5f1b8d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workshops",
        sa.Column(
            "feishu_chat_id",
            sa.String(length=64),
            nullable=True,
            comment="车间维修群 chat_id；派单卡按此路由，空则回落全局默认群",
        ),
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_column("workshops", "feishu_chat_id", schema="equipment")
