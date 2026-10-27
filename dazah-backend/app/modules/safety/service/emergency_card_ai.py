"""应急处置卡 AI 审阅：完整性检查与完善建议。

按 LLM 调用边界走「业务模块 Service → app.core.llm.llm_client」：
AI 输出仅作为辅助分析，须经过 Pydantic 校验；采纳建议由用户在页面上
逐条确认后写入，不代替人工责任判断。
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.core.exceptions import AppException
from app.core.llm import llm_client
from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.safety.models import EmergencyCard
from app.modules.safety.schemas.emergency_cards import (
    EmergencyCardCompletenessItem,
    EmergencyCardReviewResponse,
    EmergencyCardSuggestion,
)

REVIEW_INSTRUCTION = "\n".join(
    [
        "你是原料药工厂的资深安全管理专家。",
        "请审阅下面这张事故现场应急处置卡，检查内容完整性并给出完善建议。",
        "",
        "公司应急管理流程规则（审阅时必须遵守，不得违背）：",
        "- 报警流程：现场人员发现事故后只能逐级向内部领导上报",
        "  （岗位员工→班组长→车间负责人→公司安全管理部门/分管领导），",
        "  对外报警由公司统一决策执行。",
        "- 关于 119/120 等外部救援号码与对外报警的话题一律不谈：",
        "  卡面上有或没有外部号码都属正常写法，",
        "  completeness 不因此判 missing/unclear；",
        "  suggestions 不得出现任何涉及外部救援电话、119/120、对外报警的内容",
        "  （不建议补充、不建议删除、也不建议增加「严禁擅自拨打」之类的文字）；",
        "  summary 同样不得提及。",
        "- 完整性检查中的「报警与报告」只看内部逐级上报流程是否清晰；",
        "  「应急电话」只看内部联系电话登记是否齐全、准确。",
        "",
        "",
        "审阅输出要求：",
        "1. completeness：逐项检查以下要素是否齐备且具体——报警与报告、",
        "   个体防护用品、切断或隔离危险源、伤员抢救、疏散与警戒、应急处置方法、",
        "   应急电话、主要风险及后果、应急注意事项。",
        "   status 取 ok（已覆盖且具体）/ missing（缺失）/ unclear（有内容但不明确），",
        "   note 用一句话说明。",
        "2. suggestions：给出 2~5 条具体、可执行的完善建议；",
        "   section 指明建议补充的位置（steps=处置步骤 / phones=应急电话 /",
        "   risks=主要风险 / precautions=注意事项）；title 为建议标题；",
        "   content 为可直接追加进该部分的具体文字，",
        "   不得空泛（如「加强管理」），不得重复已有内容。",
        "3. summary：一句话总体评价。",
        "只输出 JSON 对象：",
        '{"summary": "...",',
        ' "completeness": [',
        '   {"item": "...", "status": "ok|missing|unclear", "note": "..."}],',
        ' "suggestions": [',
        '   {"section": "steps|phones|risks|precautions",',
        '    "title": "...", "content": "..."}]}',
        "",
        "应急处置卡内容：",
    ]
)


def build_card_digest(card: EmergencyCard) -> str:
    """把卡片内容拼成给模型的结构化文本（截断超长字段控制 token）。"""

    def clip(text: str, limit: int) -> str:
        text = (text or "").strip()
        return text if len(text) <= limit else text[:limit] + "…"

    lines = [
        f"标题：{card.title}",
        f"车间/部门：{card.workshop}",
        f"岗位：{card.position or '（车间级/公司级）'}",
        "处置步骤：",
    ]
    for index, step in enumerate(card.steps or [], 1):
        if not isinstance(step, dict):
            continue
        action = clip(str(step.get("action") or ""), 300)
        person = step.get("person") or "未注明"
        order = step.get("order") or index
        lines.append(
            f"{index}. [{order}] {step.get('step') or ''}：{action}（负责人：{person}）"
        )
    lines.append(f"应急电话：{clip(card.phones, 400) or '（空）'}")
    lines.append(f"主要导致风险及导致的后果：{clip(card.risks, 600) or '（空）'}")
    lines.append(f"应急注意事项：{clip(card.precautions, 600) or '（空）'}")
    for extra in card.extras or []:
        if isinstance(extra, dict) and extra.get("label"):
            content = clip(str(extra.get("content") or ""), 300)
            lines.append(f"{extra['label']}：{content}")
    return "\n".join(lines)


def _validate_review(raw: dict[str, Any]) -> EmergencyCardReviewResponse:
    """按业务校验过滤模型输出：非法条目丢弃；全空视为无效输出。"""

    completeness: list[EmergencyCardCompletenessItem] = []
    for item in raw.get("completeness") or []:
        if isinstance(item, dict):
            try:
                completeness.append(EmergencyCardCompletenessItem.model_validate(item))
            except ValidationError:
                continue

    suggestions: list[EmergencyCardSuggestion] = []
    for item in raw.get("suggestions") or []:
        if isinstance(item, dict):
            try:
                suggestions.append(EmergencyCardSuggestion.model_validate(item))
            except ValidationError:
                continue

    summary = str(raw.get("summary") or "").strip()
    if not summary and not completeness and not suggestions:
        raise LLMOutputError("AI 审阅结果为空")

    return EmergencyCardReviewResponse(
        summary=summary[:2000],
        completeness=completeness,
        suggestions=suggestions,
    )


async def review_emergency_card(card: EmergencyCard) -> EmergencyCardReviewResponse:
    """调用统一 LLM 客户端审阅卡片，输出结构化审阅结果。"""

    messages = [
        {
            "role": "user",
            "content": REVIEW_INSTRUCTION + build_card_digest(card),
        }
    ]
    try:
        raw = await llm_client.chat_json(
            messages,
            expected_keys=["summary", "completeness", "suggestions"],
        )
        return _validate_review(raw)
    except LLMConfigError as exc:
        raise AppException(
            status_code=400,
            message="尚未配置分析模型，请先在系统管理中启用 AI 模型配置",
        ) from exc
    except LLMRateLimitError as exc:
        raise AppException(
            status_code=429, message="模型调用触发限流，请稍后重试"
        ) from exc
    except LLMOutputError as exc:
        raise AppException(
            status_code=502, message="AI 返回内容无法解析，请重试"
        ) from exc
    except LLMProviderError as exc:
        raise AppException(
            status_code=502, message="模型服务暂不可用，请稍后重试"
        ) from exc
