"""add radar_scan_enabled switch to safety.feishu_app_settings

法规雷达自动扫描开关（控制每周一 08:00 的定时扫描是否执行）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9e1f2a4b6c8"
down_revision: str | None = "c5d7f9a3e8b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "radar_scan_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="是否启用法规雷达自动扫描（每周一 08:00）",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column("feishu_app_settings", "radar_scan_enabled", schema="safety")
