"""Add procurement material source configuration.

Revision ID: c8e4f1a2b3d5
Revises: b3d7f1a9c2e4
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8e4f1a2b3d5"
down_revision: str | None = "b3d7f1a9c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_source_configs",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            nullable=False,
        ),
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
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "config_key",
            sa.String(length=64),
            server_default="material-master",
            nullable=False,
            comment="配置业务键",
        ),
        sa.Column(
            "source_url",
            sa.String(length=1024),
            nullable=False,
            comment="飞书多维表格原始链接",
        ),
        sa.Column(
            "app_token",
            sa.String(length=128),
            nullable=False,
            comment="解析后的多维表格 app_token",
        ),
        sa.Column(
            "table_id",
            sa.String(length=128),
            nullable=False,
            comment="解析后的多维表格 table_id",
        ),
        sa.Column(
            "view_id",
            sa.String(length=128),
            nullable=True,
            comment="解析后的多维表格 view_id",
        ),
        sa.Column(
            "material_code_field",
            sa.String(length=128),
            nullable=False,
            comment="物料编码实际字段名",
        ),
        sa.Column(
            "material_description_field",
            sa.String(length=128),
            nullable=False,
            comment="物料说明实际字段名",
        ),
        sa.Column(
            "rule_model_field",
            sa.String(length=128),
            nullable=False,
            comment="规格型号实际字段名",
        ),
        sa.Column(
            "last_test_status",
            sa.String(length=32),
            server_default="not_tested",
            nullable=False,
            comment="最近测试状态",
        ),
        sa.Column(
            "last_test_error",
            sa.Text(),
            nullable=True,
            comment="最近测试错误（不含第三方原始响应）",
        ),
        sa.Column(
            "last_tested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近测试时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "config_key",
            name="uq_procurement_material_source_config_key",
        ),
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_material_source_config_active",
        "material_source_configs",
        ["config_key", "is_deleted"],
        unique=False,
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_procurement_material_source_config_active",
        table_name="material_source_configs",
        schema="procurement",
    )
    op.drop_table("material_source_configs", schema="procurement")
