"""add_material_price_records

Revision ID: c3f7a1d9e2b4
Revises: d4c8e2f7a1b9
Create Date: 2026-11-25 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f7a1d9e2b4"
down_revision: str | None = "d4c8e2f7a1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS procurement")
    op.create_table(
        "material_price_records",
        sa.Column("data_year", sa.Integer(), nullable=False, comment="数据年度"),
        sa.Column(
            "data_date",
            sa.Date(),
            nullable=True,
            comment="业务日期（订单/入库单有，年度汇总表为空）",
        ),
        sa.Column(
            "doc_no",
            sa.String(length=128),
            server_default="",
            nullable=False,
            comment="单据号",
        ),
        sa.Column(
            "department",
            sa.String(length=200),
            server_default="",
            nullable=False,
            comment="申购部门",
        ),
        sa.Column(
            "sub_inventory",
            sa.String(length=64),
            server_default="",
            nullable=False,
            comment="子库存",
        ),
        sa.Column(
            "batch_no",
            sa.String(length=128),
            server_default="",
            nullable=False,
            comment="批次号",
        ),
        sa.Column(
            "material_code",
            sa.String(length=64),
            nullable=False,
            comment="物料编码",
        ),
        sa.Column(
            "material_name",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="物料名称",
        ),
        sa.Column(
            "material_alias",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="物料别名",
        ),
        sa.Column(
            "unit",
            sa.String(length=32),
            server_default="",
            nullable=False,
            comment="主单位",
        ),
        sa.Column(
            "material_category",
            sa.String(length=128),
            server_default="",
            nullable=False,
            comment="物料类别",
        ),
        sa.Column(
            "cost_category",
            sa.String(length=64),
            server_default="",
            nullable=False,
            comment="成本类别",
        ),
        sa.Column(
            "unit_price",
            sa.Numeric(precision=18, scale=4),
            server_default="0",
            nullable=False,
            comment="单位价格",
        ),
        sa.Column(
            "quantity",
            sa.Numeric(precision=18, scale=4),
            server_default="0",
            nullable=False,
            comment="采购数量",
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=18, scale=2),
            server_default="0",
            nullable=False,
            comment="金额",
        ),
        sa.Column(
            "supplier_name",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="供应商名称",
        ),
        sa.Column(
            "price_flag",
            sa.String(length=16),
            server_default="normal",
            nullable=False,
            comment="价格标记：normal/suspicious",
        ),
        sa.Column(
            "source_type",
            sa.String(length=32),
            server_default="erp_stock",
            nullable=False,
            comment="来源类型：erp_stock/erp_order/manual",
        ),
        sa.Column(
            "row_key",
            sa.String(length=128),
            nullable=False,
            comment="幂等指纹",
        ),
        sa.Column(
            "source_file",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="来源文件名",
        ),
        sa.Column(
            "source_sheet",
            sa.String(length=128),
            server_default="",
            nullable=False,
            comment="来源工作表",
        ),
        sa.Column(
            "source_row",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="来源行号",
        ),
        sa.Column(
            "raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="原始行数据",
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_price_category",
        "material_price_records",
        ["cost_category"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_price_code",
        "material_price_records",
        ["material_code"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_price_name",
        "material_price_records",
        ["material_name"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_price_source",
        "material_price_records",
        ["source_type"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_price_supplier",
        "material_price_records",
        ["supplier_name"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_price_year",
        "material_price_records",
        ["data_year"],
        unique=False,
        schema="procurement",
    )
    op.create_index(
        "uq_procurement_price_row_key",
        "material_price_records",
        ["row_key"],
        unique=True,
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_procurement_price_row_key",
        table_name="material_price_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_price_year",
        table_name="material_price_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_price_supplier",
        table_name="material_price_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_price_source",
        table_name="material_price_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_price_name",
        table_name="material_price_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_price_code",
        table_name="material_price_records",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_price_category",
        table_name="material_price_records",
        schema="procurement",
    )
    op.drop_table("material_price_records", schema="procurement")
