"""应急预案确定性校验：完整性、组织机构一致性、时间线、公司名称与术语。

全部为纯函数，不调用 LLM；输入为预案文档（可选附涉及物质与 MSDS 文本），
输出 CheckIssue 列表。只有语义上无歧义的问题（公司非全称、事故术语
“泄露”）才给出确定性替换并由 ``apply_deterministic_fixes`` 自动修正；
需要结合上下文判断的问题（灭火剂选择、陌生人员、时间冲突）交给 AI 审阅。
"""

from __future__ import annotations

import re
from typing import Literal

from app.modules.safety.schemas.emergency_plan_ai import (
    CheckIssue,
    EmergencyPlanDocument,
    PlanChapter,
)
from app.modules.safety.service.emergency_plan_template import strip_markup

Severity = Literal["high", "medium", "low"]

_GROUP_TOKEN_RE = re.compile(
    r"([\u4e00-\u9fa5]{1,8}?(?:处置|抢险|救护|监测|疏散|保障|后勤|联络|资源)组)"
)
_GROUP_PREFIXES = ("公司", "车间", "现场", "消保队")
_LEADER_STOPWORDS = {"组长", "副组长", "成员", "组员", "人员", "全体"}
# 组名后紧跟这些字时是动词/介词/名词短语，不是「组名+人名」引用
_NON_NAME_LEADING_CHARS = set(
    "对在从向到把将的是了与和及按依用以被由于通过进入离开返回开始继续"
    "立即马上赶迅速全力负责协助组织参加现场火情火灾泄漏各全体组"
    "救护配持禁调要需应采取处严立通撤执观收结束完由经已正才再"
    "指挥率带集领巡下达派命"
)
_TIME_RE = re.compile(r"(\d{1,2})时(\d{2})分")
_SCENE_MARK_RE = re.compile(r"（情景([一二三四五六七八九十]+)）")
_NAME_DELIMITERS = set("，。、：；！？“”\"'‘’（）()《》 \t\n的是为在向与和及")
_LEAK_TYPO_RE = re.compile(r"泄露(?!(?:信息|消息|秘密|机密|内容|隐私|事故信息))")
_NUMBER_RE = re.compile(r"[-－−]?\d+(?:\.\d+)?")
_VALUE_WITH_UNIT_RE = re.compile(r"[-－−]?\d+(?:\.\d+)?\s*(?:℃|%|％)")

# 水溶性易燃液体：灭火必须用抗溶性泡沫
WATER_SOLUBLE_FUELS = ("乙醇", "酒精", "甲醇", "丙酮", "乙二醇", "异丙醇", "乙腈")
_FOAM_RE = re.compile(
    r"(?<!抗溶性)(?<!抗溶)(?<!严禁使用)(?<!不得使用)泡沫(?=水枪|灭火|枪)"
)

_CN_DIGITS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def cn_to_int(text: str) -> int:
    """一~九十九 中文数字转整数，无法识别返回 0。"""
    if not text:
        return 0
    if "十" not in text:
        return _CN_DIGITS.get(text, 0) if len(text) == 1 else 0
    tens_part, _, ones_part = text.partition("十")
    tens = _CN_DIGITS.get(tens_part, 0) if tens_part else 1
    ones = _CN_DIGITS.get(ones_part, 0) if ones_part else 0
    return tens * 10 + ones


class _Collector:
    def __init__(self) -> None:
        self.issues: list[CheckIssue] = []

    def add(
        self,
        code: str,
        severity: Severity,
        section: str,
        message: str,
        *,
        quote: str = "",
        replacement: str | None = None,
    ) -> None:
        self.issues.append(
            CheckIssue(
                code=code,
                severity=severity,
                section=section,
                quote=quote[:1000],
                message=message,
                replacement=replacement,
            )
        )


def _text_sections(document: EmergencyPlanDocument) -> list[tuple[str, str]]:
    """可校验的自由文本区块（不含结构化组织机构）。"""
    sections: list[tuple[str, str]] = [("preface", document.preface)]
    sections.extend(
        (chapter.key, strip_markup(chapter.content)) for chapter in document.chapters
    )
    return sections


def _split_names(value: str) -> list[str]:
    parts = re.split(r"[、，,\s;；/]+", value)
    names: list[str] = []
    for raw in parts:
        part = raw.strip()
        if not part or len(part) > 6:
            continue
        # “张占臣、林宗伟、安伟等”末位的“等”是省略标记，剥离后仍是有效姓名
        if part.endswith("等"):
            part = part[:-1]
        if not part or "全体" in part or "等" in part:
            continue
        names.append(part)
    return names


def registered_people(document: EmergencyPlanDocument) -> set[str]:
    org = document.organization
    names: set[str] = set(_split_names(org.commander))
    for deputy in org.deputy_commanders:
        names.update(_split_names(deputy))
    for group in org.groups:
        names.update(_split_names(group.leader))
        names.update(_split_names(group.members))
    workshop = document.workshop_organization
    if workshop:
        names.update(_split_names(workshop.commander))
        names.update(_split_names(workshop.deputy_commander))
        for group in workshop.groups:
            names.update(_split_names(group.leader))
            names.update(_split_names(group.members))
    return {name for name in names if 2 <= len(name) <= 4 and "*" not in name}


def registered_groups(document: EmergencyPlanDocument) -> list[str]:
    names = [group.name.strip() for group in document.organization.groups]
    if document.workshop_organization:
        names.extend(
            group.name.strip() for group in document.workshop_organization.groups
        )
    return [name for name in names if name]


# ---------- 各项检查 ----------


def _check_completeness(document: EmergencyPlanDocument, out: _Collector) -> None:
    cover = document.cover
    for field_name, label in (
        ("title", "预案标题"),
        ("company", "公司名称"),
        ("level", "级别"),
        ("drill_date", "演练时间"),
        ("archive_department", "建档部门"),
    ):
        if not str(getattr(cover, field_name)).strip():
            out.add("cover_missing", "medium", "cover", f"封面缺少{label}，需人工补充")
    if not document.preface.strip():
        out.add("preface_missing", "medium", "preface", "缺少引言段落")
    for chapter in document.chapters:
        if chapter.key in ("organization", "workshop_organization"):
            continue
        if not chapter.content.strip():
            out.add(
                "chapter_empty",
                "high",
                chapter.key,
                f"「{chapter.title}」章节内容为空",
            )
    org = document.organization
    if not org.commander.strip():
        out.add(
            "org_commander_missing", "high", "organization", "未填写总指挥，需人工补充"
        )
    if not org.groups:
        out.add("org_groups_missing", "high", "organization", "未设置任何应急小组")
    for group in org.groups:
        if not group.leader.strip():
            out.add(
                "org_leader_missing",
                "medium",
                "organization",
                f"「{group.name}」未填写组长，需人工补充",
                quote=group.name,
            )


def _check_group_names(document: EmergencyPlanDocument, out: _Collector) -> None:
    known = registered_groups(document)
    if not known:
        return
    reported: set[tuple[str, str]] = set()
    for key, text in _text_sections(document):
        for token in _GROUP_TOKEN_RE.findall(text):
            normalized = token
            for prefix in _GROUP_PREFIXES:
                if normalized.startswith(prefix) and len(normalized) > len(prefix) + 2:
                    normalized = normalized[len(prefix) :]
            if any(
                normalized.endswith(name) or name.endswith(normalized) for name in known
            ):
                continue
            # 正则会把组名前的动词一并带上，按同类小组的名称长度截出实际写法
            similar = [name for name in known if name[-3:] == normalized[-3:]]
            mention = normalized[-len(similar[0]) :] if similar else normalized[-8:]
            if (key, mention) in reported:
                continue
            reported.add((key, mention))
            hint = f"，组织架构中为「{similar[0]}」" if similar else ""
            out.add(
                "group_unknown",
                "high",
                key,
                f"正文出现「{mention}」，与组织架构中的小组名称不一致{hint}",
                quote=mention,
            )


def _check_people(document: EmergencyPlanDocument, out: _Collector) -> None:
    """只比对已登记人员之间的错位（如把副总指挥写成总指挥）。"""
    people = registered_people(document)
    commander = document.organization.commander.strip()
    leaders = {
        group.name.strip(): group.leader.strip()
        for group in document.organization.groups
        if group.leader.strip()
    }
    for key, text in _text_sections(document):
        if commander:
            for match in re.finditer(r"(?<!副)总指挥", text):
                following = text[match.end() : match.end() + 4]
                other = next(
                    (
                        name
                        for name in people
                        if name != commander and following.startswith(name)
                    ),
                    None,
                )
                if other:
                    out.add(
                        "commander_mismatch",
                        "high",
                        key,
                        f"正文称「总指挥{other}」，组织架构中总指挥为「{commander}」",
                        quote=f"总指挥{other}",
                    )
        for group_name, leader in leaders.items():
            for match in re.finditer(rf"{re.escape(group_name)}组长", text):
                rest = text[match.end() :]
                # 姓名后紧跟正文字符，按 2/3/4 字候选截取；任一候选等于
                # 组长即视为一致（如“朱少军分”实为“朱少军”+下文）
                candidates = [rest[:length] for length in (2, 3, 4)]
                if not leader or not rest.strip():
                    continue
                if any(candidate == leader for candidate in candidates):
                    continue
                other = next(
                    (candidate for candidate in candidates if candidate in people),
                    None,
                )
                if other is not None:
                    out.add(
                        "leader_mismatch",
                        "high",
                        key,
                        f"正文称「{group_name}组长{other}」，"
                        f"组织架构中组长为「{leader}」",
                        quote=f"{group_name}组长{other}",
                    )
    # 「组名+人名」出现在正文中时，人名必须在组织架构名单内
    known_groups = registered_groups(document)
    reported: set[tuple[str, str]] = set()
    for key, text in _text_sections(document):
        for group_name in known_groups:
            start = 0
            while True:
                index = text.find(group_name, start)
                if index < 0:
                    break
                start = index + len(group_name)
                # 窗口放大到 6 字：容纳“组长+姓名”（如 组长朱少军）
                name_match = re.match(r"[\u4e00-\u9fa5]{2,6}", text[start:])
                if not name_match:
                    continue
                name = name_match.group(0)
                while len(name) > 2 and name[:2] in (
                    "组长",
                    "副组",
                    "成员",
                    "组员",
                    "人员",
                    "队员",
                    "全员",
                ):
                    name = name[2:]
                # 剥离头衔/集合前缀后，剩余部分以动词/介词等开头时不是人名
                # （如「应急处置组人员处置不当」剥离后为「处置不当」）
                if name and name[0] in _NON_NAME_LEADING_CHARS:
                    continue
                follower = text[
                    start + len(name_match.group(0)) : start
                    + len(name_match.group(0))
                    + 2
                ]
                if follower.startswith(
                    ("人员", "全体", "组长", "成员", "组员")
                ) or follower.startswith("的"):
                    continue
                if name in people:
                    continue
                # 姓名与正文粘连（如“朱少军立即通知”），按 2/3/4 字候选
                # 匹配已登记人员；任一命中即视为名单内人员
                if len(name) >= 3 and any(
                    name[:length] in people for length in (2, 3, 4)
                ):
                    continue
                # 剥离“组长/成员”等前缀后再试（如“组长朱少军”→朱少军）
                if len(name) >= 4 and any(
                    name[offset : offset + length] in people
                    for offset in (0, 2)
                    for length in (2, 3, 4)
                    if offset + length <= len(name)
                ):
                    continue
                if name in _LEADER_STOPWORDS:
                    continue
                if (key, name) in reported:
                    continue
                reported.add((key, name))
                out.add(
                    "person_unknown",
                    "high",
                    key,
                    f"正文出现「{group_name}{name}」，疑似人员「{name}」"
                    "不在组织架构名单中，请核对或修改",
                    quote=f"{group_name}{name}",
                )


def _scenario(document: EmergencyPlanDocument) -> PlanChapter | None:
    return next((c for c in document.chapters if c.key == "scenario"), None)


def _check_timeline(document: EmergencyPlanDocument, out: _Collector) -> None:
    chapter = _scenario(document)
    if chapter is None or not chapter.content.strip():
        return
    last_minute = -1
    last_label = ""
    expected_scene = 1
    for line in strip_markup(chapter.content).splitlines():
        scene = _SCENE_MARK_RE.search(line)
        if scene:
            number = cn_to_int(scene.group(1))
            if number and number != expected_scene:
                out.add(
                    "scene_numbering",
                    "medium",
                    "scenario",
                    f"情景编号不连续：应为（情景{expected_scene}），实际为"
                    f"{scene.group(0)}",
                    quote=scene.group(0),
                )
            expected_scene = (number or expected_scene) + 1
            if not _TIME_RE.search(line):
                out.add(
                    "scene_missing_time",
                    "medium",
                    "scenario",
                    f"{scene.group(0)}未标注时间",
                    quote=line.strip()[:80],
                )
        for match in _TIME_RE.finditer(line):
            minute = int(match.group(1)) * 60 + int(match.group(2))
            if minute < last_minute:
                out.add(
                    "timeline_backwards",
                    "medium",
                    "scenario",
                    f"情景时间倒退：「{last_label}」之后出现「{match.group(0)}」，"
                    "演练脚本应按时间先后推进",
                    quote=match.group(0),
                )
            last_minute = max(last_minute, minute)
            last_label = match.group(0)


def find_company_mentions(text: str) -> list[str]:
    """抽取文中“XX有限公司”式名称（从后缀向前回溯到分隔符）。"""
    names: list[str] = []
    for suffix in ("有限公司",):
        start = 0
        while True:
            index = text.find(suffix, start)
            if index < 0:
                break
            end = index + len(suffix)
            begin = index
            while begin > 0 and index - begin < 24:
                char = text[begin - 1]
                if char in _NAME_DELIMITERS and char not in "（）()":
                    break
                begin -= 1
            name = text[begin:end]
            # 括号不成对时从左括号外侧截断（如“…园区（丽珠…”）
            if name.count("（") != name.count("）"):
                name = name[name.rfind("（") + 1 :] if "（" in name else name
            if len(name) > len(suffix) + 1:
                names.append(name)
            start = end
    return names


def _same_brand(name: str, company: str) -> bool:
    return len(name) >= 2 and len(company) >= 2 and name[:2] == company[:2]


def _check_company(document: EmergencyPlanDocument, out: _Collector) -> None:
    company = document.cover.company.strip()
    if not company:
        return
    for key, text in _text_sections(document):
        for name in find_company_mentions(text):
            if name == company or (company.endswith(name) and len(name) > 6):
                continue
            if _same_brand(name, company):
                out.add(
                    "company_not_full_name",
                    "medium",
                    key,
                    f"「{name}」未使用公司全称，统一为「{company}」",
                    quote=name,
                    replacement=company,
                )
            else:
                out.add(
                    "company_unknown",
                    "low",
                    key,
                    f"文中出现「{name}」，与封面公司名称「{company}」不同，请核对",
                    quote=name,
                )


def _check_leak_typo(document: EmergencyPlanDocument, out: _Collector) -> None:
    for chapter in document.chapters:
        if _LEAK_TYPO_RE.search(chapter.title):
            out.add(
                "typo_leak",
                "low",
                chapter.key,
                f"章节标题「{chapter.title}」中「泄露」应为「泄漏」",
                quote=chapter.title,
                replacement=_LEAK_TYPO_RE.sub("泄漏", chapter.title),
            )
    for key, text in _text_sections(document):
        count = len(_LEAK_TYPO_RE.findall(text))
        if count:
            out.add(
                "typo_leak",
                "low",
                key,
                f"「泄露」应为「泄漏」（{count} 处）",
                quote="泄露",
                replacement="泄漏",
            )


def _check_foam(
    document: EmergencyPlanDocument, substances: list[str], out: _Collector
) -> None:
    joined = "".join(substances)
    if not any(fuel in joined for fuel in WATER_SOLUBLE_FUELS):
        return
    for chapter in document.chapters:
        if chapter.key not in ("scenario", "handling", "hazard_analysis"):
            continue
        for match in _FOAM_RE.finditer(chapter.content):
            context = chapter.content[max(0, match.start() - 6) : match.end() + 4]
            out.add(
                "foam_not_alcohol_resistant",
                "high",
                chapter.key,
                f"{joined}属水溶性易燃液体，普通泡沫遇其会被破坏，"
                f"「{context.strip()}」处应明确使用抗溶性泡沫",
                quote=context.strip(),
            )


def _numbers(text: str) -> set[float]:
    values: set[float] = set()
    for raw in _NUMBER_RE.findall(text):
        normalized = raw.replace("－", "-").replace("−", "-")
        try:
            values.add(float(normalized))
        except ValueError:
            continue
    return values


def _check_values_against_msds(
    document: EmergencyPlanDocument, msds_text: str, out: _Collector
) -> None:
    if not msds_text.strip():
        return
    chapter = document.chapter("properties")
    if chapter is None or not chapter.content.strip():
        return
    source_values = _numbers(msds_text)
    for match in _VALUE_WITH_UNIT_RE.finditer(chapter.content):
        value_numbers = _numbers(match.group(0))
        if value_numbers and not value_numbers & source_values:
            out.add(
                "value_without_source",
                "medium",
                "properties",
                f"理化数值「{match.group(0).strip()}」在 MSDS 原文中未找到，请核对出处",
                quote=match.group(0).strip(),
            )


# ---------- 对外入口 ----------


def run_checks(
    document: EmergencyPlanDocument,
    *,
    substances: list[str] | None = None,
    msds_text: str = "",
) -> list[CheckIssue]:
    out = _Collector()
    _check_completeness(document, out)
    _check_group_names(document, out)
    _check_people(document, out)
    _check_timeline(document, out)
    _check_company(document, out)
    _check_leak_typo(document, out)
    _check_foam(document, substances or [], out)
    _check_values_against_msds(document, msds_text, out)
    return out.issues


def _fix_company(text: str, company: str) -> tuple[str, list[str]]:
    replaced: list[str] = []
    for name in find_company_mentions(text):
        if (
            name != company
            and _same_brand(name, company)
            and not (company.endswith(name) and len(name) > 6)
        ):
            text = text.replace(name, company)
            replaced.append(name)
    return text, replaced


def apply_deterministic_fixes(
    document: EmergencyPlanDocument,
) -> tuple[EmergencyPlanDocument, list[CheckIssue]]:
    """应用无歧义的确定性修正（公司全称、事故术语“泄漏”），返回新文档与修正记录。"""
    fixes: list[CheckIssue] = []
    company = document.cover.company.strip()

    def fix_text(section: str, text: str) -> str:
        leak_count = len(_LEAK_TYPO_RE.findall(text))
        if leak_count:
            text = _LEAK_TYPO_RE.sub("泄漏", text)
            fixes.append(
                CheckIssue(
                    code="typo_leak",
                    severity="low",
                    section=section,
                    quote="泄露",
                    message=f"「泄露」统一为「泄漏」（{leak_count} 处）",
                    replacement="泄漏",
                )
            )
        if company:
            text, replaced = _fix_company(text, company)
            for name in replaced:
                fixes.append(
                    CheckIssue(
                        code="company_not_full_name",
                        severity="medium",
                        section=section,
                        quote=name,
                        message=f"「{name}」统一为公司全称「{company}」",
                        replacement=company,
                    )
                )
        return text

    chapters = []
    for chapter in document.chapters:
        title = chapter.title
        if _LEAK_TYPO_RE.search(title):
            new_title = _LEAK_TYPO_RE.sub("泄漏", title)
            fixes.append(
                CheckIssue(
                    code="typo_leak",
                    severity="low",
                    section=chapter.key,
                    quote=title,
                    message=f"章节标题「{title}」改为「{new_title}」",
                    replacement=new_title,
                )
            )
            title = new_title
        chapters.append(
            chapter.model_copy(
                update={
                    "title": title,
                    "content": fix_text(chapter.key, chapter.content),
                }
            )
        )
    preface = fix_text("preface", document.preface)
    return (
        document.model_copy(update={"preface": preface, "chapters": chapters}),
        fixes,
    )
