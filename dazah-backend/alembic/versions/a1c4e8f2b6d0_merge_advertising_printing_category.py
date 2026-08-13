"""merge advertising and printing procurement categories

Revision ID: a1c4e8f2b6d0
Revises: f7a2c9d4e6b1
Create Date: 2026-08-12 00:00:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c4e8f2b6d0"
down_revision: str | None = "f7a2c9d4e6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The two legacy categories now share one user-visible category. Update
    # historical rows as well so hidden records cannot retain an invalid enum.
    op.execute(
        """
        UPDATE procurement.purchase_requests
        SET category = 'advertising-printing', updated_at = now()
        WHERE category IN ('advertising', 'printing')
        """
    )


def downgrade() -> None:
    # The merged value cannot be split back without the original source
    # category. Keep it intact rather than guessing a classification.
    pass
