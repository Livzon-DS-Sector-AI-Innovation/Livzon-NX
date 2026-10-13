"""备件编码唯一键改为 (车间, 编码)。

五金物料会同时出现在多个车间的分布表中，全局唯一编码会导致
跨车间同步互相覆盖；改为未删除行内同车间同编码唯一。

Revision ID: b8d4f2a6c9e1
Revises: a7c3e9f1d2b4
Create Date: 2026-10-13

"""

import sqlalchemy as sa

from alembic import op

revision: str = "b8d4f2a6c9e1"
down_revision: str | None = "a7c3e9f1d2b4"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.drop_index("uq_spare_parts_code", schema="equipment")
    op.create_index(
        "uq_spare_parts_workshop_code",
        "spare_parts",
        ["workshop_code", "code"],
        unique=True,
        schema="equipment",
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_spare_parts_workshop_code", schema="equipment")
    op.create_index(
        "uq_spare_parts_code",
        "spare_parts",
        ["code"],
        unique=True,
        schema="equipment",
        postgresql_where=sa.text("is_deleted = false"),
    )
