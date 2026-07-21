"""add agent skills and workflows

Revision ID: 8f2d4c6a9b10
Revises: 3b7d9a2c4e6f
Create Date: 2026-07-01 00:00:00.000000
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8f2d4c6a9b10"
down_revision: str | None = "3b7d9a2c4e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WORKFLOW_SKILL_CONTENT = (
    "# Livzon 工作流创建助手\n\n"
    "当用户希望创建、查询、启停、运行或查看工作流状态时，按以下流程处理。\n\n"
    "1. 先调用 `dazah_tool` 的 `agent.list_workflow_capabilities`，"
    "获取当前可编排业务能力。只能使用返回结果中的 "
    "`workflow_allowed=true` 操作。\n"
    "2. 如果用户需求缺少必要业务字段，先用简短问题澄清；"
    "不要编造库存、采购、合同、飞书同步等数据。\n"
    "3. 创建工作流时调用 `agent.create_workflow`，步骤必须按 "
    "`order/title/operation/params/body/description` 输出。\n"
    "4. 工作流步骤不得包含高风险人工责任判断操作，例如审批、驳回、"
    "批准、重启。遇到这类需求时，说明只能查询和整理背景，"
    "最终操作需要用户到业务页面自行判断。\n"
    "5. 查询、启用、停用、运行工作流时分别使用 "
    "`agent.list_workflows`、`agent.set_workflow_enabled`、"
    "`agent.run_workflow`、`agent.get_workflow_run`。\n"
    "6. 写操作只会生成确认项。用户确认前，不要声称工作流已经创建、"
    "启停或运行完成。\n"
    "7. 回答使用业务卡片式文本，展示工作流名称、状态、步骤、"
    "当前运行状态和下一步动作；不要使用 Markdown 表格。\n"
)


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "agent_skills",
        *_base_columns(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "trigger_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="active", nullable=False
        ),
        sa.Column("is_builtin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_core_agent_skills_name"),
        schema="core",
        comment="Agent progressive disclosure skills",
    )
    op.create_index(
        "ix_core_agent_skills_name", "agent_skills", ["name"], schema="core"
    )
    op.create_index(
        "ix_core_agent_skills_status", "agent_skills", ["status"], schema="core"
    )

    op.create_table(
        "agent_workflows",
        *_base_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default="enabled", nullable=False
        ),
        sa.Column(
            "trigger_phrases",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("source_skill", sa.String(length=120), nullable=True),
        sa.Column("source_request", sa.Text(), nullable=True),
        sa.Column("last_run_id", sa.Uuid(), nullable=True),
        sa.Column("last_run_status", sa.String(length=32), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
        comment="Agent user workflow definitions",
    )
    op.create_index(
        "ix_core_agent_workflows_user_id", "agent_workflows", ["user_id"], schema="core"
    )
    op.create_index(
        "ix_core_agent_workflows_session_id",
        "agent_workflows",
        ["session_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_workflows_status", "agent_workflows", ["status"], schema="core"
    )

    op.create_table(
        "agent_workflow_runs",
        *_base_columns(),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column("current_step", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "steps_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "step_results",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="core",
        comment="Agent workflow run state",
    )
    op.create_index(
        "ix_core_agent_workflow_runs_workflow_id",
        "agent_workflow_runs",
        ["workflow_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_workflow_runs_user_id",
        "agent_workflow_runs",
        ["user_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_workflow_runs_session_id",
        "agent_workflow_runs",
        ["session_id"],
        schema="core",
    )
    op.create_index(
        "ix_core_agent_workflow_runs_status",
        "agent_workflow_runs",
        ["status"],
        schema="core",
    )

    skills = sa.table(
        "agent_skills",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("trigger_keywords", postgresql.JSONB()),
        sa.column("content", sa.Text()),
        sa.column("status", sa.String()),
        sa.column("is_builtin", sa.Boolean()),
        sa.column("version", sa.Integer()),
        schema="core",
    )
    op.bulk_insert(
        skills,
        [
            {
                "id": uuid.UUID("0d5fc447-e6bd-4d11-a3df-75ccdb2af971"),
                "name": "livzon-workflow-builder",
                "title": "Livzon 工作流创建助手",
                "description": (
                    "当用户提到工作流、流程、自动化、编排、SOP、运行、启用、停用、状态等意图时，"
                    "用于基于当前 Dazah 可操作业务能力创建、"
                    "查询、启停和运行助手工作流。"
                ),
                "trigger_keywords": [
                    "工作流",
                    "流程",
                    "自动化",
                    "编排",
                    "SOP",
                    "运行",
                    "启用",
                    "停用",
                    "状态",
                ],
                "content": WORKFLOW_SKILL_CONTENT,
                "status": "active",
                "is_builtin": True,
                "version": 1,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_agent_workflow_runs_status",
        table_name="agent_workflow_runs",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_workflow_runs_session_id",
        table_name="agent_workflow_runs",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_workflow_runs_user_id",
        table_name="agent_workflow_runs",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_workflow_runs_workflow_id",
        table_name="agent_workflow_runs",
        schema="core",
    )
    op.drop_table("agent_workflow_runs", schema="core")
    op.drop_index(
        "ix_core_agent_workflows_status",
        table_name="agent_workflows",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_workflows_session_id",
        table_name="agent_workflows",
        schema="core",
    )
    op.drop_index(
        "ix_core_agent_workflows_user_id",
        table_name="agent_workflows",
        schema="core",
    )
    op.drop_table("agent_workflows", schema="core")
    op.drop_index(
        "ix_core_agent_skills_status", table_name="agent_skills", schema="core"
    )
    op.drop_index(
        "ix_core_agent_skills_name", table_name="agent_skills", schema="core"
    )
    op.drop_table("agent_skills", schema="core")
