"""霉酚酸产品代码统一为 MC：MP -> MC

业务口径统一（车间叫 MC），系统产品代码从 MP 更名为 MC。仅数据值更名，
无表结构变化：排产存档、月度计划产能、批次实际产量三张表按 product_code
关联的存量行同步更名。

Revision ID: c9d400000035
Revises: c9d400000034
Create Date: 2026-09-16 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000035"
down_revision: str | None = "c9d400000034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "production.schedule_excel_archives",
    "production.fermentation_month_settings",
    "production.fermentation_batch_actuals",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"UPDATE {table} SET product_code = 'MC' WHERE product_code = 'MP'"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"UPDATE {table} SET product_code = 'MP' WHERE product_code = 'MC'"
        )
