"""update workflow skill batch guard

Revision ID: 9a1b2c3d4e5f
Revises: 8f2d4c6a9b10
Create Date: 2026-07-01 17:32:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9a1b2c3d4e5f"
down_revision: str | None = "8f2d4c6a9b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_WORKFLOW_SKILL_CONTENT = (
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

NEW_WORKFLOW_SKILL_CONTENT = (
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
    "5. 不得创建把上一步查询结果自动循环带入写操作的批量工作流。"
    "带 `{request_id}`、`{table_id}` 等路径参数的步骤必须提供明确 ID；"
    "如果用户想批量提交、批量同步或批量修改，先创建查询/提醒步骤，"
    "并提示用户逐项确认或到业务页面操作。\n"
    "6. 查询、启用、停用、运行工作流时分别使用 "
    "`agent.list_workflows`、`agent.set_workflow_enabled`、"
    "`agent.run_workflow`、`agent.get_workflow_run`。\n"
    "7. 写操作只会生成确认项。用户确认前，不要声称工作流已经创建、"
    "启停或运行完成。\n"
    "8. 回答使用业务卡片式文本，展示工作流名称、状态、步骤、"
    "当前运行状态和下一步动作；不要使用 Markdown 表格。\n"
)


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE core.agent_skills
            SET content = :content,
                version = version + 1,
                updated_at = now()
            WHERE name = 'livzon-workflow-builder'
              AND is_builtin IS true
              AND is_deleted IS false
            """
        ).bindparams(content=NEW_WORKFLOW_SKILL_CONTENT)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE core.agent_skills
            SET content = :content,
                version = GREATEST(version - 1, 1),
                updated_at = now()
            WHERE name = 'livzon-workflow-builder'
              AND is_builtin IS true
              AND is_deleted IS false
            """
        ).bindparams(content=OLD_WORKFLOW_SKILL_CONTENT)
    )
