"""add base_url to equipment inspection feishu config

Revision ID: c9d400000062
Revises: c9d400000061
Create Date: 2026-10-20 14:30:00.000000
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000062"
down_revision: str = "c9d400000061"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "inspection_feishu_config",
        sa.Column(
            "base_url",
            sa.String(length=500),
            nullable=False,
            server_default="",
            comment="多维表格完整链接（含租户域名，用于飞书配置页直达）",
        ),
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_column("inspection_feishu_config", "base_url", schema="equipment")
