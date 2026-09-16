"""Add expiry governance for sensitive page actions."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000038"
down_revision: str | None = "c9d400000037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("role_page_grants", "user_page_grants"):
        op.add_column(
            table_name,
            sa.Column(
                "sensitive_actions_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="高风险动作授权到期时间；空值为待治理的历史授权",
            ),
            schema="identity",
        )


def downgrade() -> None:
    for table_name in ("user_page_grants", "role_page_grants"):
        op.drop_column(
            table_name, "sensitive_actions_expires_at", schema="identity"
        )
