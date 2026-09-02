"""人事 Agent 工具执行守卫测试：写操作确认门、未知工具、审计脱敏。

仅覆盖不触库的早退分支（未知工具 / 写工具未确认）与纯函数，
LLM 与 DB 均不接入（符合后端测试规范）。
"""

import json

import pytest

from app.modules.hr.ai_agent_service import (
    WRITE_TOOLS,
    _latest_user_text,
    _sanitize_args,
    execute_tool_call,
)


def test_latest_user_text_picks_last_user_string() -> None:
    messages = [
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "回复"},
        {"role": "user", "content": "确认执行"},
    ]
    assert _latest_user_text(messages) == "确认执行"


def test_latest_user_text_empty_when_no_user_or_non_str() -> None:
    assert _latest_user_text([{"role": "assistant", "content": "x"}]) == ""
    assert _latest_user_text([{"role": "user", "content": {"complex": 1}}]) == ""
    assert _latest_user_text([]) == ""


def test_sanitize_args_masks_non_pii_and_caps_length() -> None:
    out = _sanitize_args(
        {"employee_number": "E001", "id_card": "110101199001011234", "note": "长" * 50}
    )
    assert out["employee_number"] == "E001"
    assert out["id_card"] == "<masked>"
    assert len(out["note"]) <= 32


@pytest.mark.asyncio
async def test_execute_tool_call_unknown_tool() -> None:
    result = json.loads(
        await execute_tool_call(None, "no_such_tool", {}, messages=[])
    )
    assert result["success"] is False
    assert "未知工具" in result["error"]


@pytest.mark.asyncio
async def test_execute_tool_call_blocks_write_without_confirmation() -> None:
    tool = sorted(WRITE_TOOLS)[0]
    result = json.loads(
        await execute_tool_call(
            None, tool, {"employee_number": "E001"},
            messages=[{"role": "user", "content": "帮我记一下"}],
        )
    )
    assert result["success"] is False
    assert result["needs_confirmation"] is True
    assert "确认" in result["error"]
