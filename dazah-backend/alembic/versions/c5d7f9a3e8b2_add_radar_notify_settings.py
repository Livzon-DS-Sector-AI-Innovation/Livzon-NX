"""add regulation radar notify settings to safety.feishu_app_settings

法规雷达扫描结果可推送飞书群/个人，接收目标在设置页配置。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5d7f9a3e8b2"
down_revision: str | None = "a7c3e5b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "radar_notify_enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="法规雷达扫描后是否推送飞书通知",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "radar_notify_chat_ids",
            sa.JSON(),
            nullable=True,
            comment="通知群 chat_id 列表",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "radar_notify_user_ids",
            sa.JSON(),
            nullable=True,
            comment="通知个人 open_id 列表",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column("feishu_app_settings", "radar_notify_user_ids", schema="safety")
    op.drop_column("feishu_app_settings", "radar_notify_chat_ids", schema="safety")
    op.drop_column("feishu_app_settings", "radar_notify_enabled", schema="safety")
