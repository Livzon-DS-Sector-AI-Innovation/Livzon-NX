"""成品检测趋势 AI 分析服务（调用层，不含渲染/推送/落库）。

严格对齐 validation_review 的 LLM 边界：模块级 ``llm_client`` 与 ``get_config``，
限流指数退避有上限、结构化输出先白名单校验再落库；LLM 结论仅作趋势辅助解读，
不写回任何质量业务字段。本模块可被后台 job 复用（渲染/推送/落库在 calc 侧）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.core.llm.config import get_config
from app.modules.quality.service.trend_ai_prompt import (
    CONFIDENCE_LEVELS,
    SEVERITY_LEVELS,
    build_trend_ai_prompt,
)

logger = logging.getLogger(__name__)

_AI_MAX_RETRIES = 3
# 单次趋势解读覆盖多条指标，给足预算但仍设上限，避免后台任务无限挂起
_AI_SINGLE_TIMEOUT = 120
# 外层 wait_for 相对内层超时留出的固定余量（秒）
_AI_TIMEOUT_MARGIN = 15

_EXPECTED_KEYS = [
    "summary",
    "trend_reading",
    "signals",
    "outlook",
    "recommendation",
    "confidence",
]
_VALID_RULE_TYPES = {
    "month_level",
    "month_slope",
    "slope_change",
    "month_over_month",
    # 旧口径（历史缓存行兼容）
    "continuous_move",
    "slope_break",
    "mean_shift",
    "level_step",
}
_VALID_DIRECTIONS = {"up", "down", "flat"}

# 各文本字段最大长度（防超长输出撑爆卡片/前端）
_LIMITS = {
    "summary": 120,
    "trend_reading": 600,
    "note": 160,
    "risk": 160,
    "recommendation": 200,
}


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _clean_signal(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    rule_type = str(item.get("rule_type") or "").strip()
    if rule_type not in _VALID_RULE_TYPES:
        return None
    severity = str(item.get("severity") or "").strip()
    if severity not in SEVERITY_LEVELS:
        severity = "medium"
    return {
        "batch_no": _clip(item.get("batch_no"), 128),
        "rule_type": rule_type,
        "severity": severity,
        "note": _clip(item.get("note"), _LIMITS["note"]),
    }


def _clean_outlook(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    direction = str(raw.get("direction") or "").strip()
    if direction not in _VALID_DIRECTIONS:
        direction = "flat"
    batches_raw = raw.get("batches_to_limit")
    batches_to_limit: int | None = None
    if isinstance(batches_raw, bool):
        batches_to_limit = None
    elif isinstance(batches_raw, (int, float)):
        batches_to_limit = max(0, int(batches_raw))
    elif isinstance(batches_raw, str) and batches_raw.strip().lstrip("-").isdigit():
        batches_to_limit = max(0, int(batches_raw.strip()))
    return {
        "direction": direction,
        "batches_to_limit": batches_to_limit,
        "risk": _clip(raw.get("risk"), _LIMITS["risk"]),
    }


def validate_trend_ai_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """把模型原始输出裁剪为可信结构：白名单/枚举/长度/数值校验。

    缺关键字段由 chat_json 的 expected_keys 先行抛错；这里进一步丢弃非法
    signal 与回退非法枚举，保证可安全落库与展示。
    """
    confidence = str(raw.get("confidence") or "").strip()
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "low"
    signals_raw = raw.get("signals")
    signals: list[dict[str, Any]] = []
    if isinstance(signals_raw, list):
        for item in signals_raw[:20]:
            cleaned = _clean_signal(item)
            if cleaned is not None:
                signals.append(cleaned)
    return {
        "summary": _clip(raw.get("summary"), _LIMITS["summary"]),
        "trend_reading": _clip(raw.get("trend_reading"), _LIMITS["trend_reading"]),
        "signals": signals,
        "outlook": _clean_outlook(raw.get("outlook")),
        "recommendation": _clip(raw.get("recommendation"), _LIMITS["recommendation"]),
        "confidence": confidence,
    }


async def _call_trend_llm(
    prompt: str,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """调用 LLM 并校验；返回 (校验后载荷|None, model_name, error_code)。

    限流指数退避至多重试；无配置/输出非法/供应商失败分别映射独立错误码，
    绝不把 raw_response/密钥回传上层。
    """
    try:
        config = await get_config("text")
    except LLMConfigError:
        return None, None, "no_config"
    model_name = getattr(config, "model_name", None)

    last_error: str | None = None
    for attempt in range(_AI_MAX_RETRIES):
        try:
            raw = await asyncio.wait_for(
                llm_client.chat_json(
                    [{"role": "user", "content": prompt}],
                    expected_keys=_EXPECTED_KEYS,
                    temperature=0.2,
                    timeout=_AI_SINGLE_TIMEOUT,
                ),
                timeout=_AI_SINGLE_TIMEOUT + _AI_TIMEOUT_MARGIN,
            )
        except LLMRateLimitError:
            last_error = "rate_limited"
            if attempt < _AI_MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)
                continue
            return None, model_name, last_error
        except LLMOutputError:
            return None, model_name, "invalid_output"
        except TimeoutError:
            last_error = "timeout"
            if attempt < _AI_MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)
                continue
            return None, model_name, last_error
        except LLMProviderError:
            return None, model_name, "provider_error"
        except Exception as exc:  # noqa: BLE001 —— 兜底，不泄露堆栈
            logger.warning("trend ai llm call failed: %s", type(exc).__name__)
            return None, model_name, "provider_error"

        try:
            return validate_trend_ai_payload(raw), model_name, None
        except LLMOutputError:
            return None, model_name, "invalid_output"
    return None, model_name, last_error or "provider_error"


async def run_trend_ai_analysis(
    *,
    source_label: str,
    metric_label: str,
    points: list[dict[str, Any]],
    mean: float | None,
    std_dev: float | None,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
    spec_lines: list[dict[str, Any]] | None,
    anomalies: list[dict[str, Any]],
) -> dict[str, Any]:
    """对单指标的趋势异常做 AI 解读，返回状态字典供 job 落库。

    status：completed（含 ai_summary）/ 失败原因码。失败时 ai_summary=None，
    调用方降级为仅展示确定性统计结论。
    """
    prompt = build_trend_ai_prompt(
        source_label=source_label,
        metric_label=metric_label,
        points=points,
        mean=mean,
        std_dev=std_dev,
        upper_control_limit=upper_control_limit,
        lower_control_limit=lower_control_limit,
        spec_lines=spec_lines,
        anomalies=anomalies,
    )
    payload, model_name, error = await _call_trend_llm(prompt)
    if error is not None:
        return {
            "status": "failed",
            "error": error,
            "model_name": model_name,
            "ai_summary": None,
        }
    return {
        "status": "completed",
        "error": None,
        "model_name": model_name,
        "ai_summary": payload,
    }
