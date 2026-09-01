"""training_ledgers add is_presented

培训台账新增"是否呈现"字段：默认呈现，不呈现的记录不进入员工培训清单。
与旧线 5afd8a10a960 迁移语义一致（旧线 Alembic 链与本项目不同，此为独立迁移）。

Revision ID: c8d9e0f1a2b3
Revises: e2f7a4c1b9d3
Create Date: 2026-08-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "e2f7a4c1b9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_ledgers",
        sa.Column(
            "is_presented",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="是否呈现（默认显示，不呈现则不进入员工培训清单）",
        ),
        schema="hr",
    )


def downgrade() -> None:
    op.drop_column("training_ledgers", "is_presented", schema="hr")
