"""equipment feishu app library for inspection configs

Revision ID: c9d400000064
Revises: c9d400000063
Create Date: 2026-10-21 04:10:00.000000
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000064"
down_revision: str = "c9d400000063"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "feishu_apps",
        # 部分唯一索引：未删除行内 App ID 唯一，删除后可重建
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False,
                  comment="应用名称（便于辨认，如：设备巡检同步应用）"),
        sa.Column("app_id", sa.String(length=100), nullable=False,
                  comment="飞书应用 App ID"),
        sa.Column("app_secret", sa.Text(), nullable=False,
                  comment="飞书应用 App Secret（加密存储）"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        schema="equipment",
    )
    op.create_index(
        "uq_feishu_apps_app_id",
        "feishu_apps",
        ["app_id"],
        unique=True,
        schema="equipment",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.add_column(
        "inspection_feishu_config",
        sa.Column(
            "feishu_app_id",
            sa.Uuid(),
            sa.ForeignKey("equipment.feishu_apps.id"),
            nullable=True,
            comment="引用的自建应用库记录；空=使用本行内联凭据",
        ),
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_column("inspection_feishu_config", "feishu_app_id", schema="equipment")
    op.drop_index("uq_feishu_apps_app_id", table_name="feishu_apps", schema="equipment")
    op.drop_table("feishu_apps", schema="equipment")
