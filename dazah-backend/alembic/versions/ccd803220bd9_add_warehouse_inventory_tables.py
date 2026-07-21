"""add warehouse inventory tables

Revision ID: ccd803220bd9
Revises: 9a1c4e7b8f2d
Create Date: 2026-06-27 15:55:51.517768
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ccd803220bd9"
down_revision: str | None = "9a1c4e7b8f2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS warehouse")

    op.create_table(
        "raw_material_inventories",
        sa.Column(
            "source_id", sa.String(length=64), nullable=True, comment="来源记录 ID"
        ),
        sa.Column("code", sa.String(length=64), nullable=False, comment="物料编码"),
        sa.Column("name", sa.String(length=255), nullable=False, comment="物料名称"),
        sa.Column("spec", sa.String(length=255), nullable=True, comment="规格"),
        sa.Column("unit", sa.String(length=32), nullable=True, comment="单位"),
        sa.Column("available", sa.Float(), nullable=False, comment="可用库存"),
        sa.Column("safety", sa.Float(), nullable=False, comment="安全库存"),
        sa.Column("last_month", sa.Float(), nullable=False, comment="上月库存/用量"),
        sa.Column(
            "two_months_ago", sa.Float(), nullable=False, comment="前月库存/用量"
        ),
        sa.Column("today_balance", sa.Float(), nullable=False, comment="今日结存"),
        sa.Column("front_stock", sa.Float(), nullable=False, comment="前台库存"),
        sa.Column("this_month_use", sa.Float(), nullable=False, comment="本月用量"),
        sa.Column("warning", sa.String(length=128), nullable=True, comment="预警"),
        sa.Column(
            "product_line", sa.String(length=64), nullable=True, comment="使用产品/类别"
        ),
        sa.Column("erp_no", sa.String(length=128), nullable=True, comment="ERP 编号"),
        sa.Column("delivery", sa.Text(), nullable=True, comment="到货时间"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column(
            "import_key", sa.String(length=64), nullable=False, comment="导入唯一键"
        ),
        sa.Column("source", sa.String(length=255), nullable=True, comment="数据来源"),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最近同步时间",
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_raw_materials_code",
        "raw_material_inventories",
        ["code"],
        unique=False,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_raw_materials_product_line",
        "raw_material_inventories",
        ["product_line"],
        unique=False,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_raw_materials_import_key",
        "raw_material_inventories",
        ["import_key"],
        unique=True,
        schema="warehouse",
    )

    op.create_table(
        "packaging_material_inventories",
        sa.Column(
            "source_id", sa.String(length=64), nullable=True, comment="来源记录 ID"
        ),
        sa.Column("code", sa.String(length=64), nullable=False, comment="包材编码"),
        sa.Column("name", sa.String(length=255), nullable=False, comment="名称"),
        sa.Column("spec", sa.String(length=255), nullable=True, comment="规格"),
        sa.Column("batch", sa.Text(), nullable=True, comment="批次"),
        sa.Column("available", sa.Float(), nullable=False, comment="可用库存"),
        sa.Column("safety", sa.Float(), nullable=False, comment="安全库存"),
        sa.Column("last_month", sa.Float(), nullable=False, comment="上月库存/用量"),
        sa.Column(
            "two_months_ago", sa.Float(), nullable=False, comment="前月库存/用量"
        ),
        sa.Column("today_balance", sa.Float(), nullable=False, comment="今日结存"),
        sa.Column("front_stock", sa.Float(), nullable=False, comment="前台库存"),
        sa.Column("this_month_use", sa.Float(), nullable=False, comment="本月用量"),
        sa.Column("warning", sa.String(length=128), nullable=True, comment="预警"),
        sa.Column(
            "product_line", sa.String(length=64), nullable=True, comment="使用产品"
        ),
        sa.Column("erp_no", sa.String(length=128), nullable=True, comment="ERP 编号"),
        sa.Column("delivery", sa.Text(), nullable=True, comment="到货时间"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column(
            "import_key", sa.String(length=64), nullable=False, comment="导入唯一键"
        ),
        sa.Column("source", sa.String(length=255), nullable=True, comment="数据来源"),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最近同步时间",
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_packaging_materials_code",
        "packaging_material_inventories",
        ["code"],
        unique=False,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_packaging_materials_product_line",
        "packaging_material_inventories",
        ["product_line"],
        unique=False,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_packaging_materials_import_key",
        "packaging_material_inventories",
        ["import_key"],
        unique=True,
        schema="warehouse",
    )

    op.create_table(
        "product_inventories",
        sa.Column(
            "source_id", sa.String(length=64), nullable=True, comment="来源记录 ID"
        ),
        sa.Column("name", sa.String(length=255), nullable=False, comment="产品名称"),
        sa.Column("spec", sa.String(length=255), nullable=True, comment="包装规格"),
        sa.Column("order_quantity", sa.Float(), nullable=False, comment="订单量"),
        sa.Column("pending_quantity", sa.Float(), nullable=False, comment="待检数量"),
        sa.Column("qualified_quantity", sa.Float(), nullable=False, comment="合格数量"),
        sa.Column("subtotal_quantity", sa.Float(), nullable=False, comment="小计"),
        sa.Column("remaining_quantity", sa.Float(), nullable=False, comment="剩余量"),
        sa.Column("unit", sa.String(length=32), nullable=True, comment="单位"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column(
            "import_key", sa.String(length=64), nullable=False, comment="导入唯一键"
        ),
        sa.Column("source", sa.String(length=255), nullable=True, comment="数据来源"),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最近同步时间",
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_products_name",
        "product_inventories",
        ["name"],
        unique=False,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_products_import_key",
        "product_inventories",
        ["import_key"],
        unique=True,
        schema="warehouse",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_warehouse_products_import_key",
        table_name="product_inventories",
        schema="warehouse",
    )
    op.drop_index(
        "ix_warehouse_products_name",
        table_name="product_inventories",
        schema="warehouse",
    )
    op.drop_table("product_inventories", schema="warehouse")

    op.drop_index(
        "ix_warehouse_packaging_materials_import_key",
        table_name="packaging_material_inventories",
        schema="warehouse",
    )
    op.drop_index(
        "ix_warehouse_packaging_materials_product_line",
        table_name="packaging_material_inventories",
        schema="warehouse",
    )
    op.drop_index(
        "ix_warehouse_packaging_materials_code",
        table_name="packaging_material_inventories",
        schema="warehouse",
    )
    op.drop_table("packaging_material_inventories", schema="warehouse")

    op.drop_index(
        "ix_warehouse_raw_materials_import_key",
        table_name="raw_material_inventories",
        schema="warehouse",
    )
    op.drop_index(
        "ix_warehouse_raw_materials_product_line",
        table_name="raw_material_inventories",
        schema="warehouse",
    )
    op.drop_index(
        "ix_warehouse_raw_materials_code",
        table_name="raw_material_inventories",
        schema="warehouse",
    )
    op.drop_table("raw_material_inventories", schema="warehouse")
