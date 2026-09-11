"""add notification message templates

注册证书到期提醒与法规推送两类通知开放「开头语/结尾语」模板配置：
registration.certificate_reminder_settings、regulatory_tracker.notification_settings
各加 header_template / footer_template 可空字段，空值走代码内置默认文案。

Revision ID: c9d400000027
Revises: c9d400000026
Create Date: 2026-09-11 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000027"
down_revision: str | None = "c9d400000026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEMPLATE_COLUMNS = [
    sa.Column(
        "header_template",
        sa.Text(),
        nullable=True,
        comment="消息开头语模板（空用内置默认）",
    ),
    sa.Column(
        "footer_template",
        sa.Text(),
        nullable=True,
        comment="消息结尾语模板（空用内置默认）",
    ),
]


def upgrade() -> None:
    for schema, table in (
        ("registration", "certificate_reminder_settings"),
        ("regulatory_tracker", "notification_settings"),
    ):
        for column in TEMPLATE_COLUMNS:
            op.add_column(
                table,
                column.copy(),
                schema=schema,
            )


def downgrade() -> None:
    for schema, table in (
        ("registration", "certificate_reminder_settings"),
        ("regulatory_tracker", "notification_settings"),
    ):
        op.drop_column(table, "footer_template", schema=schema)
        op.drop_column(table, "header_template", schema=schema)
