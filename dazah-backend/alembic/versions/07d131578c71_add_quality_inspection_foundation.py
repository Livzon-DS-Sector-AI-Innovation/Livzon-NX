"""add quality inspection foundation

Revision ID: 07d131578c71
Revises: 6c9b3dc4b141
Create Date: 2026-07-13 09:17:10.301862
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "07d131578c71"
down_revision: str | None = "6c9b3dc4b141"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")

    op.create_table(
        "lab_items",
        sa.Column("name", sa.String(length=200), nullable=False, comment="物品名称"),
        sa.Column(
            "specification", sa.String(length=200), nullable=True, comment="规格/型号"
        ),
        sa.Column("category", sa.String(length=50), nullable=True, comment="类别"),
        sa.Column(
            "quantity", sa.Integer(), server_default="0", nullable=False, comment="数量"
        ),
        sa.Column("unit", sa.String(length=20), nullable=True, comment="单位"),
        sa.Column("location", sa.String(length=100), nullable=True, comment="存放位置"),
        sa.Column("supplier", sa.String(length=200), nullable=True, comment="供应商"),
        sa.Column("batch_no", sa.String(length=100), nullable=True, comment="批号"),
        sa.Column("expiry_date", sa.Date(), nullable=True, comment="有效期至"),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="normal",
            nullable=False,
            comment="状态",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="quality",
    )
    op.create_index(
        "ix_quality_lab_items_active_status_expiry",
        "lab_items",
        ["is_deleted", "status", "expiry_date"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_lab_items_name",
        "lab_items",
        ["name"],
        unique=False,
        schema="quality",
    )

    op.create_table(
        "lab_instruments",
        sa.Column("name", sa.String(length=200), nullable=False, comment="仪器名称"),
        sa.Column("model", sa.String(length=100), nullable=True, comment="型号"),
        sa.Column("serial_no", sa.String(length=100), nullable=True, comment="序列号"),
        sa.Column(
            "manufacturer", sa.String(length=200), nullable=True, comment="生产厂家"
        ),
        sa.Column(
            "department", sa.String(length=100), nullable=True, comment="所属部门"
        ),
        sa.Column("location", sa.String(length=100), nullable=True, comment="放置位置"),
        sa.Column("calibration_date", sa.Date(), nullable=True, comment="最近校准日期"),
        sa.Column(
            "next_calibration_date", sa.Date(), nullable=True, comment="下次校准日期"
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="normal",
            nullable=False,
            comment="状态",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial_no", name="uq_quality_lab_instruments_serial_no"),
        schema="quality",
    )
    op.create_index(
        "ix_quality_lab_instruments_active_status_calibration",
        "lab_instruments",
        ["is_deleted", "status", "next_calibration_date"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_lab_instruments_name",
        "lab_instruments",
        ["name"],
        unique=False,
        schema="quality",
    )

    op.create_table(
        "inspection_records",
        sa.Column(
            "inspection_no", sa.String(length=50), nullable=False, comment="检验编号"
        ),
        sa.Column(
            "product_name", sa.String(length=200), nullable=True, comment="产品名称"
        ),
        sa.Column("batch_no", sa.String(length=100), nullable=True, comment="批号"),
        sa.Column(
            "inspection_type", sa.String(length=50), nullable=True, comment="检验类型"
        ),
        sa.Column(
            "inspection_item", sa.String(length=500), nullable=True, comment="检验项目"
        ),
        sa.Column("specification", sa.Text(), nullable=True, comment="标准规定"),
        sa.Column("test_result", sa.Text(), nullable=True, comment="检验结果"),
        sa.Column(
            "conclusion", sa.String(length=20), nullable=True, comment="检验结论"
        ),
        sa.Column("inspector", sa.String(length=100), nullable=True, comment="检验人"),
        sa.Column("inspection_date", sa.Date(), nullable=True, comment="检验日期"),
        sa.Column(
            "department", sa.String(length=100), nullable=True, comment="检验部门"
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "inspection_no", name="uq_quality_inspection_records_inspection_no"
        ),
        schema="quality",
    )
    op.create_index(
        "ix_quality_inspection_records_active_type_date",
        "inspection_records",
        ["is_deleted", "inspection_type", "inspection_date"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_inspection_records_active_conclusion_date",
        "inspection_records",
        ["is_deleted", "conclusion", "inspection_date"],
        unique=False,
        schema="quality",
    )

    _create_material_inspection_table(
        "finished_product_inspections",
        material_columns=[
            sa.Column(
                "product_name", sa.String(length=200), nullable=True, comment="产品名称"
            ),
            sa.Column("batch_no", sa.String(length=100), nullable=True, comment="批号"),
        ],
        unique_name="uq_quality_finished_product_inspections_no",
    )
    op.create_index(
        "ix_quality_finished_product_inspections_active_date",
        "finished_product_inspections",
        ["is_deleted", "inspection_date"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_finished_product_inspections_product_batch",
        "finished_product_inspections",
        ["product_name", "batch_no"],
        unique=False,
        schema="quality",
    )

    _create_material_inspection_table(
        "solid_material_inspections",
        material_columns=_material_columns(),
        unique_name="uq_quality_solid_material_inspections_no",
    )
    op.create_index(
        "ix_quality_solid_material_inspections_active_date",
        "solid_material_inspections",
        ["is_deleted", "inspection_date"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_solid_material_inspections_material_batch",
        "solid_material_inspections",
        ["material_name", "material_batch"],
        unique=False,
        schema="quality",
    )

    _create_material_inspection_table(
        "liquid_material_inspections",
        material_columns=_material_columns(),
        unique_name="uq_quality_liquid_material_inspections_no",
    )
    op.create_index(
        "ix_quality_liquid_material_inspections_active_date",
        "liquid_material_inspections",
        ["is_deleted", "inspection_date"],
        unique=False,
        schema="quality",
    )
    op.create_index(
        "ix_quality_liquid_material_inspections_material_batch",
        "liquid_material_inspections",
        ["material_name", "material_batch"],
        unique=False,
        schema="quality",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quality_liquid_material_inspections_material_batch",
        table_name="liquid_material_inspections",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_liquid_material_inspections_active_date",
        table_name="liquid_material_inspections",
        schema="quality",
    )
    op.drop_table("liquid_material_inspections", schema="quality")
    op.drop_index(
        "ix_quality_solid_material_inspections_material_batch",
        table_name="solid_material_inspections",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_solid_material_inspections_active_date",
        table_name="solid_material_inspections",
        schema="quality",
    )
    op.drop_table("solid_material_inspections", schema="quality")
    op.drop_index(
        "ix_quality_finished_product_inspections_product_batch",
        table_name="finished_product_inspections",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_finished_product_inspections_active_date",
        table_name="finished_product_inspections",
        schema="quality",
    )
    op.drop_table("finished_product_inspections", schema="quality")
    op.drop_index(
        "ix_quality_inspection_records_active_conclusion_date",
        table_name="inspection_records",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_inspection_records_active_type_date",
        table_name="inspection_records",
        schema="quality",
    )
    op.drop_table("inspection_records", schema="quality")
    op.drop_index(
        "ix_quality_lab_instruments_name",
        table_name="lab_instruments",
        schema="quality",
    )
    op.drop_index(
        "ix_quality_lab_instruments_active_status_calibration",
        table_name="lab_instruments",
        schema="quality",
    )
    op.drop_table("lab_instruments", schema="quality")
    op.drop_index("ix_quality_lab_items_name", table_name="lab_items", schema="quality")
    op.drop_index(
        "ix_quality_lab_items_active_status_expiry",
        table_name="lab_items",
        schema="quality",
    )
    op.drop_table("lab_items", schema="quality")


def _material_columns() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "material_name", sa.String(length=200), nullable=True, comment="物料名称"
        ),
        sa.Column(
            "material_batch", sa.String(length=100), nullable=True, comment="物料批号"
        ),
        sa.Column("supplier", sa.String(length=200), nullable=True, comment="供应商"),
    ]


def _create_material_inspection_table(
    table_name: str,
    *,
    material_columns: list[sa.Column[object]],
    unique_name: str,
) -> None:
    op.create_table(
        table_name,
        sa.Column(
            "inspection_no", sa.String(length=50), nullable=False, comment="检验编号"
        ),
        *material_columns,
        sa.Column(
            "inspection_item", sa.String(length=500), nullable=True, comment="检验项目"
        ),
        sa.Column("specification", sa.Text(), nullable=True, comment="标准规定"),
        sa.Column("test_result", sa.Text(), nullable=True, comment="检验结果"),
        sa.Column(
            "conclusion", sa.String(length=20), nullable=True, comment="检验结论"
        ),
        sa.Column("inspector", sa.String(length=100), nullable=True, comment="检验人"),
        sa.Column("inspection_date", sa.Date(), nullable=True, comment="检验日期"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inspection_no", name=unique_name),
        schema="quality",
    )
