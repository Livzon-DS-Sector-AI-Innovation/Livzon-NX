"""core.llm_configs add thinking and context fields

LLM 配置新增：enable_thinking / custom_context / context_window_tokens /
compress_threshold / stream_output（AI Agent 与导入 AI 的思考/上下文能力）。

Revision ID: c7e3a9b2d5f8
Revises: b4c2e8a1f3d6
Create Date: 2026-08-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e3a9b2d5f8"
down_revision: str | None = "b4c2e8a1f3d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE core.llm_configs
            ADD COLUMN IF NOT EXISTS enable_thinking boolean NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS custom_context text,
            ADD COLUMN IF NOT EXISTS context_window_tokens integer
                NOT NULL DEFAULT 200000,
            ADD COLUMN IF NOT EXISTS compress_threshold double precision
                NOT NULL DEFAULT 0.8,
            ADD COLUMN IF NOT EXISTS stream_output boolean NOT NULL DEFAULT true
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE core.llm_configs
            DROP COLUMN IF EXISTS enable_thinking,
            DROP COLUMN IF EXISTS custom_context,
            DROP COLUMN IF EXISTS context_window_tokens,
            DROP COLUMN IF EXISTS compress_threshold,
            DROP COLUMN IF EXISTS stream_output
        """
    )
