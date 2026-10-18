"""隐患到期提醒推送：设置表新增开关/提醒节点/通知目标列 + 推送记录表。

提醒节点为 JSON 天数数组（如 [30,15,7]）：隐患目标完成日期进入某节点
才推送一次，逾期再推一次；推送记录表保证每个节点只推一次。

Revision ID: d4e7f1a9c3b5
Revises: c9f1a5e3b8d2
Create Date: 2026-10-17

"""

import sqlalchemy as sa

from alembic import op

revision = "d4e7f1a9c3b5"
down_revision = "c9f1a5e3b8d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "hazard_due_notify_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="是否启用隐患到期提醒推送（每天检查，进入提醒节点才推送）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "hazard_due_notify_milestones",
            sa.JSON(),
            nullable=True,
            comment=(
                "提醒节点天数列表（如 [30,15,7]：到期前一个月/半个月/一周各提醒一次）"
            ),
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "hazard_due_notify_chat_ids",
            sa.JSON(),
            nullable=True,
            comment="到期提醒群 chat_id 列表",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "hazard_due_notify_user_ids",
            sa.JSON(),
            nullable=True,
            comment="到期提醒个人 open_id 列表",
        ),
        schema="safety",
    )
    op.create_table(
        "hazard_due_notification_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("table_id", sa.String(length=64), nullable=False),
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column(
            "milestone_days",
            sa.Integer(),
            nullable=False,
            comment="触发的提醒节点天数；0 表示已逾期节点",
        ),
        sa.Column(
            "notified_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by", sa.UUID(), sa.ForeignKey("identity.users.id"), nullable=True
        ),
        sa.Column(
            "updated_by", sa.UUID(), sa.ForeignKey("identity.users.id"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "table_id",
            "record_id",
            "milestone_days",
            name="uq_hazard_due_notify_once_per_milestone",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_table("hazard_due_notification_log", schema="safety")
    op.drop_column("feishu_app_settings", "hazard_due_notify_user_ids", schema="safety")
    op.drop_column("feishu_app_settings", "hazard_due_notify_chat_ids", schema="safety")
    op.drop_column(
        "feishu_app_settings", "hazard_due_notify_milestones", schema="safety"
    )
    op.drop_column("feishu_app_settings", "hazard_due_notify_enabled", schema="safety")
