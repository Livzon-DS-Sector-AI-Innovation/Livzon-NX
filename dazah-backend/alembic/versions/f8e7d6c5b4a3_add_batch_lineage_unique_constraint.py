"""add unique constraint on batch_lineage link pair

Revision ID: f8e7d6c5b4a3
Revises: a7c100000021
Create Date: 2026-09-07 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8e7d6c5b4a3"
down_revision: str | None = "a7c100000021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "uq_batch_lineage_link"
TABLE_NAME = "batch_lineage"
SCHEMA_NAME = "production"


def upgrade() -> None:
    # MC 飞书同步的 _sync_lineage 用
    # INSERT ... ON CONFLICT DO NOTHING 增量维护批次血缘。
    # 同一对批次可能携带不同环节语义（如二级混粉 blending→blending
    # 与混粉入库 blending→qc 使用相同的起止批号），
    # 唯一键必须包含环节类型，否则后插入的关系会被 ON CONFLICT 吞掉。
    op.create_unique_constraint(
        CONSTRAINT_NAME,
        TABLE_NAME,
        [
            "upstream_type",
            "upstream_batch",
            "downstream_type",
            "downstream_batch",
        ],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, TABLE_NAME, schema=SCHEMA_NAME)

