"""Add material synchronization observability and watermark metadata.

Revision ID: 7a8b9c0d1e2f
Revises: f5e4d3c2b1a0
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7a8b9c0d1e2f"
down_revision: str | None = "f5e4d3c2b1a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "material_source_configs",
        sa.Column(
            "sync_phase",
            sa.String(32),
            server_default="idle",
            nullable=False,
            comment="同步阶段",
        ),
        schema="procurement",
    )
    op.add_column(
        "material_source_configs",
        sa.Column(
            "sync_persisted_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="本次同步已持久化记录数",
        ),
        schema="procurement",
    )
    op.add_column(
        "material_source_configs",
        sa.Column(
            "sync_heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="同步最近心跳时间",
        ),
        schema="procurement",
    )
    op.add_column(
        "material_source_configs",
        sa.Column(
            "last_successful_modified_time",
            sa.Integer(),
            nullable=True,
            comment="最近成功同步观察到的飞书最大修改时间；未启用可靠过滤前仅作水位记录",
        ),
        schema="procurement",
    )


def downgrade() -> None:
    for name in (
        "last_successful_modified_time",
        "sync_heartbeat_at",
        "sync_persisted_count",
        "sync_phase",
    ):
        op.drop_column("material_source_configs", name, schema="procurement")
