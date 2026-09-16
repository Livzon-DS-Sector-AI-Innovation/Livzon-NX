"""人事飞书设置拆分双应用：通讯录/部门管理 与 多维表格 各自独立配置。

背景（2026-09）：原 hr.hr_feishu_app_settings 是单行单应用，通讯录与多维
表格共用一套凭证。实际人事模块用两个独立飞书应用：
- contact（cli_aa0786256bf99cc5）：通讯录/部门管理/飞书联系人；
- bitable（cli_aa1e45ff77badcde）：多维表格同步。
本迁移给表加 purpose 列并置唯一约束，既有行归为 bitable；contact 行由
ensure 播种或页面填写。downgrade 回退为单行（保留 bitable 行）。

Revision ID: c9d400000038
Revises: c9d400000037
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000040"
down_revision: str | None = "c9d400000039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "hr_feishu_app_settings"
_SCHEMA = "hr"
_PURPOSE_COLUMN = "purpose"
_PURPOSES = ("contact", "bitable")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns(_TABLE, schema=_SCHEMA)}
    if _PURPOSE_COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(_PURPOSE_COLUMN, sa.String(20), nullable=False,
                      server_default="bitable"),
            schema=_SCHEMA,
        )
    # 既有唯一行归为 bitable（多维表格）；清掉同表多行旧行避免约束冲突
    bind.execute(sa.text(
        f"DELETE FROM {_SCHEMA}.{_TABLE} WHERE id NOT IN "
        f"(SELECT id FROM {_SCHEMA}.{_TABLE} ORDER BY created_at ASC LIMIT 1)"
    ))
    # 兼容历史空表：为 bitable 补一行空壳（页面种子也会 ensure）
    existing = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {_SCHEMA}.{_TABLE}")
    ).scalar_one()
    if existing == 0:
        bind.execute(sa.text(
            f"INSERT INTO {_SCHEMA}.{_TABLE} "
            "(id, purpose, app_id, app_secret, is_enabled, created_at, updated_at, is_deleted) "
            "VALUES (gen_random_uuid(), 'bitable', '', '', true, now(), now(), false)"
        ))
    op.create_unique_constraint(
        f"uq_{_TABLE}_purpose", _TABLE, [_PURPOSE_COLUMN], schema=_SCHEMA
    )


def downgrade() -> None:
    op.drop_constraint(f"uq_{_TABLE}_purpose", _TABLE, schema=_SCHEMA)
    # 保留 bitable 行作为单应用配置；删除 contact 行
    op.get_bind().execute(sa.text(
        f"DELETE FROM {_SCHEMA}.{_TABLE} WHERE {_PURPOSE_COLUMN} = 'contact'"
    ))
    op.drop_column(_TABLE, _PURPOSE_COLUMN, schema=_SCHEMA)
