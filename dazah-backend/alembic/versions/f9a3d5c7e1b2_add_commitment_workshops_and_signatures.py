"""安全承诺车间分填报与签署公告

- ``safety.safety_commitment_workshop_configs``：车间填报配置（12 车间
  名单 + 各自填报负责人），惰性种子由服务层写入。
- ``safety.safety_commitment_workshop_fills``：每日各车间企业状态填报
  记录（report_date + workshop_name 软删内唯一，可覆盖重填）。
- ``safety.safety_commitment_signatures``：企业安全承诺公告手写签名
  存档（每日一条，重签覆盖）。
- ``safety.safety_commitment_reports`` 加列 workshop_summary（汇总时
  12 车间明细快照）。
- ``safety.feishu_app_settings`` 加列 commitment_signer_open_id（签署
  人）与 commitment_remind_interval_minutes（车间催办间隔，默认 30）。

Revision ID: f9a3d5c7e1b2
Revises: e7c2a9f4b6d8
Create Date: 2026-11-14 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f9a3d5c7e1b2"
down_revision: str | None = "e7c2a9f4b6d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

jsonb = postgresql.JSONB(astext_type=sa.Text())


def _base_columns() -> list[sa.Column]:
    """每张表独立生成基础列（Column 对象不可跨表复用）。"""
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    ]


def _base_constraints() -> tuple[sa.Constraint, ...]:
    return (
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    op.create_table(
        "safety_commitment_workshop_configs",
        *_base_columns(),
        sa.Column(
            "workshop_name",
            sa.String(100),
            nullable=False,
            comment="车间名称（含括号身份）",
        ),
        sa.Column(
            "reporter_open_id",
            sa.String(100),
            nullable=True,
            comment="车间填报负责人飞书 open_id",
        ),
        sa.Column(
            "reporter_name",
            sa.String(100),
            nullable=True,
            comment="车间填报负责人姓名（展示用）",
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="排序",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="是否启用该车间填报",
        ),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "uq_safety_commitment_ws_config_name",
        "safety_commitment_workshop_configs",
        ["workshop_name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="safety",
    )

    op.create_table(
        "safety_commitment_workshop_fills",
        *_base_columns(),
        sa.Column("report_date", sa.Date(), nullable=False, comment="报告日期"),
        sa.Column("workshop_name", sa.String(100), nullable=False, comment="车间名称"),
        sa.Column(
            "fields",
            jsonb,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="企业状态全套填报数据（与日报 enterprise_status 同构）",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="车间备注"),
        sa.Column(
            "filled_by_name",
            sa.String(100),
            nullable=True,
            comment="填报人姓名",
        ),
        sa.Column(
            "filled_by_open_id",
            sa.String(100),
            nullable=True,
            comment="填报人飞书 open_id",
        ),
        sa.Column(
            "filled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近提交时间",
        ),
        sa.Column(
            "source",
            sa.String(20),
            nullable=True,
            comment="填报来源: feishu/web",
        ),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "uq_safety_commitment_ws_fill",
        "safety_commitment_workshop_fills",
        ["report_date", "workshop_name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="safety",
    )

    op.create_table(
        "safety_commitment_signatures",
        *_base_columns(),
        sa.Column("report_date", sa.Date(), nullable=False, comment="承诺公告日期"),
        sa.Column(
            "signer_open_id",
            sa.String(100),
            nullable=True,
            comment="签署人飞书 open_id",
        ),
        sa.Column(
            "signer_name",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="签署人姓名",
        ),
        sa.Column(
            "image_key",
            sa.String(500),
            nullable=False,
            comment="签名 PNG 存储键",
        ),
        sa.Column(
            "signed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="签名时间",
        ),
        sa.Column(
            "reused",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="是否复用历史签名（非现场手写）",
        ),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "uq_safety_commitment_signatures_date",
        "safety_commitment_signatures",
        ["report_date"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="safety",
    )

    op.add_column(
        "safety_commitment_reports",
        sa.Column(
            "workshop_summary",
            jsonb,
            nullable=True,
            comment="车间填报明细快照（12 车间各自提交的企业状态全套，汇总生成时写入）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "commitment_signer_open_id",
            sa.String(100),
            nullable=True,
            comment="企业安全承诺签署人 open_id（主要负责人，发布后推手写签名）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "commitment_remind_interval_minutes",
            sa.Integer(),
            nullable=True,
            server_default="30",
            comment="车间未填报催办间隔（分钟，默认 30）",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column(
        "feishu_app_settings",
        "commitment_remind_interval_minutes",
        schema="safety",
    )
    op.drop_column("feishu_app_settings", "commitment_signer_open_id", schema="safety")
    op.drop_column("safety_commitment_reports", "workshop_summary", schema="safety")
    op.drop_index(
        "uq_safety_commitment_signatures_date",
        table_name="safety_commitment_signatures",
        schema="safety",
    )
    op.drop_table("safety_commitment_signatures", schema="safety")
    op.drop_index(
        "uq_safety_commitment_ws_fill",
        table_name="safety_commitment_workshop_fills",
        schema="safety",
    )
    op.drop_table("safety_commitment_workshop_fills", schema="safety")
    op.drop_index(
        "uq_safety_commitment_ws_config_name",
        table_name="safety_commitment_workshop_configs",
        schema="safety",
    )
    op.drop_table("safety_commitment_workshop_configs", schema="safety")
