"""Add feishu form url columns to warehouse page feishu configs."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000050"
down_revision: str | None = "c9d400000049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "warehouse_page_feishu_configs"
_SCHEMA = "warehouse"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "feishu_inbound_form_url",
            sa.String(length=512),
            nullable=True,
            comment="飞书多维表单分享链接（入库登记入口）",
        ),
        schema=_SCHEMA,
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "feishu_outbound_form_url",
            sa.String(length=512),
            nullable=True,
            comment="飞书多维表单分享链接（出库登记入口）",
        ),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "feishu_outbound_form_url", schema=_SCHEMA)
    op.drop_column(_TABLE, "feishu_inbound_form_url", schema=_SCHEMA)
