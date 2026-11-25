"""repair records persons jsonb

检修记录镜像新增 persons JSONB 列：同步时把「维修人员」解析为
[{name, open_id, avatar_url}]（人员字段按 open_id 精确取，手打文本按
姓名匹配通讯录；无权限/未匹配时该列为空，展示回退 person_text）。

Revision ID: db1d4d7f5632
Revises: b098d78d072c
Create Date: 2026-11-24 01:40:07.757564
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db1d4d7f5632"
down_revision: str | None = "b098d78d072c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "repair_records",
        sa.Column(
            "persons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "维修人员结构化（[{name, open_id, avatar_url}]）；"
                "通讯录无权限或未匹配到时为空，展示回退 person_text"
            ),
        ),
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_column("repair_records", "persons", schema="equipment")
