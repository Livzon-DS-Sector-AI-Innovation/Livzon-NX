"""widen quality change_object to text

Revision ID: b7d2e4f60a58
Revises: a3f8c2d91e47
Create Date: 2026-10-08

变更台账 Word 导入中存在超长"变更对象"文本（实测 2125 字），
quality_change_controls.change_object 原为 VARCHAR(255)，导入失败。
放宽为 TEXT，与 change_content 一致。
"""

from alembic import op

revision: str = "b7d2e4f60a58"
down_revision: str | None = "a3f8c2d91e47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE quality.quality_change_controls "
        "ALTER COLUMN change_object TYPE TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE quality.quality_change_controls "
        "ALTER COLUMN change_object TYPE VARCHAR(255)"
    )
