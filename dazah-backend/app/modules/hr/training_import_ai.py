"""培训统计导入 AI 识别模块.

三级识别中的第三级：规则别名表无法识别时，调用 LLM 生成列映射草稿。
AI 只做列映射建议，绝不生成数据；导入的每个值都来自 Excel 单元格原文。
"""

import hashlib
import logging
from typing import Any

from app.core.llm import (
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)

logger = logging.getLogger(__name__)

# 可映射的系统字段目录（字段名, 说明），同时用于 AI prompt 与前端纠正下拉
FIELD_CATALOG: list[tuple[str, str]] = [
    ("training_datetime", "培训时间（日期+时间），如 2026.01.06 09:00~10:00"),
    ("training_date", "培训日期"),
    ("duration_hours", "培训时长（小时数）"),
    ("training_content", "培训内容/课程名称"),
    ("teaching_dept", "授课部门"),
    ("instructor", "授课人/培训师/讲师"),
    ("level_category", "一级/二级培训级别"),
    ("involved_depts", "涉及部门/受训部门"),
    ("trainees", "培训对象/受训人员名单"),
    ("training_type", "培训类型"),
    ("ledger_assessment_method", "考核方式（口试/笔试）"),
    ("score_summary", "考核结果/成绩汇总"),
    ("plan_source", "部门/公司计划"),
    ("drug_category", "人药/兽药"),
    ("remarks", "备注"),
]

_VALID_FIELDS = {key for key, _ in FIELD_CATALOG}


def header_fingerprint(headers: list[str]) -> str:
    """表头指纹：表头文本排序拼接后的 md5，用于记忆表匹配."""
    normalized = sorted(h.strip() for h in headers if h and h.strip())
    return hashlib.md5("|".join(normalized).encode("utf-8")).hexdigest()


def field_catalog_payload() -> list[dict[str, str]]:
    """供前端下拉选择使用的字段目录."""
    return [{"key": key, "label": label} for key, label in FIELD_CATALOG]


async def analyze_headers_by_llm(sheet_name: str, headers: list[str]) -> dict[str, Any]:
    """调 LLM 分析表头，返回 {"mapping": {列号str: 字段名}, "judgment": str}.

    mapping 仅包含有把握的列；无法识别时返回空 mapping，由前端引导人工指定。
    """
    catalog_text = "\n".join(f"- {key}: {label}" for key, label in FIELD_CATALOG)
    headers_text = "\n".join(
        f"{i}: {h}" for i, h in enumerate(headers) if h and h.strip()
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是药企培训台账的 Excel 列映射助手。根据用户提供的 Excel 表头，"
                "判断每一列对应系统中的哪个字段。只映射有充分把握的列，"
                "不确定或无关的列（如序号）不要映射。严格输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"系统字段目录：\n{catalog_text}\n\n"
                f"工作表「{sheet_name}」的表头（列号: 表头文本）：\n{headers_text}\n\n"
                '请输出 JSON：{"mapping": {"列号": "字段名"}, '
                '"judgment": "对该表内容的一句话判断（培训统计数据/往年历史数据/非'
                '培训数据建议跳过）"}'
            ),
        },
    ]

    try:
        result = await llm_client.chat_json(
            messages=messages,
            expected_keys=["mapping", "judgment"],
            temperature=0.0,
        )
    except LLMOutputError:
        # 注意：extra 不能覆盖 LogRecord 保留属性（如 module），否则 logging 抛 KeyError
        logger.error("导入映射AI输出格式错误", extra={"sheet": sheet_name})
        return {"mapping": {}, "judgment": ""}
    except (LLMProviderError, LLMRateLimitError):
        logger.warning("导入映射AI服务暂不可用", extra={"sheet": sheet_name})
        return {"mapping": {}, "judgment": ""}

    # 校验：过滤掉非法字段名与非整数列号
    raw_mapping = result.get("mapping") or {}
    mapping: dict[str, str] = {}
    for col, field in raw_mapping.items():
        if not isinstance(field, str) or field not in _VALID_FIELDS:
            continue
        try:
            col_idx = int(col)
        except (TypeError, ValueError):
            continue
        if 0 <= col_idx < len(headers):
            mapping[str(col_idx)] = field

    judgment = result.get("judgment")
    return {
        "mapping": mapping,
        "judgment": judgment if isinstance(judgment, str) else "",
    }
