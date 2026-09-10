"""检验进度 AI 分析（后端能力，无独立展示页）。

聚合 inspection_progress 的确定性统计 → llm_client.chat_json 解读 →
白名单裁剪校验。LLM 输出仅作辅助分析，不替代人工判断，不写入关键业务字段。
"""

from __future__ import annotations

import json
import time as time_module
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.modules.warehouse.inspection_progress import (
    SCOPE_LABELS,
    build_inspection_overview,
)

CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")

AI_ANALYSIS_EXPECTED_KEYS = [
    "overall_status",
    "risk_level",
    "key_findings",
    "suggestions",
    "summary_text",
]
_VALID_OVERALL_STATUS = {"正常", "需关注", "需紧急处理"}
_VALID_RISK_LEVEL = {"低", "中", "高"}
_MAX_FINDINGS = 8
_MAX_SUGGESTIONS = 8
_MAX_ITEM_LENGTH = 200
_MAX_SUMMARY_LENGTH = 600

_AI_ANALYSIS_CACHE: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}
_AI_ANALYSIS_CACHE_TTL_SECONDS = 600.0


def build_inspection_ai_messages(overview: dict[str, Any]) -> list[dict[str, str]]:
    """构造 AI 分析消息：人设 + 统计事实 + 严格 JSON 契约。"""
    system_content = (
        "你是制药工厂仓储质量管理分析专家，负责解读物料与成品的检验进度统计。"
        "统计事实由系统计算，你只需基于给定数字做解读，不得编造不存在的数据。"
        "请以 JSON 格式返回，包含以下字段：\n"
        "- overall_status: 总体状况（正常/需关注/需紧急处理）\n"
        "- risk_level: 风险等级（低/中/高）\n"
        "- key_findings: 关键发现列表（字符串数组，最多 8 条）\n"
        "- suggestions: 改进建议列表（字符串数组，最多 8 条）\n"
        "- summary_text: 简要总结文字（300 字以内）"
    )
    user_content = (
        f"请根据以下检验进度统计数据（范围：{overview.get('scope_label', '')}，"
        f"统计起点：{overview.get('start_date', '')}）生成分析：\n\n"
        f"{json.dumps(overview, ensure_ascii=False, indent=2, default=str)}"
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def validate_inspection_ai_payload(raw: Any) -> dict[str, Any]:
    """白名单裁剪校验：非法枚举回退默认、长度截断、类型兜底。"""
    if not isinstance(raw, dict):
        return {
            "overall_status": None,
            "risk_level": None,
            "key_findings": [],
            "suggestions": [],
            "summary_text": "",
        }

    def _clean_items(value: Any, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            if len(items) >= limit:
                break
            if not isinstance(item, str):
                continue
            text = item.strip()
            if text:
                items.append(text[:_MAX_ITEM_LENGTH])
        return items

    overall_status = str(raw.get("overall_status") or "").strip()
    if overall_status not in _VALID_OVERALL_STATUS:
        overall_status = "需关注"
    risk_level = str(raw.get("risk_level") or "").strip()
    if risk_level not in _VALID_RISK_LEVEL:
        risk_level = "中"
    summary_text = str(raw.get("summary_text") or "").strip()
    return {
        "overall_status": overall_status,
        "risk_level": risk_level,
        "key_findings": _clean_items(raw.get("key_findings"), _MAX_FINDINGS),
        "suggestions": _clean_items(raw.get("suggestions"), _MAX_SUGGESTIONS),
        "summary_text": summary_text[:_MAX_SUMMARY_LENGTH],
    }


def _degraded_payload(
    status: str, summary_text: str, scope_label: str
) -> dict[str, Any]:
    return {
        "status": status,
        "scope_label": scope_label,
        "summary_text": summary_text,
        "overall_status": None,
        "risk_level": None,
        "key_findings": [],
        "suggestions": [],
        "generated_at": datetime.now(CHINA_TIMEZONE).isoformat(),
    }


async def run_inspection_ai_analysis(
    session: AsyncSession,
    scope: str,
    *,
    days: int = 30,
    force: bool = False,
) -> dict[str, Any]:
    """对检验进度统计做 AI 分析；失败返回降级文案，不向上抛异常。"""
    scope_label = SCOPE_LABELS.get(scope, scope)
    cache_key = (scope, days)
    if not force:
        cached = _AI_ANALYSIS_CACHE.get(cache_key)
        if (
            cached
            and time_module.monotonic() - cached[0] < _AI_ANALYSIS_CACHE_TTL_SECONDS
        ):
            return cached[1]

    overview = await build_inspection_overview(session, scope, days=days)
    messages = build_inspection_ai_messages(overview)
    try:
        raw = await llm_client.chat_json(
            messages,
            expected_keys=AI_ANALYSIS_EXPECTED_KEYS,
            temperature=0.3,
            timeout=120,
        )
    except LLMConfigError:
        payload = _degraded_payload(
            "no_config", "AI 服务尚未配置，请改用人工分析。", scope_label
        )
    except LLMRateLimitError:
        payload = _degraded_payload(
            "rate_limited", "AI 服务繁忙，请稍后重试。", scope_label
        )
    except LLMOutputError:
        payload = _degraded_payload(
            "invalid_output", "AI 输出无法解析，请稍后重试。", scope_label
        )
    except TimeoutError:
        payload = _degraded_payload(
            "timeout", "AI 分析响应超时，请稍后重试。", scope_label
        )
    except LLMProviderError:
        payload = _degraded_payload(
            "provider_error", "AI 服务暂不可用，请稍后重试。", scope_label
        )
    else:
        payload = {
            "status": "completed",
            "scope_label": scope_label,
            **validate_inspection_ai_payload(raw),
            "generated_at": datetime.now(CHINA_TIMEZONE).isoformat(),
        }

    _AI_ANALYSIS_CACHE[cache_key] = (time_module.monotonic(), payload)
    return payload
