"""Add optional material source fields (unit, template, categories).

Revision ID: e6d5c4b3a291
Revises: 7a8b9c0d1e2f
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6d5c4b3a291"
down_revision: str | None = "7a8b9c0d1e2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONFIG_FIELD_COLUMNS = [
    ("material_unit_field", "主要单位实际字段名"),
    ("material_template_field", "物料模板实际字段名"),
    ("material_category_field", "物料大类实际字段名"),
    ("material_subcategory_field", "物料小类实际字段名"),
    ("material_cost_category_field", "物料成本大类实际字段名"),
]

_CATALOG_VALUE_COLUMNS = [
    ("material_unit", "主要单位", 64),
    ("material_template", "物料模板", 255),
    ("material_category", "物料大类", 255),
    ("material_subcategory", "物料小类", 255),
    ("material_cost_category", "物料成本大类", 255),
]


def upgrade() -> None:
    for name, comment in _CONFIG_FIELD_COLUMNS:
        op.add_column(
            "material_source_configs",
            sa.Column(name, sa.String(128), nullable=True, comment=comment),
            schema="procurement",
        )
    for name, comment, length in _CATALOG_VALUE_COLUMNS:
        op.add_column(
            "material_catalog_records",
            sa.Column(
                name,
                sa.String(length),
                nullable=False,
                server_default="",
                comment=comment,
            ),
            schema="procurement",
        )


def downgrade() -> None:
    for name, _comment in reversed(_CATALOG_VALUE_COLUMNS):
        op.drop_column("material_catalog_records", name, schema="procurement")
    for name, _comment in reversed(_CONFIG_FIELD_COLUMNS):
        op.drop_column("material_source_configs", name, schema="procurement")
