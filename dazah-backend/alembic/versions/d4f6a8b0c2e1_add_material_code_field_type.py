"""Add Feishu material code field type metadata.

Revision ID: d4f6a8b0c2e1
Revises: c8e4f1a2b3d5
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4f6a8b0c2e1"
down_revision: str | None = "c8e4f1a2b3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "material_source_configs",
        sa.Column(
            "material_code_field_type",
            sa.Integer(),
            nullable=True,
            comment="飞书物料编码字段类型",
        ),
        schema="procurement",
    )
    op.alter_column(
        "purchase_request_items",
        "rule_model",
        existing_type=sa.String(length=255),
        existing_nullable=False,
        existing_server_default="",
        comment="规格型号",
        existing_comment="规则型号",
        schema="procurement",
    )


def downgrade() -> None:
    op.alter_column(
        "purchase_request_items",
        "rule_model",
        existing_type=sa.String(length=255),
        existing_nullable=False,
        existing_server_default="",
        comment="规则型号",
        existing_comment="规格型号",
        schema="procurement",
    )
    op.drop_column(
        "material_source_configs",
        "material_code_field_type",
        schema="procurement",
    )
