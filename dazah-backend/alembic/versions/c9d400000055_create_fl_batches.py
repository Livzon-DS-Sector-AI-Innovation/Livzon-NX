"""create production.fl_batches for florfenicol premix batch flow"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c9d400000055"
down_revision: str | None = "c9d400000054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 氟苯尼考预混剂批次工序流转：飞书多维表按月分表同步入库，
    # 以生产批号全局唯一（软删除记录不参与唯一约束）
    op.create_table(
        "fl_batches",
        sa.Column(
            "batch_no",
            sa.String(length=64),
            nullable=False,
            comment="生产批号（FL-YYMM+月内流水，如 FL-2609001）",
        ),
        sa.Column("order_date", sa.Date(), nullable=True, comment="指令日期"),
        sa.Column("pick_date", sa.Date(), nullable=True, comment="领料日期"),
        sa.Column("charge_date", sa.Date(), nullable=True, comment="投料日期"),
        sa.Column(
            "charge_time",
            sa.String(length=64),
            nullable=True,
            comment="投料时间（文本区间，如 8:00~10:00）",
        ),
        sa.Column("mix_date", sa.Date(), nullable=True, comment="混合（生产）日期"),
        sa.Column(
            "mix_time",
            sa.String(length=64),
            nullable=True,
            comment="混合时间（文本区间）",
        ),
        sa.Column(
            "spec",
            sa.String(length=128),
            nullable=True,
            comment="规格（如 10kg/袋、2袋/箱）",
        ),
        sa.Column(
            "pack_weight_kg",
            sa.Float(),
            nullable=True,
            comment="包装重量实际值（kg）",
        ),
        sa.Column("pack_date", sa.Date(), nullable=True, comment="包装日期"),
        sa.Column(
            "pack_time",
            sa.String(length=64),
            nullable=True,
            comment="包装时间（文本区间）",
        ),
        sa.Column("inspection_date", sa.Date(), nullable=True, comment="请检日期"),
        sa.Column("inbound_date", sa.Date(), nullable=True, comment="入库日期"),
        sa.Column(
            "source_table",
            sa.String(length=128),
            nullable=True,
            comment="来源飞书月表名（如 9月排产）",
        ),
        sa.Column(
            "data_month",
            sa.String(length=7),
            nullable=True,
            comment="归组月份 YYYY-MM（按批号 YYMM）",
        ),
        sa.Column(
            "sync_note", sa.Text(), nullable=True, comment="同步备注（异常与跳过原因）"
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_fl_batches_data_month",
        "fl_batches",
        ["data_month"],
        unique=False,
        schema="production",
    )
    op.create_index(
        "uq_fl_batches_batch_no",
        "fl_batches",
        ["batch_no"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_fl_batches_batch_no", table_name="fl_batches", schema="production"
    )
    op.drop_index(
        "ix_fl_batches_data_month", table_name="fl_batches", schema="production"
    )
    op.drop_table("fl_batches", schema="production")
