"""检验进度 AI 分析（inspection_progress_ai）测试。

按项目规范 mock 业务模块实际导入的 llm_client，覆盖：
正常输出 / 无配置 / 无效输出 / 限流 / 超时 / 供应商失败 六类场景，
以及白名单裁剪校验与结果缓存。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.warehouse import inspection_progress_ai as ai_module
from app.modules.warehouse.inspection_progress import SCOPE_LABELS
from app.modules.warehouse.inspection_progress_ai import (
    build_inspection_ai_messages,
    run_inspection_ai_analysis,
    validate_inspection_ai_payload,
)


@pytest.fixture(autouse=True)
async def _create_transition_table(db_session: AsyncSession) -> None:
    """概览查询会读状态变更日志表；测试事务内自建。"""
    from app.modules.warehouse.models import MaterialStatusTransition

    await db_session.run_sync(
        lambda sync_db: MaterialStatusTransition.__table__.create(
            sync_db.connection(), checkfirst=True
        )
    )


async def test_ai_analysis_completed(db_session: AsyncSession) -> None:
    mock = AsyncMock(
        return_value={
            "overall_status": "正常",
            "risk_level": "低",
            "key_findings": ["近 30 天完成检验周期平稳"],
            "suggestions": ["继续保持"],
            "summary_text": "检验进度总体正常。",
        }
    )
    original = ai_module.llm_client.chat_json
    ai_module.llm_client.chat_json = mock  # type: ignore[method-assign]
    try:
        payload = await run_inspection_ai_analysis(
            db_session, "raw", days=7, force=True
        )
    finally:
        ai_module.llm_client.chat_json = original  # type: ignore[method-assign]

    assert payload["status"] == "completed"
    assert payload["scope_label"] == SCOPE_LABELS["raw"]
    assert payload["overall_status"] == "正常"
    assert payload["summary_text"] == "检验进度总体正常。"
    assert mock.await_count == 1
    # 消息契约：system 人设 + user 统计事实，expected_keys 传齐
    _, kwargs = mock.await_args
    assert "expected_keys" in kwargs
    assert mock.await_args.args[0][0]["role"] == "system"


async def test_ai_analysis_maps_llm_failures(
    db_session: AsyncSession, monkeypatch: Any
) -> None:
    cases = [
        (LLMConfigError("no config"), "no_config", "AI 服务尚未配置"),
        (LLMRateLimitError("429"), "rate_limited", "AI 服务繁忙"),
        (LLMOutputError("bad json"), "invalid_output", "无法解析"),
        (TimeoutError(), "timeout", "超时"),
        (LLMProviderError("502"), "provider_error", "暂不可用"),
    ]
    for error, expected_status, expected_text in cases:
        mock = AsyncMock(side_effect=error)
        monkeypatch.setattr(ai_module.llm_client, "chat_json", mock)
        payload = await run_inspection_ai_analysis(
            db_session, "raw", days=7, force=True
        )
        assert payload["status"] == expected_status, str(error)
        assert expected_text in payload["summary_text"]
        assert payload["key_findings"] == []
        assert payload["suggestions"] == []


async def test_ai_analysis_result_cached(db_session: AsyncSession) -> None:
    mock = AsyncMock(
        return_value={
            "overall_status": "正常",
            "risk_level": "低",
            "key_findings": [],
            "suggestions": [],
            "summary_text": "ok",
        }
    )
    original = ai_module.llm_client.chat_json
    ai_module.llm_client.chat_json = mock  # type: ignore[method-assign]
    try:
        await run_inspection_ai_analysis(db_session, "product", days=7, force=True)
        await run_inspection_ai_analysis(db_session, "product", days=7, force=False)
        await run_inspection_ai_analysis(db_session, "product", days=7, force=False)
        assert mock.await_count == 1  # 缓存命中，不重复调用
    finally:
        ai_module.llm_client.chat_json = original  # type: ignore[method-assign]


def test_validate_payload_whitelist_and_clamp() -> None:
    payload = validate_inspection_ai_payload(
        {
            "overall_status": "瞎编的状态",
            "risk_level": 123,
            "key_findings": ["发现A", 42, "  ", "发现B"]
            + [f"多余{i}" for i in range(10)],
            "suggestions": "不是列表",
            "summary_text": "长" * 1000,
            "extra_field": "ignored",
        }
    )
    # 非法枚举回退默认；非字符串项剔除；列表截断到 8 条；summary 截断
    assert payload["overall_status"] == "需关注"
    assert payload["risk_level"] == "中"
    assert payload["key_findings"] == ["发现A", "发现B"] + [
        f"多余{i}" for i in range(6)
    ]
    assert len(payload["key_findings"]) == 8
    assert payload["suggestions"] == []
    assert len(payload["summary_text"]) == 600
    assert "extra_field" not in payload


def test_validate_payload_rejects_non_dict() -> None:
    payload = validate_inspection_ai_payload(["not", "a", "dict"])
    assert payload["key_findings"] == []
    assert payload["summary_text"] == ""


def test_build_messages_contains_stats_contract() -> None:
    messages = build_inspection_ai_messages(
        {"scope": "raw", "scope_label": "原辅料及包材", "current": {"pending_count": 3}}
    )
    assert len(messages) == 2
    assert "JSON" in messages[0]["content"]
    assert "原辅料及包材" in messages[1]["content"]
    assert "pending_count" in messages[1]["content"]
