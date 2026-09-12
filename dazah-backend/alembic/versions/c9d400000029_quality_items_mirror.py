"""add quality items local mirror tables

质量管理-质量检验-物品管理本地镜像：照搬仓储 material_page_snapshots /
material_page_rows 模式，为物品三张飞书多维表格（qc_items_inventory /
qc_items_inbound / qc_items_outbound）建本地镜像页快照 + 行表（cells 以中文
列名为键），列表读取改为读本地镜像，全量回填 + 增量双路单页同步。另建
quality_items_stock_alert_notifications 作为库存不足一键推送的幂等记录表。

列注释与 ORM（quality/models/inspection_items_mirror.py）逐列一致。

Revision ID: c9d400000029
Revises: c9d400000028
Create Date: 2026-09-11 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000029"
down_revision: str | None = "c9d400000028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
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
            "is_deleted", sa.Boolean(), server_default="false", nullable=False
        ),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table("quality_items_page_snapshots", schema="quality"):
        op.create_table(
            "quality_items_page_snapshots",
            sa.Column(
                "page_key",
                sa.String(length=64),
                nullable=False,
                comment="镜像页唯一键（=飞书实体编码）",
            ),
            sa.Column(
                "page_title", sa.String(length=255), nullable=False, comment="页面标题"
            ),
            sa.Column(
                "table_name",
                sa.String(length=255),
                nullable=False,
                comment="飞书来源表名",
            ),
            sa.Column(
                "table_id",
                sa.String(length=64),
                nullable=False,
                comment="飞书 table_id",
            ),
            sa.Column(
                "source",
                sa.String(length=64),
                server_default="feishu_bitable",
                nullable=False,
                comment="快照来源",
            ),
            sa.Column(
                "columns",
                postgresql.JSONB(astext_type=sa.Text()),
                # PG 的 JSONB 默认值必须是合法表达式：裸 [] 会语法错误
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
                comment="列结构快照（key/title/field_type/ui_type/editable）",
            ),
            sa.Column(
                "total_rows",
                sa.Integer(),
                server_default="0",
                nullable=False,
                comment="同步行数（增量轮次后以本地存量修正）",
            ),
            sa.Column(
                "last_error", sa.Text(), nullable=True, comment="最近一次同步错误"
            ),
            sa.Column(
                "last_synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
                comment="最近同步时间（增量水线）",
            ),
            *_base_columns(),
            sa.PrimaryKeyConstraint("id"),
            schema="quality",
        )
        op.create_index(
            "ix_quality_items_page_snapshots_page_key",
            "quality_items_page_snapshots",
            ["page_key"],
            unique=True,
            schema="quality",
        )

    if not inspector.has_table("quality_items_page_rows", schema="quality"):
        op.create_table(
            "quality_items_page_rows",
            sa.Column(
                "page_snapshot_id",
                sa.Uuid(),
                nullable=False,
                comment="所属页快照 ID",
            ),
            sa.Column(
                "source_record_id",
                sa.String(length=64),
                nullable=False,
                comment="飞书记录 ID",
            ),
            sa.Column(
                "row_order",
                sa.Integer(),
                server_default="0",
                nullable=False,
                comment="行序号",
            ),
            sa.Column(
                "cells",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
                comment="整行内容快照（中文列名为键，值已归一化）",
            ),
            sa.Column(
                "search_text",
                sa.Text(),
                server_default="",
                nullable=False,
                comment="关键词检索串",
            ),
            sa.Column(
                "last_synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
                comment="最近同步时间",
            ),
            *_base_columns(),
            sa.ForeignKeyConstraint(
                ["page_snapshot_id"],
                ["quality.quality_items_page_snapshots.id"],
                name="fk_quality_items_page_rows_snapshot",
            ),
            sa.PrimaryKeyConstraint("id"),
            schema="quality",
        )
        op.create_index(
            "ix_quality_items_page_rows_page_id",
            "quality_items_page_rows",
            ["page_snapshot_id"],
            schema="quality",
        )
        op.create_index(
            "ix_quality_items_page_rows_source_record_id",
            "quality_items_page_rows",
            ["source_record_id"],
            schema="quality",
        )
        op.create_index(
            "ix_quality_items_page_rows_page_record",
            "quality_items_page_rows",
            ["page_snapshot_id", "source_record_id"],
            unique=True,
            schema="quality",
        )

    if not inspector.has_table(
        "quality_items_stock_alert_notifications", schema="quality"
    ):
        op.create_table(
            "quality_items_stock_alert_notifications",
            sa.Column(
                "page_key",
                sa.String(length=64),
                nullable=False,
                comment="镜像页键（qc_items_inventory）",
            ),
            sa.Column(
                "source_record_id",
                sa.String(length=64),
                nullable=False,
                comment="物料飞书记录 ID",
            ),
            sa.Column(
                "recipient_open_id",
                sa.String(length=128),
                nullable=False,
                comment="接收人 open_id（或姓名兜底键）",
            ),
            sa.Column(
                "recipient_name",
                sa.String(length=128),
                nullable=True,
                comment="接收人姓名快照",
            ),
            sa.Column(
                "period_key",
                sa.String(length=32),
                nullable=False,
                comment="推送周期标识（默认 YYYY-MM-DD）",
            ),
            sa.Column(
                "item_name",
                sa.String(length=255),
                nullable=True,
                comment="物料名称快照",
            ),
            sa.Column(
                "feishu_message_id",
                sa.String(length=128),
                nullable=True,
                comment="飞书消息 ID",
            ),
            sa.Column(
                "notification_status",
                sa.String(length=20),
                server_default="sent",
                nullable=False,
                comment="推送状态：sent/failed",
            ),
            sa.Column(
                "notified_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
                comment="推送时间",
            ),
            *_base_columns(),
            sa.PrimaryKeyConstraint("id"),
            schema="quality",
        )
        op.create_index(
            "ix_quality_items_stock_alert_notify_unique",
            "quality_items_stock_alert_notifications",
            ["page_key", "source_record_id", "recipient_open_id", "period_key"],
            unique=True,
            schema="quality",
        )
        op.create_index(
            "ix_quality_items_stock_alert_notify_period",
            "quality_items_stock_alert_notifications",
            ["period_key"],
            schema="quality",
        )


def downgrade() -> None:
    op.drop_index(
        "ix_quality_items_stock_alert_notify_period",
        table_name="quality_items_stock_alert_notifications",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_items_stock_alert_notify_unique",
        table_name="quality_items_stock_alert_notifications",
        schema="quality",
    )
    op.drop_table("quality_items_stock_alert_notifications", schema="quality")

    op.drop_index(
        "ix_quality_items_page_rows_page_record",
        table_name="quality_items_page_rows",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_items_page_rows_source_record_id",
        table_name="quality_items_page_rows",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_items_page_rows_page_id",
        table_name="quality_items_page_rows",
        schema="quality",
    )
    op.drop_table("quality_items_page_rows", schema="quality")

    op.drop_index(
        "ix_quality_items_page_snapshots_page_key",
        table_name="quality_items_page_snapshots",
        schema="quality",
    )
    op.drop_table("quality_items_page_snapshots", schema="quality")
