"""add quality_trend_alert_escalations + seed escalation notification row

成品/纯化水异常升级推送：
- 新表 quality.quality_trend_alert_escalations：首波告警后入队，到点由
  周期 Generator 复检，仍异常升级推送各部门负责人（status+escalate_at 索引
  供扫描，retry_count 防死循环）。
- quality_notification_settings 播种第三行 inspection_trend_alert_escalation
  （首推人默认李文昊、2 小时），ON CONFLICT DO NOTHING 幂等。

Revision ID: c9d400000028
Revises: c9d400000027
Create Date: 2026-09-11 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000028"
down_revision: str | None = "c9d400000027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table("quality_trend_alert_escalations", schema="quality"):
        op.create_table(
            "quality_trend_alert_escalations",
            sa.Column("entity_code", sa.String(length=64), nullable=False),
            sa.Column("source_label", sa.String(length=128), nullable=True),
            sa.Column("batch_no", sa.String(length=128), nullable=False),
            sa.Column("metric_key", sa.String(length=256), nullable=False),
            sa.Column("metric_label", sa.String(length=256), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("first_message_id", sa.String(length=128), nullable=True),
            sa.Column(
                "first_notified_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column(
                "status",
                sa.String(length=32),
                server_default="pending",
                nullable=False,
            ),
            sa.Column("escalate_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "escalated_message_id", sa.String(length=128), nullable=True
            ),
            sa.Column("retry_count", sa.Integer(), nullable=False),
            sa.Column("last_error", sa.Text(), nullable=True),
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
            sa.PrimaryKeyConstraint("id"),
            schema="quality",
        )
        op.create_index(
            "ix_quality_trend_alert_escalation_status_escalate_at",
            "quality_trend_alert_escalations",
            ["status", "escalate_at"],
            schema="quality",
        )

    op.execute(
        """
        INSERT INTO quality.quality_notification_settings (
            notification_type, notification_label, is_enabled,
            lead_days, repeat_interval_days, send_time,
            recipients, sort_order, id
        )
        VALUES (
            'inspection_trend_alert_escalation',
            '成品/纯化水异常升级推送',
            true,
            3, 1, '09:00',
            '{"first_recipients": [{"name": "李文昊"}], "escalation_hours": 2}',
            3,
            '10000000-0000-0000-0000-000000000303'
        )
        ON CONFLICT (notification_type) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM quality.quality_notification_settings "
        "WHERE notification_type = 'inspection_trend_alert_escalation'"
    )
    op.drop_index(
        "ix_quality_trend_alert_escalation_status_escalate_at",
        table_name="quality_trend_alert_escalations",
        schema="quality",
    )
    op.drop_table("quality_trend_alert_escalations", schema="quality")
