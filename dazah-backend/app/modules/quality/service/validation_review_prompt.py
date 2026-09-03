"""验证方案/报告 AI 审核提示词模板。

prompt 明确要求模型仅基于提供的原文输出、禁止编造，引用必须给出原文片段
（quote），供后端做原文包含校验（quote_verified）。
"""

from __future__ import annotations

from typing import Any

FINDING_CATEGORIES = [
    "reference_missing",
    "version_mismatch",
    "plan_report_mismatch",
    "content_consistency",
    "format_issue",
    "numeric_check",
]
SEVERITY_LEVELS = ["high", "medium", "low"]

# 单份正文输入 LLM 的最大字符数（超长截断，保留开头+结尾）
PLAN_TEXT_LIMIT = 12000
REPORT_TEXT_LIMIT = 12000
TAIL_KEEP = 2000


def _truncate_text(text: str, limit: int, tail: int = TAIL_KEEP) -> str:
    """超长正文截断：保留开头主体 + 结尾（结论/判定标准常在尾部）。"""
    if len(text) <= limit:
        return text
    return (
        f"{text[: limit - tail]}\n"
        f"……【中间内容因长度限制省略，共省略{len(text) - limit}字】……\n"
        f"{text[-tail:]}"
    )


def build_review_prompt(
    *,
    plan_text: str | None,
    report_text: str | None,
    reference_summary: list[dict[str, Any]],
    plan_identity: dict[str, Any] | None = None,
    report_identity: dict[str, Any] | None = None,
) -> str:
    """组装一次 AI 语义审核的完整 prompt。

    引用核对结果（reference_summary）由代码比对生成，作为事实输入供模型引用，
    模型不得自行判断引用是否存在/版本新旧。
    """
    parts: list[str] = [
        "你是原料药工厂质量管理专家，负责对验证方案（VP）与验证报告（VR）做合规审核。",
        "请仅基于下面提供的原文核对以下内容，没有证据的问题不要提出，禁止编造：",
        "1. 方案↔报告一致性：报告引用的方案编号/标题、验证参数、判定标准、批次"
        "是否与方案一致；",
        "2. 数值核对：报告中的实测结果是否落在方案或质量标准规定的区间内；",
        "3. 内容一致性：两份文档内部及之间的关键数据、上下文、结论是否自洽；",
        "4. 规范性：文档编号（封面/页眉/文件名）是否一致、章节是否齐全。",
        "每一条发现必须给出可核对的原文片段（quote，尽量短，10~120字），"
        "并说明位置（location，如章节或表格名）。",
        "分类（category）只能是：" + "/".join(FINDING_CATEGORIES) + "。",
        "严重程度（severity）只能是 high/medium/low。",
        "只输出 JSON：{\"findings\": [{\"category\": \"...\", \"severity\": \"...\", "
        "\"location\": \"...\", \"quote\": \"...\", \"detail\": \"...\"}]}",
    ]

    if plan_identity:
        parts.append(
            "方案文档身份（从文件名/正文提取）：" + _format_identity(plan_identity)
        )
    if report_identity:
        parts.append(
            "报告文档身份（从文件名/正文提取）：" + _format_identity(report_identity)
        )

    if reference_summary:
        parts.append(
            "引用文件核对结果（代码比对，已确定，直接引用即可，不要重新判断）："
            + str(reference_summary)
        )

    if plan_text:
        parts.append("【验证方案正文】\n" + _truncate_text(plan_text, PLAN_TEXT_LIMIT))
    if report_text:
        parts.append(
            "【验证报告正文】\n" + _truncate_text(report_text, REPORT_TEXT_LIMIT)
        )

    return "\n\n".join(parts)


def _format_identity(identity: dict[str, Any]) -> str:
    items = [f"{key}={value}" for key, value in identity.items() if value]
    return "；".join(items) if items else "未提取到身份信息"
