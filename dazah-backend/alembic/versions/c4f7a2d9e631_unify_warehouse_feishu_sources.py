"""unify warehouse Feishu sources

Revision ID: c4f7a2d9e631
Revises: 99293e22f066
Create Date: 2026-07-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4f7a2d9e631"
down_revision: str | None = "99293e22f066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "uq_warehouse_feishu_tables_domain_app_token_table_id",
        table_name="feishu_tables",
        schema="warehouse",
    )
    op.drop_index(
        "ix_warehouse_feishu_tables_domain_enabled",
        table_name="feishu_tables",
        schema="warehouse",
    )
    op.execute(
        "UPDATE warehouse.feishu_fields AS f "
        "SET business_domain = 'root:' || t.source_root_id::text "
        "FROM warehouse.feishu_tables AS t "
        "WHERE t.source_root_id IS NOT NULL "
        "AND f.business_domain = t.business_domain "
        "AND f.app_token = t.app_token "
        "AND f.table_id = t.table_id"
    )
    op.execute(
        "UPDATE warehouse.feishu_records AS r "
        "SET business_domain = 'root:' || t.source_root_id::text "
        "FROM warehouse.feishu_tables AS t "
        "WHERE t.source_root_id IS NOT NULL "
        "AND r.business_domain = t.business_domain "
        "AND r.app_token = t.app_token "
        "AND r.table_id = t.table_id"
    )
    op.execute(
        "UPDATE warehouse.feishu_tables "
        "SET business_domain = 'root:' || source_root_id::text "
        "WHERE source_root_id IS NOT NULL"
    )
    op.create_index(
        "uq_warehouse_feishu_tables_root_app_token_table_id",
        "feishu_tables",
        ["source_root_id", "app_token", "table_id"],
        unique=True,
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_feishu_tables_root",
        "feishu_tables",
        ["source_root_id"],
        schema="warehouse",
    )
    op.drop_column("feishu_tables", "is_enabled", schema="warehouse")

    op.drop_column("feishu_source_roots", "business_domain", schema="warehouse")

    for column_name in (
        "product_table_id",
        "packaging_table_id",
        "raw_material_table_id",
        "hardware_app_token",
        "materials_packaging_app_token",
        "finished_product_app_token",
        "bitable_app_token",
    ):
        op.drop_column("feishu_configs", column_name, schema="warehouse")


def downgrade() -> None:
    op.add_column(
        "feishu_tables",
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema="warehouse",
    )
    op.add_column(
        "feishu_configs",
        sa.Column("bitable_app_token", sa.String(128), nullable=True),
        schema="warehouse",
    )
    for column_name in (
        "finished_product_app_token",
        "materials_packaging_app_token",
        "hardware_app_token",
        "raw_material_table_id",
        "packaging_table_id",
        "product_table_id",
    ):
        op.add_column(
            "feishu_configs",
            sa.Column(column_name, sa.String(128), nullable=True),
            schema="warehouse",
        )
    op.execute(
        "UPDATE warehouse.feishu_configs SET bitable_app_token = '' "
        "WHERE bitable_app_token IS NULL"
    )
    op.alter_column(
        "feishu_configs",
        "bitable_app_token",
        nullable=False,
        schema="warehouse",
    )

    op.add_column(
        "feishu_source_roots",
        sa.Column("business_domain", sa.String(64), nullable=True),
        schema="warehouse",
    )
    op.execute(
        "UPDATE warehouse.feishu_source_roots "
        "SET business_domain = 'root_' || replace(id::text, '-', '') "
        "WHERE business_domain IS NULL"
    )
    op.alter_column(
        "feishu_source_roots",
        "business_domain",
        nullable=False,
        schema="warehouse",
    )

    op.drop_index(
        "ix_warehouse_feishu_tables_root",
        table_name="feishu_tables",
        schema="warehouse",
    )
    op.drop_index(
        "uq_warehouse_feishu_tables_root_app_token_table_id",
        table_name="feishu_tables",
        schema="warehouse",
    )
    op.execute(
        "UPDATE warehouse.feishu_fields "
        "SET business_domain = 'root_' || replace(substring(business_domain, 6), "
        "'-', '') "
        "WHERE business_domain LIKE 'root:%'"
    )
    op.execute(
        "UPDATE warehouse.feishu_records "
        "SET business_domain = 'root_' || replace(substring(business_domain, 6), "
        "'-', '') "
        "WHERE business_domain LIKE 'root:%'"
    )
    op.execute(
        "UPDATE warehouse.feishu_tables "
        "SET business_domain = 'root_' || replace(source_root_id::text, '-', '') "
        "WHERE source_root_id IS NOT NULL"
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
        schema="warehouse",
    )
