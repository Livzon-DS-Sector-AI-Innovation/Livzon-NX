"""Add procurement material catalog mirror and sync metadata.

Revision ID: e6a7b8c9d0e1
Revises: d4f6a8b0c2e1
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6a7b8c9d0e1"
down_revision: str | None = "d4f6a8b0c2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "material_source_configs",
        sa.Column(
            "sync_status",
            sa.String(length=32),
            server_default="not_synced",
            nullable=False,
            comment="最近同步状态",
        ),
        schema="procurement",
    )
    op.add_column(
        "material_source_configs",
        sa.Column(
            "sync_error",
            sa.Text(),
            nullable=True,
            comment="最近同步错误（不含第三方原始响应）",
        ),
        schema="procurement",
    )
    op.add_column(
        "material_source_configs",
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近成功同步时间",
        ),
        schema="procurement",
    )
    op.add_column(
        "material_source_configs",
        sa.Column(
            "last_sync_record_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="最近成功同步记录数",
        ),
        schema="procurement",
    )
    op.create_table(
        "material_catalog_records",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
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
            "source_config_id",
            sa.Uuid(as_uuid=True),
            nullable=False,
            comment="物料数据源配置 ID",
        ),
        sa.Column(
            "feishu_record_id",
            sa.String(length=128),
            nullable=False,
            comment="飞书记录 ID",
        ),
        sa.Column(
            "material_code",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="物料编码",
        ),
        sa.Column(
            "material_description",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="物料说明",
        ),
        sa.Column(
            "rule_model",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="规格型号",
        ),
        sa.Column(
            "feishu_created_time",
            sa.Integer(),
            nullable=True,
            comment="飞书创建时间",
        ),
        sa.Column(
            "feishu_last_modified_time",
            sa.Integer(),
            nullable=True,
            comment="飞书最近修改时间",
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最近同步时间",
        ),
        sa.ForeignKeyConstraint(
            ["source_config_id"],
            ["procurement.material_source_configs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_config_id",
            "feishu_record_id",
            name="uq_procurement_material_catalog_source_record",
        ),
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_material_catalog_source_active",
        "material_catalog_records",
        ["source_config_id", "is_deleted"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_material_catalog_code",
        "material_catalog_records",
        ["source_config_id", "material_code"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_material_catalog_description",
        "material_catalog_records",
        ["source_config_id", "material_description"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_material_catalog_rule_model",
        "material_catalog_records",
        ["source_config_id", "rule_model"],
        unique=False,
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_procurement_material_catalog_rule_model",
        table_name="material_catalog_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_material_catalog_description",
        table_name="material_catalog_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_material_catalog_code",
        table_name="material_catalog_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_material_catalog_source_active",
        table_name="material_catalog_records",
        schema="procurement",
    )
    op.drop_table("material_catalog_records", schema="procurement")
    op.drop_column(
        "material_source_configs",
        "last_sync_record_count",
        schema="procurement",
    )
    op.drop_column(
        "material_source_configs",
        "last_synced_at",
        schema="procurement",
    )
    op.drop_column("material_source_configs", "sync_error", schema="procurement")
    op.drop_column("material_source_configs", "sync_status", schema="procurement")
