"""add procurement suppliers

Revision ID: 3b7d9a2c4e6f
Revises: c2e7a4d9f8b6
Create Date: 2026-07-01 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b7d9a2c4e6f"
down_revision: str | None = "c2e7a4d9f8b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS procurement")
    op.create_table(
        "suppliers",
        sa.Column(
            "supplier_code",
            sa.String(length=100),
            server_default="",
            nullable=False,
            comment="供应商代码",
        ),
        sa.Column(
            "supplier_name",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="供应商名称",
        ),
        sa.Column(
            "material_code",
            sa.String(length=100),
            server_default="",
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
            "manufacturer_code",
            sa.String(length=100),
            server_default="",
            nullable=False,
            comment="生产厂家编码",
        ),
        sa.Column(
            "manufacturer_name",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="生产厂家名称",
        ),
        sa.Column(
            "purchase_category",
            sa.String(length=100),
            server_default="",
            nullable=False,
            comment="采购品类名称",
        ),
        sa.Column(
            "last_updated_by",
            sa.String(length=100),
            server_default="",
            nullable=False,
            comment="最后更新人",
        ),
        sa.Column(
            "last_updated_date",
            sa.Date(),
            nullable=True,
            comment="最后更新日期",
        ),
        sa.Column(
            "import_file_name",
            sa.String(length=255),
            server_default="",
            nullable=False,
            comment="导入文件名",
        ),
        sa.Column(
            "import_sheet_name",
            sa.String(length=100),
            server_default="",
            nullable=False,
            comment="导入工作表",
        ),
        sa.Column(
            "import_row_number",
            sa.Integer(),
            nullable=False,
            comment="导入文件行号",
        ),
        sa.Column(
            "import_columns",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
            comment="导入文件字段顺序",
        ),
        sa.Column(
            "raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
            comment="导入原始行数据",
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
        sa.PrimaryKeyConstraint("id"),
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_supplier_code",
        "suppliers",
        ["supplier_code"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_supplier_name",
        "suppliers",
        ["supplier_name"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_supplier_material_code",
        "suppliers",
        ["material_code"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_supplier_material_name",
        "suppliers",
        ["material_name"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_supplier_category",
        "suppliers",
        ["purchase_category"],
        schema="procurement",
    )
    op.create_index(
        "ix_procurement_supplier_updated_date",
        "suppliers",
        ["last_updated_date"],
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_procurement_supplier_updated_date",
        table_name="suppliers",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_supplier_category",
        table_name="suppliers",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_supplier_material_name",
        table_name="suppliers",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_supplier_material_code",
        table_name="suppliers",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_supplier_name",
        table_name="suppliers",
        schema="procurement",
    )
    op.drop_index(
        "ix_procurement_supplier_code",
        table_name="suppliers",
        schema="procurement",
    )
    op.drop_table("suppliers", schema="procurement")
