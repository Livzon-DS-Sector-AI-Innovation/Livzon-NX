"""add warehouse material status transitions

仓储检验进度统计：新增 warehouse.material_status_transitions 状态变更日志表。
同步镜像行时对比受监控字段（入库总账「检测结果」/成品明细「质量状态」），
记录每次取值变化与新行初始状态，occurred_at 取飞书记录 last_modified_time，
供检验周期统计（入库→待验→合格/不合格分段时长）使用。

Revision ID: a7c8d9e0f1b2
Revises: c9d400000024
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c8d9e0f1b2"
down_revision: str | None = "c9d400000024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_status_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "page_key", sa.String(length=64), nullable=False, comment="页面唯一键"
        ),
        sa.Column(
            "page_snapshot_id",
            sa.Uuid(),
            nullable=False,
            comment="所属页面快照 ID",
        ),
        sa.Column(
            "source_record_id",
            sa.String(length=64),
            nullable=False,
            comment="飞书记录 ID",
        ),
        sa.Column(
            "field_name",
            sa.String(length=64),
            nullable=False,
            comment="监控字段名（检测结果/质量状态）",
        ),
        sa.Column(
            "old_value",
            sa.String(length=64),
            nullable=True,
            comment="变更前取值（初始记录为空）",
        ),
        sa.Column(
            "new_value",
            sa.String(length=64),
            nullable=True,
            comment="变更后取值（清空时为空）",
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="状态发生时刻（飞书记录最后修改时间）",
        ),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="同步捕获时刻",
        ),
        sa.ForeignKeyConstraint(
            ["page_snapshot_id"],
            ["warehouse.material_page_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="物料/成品质量状态变更日志（检验周期统计数据源）",
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_material_status_transitions_page_record",
        "material_status_transitions",
        ["page_key", "source_record_id"],
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_material_status_transitions_occurred_at",
        "material_status_transitions",
        ["occurred_at"],
        schema="warehouse",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_warehouse_material_status_transitions_occurred_at",
        table_name="material_status_transitions",
        schema="warehouse",
    )
    op.drop_index(
        "ix_warehouse_material_status_transitions_page_record",
        table_name="material_status_transitions",
        schema="warehouse",
    )
    op.drop_table("material_status_transitions", schema="warehouse")
