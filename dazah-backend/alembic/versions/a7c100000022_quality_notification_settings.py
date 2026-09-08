"""add quality notification settings

Revision ID: a7c100000022
Revises: a7c100000021
Create Date: 2026-09-07 10:00:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000022"
down_revision: str | None = "a7c100000021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_CHANGE_ACTION_PLAN_ID = "a7c10000-0000-0000-0000-000000000301"
_SEED_INSPECTION_TREND_ALERT_ID = "a7c10000-0000-0000-0000-000000000302"

# 与 FINISHED_DASHBOARD_RECIPIENT_OVERRIDES 保持一致的初始通知对象
_SEED_INSPECTION_LINE_RECIPIENTS: dict[str, list[dict[str, str]]] = {
    "qc_finished_internal": [{"name": "陈连平"}, {"name": "席晓"}],
    "qc_finished_high_spec": [{"name": "陈连平"}, {"name": "席晓"}],
    "qc_finished_mvt": [{"name": "罗勇"}, {"name": "周方圆"}],
    "qc_finished_lft_ep": [{"name": "罗勇"}, {"name": "周方圆"}],
    "qc_finished_lft_usp": [{"name": "罗勇"}, {"name": "周方圆"}],
    "qc_finished_dor_gb": [{"name": "梁友辉"}, {"name": "席晓"}],
    "qc_finished_dor_vet": [{"name": "梁友辉"}, {"name": "席晓"}],
    "qc_finished_lkms_vet": [{"name": "刘伟"}, {"name": "严红玲"}],
}

_SEED_INSPECTION_LINE_CODES = [
    "qc_finished_internal",
    "qc_finished_high_spec",
    "qc_finished_mvt",
    "qc_finished_lft_ep",
    "qc_finished_lft_usp",
    "qc_finished_dor_gb",
    "qc_finished_dor_vet",
    "qc_finished_lkms_vet",
    "qc_finished_fcc14",
    "qc_finished_bbas_hanguang_k1",
    "qc_finished_trp_powder",
    "qc_finished_trp_granule",
    "qc_finished_flu_powder",
    "qc_finished_fen_powder",
    "qc_finished_pure_water",
]


def _build_inspection_recipients() -> str:
    lines = {
        code: {
            "enabled": True,
            "recipients": _SEED_INSPECTION_LINE_RECIPIENTS.get(code, []),
        }
        for code in _SEED_INSPECTION_LINE_CODES
    }
    return json.dumps({"lines": lines}, ensure_ascii=False)


_INSERT_SQL = sa.text(
    """
    INSERT INTO quality.quality_notification_settings (
        id, notification_type, notification_label, is_enabled,
        lead_days, repeat_interval_days, send_time, recipients, sort_order,
        created_at, updated_at, is_deleted
    ) VALUES (
        :id, :notification_type, :notification_label, :is_enabled,
        :lead_days, :repeat_interval_days, :send_time,
        CAST(:recipients AS json), :sort_order,
        now(), now(), false
    )
    ON CONFLICT (notification_type) DO NOTHING
    """
)


def _seed_rows() -> list[dict[str, object]]:
    return [
        {
            "id": _SEED_CHANGE_ACTION_PLAN_ID,
            "notification_type": "change_action_plan_due",
            "notification_label": "变更计划到期提醒",
            "is_enabled": True,
            "lead_days": 3,
            "repeat_interval_days": 1,
            "send_time": "09:00",
            "recipients": json.dumps({"fallback_recipients": []}),
            "sort_order": 1,
        },
        {
            "id": _SEED_INSPECTION_TREND_ALERT_ID,
            "notification_type": "inspection_trend_alert",
            "notification_label": "成品检验趋势异常提醒",
            "is_enabled": True,
            "lead_days": 3,
            "repeat_interval_days": 1,
            "send_time": "09:00",
            "recipients": _build_inspection_recipients(),
            "sort_order": 2,
        },
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    if not inspector.has_table("quality_notification_settings", schema="quality"):
        op.create_table(
            "quality_notification_settings",
            sa.Column("notification_type", sa.String(length=50), nullable=False),
            sa.Column("notification_label", sa.String(length=100), nullable=False),
            sa.Column(
                "is_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "lead_days", sa.Integer(), nullable=False, server_default="3"
            ),
            sa.Column(
                "repeat_interval_days",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "send_time", sa.String(length=5), nullable=False, server_default="09:00"
            ),
            sa.Column("recipients", sa.JSON(), nullable=True),
            sa.Column(
                "sort_order", sa.Integer(), nullable=False, server_default="0"
            ),
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
            sa.UniqueConstraint(
                "notification_type",
                name="uq_quality_notification_settings_notification_type",
            ),
            schema="quality",
        )

    for row in _seed_rows():
        bind.execute(_INSERT_SQL, row)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("quality_notification_settings", schema="quality"):
        op.drop_table("quality_notification_settings", schema="quality")
