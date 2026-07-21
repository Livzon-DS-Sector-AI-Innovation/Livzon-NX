"""add purchase approval role view index

Revision ID: 21e7046001c0
Revises: 2f06bd65d7da
Create Date: 2026-06-28 13:27:00.011128
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "21e7046001c0"
down_revision: str | None = "2f06bd65d7da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_procurement_purchase_request_approval_role_result_time",
        "purchase_request_approvals",
        ["approval_role", "result", "approval_time"],
        schema="procurement",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_procurement_purchase_request_approval_role_result_time",
        table_name="purchase_request_approvals",
        schema="procurement",
    )
