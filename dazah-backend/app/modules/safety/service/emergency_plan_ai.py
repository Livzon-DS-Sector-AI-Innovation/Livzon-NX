"""应急预案 AI 编排：生成、审核修正与对话修改。

全部 LLM 调用走 ``app.core.llm.llm_client``（JSON 输出 + Pydantic 校验 +
非法条目丢弃），提示词经「DB AI 工作流配置优先 → 硬编码兜底」取用，
安全管理员可在 AI 工作流配置页覆盖。AI 输出只作为起草与建议：
所有修改都落修订快照、可撤销，定稿由人工确认。

生成拆成两次调用以规避 json_object 部分字段输出：
A 写分析四章（危险源/理化/防护/处置），B 写情景脚本；
审核修正 = 确定性修正 + AI 审阅 + 按问题类型应用（替换/按章重写/需人工）。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import llm_client
from app.core.llm.exceptions import LLMOutputError
from app.modules.safety.ai_workflow_configs import SAFETY_WORKFLOW_CONFIGS
from app.modules.safety.repository import SafetyRepository
from app.modules.safety.schemas.emergency_plan_ai import (
    ChatEdit,
    EmergencyPlanDocument,
    EmergencyPlanGenerateRequest,
    EmergencyPlanReviewReport,
    PlanChapter,
    ReviewDimension,
    ReviewIssue,
)
from app.modules.safety.service.emergency_plan_checks import (
    apply_deterministic_fixes,
    run_checks,
)
from app.modules.safety.service.emergency_plan_template import (
    PENDING,
    merge_organization_patch,
    merge_workshop_patch,
)
from app.platform.integrations.ai.prompts import build_prompt

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 240
REWRITE_LENGTH_TOLERANCE = 0.3
GENERATE_WORKFLOW = "emergency-plan-generate"
REVIEW_WORKFLOW = "emergency-plan-review"
CHAT_WORKFLOW = "emergency-plan-chat"

ProgressCallback = Callable[[str], Awaitable[None]]

_REWRITE_FIX_INSTRUCTION = (
    "你是原料药工厂安全管理专家。下面是应急预案的一个章节原文和该章需要修正的"
    "问题清单。请输出修正后的完整章节：只修复清单中的问题，其余文字一字不改，"
    "保持原有分段与编号风格。只输出 JSON 对象。"
)


def _fallback_rules(module_code: str) -> str:
    config = SAFETY_WORKFLOW_CONFIGS.get(module_code, {})
    return build_prompt(config)


async def _get_workflow_config(session: AsyncSession, module_code: str) -> str:
    """DB AI 工作流配置优先，回退安全模块硬编码业务规则。"""
    repo = SafetyRepository(session)
    workflow = await repo.get_ai_workflow_config_by_module(module_code)
    if workflow and workflow.is_enabled and workflow.script_configs:
        scripts = workflow.script_configs
        if isinstance(scripts, list) and scripts and isinstance(scripts[0], dict):
            if scripts[0].get("is_enabled", True):
                return build_prompt(scripts[0])
    return _fallback_rules(module_code)


async def _call_json(
    session: AsyncSession,
    *,
    module_code: str,
    user_content: str,
    expected_keys: list[str],
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    rules = await _get_workflow_config(session, module_code)
    messages = [
        {
            "role": "user",
            "content": (
                f"{rules}\n\n## 输出格式\n只输出 JSON 对象，键为："
                f"{', '.join(expected_keys)}。不要输出 JSON 以外的文字。\n\n"
                f"## 本次任务输入\n{user_content}"
            ),
        }
    ]
    for attempt in (1, 2):
        try:
            return await llm_client.chat_json(
                messages,
                expected_keys=expected_keys,
                temperature=0.1,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except LLMOutputError:
            if attempt == 2:
                raise
            if on_progress:
                await on_progress("AI 输出不完整，正在重试…")
            messages[-1]["content"] += (
                "\n\n注意：上一次输出不完整。必须完整输出全部键："
                f"{', '.join(expected_keys)}，每个值都不能省略。"
            )
    raise LLMOutputError("unreachable")  # pragma: no cover


# ---------- 文本化 ----------


def _org_roster(document: EmergencyPlanDocument) -> str:
    org = document.organization
    lines = [f"总指挥：{org.commander or PENDING}"]
    if org.deputy_commanders:
        lines.append("副总指挥：" + "、".join(org.deputy_commanders))
    for group in org.groups:
        lines.append(
            f"{group.name}：组长 {group.leader or PENDING}；"
            f"成员 {group.members or PENDING}"
        )
    workshop = document.workshop_organization
    if workshop:
        lines.append(
            f"车间应急组（{workshop.department or '车间'}）："
            f"总指挥 {workshop.commander or PENDING}"
        )
        for group in workshop.groups:
            lines.append(f"  {group.name}：组长 {group.leader or PENDING}")
    return "\n".join(lines)


def _document_digest(document: EmergencyPlanDocument, max_chars: int = 26000) -> str:
    from app.modules.safety.service.emergency_plan_template import document_sections

    parts = [f"【封面】{document.cover.title}（{document.cover.level}）"]
    for key, title, text in document_sections(document):
        content = text if len(text) <= 8000 else text[:8000] + "…（截断）"
        parts.append(f"### [{key}] {title}\n{content}")
    digest = "\n\n".join(parts)
    return digest if len(digest) <= max_chars else digest[:max_chars] + "…（截断）"


def _section_text(document: EmergencyPlanDocument, section: str) -> str:
    if section == "preface":
        return document.preface
    chapter = document.chapter(section)
    return chapter.content if chapter else ""


def _replace_in_section(
    document: EmergencyPlanDocument, section: str, quote: str, replacement: str
) -> EmergencyPlanDocument | None:
    if section == "preface":
        if quote in document.preface:
            return document.model_copy(
                update={"preface": document.preface.replace(quote, replacement, 1)}
            )
        return None
    chapter = document.chapter(section)
    if chapter is None or quote not in chapter.content:
        return None
    updated = chapter.content.replace(quote, replacement, 1)
    new_chapter = chapter.model_copy(update={"content": updated})
    chapters = [
        new_chapter if item.key == section else item for item in document.chapters
    ]
    return document.model_copy(update={"chapters": chapters})


# ---------- 生成 ----------


async def generate_document(
    session: AsyncSession,
    *,
    params: EmergencyPlanGenerateRequest,
    plan_name: str,
    context: Any,
    on_progress: ProgressCallback | None = None,
) -> EmergencyPlanDocument:
    from app.modules.safety.service.emergency_plan_template import (
        build_keywords,
        build_skeleton,
        chapter_title,
    )

    document = build_skeleton(params, plan_name)
    keywords = build_keywords(params, plan_name)
    location_detail = f"（{params.location_detail}）" if params.location_detail else ""
    facts = context.facts_text()
    substances = "、".join(context.substance_names) or "无"
    level = "公司级" if params.level == "company" else "车间级"

    if on_progress:
        await on_progress("正在起草危险源与理化分析章节…")
    analysis = await _call_json(
        session,
        module_code=GENERATE_WORKFLOW,
        user_content=(
            f"预案标题：{plan_name}（{level}）\n"
            f"事故类型：{params.accident_type}\n事故场所：{params.location}"
            f"{location_detail}\n"
            f"涉及物质：{substances}\n"
            f"公司名称：{document.cover.company}\n\n"
            "【事实资料】\n"
            f"{facts}\n\n"
            "请依次撰写以下 4 个章节的正文（不要写章节大标题，直接输出正文）：\n"
            f"1. hazard_analysis：危险源分析（场所布局、储存形式、主要风险，"
            "必须与给定事实一致）\n"
            f"2. properties：章节标题为「{chapter_title('properties', keywords)}」，"
            "逐项写理化性质与化学性质，数值只能取自 MSDS 原文\n"
            f"3. protection：防护措施（个体防护与环境防护）\n"
            f"4. handling：处置措施（泄漏/火灾处置与后期处理）"
        ),
        expected_keys=["hazard_analysis", "properties", "protection", "handling"],
        on_progress=on_progress,
    )

    if on_progress:
        await on_progress("正在编写情景演练脚本…")
    scenario = await _call_json(
        session,
        module_code=GENERATE_WORKFLOW,
        user_content=(
            f"预案标题：{plan_name}（{level}）\n"
            f"事故类型：{params.accident_type}\n事故场所：{params.location}"
            f"{location_detail}\n"
            f"涉及物质：{substances}\n"
            f"演练时间：{document.cover.drill_date or '（待定）'}，"
            f"情景从 {params.start_time} 开始\n"
            f"参演部门：{'、'.join(params.participating_departments) or '（未指定）'}\n"
            + (
                f"补充要求：{params.scenario_requirements}\n"
                if params.scenario_requirements.strip()
                else ""
            )
            + "\n【组织机构名单（出场人员只能使用这些人）】\n"
            f"{_org_roster(document)}\n\n"
            "请撰写情景设置章节正文：以“假设事故:”开头说明背景，随后按时间先后"
            "编排（情景一）（情景二）…，每个情景以“（情景X）HH时MM分，”开头；"
            "对话直接引用汇报原话；处置动作要与涉及物质的特性相符"
            "（水溶性易燃液体用抗溶性泡沫）；结尾火灾扑灭、环境监测达标、"
            "总指挥宣布演练结束。"
        ),
        expected_keys=["scenario"],
        on_progress=on_progress,
    )

    fill: dict[str, str] = {
        key: str(analysis.get(key) or "").strip()
        for key in ("hazard_analysis", "properties", "protection", "handling")
    }
    fill["scenario"] = str(scenario.get("scenario") or "").strip()
    chapters = []
    for chapter in document.chapters:
        content = fill.get(chapter.key)
        chapters.append(
            chapter.model_copy(update={"content": content}) if content else chapter
        )
    return document.model_copy(update={"chapters": chapters})


# ---------- 审核修正 ----------

_CATEGORY_VALUES = {
    "contradiction",
    "technical",
    "compliance",
    "completeness",
    "typo",
    "format",
}


def _normalize_ai_issues(raw: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for index, item in enumerate(raw.get("issues") or [], 1):
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        problem = str(item.get("problem") or "").strip()
        if not problem:
            continue
        category = str(item.get("category") or "technical")
        issues.append(
            {
                "section": str(item.get("section") or "").strip(),
                "quote": quote[:1000],
                "problem": problem[:1000],
                "category": category if category in _CATEGORY_VALUES else "technical",
                "severity": str(item.get("severity") or "medium"),
                "fix": str(item.get("fix") or "none").strip(),
                "replacement": str(item.get("replacement") or "").strip(),
            }
        )
    return issues


def _rule_issue_items(rule_issues: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "section": issue.section,
            "quote": issue.quote,
            "problem": issue.message,
            "category": (
                "completeness"
                if issue.code.endswith(("missing", "empty"))
                else "typo"
                if issue.code.startswith("typo")
                else "contradiction"
                if issue.code
                in (
                    "group_unknown",
                    "commander_mismatch",
                    "leader_mismatch",
                    "timeline_backwards",
                )
                else "technical"
            ),
            "severity": issue.severity,
            "fix": "replace" if issue.replacement else "rewrite",
            "replacement": issue.replacement or "",
            "rule_code": issue.code,
        }
        for issue in rule_issues
        if issue.code not in ("typo_leak", "company_not_full_name")
    ]


async def review_document(
    session: AsyncSession,
    *,
    document: EmergencyPlanDocument,
    context: Any,
    on_progress: ProgressCallback | None = None,
) -> tuple[EmergencyPlanDocument, EmergencyPlanReviewReport]:
    document, auto_fixes = apply_deterministic_fixes(document)
    rule_issues = run_checks(
        document, substances=context.substance_names, msds_text=context.msds_text
    )
    rule_items = _rule_issue_items(rule_issues)
    # 传给 AI 的规则问题按严重度截断，避免提示词与输出膨胀
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    rule_items_for_ai = sorted(
        rule_items, key=lambda item: severity_rank.get(item["severity"], 1)
    )[:15]

    rule_findings_text = (
        "\n".join(
            f"- [{item['section']}] {item['problem']}"
            + (f"（原文：{item['quote']}）" if item["quote"] else "")
            for item in rule_items_for_ai
        )
        if rule_items_for_ai
        else "无"
    )
    digest = _document_digest(document, max_chars=16000)
    roster = _org_roster(document)

    if on_progress:
        await on_progress("AI 正在排查前后矛盾…")
    # 审核拆成两个较小调用：单次大调用（全量输入+大 JSON 输出）在
    # 长预案下容易触发模型服务超时，拆分后各自输入/输出可控。
    consistency_raw = await _call_json(
        session,
        module_code=REVIEW_WORKFLOW,
        user_content=(
            "【任务】只排查预案的前后一致性问题（不要检查专业性/错别字）：\n"
            "时间线矛盾、储存形式矛盾、数量矛盾、人员身份与组织架构不符、"
            "小组名称与组织架构不符、公司名称不一致。\n\n"
            "【预案正文】\n"
            f"{digest}\n\n"
            "【组织机构名单】\n"
            f"{roster}\n\n"
            "【规则校验已发现（不要重复报告）】\n"
            f"{rule_findings_text}\n\n"
            "输出 JSON：issues（[{section: 章节标识，quote: 原文片段, "
            "problem: 矛盾说明, severity: high|medium|low, "
            "fix: replace|rewrite|none, replacement: fix=replace 时的修正文字, "
            "category: contradiction}]，最多 15 条，没有则空数组）。"
            "quote 必须能在对应章节原文中找到；缺信息用 fix=none。"
        ),
        expected_keys=["issues"],
        on_progress=on_progress,
    )

    if on_progress:
        await on_progress("AI 正在审阅专业性与完整性…")
    quality_raw = await _call_json(
        session,
        module_code=REVIEW_WORKFLOW,
        user_content=(
            "【任务】审阅预案的专业性与完整性（一致性由另一轮负责，不要重复）：\n"
            "灭火剂/防护/处置方法是否正确、公司报告流程是否合规、"
            "必备内容是否缺失、理化数值是否有出处、需人工补充的信息。\n\n"
            "【预案正文】\n"
            f"{digest}\n\n"
            "【涉及物质与 MSDS 事实】\n"
            f"{context.facts_text()[:8000]}\n\n"
            "【规则校验已发现（不要重复报告）】\n"
            f"{rule_findings_text}\n\n"
            "输出 JSON：summary（一句话总评）、score（0-100）、"
            "dimensions（[{name:专业性|合规性|完整性|文字, "
            "status:ok|warn|error, note}]）、issues（[{section, quote, "
            "problem, category: technical|compliance|completeness|typo|format, "
            "severity, fix: replace|rewrite|none, replacement}]，最多 15 条，"
            "没有则空数组）。"
        ),
        expected_keys=["summary", "score", "dimensions", "issues"],
        on_progress=on_progress,
    )

    ai_items = [
        *_normalize_ai_issues(consistency_raw),
        *_normalize_ai_issues(quality_raw),
    ]
    raw = quality_raw
    working = document
    applied: list[ReviewIssue] = []
    needs_human: list[ReviewIssue] = []

    def _issue_base(index: int, item: dict[str, Any]) -> ReviewIssue:
        return ReviewIssue(
            id=f"AI-{index:02d}",
            source="ai",
            severity=(
                item["severity"]
                if item["severity"] in ("high", "medium", "low")
                else "medium"
            ),
            category=item["category"],
            section=item["section"] or "scenario",
            quote=item["quote"],
            problem=item["problem"],
            status="unresolved",
            before=item["quote"],
            after="",
        )

    # 1) fix=replace：唯一匹配即替换
    rewrites: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, item in enumerate(ai_items, 1):
        issue = _issue_base(index, item)
        fix = item["fix"]
        if fix == "replace" and item["replacement"] and item["quote"]:
            updated = _replace_in_section(
                working, item["section"], item["quote"], item["replacement"]
            )
            if updated is not None:
                working = updated
                issue.status = "fixed"
                issue.after = item["replacement"]
                applied.append(issue)
                continue
        if fix == "rewrite" or (fix == "replace" and not item["quote"]):
            if item["section"]:
                rewrites[item["section"]].append(item)
            continue
        issue.status = "needs_human"
        needs_human.append(issue)

    # 2) fix=rewrite：按章重写（长度保护）
    for section, items in rewrites.items():
        chapter = working.chapter(section)
        if chapter is None:
            for item in items:
                issue = _issue_base(ai_items.index(item) + 1, item)
                issue.status = "needs_human"
                needs_human.append(issue)
            continue
        original = chapter.content
        if not original.strip():
            for item in items:
                issue = _issue_base(ai_items.index(item) + 1, item)
                issue.status = "needs_human"
                needs_human.append(issue)
            continue
        if on_progress:
            await on_progress(f"正在修正「{chapter.title}」…")
        problems = "\n".join(
            f"- {item['problem']}"
            + (f"（原文：{item['quote']}）" if item["quote"] else "")
            for item in items
        )
        try:
            result = await _call_json(
                session,
                module_code=REVIEW_WORKFLOW,
                user_content=(
                    f"{_REWRITE_FIX_INSTRUCTION}\n\n"
                    f"【章节原文】\n{original}\n\n【需修正的问题】\n{problems}"
                ),
                expected_keys=["content"],
            )
            new_content = str(result.get("content") or "").strip()
        except Exception:  # noqa: BLE001 — 单章重写失败不阻断整体修正
            logger.warning("预案章节 AI 重写失败: section=%s", section, exc_info=True)
            new_content = ""
        length_ok = (
            bool(new_content)
            and abs(len(new_content) - len(original))
            <= len(original) * REWRITE_LENGTH_TOLERANCE
        )
        if length_ok:
            working = (
                _replace_in_section(working, section, original, new_content) or working
            )
            for item in items:
                issue = _issue_base(ai_items.index(item) + 1, item)
                issue.status = "fixed"
                issue.before = original[:500]
                issue.after = new_content[:500]
                applied.append(issue)
        else:
            for item in items:
                issue = _issue_base(ai_items.index(item) + 1, item)
                issue.status = "needs_human"
                needs_human.append(issue)

    # 3) 修正后重新校验：仍存在的问题记为提示
    rechecked = run_checks(
        working, substances=context.substance_names, msds_text=context.msds_text
    )
    remaining_rules = [
        ReviewIssue(
            id=f"RULE-{index:02d}",
            source="rule",
            severity=issue.severity,
            category=(
                "completeness"
                if issue.code.endswith(("missing", "empty"))
                else "typo"
                if issue.code.startswith("typo")
                else "contradiction"
                if issue.code
                in (
                    "group_unknown",
                    "commander_mismatch",
                    "leader_mismatch",
                    "timeline_backwards",
                )
                else "technical"
            ),
            section=issue.section,
            quote=issue.quote,
            problem=issue.message,
            status="unresolved",
        )
        for index, issue in enumerate(rechecked, 1)
    ]

    dimensions = []
    for item in raw.get("dimensions") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:20]
        status = str(item.get("status") or "")
        if not name or status not in ("ok", "warn", "error"):
            continue
        dimensions.append(
            ReviewDimension(
                name=name, status=status, note=str(item.get("note") or "")[:500]
            )
        )

    auto_fix_issues = [
        ReviewIssue(
            id=f"AUTO-{index:02d}",
            source="rule",
            severity=fix.severity,
            category="typo",
            section=fix.section,
            quote=fix.quote,
            problem=fix.message,
            status="fixed",
            before=fix.quote,
            after=fix.replacement or "",
        )
        for index, fix in enumerate(auto_fixes, 1)
    ]
    issues = [*auto_fix_issues, *applied, *needs_human, *remaining_rules]
    score_raw = raw.get("score")
    try:
        score = max(0, min(100, int(str(score_raw))))
    except (TypeError, ValueError):
        score = 0
    report = EmergencyPlanReviewReport(
        summary=str(raw.get("summary") or "").strip()[:2000],
        score=score,
        dimensions=dimensions,
        issues=issues,
        fixed_count=len(applied) + len(auto_fixes),
        needs_human_count=len(needs_human),
        rounds=1,
    )
    return working, report


# ---------- 对话 ----------


async def chat_reply(
    session: AsyncSession,
    *,
    document: EmergencyPlanDocument,
    history: list[dict[str, str]],
    message: str,
    section: str | None = None,
) -> tuple[str, list[ChatEdit]]:
    """对话一轮：返回回复文本与校验后的修改补丁（未应用）。"""
    chapter_keys = {chapter.key for chapter in document.chapters}
    section_note = f"（用户当前聚焦章节：{section}）" if section else ""
    raw = await _call_json(
        session,
        module_code=CHAT_WORKFLOW,
        user_content=(
            "【预案正文】\n"
            f"{_document_digest(document)}\n\n"
            "【组织机构名单】\n"
            f"{_org_roster(document)}\n\n"
            "【最近对话】\n"
            + (
                "\n".join(
                    f"{item['role']}: {item['content']}" for item in history[-10:]
                )
                if history
                else "（无）"
            )
            + f"\n\n【用户本轮指令】{message}{section_note}\n\n"
            "请输出 JSON：reply（给用户的说明，简要列出做了哪些修改或回答问题）、"
            "edits（修改补丁数组，不修改正文时为空数组）。每个补丁："
            "{target: chapter|preface|organization|workshop_organization, "
            "chapter_key: 章节标识（target=chapter 时必填，取值："
            f"{', '.join(sorted(chapter_keys))}）, content: 修改后的完整章节正文"
            "（target=chapter/preface 时必填，整章输出，不要只输出差异）, "
            "organization_patch: {commander?, deputy_commanders?, groups?: "
            "[{name, leader?, members?, duties?}]}"
            "（target=organization 时，只写要改的字段，"
            "groups 按 name 合并）, workshop_patch: 同结构"
            "（target=workshop_organization 时），"
            "summary: 一句话修改说明}。"
        ),
        expected_keys=["reply", "edits"],
    )
    edits: list[ChatEdit] = []
    seen_sections: set[tuple[str, str | None]] = set()
    for item in raw.get("edits") or []:
        if not isinstance(item, dict):
            continue
        try:
            edit = ChatEdit.model_validate(item)
        except Exception:  # noqa: BLE001 — 单条补丁格式非法时丢弃
            continue
        if edit.target == "chapter" and edit.chapter_key not in chapter_keys:
            continue
        marker = (edit.target, edit.chapter_key)
        if marker in seen_sections:
            continue
        seen_sections.add(marker)
        edits.append(edit)
    reply = str(raw.get("reply") or "").strip()
    return reply, edits


def apply_chat_edits(
    document: EmergencyPlanDocument, edits: list[ChatEdit]
) -> tuple[EmergencyPlanDocument, list[str]]:
    """把对话补丁应用到文档，返回新文档与生效的章节列表。"""
    sections: list[str] = []
    working = document
    for edit in edits:
        if edit.target == "chapter" and edit.chapter_key and edit.content is not None:
            chapter = working.chapter(edit.chapter_key)
            if chapter is None:
                continue
            new_chapter = chapter.model_copy(update={"content": edit.content})
            working = working.model_copy(
                update={
                    "chapters": [
                        new_chapter if item.key == edit.chapter_key else item
                        for item in working.chapters
                    ]
                }
            )
            sections.append(edit.chapter_key)
        elif edit.target == "preface" and edit.content is not None:
            working = working.model_copy(update={"preface": edit.content})
            sections.append("preface")
        elif edit.target == "organization" and edit.organization_patch is not None:
            working = working.model_copy(
                update={
                    "organization": merge_organization_patch(
                        working.organization, edit.organization_patch
                    )
                }
            )
            sections.append("organization")
        elif edit.target == "workshop_organization" and edit.workshop_patch is not None:
            working = working.model_copy(
                update={
                    "workshop_organization": merge_workshop_patch(
                        working.workshop_organization, edit.workshop_patch
                    )
                }
            )
            sections.append("workshop_organization")
    return working, sections


async def structure_document(
    session: AsyncSession, *, document: EmergencyPlanDocument
) -> EmergencyPlanDocument | None:
    """把非模板导入的文档内容归位到公司 12 章模板（只搬运整理，不新增事实）。

    无法归位的自定义章节原样保留；LLM 失败或输出无效时返回 None，
    由调用方继续使用导入结果。
    """
    from app.modules.safety.service.emergency_plan_template import CHAPTER_SPECS

    sections_text = "\n\n".join(
        f"### [{chapter.key}] {chapter.title}\n{chapter.content[:3000]}"
        for chapter in document.chapters
        if chapter.content.strip()
    )
    if not sections_text.strip():
        return None
    template_keys = ", ".join(spec.key for spec in CHAPTER_SPECS)
    raw = await _call_json(
        session,
        module_code=GENERATE_WORKFLOW,
        user_content=(
            "以下是一份应急文档的内容（章节标识与标题为导入时的自动识别结果）。"
            "请把各段内容归位到公司标准模板章节：\n"
            f"{template_keys}\n"
            "对应关系（scenario=情景设置, properties=事故特性/理化性质, "
            "protection=防护措施, handling=处置措施, "
            "workshop_organization=车间应急组）。"
            "内容直接搬运并整理语句，不得编造新事实；某章没有对应内容时不要输出"
            "该键。\n\n"
            f"{sections_text}\n\n"
            '请输出 JSON：{"chapters": {"章节标识": "整理后的正文", ...}}'
            "（只包含有内容的章节键）。"
        ),
        expected_keys=["chapters"],
    )
    mapping = raw.get("chapters")
    if not isinstance(mapping, dict):
        return None
    valid_keys = {spec.key for spec in CHAPTER_SPECS}
    updated = 0
    chapters: list[PlanChapter] = []
    for chapter in document.chapters:
        if chapter.key in valid_keys:
            content = str(mapping.get(chapter.key) or "").strip()
            if content and content != chapter.content:
                chapters.append(chapter.model_copy(update={"content": content}))
                updated += 1
                continue
        chapters.append(chapter)
    if not updated:
        return None
    return document.model_copy(update={"chapters": chapters})
