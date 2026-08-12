"""Add actual category to procurement request items.

Revision ID: b3d7f1a9c2e4
Revises: a1c4e8f2b6d0
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3d7f1a9c2e4"
down_revision: str | None = "a1c4e8f2b6d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "purchase_request_items",
        sa.Column(
            "item_category",
            sa.String(length=64),
            nullable=True,
            server_default="",
            comment="明细实际采购类型",
        ),
        schema="procurement",
    )
    op.execute(
        sa.text(
            """
            UPDATE procurement.purchase_request_items AS items
            SET item_category = requests.category
            FROM procurement.purchase_requests AS requests
            WHERE items.purchase_request_id = requests.id::text
              AND (items.item_category IS NULL OR items.item_category = '')
            """
        )
    )
    op.alter_column(
        "purchase_request_items",
        "item_category",
        existing_type=sa.String(length=64),
        nullable=False,
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_column(
        "purchase_request_items",
        "item_category",
        schema="procurement",
    )
