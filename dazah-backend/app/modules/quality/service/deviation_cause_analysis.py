"""偏差台账根本原因归类（人机料法环）与发生部门推导。

归类口径与 CAPA 原因类别一致：人员（人）、设施/设备（机）、产品/物料（料）、
文件（法）、环境（环）、其它。优先使用统一 LLM 客户端批量分析，
LLM 未配置或调用失败时回退到关键词规则，保证仪表盘统计不依赖外部服务可用性。
"""

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)

logger = logging.getLogger(__name__)

REASON_CATEGORIES: tuple[str, ...] = (
    "人员",
    "设施/设备",
    "产品/物料",
    "文件",
    "环境",
    "其它",
)

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # 文件（法）：制度、规程缺失或不完善
    (
        "文件",
        ("文件", "规程", "SOP", "sop", "未规定", "未明确", "缺少", "不清晰", "未评估"),
    ),
    # 设施/设备（机）：设备、仪器、部件本身故障或缺陷
    (
        "设施/设备",
        (
            "设备",
            "仪器",
            "单向阀",
            "传感器",
            "滤芯",
            "进样针",
            "压缩机",
            "逆变器",
            "UPS",
            "ups",
            "键盘",
            "故障",
            "积灰",
            "堵塞",
            "衰减",
            "失效",
            "校验",
            "参数设置",
        ),
    ),
    # 产品/物料（料）：物料、样品、产品本身问题
    (
        "产品/物料",
        ("物料", "样品", "试剂", "原料", "杂质", "批号", "产品量", "留样"),
    ),
    # 环境（环）：温度、洁净、外环境影响
    ("环境", ("环境", "温度", "停电", "断电", "柳絮", "负压", "洁净")),
    # 人员（人）：操作、能力、习惯问题
    (
        "人员",
        ("人员", "操作", "习惯性", "误操作", "未清洗", "转移错误", "触碰"),
    ),
)

_DEPARTMENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("QA", ("QA", "qa", "质量保证")),
    (
        "QC",
        ("QC", "qc", "液相", "气相", "理化", "中控", "检验", "色谱", "滴定", "化验"),
    ),
    ("仓库", ("仓库", "库房", "原辅料库", "成品库")),
)

_WORKSHOP_PATTERN = re.compile(r"\d{3}.{0,2}车间")


def _extract_root_cause_sentence(text: str) -> str:
    """取"根本原因"标记之后的句子；无标记时返回全文。

    桌面登记表把直接原因与根本原因写在同一单元格，
    归类应依据根本原因而非直接原因。
    """
    matches = list(re.finditer(r"根本原因[:：]?", text))
    if matches:
        return text[matches[-1].end():].strip()
    return text.strip()


def keyword_category(root_cause_text: str | None) -> str | None:
    """按关键词规则推断根本原因归类，无法判断时返回 None。"""
    sentence = _extract_root_cause_sentence(root_cause_text or "")
    if not sentence:
        return None
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in sentence for keyword in keywords):
            return category
    return "其它"


def keyword_department(text: str | None) -> str | None:
    """从偏差描述文本推断发生部门，无法判断时返回 None。"""
    value = text or ""
    workshop = _WORKSHOP_PATTERN.search(value)
    if workshop:
        return workshop.group(0)
    for department, keywords in _DEPARTMENT_RULES:
        if any(keyword in value for keyword in keywords):
            return department
    return None


def _clip(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _build_prompt(records: list[Any]) -> list[dict[str, str]]:
    lines = [
        f"{index}. 编号：{record.deviation_code}"
        f" 描述：{_clip(record.description or '', 200)}"
        f" 根本原因：{_clip(record.root_cause_analysis or '', 200)}"
        for index, record in enumerate(records, start=1)
    ]
    return [
        {
            "role": "system",
            "content": (
                "你是原料药工厂的QA专家。对偏差台账记录做两类分析："
                "1) cause_category：按人机料法环归类根本原因，只能取"
                f"{list(REASON_CATEGORIES)}之一（人员=人，设施/设备=机，"
                "产品/物料=料，文件=法，环境=环，其它=无法归入前五类）；"
                "2) department：偏差发生部门，依据描述中的地点与岗位，"
                "用简洁名称（如 QC、QA、201二车间、仓库），无法判断填空字符串。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请分析以下偏差记录并输出JSON：\n"
                + "\n".join(lines)
                + '\n输出格式：{"results": [{"code": "编号", '
                  '"cause_category": "归类", "department": "部门"}]}'
            ),
        },
    ]


async def analyze_records(records: list[Any]) -> dict[str, dict[str, str]]:
    """批量调用 LLM 分析，返回 {偏差编号: {"category": ..., "department": ...}}。

    LLM 未配置、限流或输出异常时返回空 dict，由调用方回退关键词规则。
    """
    if not records:
        return {}
    try:
        raw: dict[str, Any] = await llm_client.chat_json(
            _build_prompt(records),
            expected_keys=["results"],
            temperature=0,
        )
    except (LLMConfigError, LLMRateLimitError, LLMOutputError, LLMProviderError) as exc:
        logger.warning(
            "偏差根因归类 LLM 分析不可用，回退关键词规则：%s", type(exc).__name__
        )
        return {}
    results: dict[str, dict[str, str]] = {}
    rows = raw.get("results")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        category = str(row.get("cause_category") or "").strip()
        department = str(row.get("department") or "").strip()
        if category not in REASON_CATEGORIES:
            category = ""
        results[code] = {"category": category, "department": department[:50]}
    return results


async def fill_missing_analysis(
    db: AsyncSession,
    deviations: list[Any],
    *,
    include_department: bool = False,
) -> None:
    """为缺少归类（及可选的部门）的偏差补齐字段并提交。

    已有人工填写值的记录不覆盖；LLM 失败时逐条回退关键词规则。
    """
    need_category = [
        item for item in deviations if not (item.root_cause_category or "").strip()
    ]
    need_department = (
        [item for item in deviations if not (item.department or "").strip()]
        if include_department
        else []
    )
    targets: list[Any] = []
    seen: set[int] = set()
    for item in [*need_category, *need_department]:
        if id(item) not in seen:
            seen.add(id(item))
            targets.append(item)
    if not targets:
        return

    analyzed = await analyze_records(targets)
    for item in need_category:
        guess = analyzed.get(item.deviation_code, {})
        item.root_cause_category = (
            guess.get("category")
            or keyword_category(item.root_cause_analysis)
            or "其它"
        )
    for item in need_department:
        guess = analyzed.get(item.deviation_code, {})
        item.department = guess.get("department") or keyword_department(
            f"{item.description or ''} {item.root_cause_analysis or ''}"
        )
    await db.commit()
