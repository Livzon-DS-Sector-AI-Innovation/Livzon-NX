"""危险源辨识台账：新增车间 Excel 表头对齐的专用字段列。

时态/状态/责任单位/检查频次/检查标准/是否重要危险源原先由导入服务
拼入备注文本，现改为独立列，供台账页面按车间表格表头直接分组展示。

Revision ID: a9c1e3f5b7d9
Revises: b6f2d8a4c1e7
Create Date: 2026-10-20

"""

import sqlalchemy as sa

from alembic import op

revision = "a9c1e3f5b7d9"
down_revision = "b6f2d8a4c1e7"
branch_labels = None
depends_on = None

COLUMNS = [
    ("tense", sa.String(50), "时态（过去/现在/将来）"),
    ("state", sa.String(50), "状态（正常/异常/紧急）"),
    ("responsible_unit", sa.String(100), "责任单位"),
    ("check_frequency", sa.String(100), "检查频次"),
    ("check_standard", sa.Text(), "检查标准（设备设施清单）"),
    ("is_major_hazard", sa.String(10), "是否重要危险源（是/否）"),
]


def upgrade() -> None:
    for name, col_type, comment in COLUMNS:
        op.add_column(
            "hazard_identifications",
            sa.Column(name, col_type, nullable=True, comment=comment),
            schema="safety",
        )


def downgrade() -> None:
    for name, _col_type, _comment in reversed(COLUMNS):
        op.drop_column("hazard_identifications", name, schema="safety")
