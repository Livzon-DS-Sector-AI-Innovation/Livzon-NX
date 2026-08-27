"""HR AI 代理服务。

实现 Agent 循环：LLM 自主决定何时调用工具查询数据，然后据此回答。
支持标准 OpenAI function calling 和 Qwen/DashScope 文本格式。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMConfigError, LLMProviderError, LLMRateLimitError, llm_client
from app.modules.hr.ai_tools import ALL_TOOL_SCHEMAS, TOOL_EXECUTORS

logger = logging.getLogger(__name__)

# 最大工具调用轮数
MAX_TOOL_ROUNDS = 5

# Qwen 模型工具调用文本格式：call\n{json}\ncall\n{json}
_QWEN_TC_RE = re.compile(
    r"call\s*\n(\{[^}]+\})",
    re.MULTILINE,
)


def _parse_qwen_tool_calls(content: str) -> list[dict[str, Any]] | None:
    """解析 Qwen/DashScope 模型的文本格式工具调用。

    Qwen 会输出:
        call
        {"name": "func_name", "arguments": {...}}

    返回 OpenAI 兼容的 tool_calls 格式，或 None 表示无法解析。
    """
    if not content or "call" not in content[:200]:
        return None

    matches = _QWEN_TC_RE.findall(content)
    if not matches:
        return None

    tool_calls = []
    for i, json_str in enumerate(matches):
        try:
            parsed = json.loads(json_str)
            if "name" in parsed:
                tool_calls.append(
                    {
                        "id": f"qwen_tc_{i}",
                        "type": "function",
                        "function": {
                            "name": parsed["name"],
                            "arguments": json.dumps(parsed.get("arguments", {})),
                        },
                    }
                )
        except json.JSONDecodeError:
            continue

    return tool_calls if tool_calls else None


async def execute_tool_call(
    session: AsyncSession,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """执行单个工具调用并返回 JSON 字符串结果。

    Args:
        session: 数据库会话
        tool_name: 工具函数名
        arguments: LLM 解析出的参数

    Returns:
        JSON 字符串（含 success/data/error 字段）
    """
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return json.dumps(
            {"success": False, "error": f"未知工具: {tool_name}"}, ensure_ascii=False
        )

    try:
        logger.info(
            "Executing tool", extra={"tool": tool_name, "tool_args": str(arguments)}
        )
        data = await executor(session, **arguments)
        result = json.dumps(
            {
                "success": True,
                "data": data,
                "count": len(data) if isinstance(data, list) else 1,
            },
            ensure_ascii=False,
            default=str,
        )
        logger.info(
            "Tool executed", extra={"tool": tool_name, "result_len": len(result)}
        )
        return result
    except Exception as e:
        logger.exception("Tool execution failed", extra={"tool": tool_name})
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


async def run_agent_loop(
    session: AsyncSession,
    messages: list[dict[str, Any]],
    system_prompt: dict[str, Any],
) -> AsyncGenerator[dict[str, Any], None]:
    """执行 HR AI 代理循环。

    流程:
    1. 将系统提示词 + 用户消息注入 messages
    2. 循环调用 chat_with_tools，最多 MAX_TOOL_ROUNDS 轮
    3. 如果 LLM 想调用工具 → 执行 → 结果注入 → 继续循环
    4. 如果 LLM 直接回复 → 跳出循环
    5. 用 stream_chat 流式输出最终回复

    Yields:
        dict: {"type": "status", "text": "..."}  — 状态提示
        dict: {"type": "reasoning", "text": "..."} — 思考过程
        dict: {"type": "content", "text": "..."} — 回复内容
        dict: {"type": "done"} — 流结束
    """
    # 构建消息列表：系统提示词 + 用户历史对话
    full_messages = [system_prompt] + list(messages)

    # ── Phase 1: 工具调用循环 ──
    for round_num in range(MAX_TOOL_ROUNDS):
        try:
            response = await llm_client.chat_with_tools(
                full_messages,
                tools=ALL_TOOL_SCHEMAS,
                temperature=0.3,
                max_tokens=4096,
            )
        except (LLMRateLimitError, LLMProviderError, LLMConfigError):
            raise  # 向上抛出，由调用方处理

        # 如果 LLM 直接回复（不需要工具）
        tool_calls = response.get("tool_calls")

        # Qwen/DashScope 兼容：工具调用可能嵌在 content 文本中
        if not tool_calls and response.get("content"):
            qwen_calls = _parse_qwen_tool_calls(response["content"])
            if qwen_calls:
                logger.info(
                    "Parsed Qwen-format tool calls", extra={"count": len(qwen_calls)}
                )
                tool_calls = qwen_calls

        if not tool_calls:
            break

        # 将 assistant 消息（含 tool_calls）加入历史
        full_messages.append(
            {
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": tool_calls,
            }
        )

        # 逐个执行工具
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            try:
                arguments = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                arguments = {}

            # 发送状态提示
            tool_cn = _tool_label(tool_name)
            yield {"type": "status", "text": f"正在查询{tool_cn}..."}

            result = await execute_tool_call(session, tool_name, arguments)

            # 将工具结果加入历史
            full_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                }
            )

        # 发送分析状态
        yield {"type": "status", "text": "正在分析数据..."}

    # ── Phase 2: 流式输出最终回复 ──
    try:
        async for chunk in llm_client.stream_chat(full_messages, max_tokens=4096):
            yield chunk
    except (LLMRateLimitError, LLMProviderError, LLMConfigError):
        raise

    yield {"type": "done"}


def _tool_label(name: str) -> str:
    """工具名称 → 中文标签"""
    labels = {
        "hr_query_employee": "员工信息",
        "hr_count_by_field": "统计数据",
        "hr_query_departments": "部门信息",
        "hr_query_contract_expiring": "合同到期信息",
        "hr_query_training_records": "培训记录",
        "hr_query_offboarding": "离职记录",
        "hr_query_position_transfers": "调动记录",
        "hr_list_teams": "班组信息",
        "hr_list_trainers": "培训师名单",
        "hr_list_training_plans": "年度培训计划",
        "hr_list_training_evaluations": "培训评估",
        "hr_list_plan_tracking": "计划跟踪",
        "hr_list_contracts": "合同管理",
        "hr_create_training_record": "创建培训记录",
        "hr_create_offboarding_record": "创建离职记录",
        "hr_update_employee_basic": "更新员工信息",
    }
    return labels.get(name, name)
