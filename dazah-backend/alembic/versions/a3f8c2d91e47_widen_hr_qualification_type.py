"""widen hr qualification_type to 64

Revision ID: a3f8c2d91e47
Revises: d7e8f9a1b2c3
Create Date: 2026-09-30

飞书多维表格中"职称"为自由文本，存在超过 32 字的合法值（如
"机械工程师、二级建造师（机电、市政）、智慧消防工程师、发明专利证书"），
hr.employees 与 hr.offboarding_records 的 qualification_type 原为
VARCHAR(32)，导致离职台账回拉逐条失败。统一放宽到 VARCHAR(64)。
"""

from alembic import op

revision: str = "a3f8c2d91e47"
down_revision: str | None = "d7e8f9a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE hr.employees "
        "ALTER COLUMN qualification_type TYPE VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE hr.offboarding_records "
        "ALTER COLUMN qualification_type TYPE VARCHAR(64)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE hr.employees "
        "ALTER COLUMN qualification_type TYPE VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE hr.offboarding_records "
        "ALTER COLUMN qualification_type TYPE VARCHAR(32)"
    )
