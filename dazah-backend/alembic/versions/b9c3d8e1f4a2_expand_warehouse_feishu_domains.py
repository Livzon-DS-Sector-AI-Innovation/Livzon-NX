"""expand warehouse feishu domains

Revision ID: b9c3d8e1f4a2
Revises: a6f2c8d4e9b1
Create Date: 2026-06-30 18:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9c3d8e1f4a2"
down_revision: str | None = "a6f2c8d4e9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS warehouse")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column(
        "feishu_configs",
        sa.Column(
            "finished_product_app_token",
            sa.String(length=128),
            nullable=True,
            comment="成品多维表格 app_token",
        ),
        schema="warehouse",
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "materials_packaging_app_token",
            sa.String(length=128),
            nullable=True,
            comment="原辅料及包材多维表格 app_token",
        ),
        schema="warehouse",
    )
    op.add_column(
        "feishu_configs",
        sa.Column(
            "hardware_app_token",
            sa.String(length=128),
            nullable=True,
            comment="五金多维表格 app_token",
        ),
        schema="warehouse",
    )
    op.execute(
        """
        UPDATE warehouse.feishu_configs
        SET materials_packaging_app_token = bitable_app_token
        WHERE materials_packaging_app_token IS NULL
          AND bitable_app_token IS NOT NULL
        """
    )

    op.drop_index(
        "uq_warehouse_feishu_tables_app_token_table_id",
        table_name="feishu_tables",
        schema="warehouse",
    )
    op.add_column(
        "feishu_tables",
        sa.Column(
            "business_domain",
            sa.String(length=64),
            nullable=False,
            server_default="materials_packaging",
            comment="仓储业务域",
        ),
        schema="warehouse",
    )
    op.add_column(
        "feishu_tables",
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="是否启用同步与监测",
        ),
        schema="warehouse",
    )
    op.add_column(
        "feishu_tables",
        sa.Column(
            "field_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="字段数量",
        ),
        schema="warehouse",
    )
    op.add_column(
        "feishu_tables",
        sa.Column(
            "record_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="记录数量",
        ),
        schema="warehouse",
    )
    op.add_column(
        "feishu_tables",
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近同步时间",
        ),
        schema="warehouse",
    )
    op.add_column(
        "feishu_tables",
        sa.Column(
            "sync_status",
            sa.String(length=32),
            nullable=True,
            comment="同步状态",
        ),
        schema="warehouse",
    )
    op.add_column(
        "feishu_tables",
        sa.Column("sync_error", sa.Text(), nullable=True, comment="最近同步错误"),
        schema="warehouse",
    )
    op.create_index(
        "uq_warehouse_feishu_tables_domain_app_token_table_id",
        "feishu_tables",
        ["business_domain", "app_token", "table_id"],
        unique=True,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_feishu_tables_domain_enabled",
        "feishu_tables",
        ["business_domain", "is_enabled"],
        unique=False,
        schema="warehouse",
    )

    op.create_table(
        "feishu_fields",
        sa.Column("business_domain", sa.String(length=64), nullable=False),
        sa.Column("app_token", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column("field_id", sa.String(length=128), nullable=False),
        sa.Column("field_name", sa.String(length=255), nullable=False),
        sa.Column("field_type", sa.Integer(), nullable=True),
        sa.Column(
            "property",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )
    op.create_index(
        "uq_warehouse_feishu_fields_domain_table_field",
        "feishu_fields",
        ["business_domain", "app_token", "table_id", "field_id"],
        unique=True,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_feishu_fields_table",
        "feishu_fields",
        ["business_domain", "app_token", "table_id"],
        unique=False,
        schema="warehouse",
    )

    op.create_table(
        "feishu_records",
        sa.Column("business_domain", sa.String(length=64), nullable=False),
        sa.Column("app_token", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column("record_id", sa.String(length=128), nullable=False),
        sa.Column(
            "fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "search_text",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
        sa.Column("feishu_created_time", sa.Integer(), nullable=True),
        sa.Column("feishu_last_modified_time", sa.Integer(), nullable=True),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )
    op.create_index(
        "uq_warehouse_feishu_records_domain_table_record",
        "feishu_records",
        ["business_domain", "app_token", "table_id", "record_id"],
        unique=True,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_feishu_records_table",
        "feishu_records",
        ["business_domain", "app_token", "table_id"],
        unique=False,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_feishu_records_fields_gin",
        "feishu_records",
        ["fields"],
        unique=False,
        schema="warehouse",
        postgresql_using="gin",
    )
    op.execute(
        """
        CREATE INDEX ix_warehouse_feishu_records_search_trgm
        ON warehouse.feishu_records
        USING gin (search_text gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS warehouse.ix_warehouse_feishu_records_search_trgm")
    op.drop_index(
        "ix_warehouse_feishu_records_fields_gin",
        table_name="feishu_records",
        schema="warehouse",
    )
    op.drop_index(
        "ix_warehouse_feishu_records_table",
        table_name="feishu_records",
        schema="warehouse",
    )
    op.drop_index(
        "uq_warehouse_feishu_records_domain_table_record",
        table_name="feishu_records",
        schema="warehouse",
    )
    op.drop_table("feishu_records", schema="warehouse")

    op.drop_index(
        "ix_warehouse_feishu_fields_table",
        table_name="feishu_fields",
        schema="warehouse",
    )
    op.drop_index(
        "uq_warehouse_feishu_fields_domain_table_field",
        table_name="feishu_fields",
        schema="warehouse",
    )
    op.drop_table("feishu_fields", schema="warehouse")

    op.drop_index(
        "ix_warehouse_feishu_tables_domain_enabled",
        table_name="feishu_tables",
        schema="warehouse",
    )
    op.drop_index(
        "uq_warehouse_feishu_tables_domain_app_token_table_id",
        table_name="feishu_tables",
        schema="warehouse",
    )
    op.drop_column("feishu_tables", "sync_error", schema="warehouse")
    op.drop_column("feishu_tables", "sync_status", schema="warehouse")
    op.drop_column("feishu_tables", "last_synced_at", schema="warehouse")
    op.drop_column("feishu_tables", "record_count", schema="warehouse")
    op.drop_column("feishu_tables", "field_count", schema="warehouse")
    op.drop_column("feishu_tables", "is_enabled", schema="warehouse")
    op.drop_column("feishu_tables", "business_domain", schema="warehouse")
    op.create_index(
        "uq_warehouse_feishu_tables_app_token_table_id",
        "feishu_tables",
        ["app_token", "table_id"],
        unique=True,
        schema="warehouse",
    )

    op.drop_column("feishu_configs", "hardware_app_token", schema="warehouse")
    op.drop_column(
        "feishu_configs", "materials_packaging_app_token", schema="warehouse"
    )
    op.drop_column("feishu_configs", "finished_product_app_token", schema="warehouse")
