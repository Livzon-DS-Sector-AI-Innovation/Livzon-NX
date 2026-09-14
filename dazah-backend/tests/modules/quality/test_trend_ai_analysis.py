"""成品检测趋势 AI 分析服务单测（mock llm_client，覆盖六类边界）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.quality.service import trend_ai_analysis as svc
from app.modules.quality.service.trend_ai_analysis import (
    run_product_trend_ai_analysis,
    run_trend_ai_analysis,
    validate_trend_ai_payload,
)


def _valid_raw() -> dict:
    return {
        "summary": "含量近 8 批持续上升，逼近上限",
        "trend_reading": "整体上行，斜率加快，关注 OOT。",
        "signals": [
            {
                "batch_no": "MC260808",
                "rule_type": "continuous_move",
                "severity": "high",
                "note": "连续 8 批上升",
            }
        ],
        "outlook": {"direction": "up", "batches_to_limit": 5, "risk": "或越限"},
        "recommendation": "建议加严监测",
        "confidence": "medium",
    }


def _patch_llm(monkeypatch, *, chat_json: AsyncMock) -> None:
    monkeypatch.setattr(
        svc,
        "get_config",
        AsyncMock(return_value=SimpleNamespace(model_name="q-test")),
    )
    monkeypatch.setattr(type(svc.llm_client), "chat_json", chat_json)


def _base_kwargs() -> dict:
    points = [
        {"batch_no": f"MC2608{k:02d}", "value": 97.0 + k * 0.2}
        for k in range(1, 9)
    ]
    return {
        "source_label": "霉酚酸（内控）",
        "metric_label": "含量（干品）",
        "points": points,
        "mean": 97.8,
        "std_dev": 0.5,
        "upper_control_limit": 99.3,
        "lower_control_limit": 96.3,
        "spec_lines": [{"label": "标准上限", "value": 103.0}],
        "anomalies": [
            {
                "rule_type": "continuous_move",
                "severity": "medium",
                "trend_end_batch": "MC260808",
                "description": "连续 8 批上升",
                "evidence": {"direction": "up"},
            }
        ],
    }


# ─── 校验器 ──────────────────────────────────────────────────────


def test_validate_keeps_valid_payload() -> None:
    clean = validate_trend_ai_payload(_valid_raw())
    assert clean["confidence"] == "medium"
    assert clean["outlook"]["direction"] == "up"
    assert clean["outlook"]["batches_to_limit"] == 5
    assert clean["signals"][0]["rule_type"] == "continuous_move"


def test_validate_drops_unknown_rule_and_falls_back_enum() -> None:
    raw = _valid_raw()
    raw["signals"] = [
        {"rule_type": "made_up", "severity": "high"},  # 非法规则 → 丢弃
        {"rule_type": "mean_shift", "severity": "bogus"},  # 非法严重度 → medium
    ]
    raw["confidence"] = "certain"  # 非法置信度 → low
    raw["outlook"] = {"direction": "sideways", "batches_to_limit": -3, "risk": "x"}
    clean = validate_trend_ai_payload(raw)
    assert len(clean["signals"]) == 1
    assert clean["signals"][0]["severity"] == "medium"
    assert clean["confidence"] == "low"
    assert clean["outlook"]["direction"] == "flat"
    assert clean["outlook"]["batches_to_limit"] == 0  # 负数钳到 0


def test_validate_clips_long_text_and_handles_null_batches() -> None:
    raw = _valid_raw()
    raw["summary"] = "字" * 500
    raw["outlook"]["batches_to_limit"] = None
    clean = validate_trend_ai_payload(raw)
    assert len(clean["summary"]) == 120
    assert clean["outlook"]["batches_to_limit"] is None


# ─── 正常 ────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_run_trend_ai_completed(monkeypatch) -> None:
    chat_json = AsyncMock(return_value=_valid_raw())
    _patch_llm(monkeypatch, chat_json=chat_json)
    result = await run_trend_ai_analysis(**_base_kwargs())
    assert result["status"] == "completed"
    assert result["model_name"] == "q-test"
    assert result["ai_summary"]["summary"].startswith("含量")
    chat_json.assert_awaited_once()


# ─── 无配置 ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_run_trend_ai_no_config(monkeypatch) -> None:
    monkeypatch.setattr(svc, "get_config", AsyncMock(side_effect=LLMConfigError("no")))
    monkeypatch.setattr(type(svc.llm_client), "chat_json", AsyncMock())
    result = await run_trend_ai_analysis(**_base_kwargs())
    assert result["status"] == "failed"
    assert result["error"] == "no_config"
    assert result["ai_summary"] is None


# ─── 无效输出（不重试） ──────────────────────────────────────────


@pytest.mark.anyio
async def test_run_trend_ai_invalid_output(monkeypatch) -> None:
    chat_json = AsyncMock(side_effect=LLMOutputError("bad", "raw"))
    _patch_llm(monkeypatch, chat_json=chat_json)
    result = await run_trend_ai_analysis(**_base_kwargs())
    assert result["status"] == "failed"
    assert result["error"] == "invalid_output"
    # 契约不符只调用一次（不重试）
    assert chat_json.await_count == 1


@pytest.mark.anyio
async def test_run_trend_ai_validation_error_on_payload(monkeypatch) -> None:
    # chat_json 返回缺键结构 → validate 抛错？validate 不抛错而是裁剪；
    # 这里覆盖 chat_json 侧 expected_keys 抛 LLMOutputError 已在上一例；
    # 本例：返回可解析但 outlook 非 dict，validate 应稳健回退默认
    raw = _valid_raw()
    raw["outlook"] = "not a dict"
    _patch_llm(monkeypatch, chat_json=AsyncMock(return_value=raw))
    result = await run_trend_ai_analysis(**_base_kwargs())
    assert result["status"] == "completed"
    assert result["ai_summary"]["outlook"]["direction"] == "flat"


# ─── 限流：耗尽后失败并带 model_name ─────────────────────────────


@pytest.mark.anyio
async def test_run_trend_ai_rate_limit_exhausted(monkeypatch) -> None:
    chat_json = AsyncMock(side_effect=LLMRateLimitError("rate limited"))
    _patch_llm(monkeypatch, chat_json=chat_json)
    # 缩短退避，避免测试慢
    monkeypatch.setattr(svc.asyncio, "sleep", AsyncMock())
    result = await run_trend_ai_analysis(**_base_kwargs())
    assert result["status"] == "failed"
    assert result["error"] == "rate_limited"
    assert result["model_name"] == "q-test"
    assert chat_json.await_count == svc._AI_MAX_RETRIES


@pytest.mark.anyio
async def test_run_trend_ai_rate_limit_then_success(monkeypatch) -> None:
    chat_json = AsyncMock(side_effect=[LLMRateLimitError("429"), _valid_raw()])
    _patch_llm(monkeypatch, chat_json=chat_json)
    monkeypatch.setattr(svc.asyncio, "sleep", AsyncMock())
    result = await run_trend_ai_analysis(**_base_kwargs())
    assert result["status"] == "completed"
    assert chat_json.await_count == 2


# ─── 超时 / 供应商失败 ───────────────────────────────────────────


@pytest.mark.anyio
async def test_run_trend_ai_provider_error(monkeypatch) -> None:
    chat_json = AsyncMock(side_effect=LLMProviderError("boom"))
    _patch_llm(monkeypatch, chat_json=chat_json)
    result = await run_trend_ai_analysis(**_base_kwargs())
    assert result["status"] == "failed"
    assert result["error"] == "provider_error"


@pytest.mark.anyio
async def test_run_trend_ai_timeout(monkeypatch) -> None:
    async def _slow(*args, **kwargs):
        import asyncio as _a

        await _a.sleep(3600)

    _patch_llm(monkeypatch, chat_json=AsyncMock(side_effect=_slow))
    # 缩短内部超时+余量并把重试压到 1 次，让外层 wait_for 快速超时（不 patch
    # sleep，否则会连带取消 _slow 的长睡眠使 wait_for 不再超时）
    monkeypatch.setattr(svc, "_AI_SINGLE_TIMEOUT", 0.01)
    monkeypatch.setattr(svc, "_AI_TIMEOUT_MARGIN", 0.05)
    monkeypatch.setattr(svc, "_AI_MAX_RETRIES", 1)
    result = await run_trend_ai_analysis(**_base_kwargs())
    assert result["status"] == "failed"
    assert result["error"] == "timeout"


# ─── 产品级（多指标合并一次分析） ────────────────────────────────


def _valid_product_raw() -> dict:
    raw = _valid_raw()
    raw["metric_findings"] = [
        {"metric_label": "含量（干品）", "summary": "持续上升，逼近上限"},
        {"metric_label": "", "summary": "缺指标名 → 丢弃"},
        "not-a-dict",
    ]
    return raw


def test_validate_product_level_cleans_metric_findings() -> None:
    clean = validate_trend_ai_payload(_valid_product_raw(), product_level=True)
    assert len(clean["metric_findings"]) == 1
    assert clean["metric_findings"][0]["metric_label"] == "含量（干品）"
    # 非产品级：不产出 findings 键
    plain = validate_trend_ai_payload(_valid_product_raw())
    assert "metric_findings" not in plain


def _product_kwargs() -> dict:
    return {
        "source_label": "霉酚酸（内控）",
        "period": "2026-09",
        "metrics": [
            {
                "metric_label": "含量（干品）",
                "points": _base_kwargs()["points"],
                "mean": 97.8,
                "std_dev": 0.5,
                "upper_control_limit": 99.3,
                "lower_control_limit": 96.3,
                "spec_lines": [{"label": "标准上限", "value": 103.0}],
                "anomalies": _base_kwargs()["anomalies"],
            }
        ],
    }


@pytest.mark.anyio
async def test_run_product_trend_ai_completed(monkeypatch) -> None:
    chat_json = AsyncMock(return_value=_valid_product_raw())
    _patch_llm(monkeypatch, chat_json=chat_json)
    result = await run_product_trend_ai_analysis(**_product_kwargs())
    assert result["status"] == "completed"
    assert len(result["ai_summary"]["metric_findings"]) == 1
    # 一次模型调用，expected_keys 含 metric_findings
    chat_json.assert_awaited_once()
    assert "metric_findings" in chat_json.await_args.kwargs["expected_keys"]


@pytest.mark.anyio
async def test_run_product_trend_ai_no_config(monkeypatch) -> None:
    monkeypatch.setattr(svc, "get_config", AsyncMock(side_effect=LLMConfigError("no")))
    monkeypatch.setattr(type(svc.llm_client), "chat_json", AsyncMock())
    result = await run_product_trend_ai_analysis(**_product_kwargs())
    assert result["status"] == "failed"
    assert result["error"] == "no_config"
