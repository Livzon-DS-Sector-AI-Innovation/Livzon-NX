from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.equipment.service import inspection_feishu, inspection_session
from app.modules.equipment.service.inspection_session import SessionState


def _patch_commands(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    mocks = {
        name: AsyncMock()
        for name in (
            "_cmd_cancel",
            "_cmd_continue",
            "_cmd_help",
            "_cmd_modify",
            "_cmd_progress",
            "_cmd_skip",
            "_cmd_start",
            "_cmd_submit",
            "_handle_inspection_selection",
            "_handle_manual_submit",
            "_handle_work_order_selection",
            "_reply_text",
        )
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(inspection_feishu, name, mock)
    return mocks


@pytest.mark.anyio
async def test_text_router_ignores_empty_and_handles_selection_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_commands(monkeypatch)
    get_selection: Any = AsyncMock(return_value=None)
    clear_selection: Any = AsyncMock()
    monkeypatch.setattr(inspection_session, "get_selection", get_selection)
    monkeypatch.setattr(inspection_session, "clear_selection", clear_selection)

    await inspection_feishu.process_feishu_text("ou_1", "   ")
    get_selection.assert_not_awaited()

    get_selection.return_value = {
        "select_type": "inspection",
        "options": [{"index": 2, "task_id": "task-2"}],
    }
    await inspection_feishu.process_feishu_text("ou_1", "2")
    clear_selection.assert_awaited_once_with("ou_1")
    mocks["_handle_inspection_selection"].assert_awaited_once()

    get_selection.return_value = {
        "select_type": "work_order",
        "options": [{"index": 3, "work_order_id": "wo-3"}],
    }
    await inspection_feishu.process_feishu_text("ou_1", "3")
    mocks["_handle_work_order_selection"].assert_awaited_once()

    get_selection.return_value = {"select_type": "inspection", "options": []}
    await inspection_feishu.process_feishu_text("ou_1", "not-a-number")
    assert "有效数字" in mocks["_reply_text"].await_args.args[1]  # type: ignore[union-attr]

    await inspection_feishu.process_feishu_text("ou_1", "取消")
    assert clear_selection.await_count == 3
    assert "已取消选择" in mocks["_reply_text"].await_args.args[1]  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_text_router_covers_global_and_session_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_commands(monkeypatch)
    monkeypatch.setattr(
        inspection_session,
        "get_selection",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(inspection_session, "clear_selection", AsyncMock())
    get_session: Any = AsyncMock(return_value=None)
    clear_session: Any = AsyncMock()
    monkeypatch.setattr(inspection_feishu, "get_session", get_session)
    monkeypatch.setattr(inspection_feishu, "clear_session", clear_session)

    await inspection_feishu.process_feishu_text("ou_1", "帮助")
    mocks["_cmd_help"].assert_awaited_once_with("ou_1")

    await inspection_feishu.process_feishu_text("ou_1", "开始", "user_1")
    mocks["_cmd_start"].assert_awaited_once_with("ou_1", "user_1")

    await inspection_feishu.process_feishu_text("ou_1", "退出")
    assert "当前没有进行中的巡检任务" in mocks["_reply_text"].await_args.args[1]  # type: ignore[union-attr]

    get_session.return_value = {
        "state": SessionState.CONFIRMING,
        "task_no": "TASK-001",
    }
    for text, expected in (
        ("提交", "_cmd_submit"),
        ("取消", "_cmd_cancel"),
        ("修改 温度正常", "_cmd_modify"),
        ("进度", "_cmd_progress"),
        ("无法识别的自然语言", "_cmd_modify"),
    ):
        await inspection_feishu.process_feishu_text("ou_1", text)
        assert mocks[expected].await_count >= 1

    await inspection_feishu.process_feishu_text("ou_1", "退出")
    clear_session.assert_awaited_once_with("ou_1")
    assert "TASK-001" in mocks["_reply_text"].await_args.args[1]  # type: ignore[union-attr]

    get_session.return_value = {"state": SessionState.GUIDING}
    for text, expected in (
        ("跳过", "_cmd_skip"),
        ("状态", "_cmd_progress"),
        ("下一台", "_cmd_continue"),
        ("轴承温度正常", "_handle_manual_submit"),
    ):
        await inspection_feishu.process_feishu_text("ou_1", text)
        assert mocks[expected].await_count >= 1

    await inspection_feishu.process_feishu_text("ou_1", "提交")
    assert "当前没有待确认" in mocks["_reply_text"].await_args.args[1]  # type: ignore[union-attr]

    get_session.return_value = {"state": "unknown"}
    await inspection_feishu.process_feishu_text("ou_1", "进度")
    assert mocks["_cmd_progress"].await_count >= 2
    await inspection_feishu.process_feishu_text("ou_1", "任意命令")
    assert "当前状态不支持" in mocks["_reply_text"].await_args.args[1]  # type: ignore[union-attr]

    get_session.return_value = None
    await inspection_feishu.process_feishu_text("ou_1", "普通文本")
    assert "当前没有活跃的巡检任务" in mocks["_reply_text"].await_args.args[1]  # type: ignore[union-attr]
