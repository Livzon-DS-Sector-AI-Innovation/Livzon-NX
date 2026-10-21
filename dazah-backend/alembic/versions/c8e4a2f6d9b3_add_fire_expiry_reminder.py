"""fire equipment expiry reminder columns

消防器材有效期到期提醒：
- ``safety.fire_equipment`` 加 ``expiry_date``（投影自飞书 有效日期 等字段）；
- ``safety.feishu_app_settings`` 加 ``fire_expiry_notify_*`` 设置
  （开关 / 节点天数 / 群与个人目标，与隐患到期提醒同口径）；
- 新表 ``safety.fire_expiry_notification_log``：每台器材每个节点只推一次。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8e4a2f6d9b3"
down_revision: str | None = "a9c1e3f5b7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fire_equipment",
        sa.Column(
            "expiry_date",
            sa.Date(),
            nullable=True,
            comment="有效日期（投影自飞书 有效日期/有效期 等字段）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "fire_expiry_notify_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="是否启用消防器材有效期到期提醒（每天检查，进入提醒节点才推送）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "fire_expiry_notify_milestones",
            sa.JSON(),
            nullable=True,
            comment="有效期提醒节点天数列表（如 [30,15,7]；0 = 已过期节点）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "fire_expiry_notify_chat_ids",
            sa.JSON(),
            nullable=True,
            comment="有效期提醒群 chat_id 列表",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "fire_expiry_notify_user_ids",
            sa.JSON(),
            nullable=True,
            comment="有效期提醒个人 open_id 列表",
        ),
        schema="safety",
    )
    op.create_table(
        "fire_expiry_notification_log",
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=False,
                  comment="器材 id（safety.fire_equipment）"),
        sa.Column("milestone_days", sa.Integer(), nullable=False,
                  comment="触发的提醒节点天数；0 表示已过期节点"),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.ForeignKeyConstraint(
            ["equipment_id"], ["safety.fire_equipment.id"]
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "equipment_id",
            "milestone_days",
            name="uq_fire_expiry_notify_once_per_milestone",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_table("fire_expiry_notification_log", schema="safety")
    op.drop_column("feishu_app_settings", "fire_expiry_notify_user_ids",
                   schema="safety")
    op.drop_column("feishu_app_settings", "fire_expiry_notify_chat_ids",
                   schema="safety")
    op.drop_column("feishu_app_settings", "fire_expiry_notify_milestones",
                   schema="safety")
    op.drop_column("feishu_app_settings", "fire_expiry_notify_enabled",
                   schema="safety")
    op.drop_column("fire_equipment", "expiry_date", schema="safety")
