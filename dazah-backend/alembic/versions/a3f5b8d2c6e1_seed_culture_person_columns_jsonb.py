"""Seed culture person columns to JSONB (avatar + name chips)

Revision ID: a3f5b8d2c6e1
Revises: 18a00b63c9b6
Create Date: 2026-11-12 14:30:00.000000

人员字段（飞书成员类型）从纯文本改为 JSONB 数组，元素形如
{"open_id": "ou_x", "name": "张三", "avatar_url": "https://…"}。
历史文本数据经 to_jsonb 转为 JSON 字符串，读取侧兼容 string → [{name}]。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f5b8d2c6e1"
down_revision: str | None = "18a00b63c9b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERSON_COLUMNS = (
    "prepare_operator",
    "sterilization_operator",
    "shaker_setup_operator",
    "inoculation_operator",
    "tank_setup_operator",
    "merge_operator",
    "workshop_inoculation_operator",
)


def upgrade() -> None:
    for column in PERSON_COLUMNS:
        op.alter_column(
            "seed_cultures",
            column,
            existing_type=sa.Text(),
            type_=postgresql.JSONB(),
            postgresql_using=f"to_jsonb({column})",
            schema="production",
        )


def downgrade() -> None:
    for column in PERSON_COLUMNS:
        op.alter_column(
            "seed_cultures",
            column,
            existing_type=postgresql.JSONB(),
            type_=sa.Text(),
            postgresql_using=f"{column}::text",
            schema="production",
        )
