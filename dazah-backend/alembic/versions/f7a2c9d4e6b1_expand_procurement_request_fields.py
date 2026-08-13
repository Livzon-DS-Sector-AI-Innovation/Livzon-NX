"""expand procurement categories and request fields

Revision ID: f7a2c9d4e6b1
Revises: e4c8a2f7b190
Create Date: 2026-08-12 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a2c9d4e6b1"
down_revision: str | None = "e4c8a2f7b190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "purchase_requests",
        sa.Column(
            "attachment_note",
            sa.Text(),
            server_default="",
            nullable=False,
            comment="附件说明",
        ),
        schema="procurement",
    )
    for name, column_type, comment in (
        ("material_code", sa.String(length=64), "物料编码"),
        ("material_description", sa.String(length=255), "物料说明"),
        ("rule_model", sa.String(length=255), "规则型号"),
    ):
        op.add_column(
            "purchase_request_items",
            sa.Column(
                name,
                column_type,
                server_default="",
                nullable=False,
                comment=comment,
            ),
            schema="procurement",
        )

    # The old generic labor category cannot be safely classified as either
    # labor-special or labor-miscellaneous. Archive its active requests and
    # related display records instead of inventing a classification.
    op.execute(
        """
        UPDATE procurement.purchase_request_items AS items
        SET is_deleted = TRUE, updated_at = now()
        WHERE items.purchase_request_id IN (
            SELECT requests.id::text
            FROM procurement.purchase_requests AS requests
            WHERE requests.category = 'labor-protection'
              AND requests.is_deleted = FALSE
        )
        """
    )
    op.execute(
        """
        UPDATE procurement.purchase_request_approvals AS approvals
        SET is_deleted = TRUE, updated_at = now()
        WHERE approvals.purchase_request_id IN (
            SELECT requests.id::text
            FROM procurement.purchase_requests AS requests
            WHERE requests.category = 'labor-protection'
              AND requests.is_deleted = FALSE
        )
        """
    )
    op.execute(
        """
        UPDATE procurement.purchase_requests
        SET is_deleted = TRUE, updated_at = now()
        WHERE category = 'labor-protection'
          AND is_deleted = FALSE
        """
    )


def downgrade() -> None:
    op.drop_column(
        "purchase_request_items",
        "rule_model",
        schema="procurement",
    )
    op.drop_column(
        "purchase_request_items",
        "material_description",
        schema="procurement",
    )
    op.drop_column(
        "purchase_request_items",
        "material_code",
        schema="procurement",
    )
    op.drop_column(
        "purchase_requests",
        "attachment_note",
        schema="procurement",
    )
