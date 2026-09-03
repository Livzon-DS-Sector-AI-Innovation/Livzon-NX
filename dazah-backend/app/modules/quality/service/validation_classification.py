"""验证确认名称的 AI 分类服务.

真实年度台账（验证主计划 Base）没有"验证类别"列。平台按确认名称用 LLM
推断验证分类（设备确认/工艺验证/清洁验证/其他验证），并以名称为唯一键
缓存到 quality.validation_title_classifications，避免列表反复调用 LLM。

统一走 app.core.llm.llm_client；LLM 不可用时降级为保守关键词规则
（仅 清洁/工艺 两个高置信度词，绝不把"确认"一律当设备确认）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.modules.quality.models import ValidationTitleClassification

logger = logging.getLogger(__name__)

# 平台验证分类白名单（与前端 validationTypeLabelMap 对应）
VALIDATION_CATEGORY_CODES: set[str] = {
    "equipment_qualification",
    "process_validation",
    "cleaning_validation",
    "other_validation",
}

# 单次 LLM 调用最多分类的名称条数（控制上下文长度与输出稳定性）
_CLASSIFY_BATCH_SIZE = 40

_PROMPT_LINES: list[str] = [
    "你是药厂 GMP 验证管理专家。请把下列验证/确认记录的名称分类到唯一类别：",
    "- equipment_qualification：设备/仪器/设施的安装、运行、性能确认（IQ/OQ/PQ）",
    "  ，对象是具体设备仪器",
    "- process_validation：生产工艺验证（发酵、提炼、回收等工艺过程验证）",
    "- cleaning_validation：清洁验证（设备/厂房/管线的清洁或批间清洁验证）",
    "- other_validation：其他验证，含温湿度/温度分布验证、厂房确认、URS、",
    "  分析方法验证、储存时间验证等",
    "注意：",
    '- "温湿度分布确认""温度分布验证"是环境验证，不是设备确认',
    '- "厂房确认/厂房设施确认"是厂房确认，不是设备确认',
    '- 名称含"清洁"通常是清洁验证；名称含"工艺"通常是工艺验证',
    "- 空调净化系统、净化系统、空调机组的确认属于设备确认",
    '- 只输出 JSON：{{"items":'
    '[{{"index":1,"category":"equipment_qualification"}},...]}}',
    "",
    "记录列表：",
    "{titles}",
]
_PROMPT_TEMPLATE = chr(10).join(_PROMPT_LINES)


async def _classify_via_llm(titles: list[str]) -> dict[str, str] | None:
    """调用 LLM 批量分类；任何 LLM 异常都返回 None（由调用方降级）。"""
    numbered = "\n".join(
        f"{index}. {title}" for index, title in enumerate(titles, start=1)
    )
    try:
        raw: dict[str, Any] = await llm_client.chat_json(
            [
                {
                    "role": "user",
                    "content": _PROMPT_TEMPLATE.format(titles=numbered),
                }
            ],
            expected_keys=["items"],
            temperature=0,
        )
    except LLMConfigError:
        logger.warning("AI 服务尚未配置，验证名称分类降级为关键词规则")
        return None
    except LLMRateLimitError:
        logger.warning("LLM 速率限制，验证名称分类降级为关键词规则")
        return None
    except (LLMOutputError, LLMProviderError):
        logger.exception("LLM 分类调用失败，验证名称分类降级为关键词规则")
        return None

    items = raw.get("items")
    if not isinstance(items, list):
        return None
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
            category = str(item.get("category") or "").strip()
        except (TypeError, ValueError):
            continue
        if 1 <= index <= len(titles) and category in VALIDATION_CATEGORY_CODES:
            result[titles[index - 1]] = category
    return result or None


def _fallback_category(title: str) -> str:
    """LLM 不可用时的保守关键词降级：绝不把"确认"一律当设备确认。"""
    if "清洁" in title:
        return "cleaning_validation"
    if "工艺" in title:
        return "process_validation"
    return "other_validation"


async def _load_cached(
    db: AsyncSession, titles: list[str]
) -> dict[str, str]:
    rows = (
        await db.execute(
            select(ValidationTitleClassification).where(
                ValidationTitleClassification.title.in_(titles),
                ValidationTitleClassification.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    return {row.title: row.category for row in rows}


async def _save_classifications(
    db: AsyncSession,
    classified: dict[str, str],
    *,
    source: str,
    model_name: str | None,
) -> None:
    now = datetime.now(UTC)
    existing = (
        await db.execute(
            select(ValidationTitleClassification.title).where(
                ValidationTitleClassification.title.in_(list(classified)),
                ValidationTitleClassification.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    new_rows = [
        ValidationTitleClassification(
            title=title,
            category=category,
            source=source,
            model_name=model_name,
            classified_at=now,
        )
        for title, category in classified.items()
        if title not in set(existing)
    ]
    if new_rows:
        db.add_all(new_rows)
        await db.commit()


async def resolve_validation_categories(
    db: AsyncSession,
    titles: list[str],
) -> dict[str, str]:
    """返回每个确认名称的验证分类（带缓存，AI 推断，失败降级关键词）。"""
    normalized = {str(t).strip(): str(t).strip() for t in titles if str(t).strip()}
    if not normalized:
        return {}

    cached = await _load_cached(db, list(normalized))
    result = dict(cached)
    pending = [t for t in normalized if t not in cached]

    for start in range(0, len(pending), _CLASSIFY_BATCH_SIZE):
        batch = pending[start : start + _CLASSIFY_BATCH_SIZE]
        ai_result = await _classify_via_llm(batch)
        if ai_result:
            await _save_classifications(
                db, ai_result, source="ai", model_name=None
            )
            result.update(ai_result)
        for title in batch:
            if title not in result:
                fallback = _fallback_category(title)
                result[title] = fallback
                await _save_classifications(
                    db, {title: fallback}, source="fallback", model_name=None
                )
    return result
