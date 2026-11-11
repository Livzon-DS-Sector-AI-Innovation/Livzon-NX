"""应急预案模板：公司 12 章标准结构、标准原文与关键词替换（确定性，不调 LLM）。

标准原文取自公司《危险品库乙醇火灾事故综合应急演练方案(公司级)》，
已修正原文中的错别字、病句与标点；生成时只替换场所、物质、事故类型、
预案标题等关键词。组织架构（第三章）、指挥部人员职责（第四章第三节）与
车间应急组（第九章）由结构化组织机构渲染，保证前后章节天然一致。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.modules.safety.schemas.emergency_plan_ai import (
    EmergencyPlanDocument,
    EmergencyPlanGenerateRequest,
    OrganizationPatch,
    OrgGroup,
    PlanChapter,
    PlanCover,
    PlanOrganization,
    WorkshopOrganization,
    WorkshopPatch,
)

ChapterKind = Literal["fixed", "structured", "ai"]

DEFAULT_COMPANY = "丽珠集团（宁夏）制药有限公司"
PENDING = "（待定）"

LEVEL_LABELS: dict[str, str] = {"company": "公司级", "workshop": "车间级"}

ACCIDENT_TYPE_LABELS: dict[str, str] = {
    "fire": "火灾",
    "leak": "泄漏",
    "leak_fire": "泄漏火灾",
    "explosion": "爆炸",
    "poisoning": "中毒窒息",
    "burn": "灼烫",
    "electric": "触电",
    "mechanical": "机械伤害",
    "fall": "高处坠落",
    "other": "其他",
}


@dataclass(frozen=True)
class ChapterSpec:
    key: str
    title: str
    kind: ChapterKind
    substance_title: str | None = None


CHAPTER_SPECS: tuple[ChapterSpec, ...] = (
    ChapterSpec("guiding_thought", "指导思想", "fixed"),
    ChapterSpec("purpose", "演练目的", "fixed"),
    ChapterSpec("organization", "组织架构", "structured"),
    ChapterSpec("responsibilities", "职责分工", "fixed"),
    ChapterSpec("hazard_analysis", "危险源分析", "ai"),
    ChapterSpec("properties", "事故特性分析", "ai", "{substance}的理化性质"),
    ChapterSpec("protection", "防护措施", "ai", "{substance}泄漏的防护"),
    ChapterSpec("handling", "处置措施", "ai", "{substance}泄漏的处理"),
    ChapterSpec("workshop_organization", "车间应急组成员、组织机构", "structured"),
    ChapterSpec("scenario", "情景设置", "ai"),
    ChapterSpec("debrief", "演练讲评", "fixed"),
    ChapterSpec("attachments", "附件", "fixed"),
)
CHAPTER_KEYS: tuple[str, ...] = tuple(spec.key for spec in CHAPTER_SPECS)
AI_CHAPTER_KEYS: tuple[str, ...] = tuple(
    spec.key for spec in CHAPTER_SPECS if spec.kind == "ai"
)
_SPEC_BY_KEY = {spec.key: spec for spec in CHAPTER_SPECS}

# ---------- 公司标准原文（已修正） ----------

PREFACE_TEMPLATE = (
    "为验证我司针对{location}的突发事故、事件人员应急处置机制，提高员工的"
    "应急疏散撤离能力、快速反应能力、应急协调处理能力及组织救援能力，增强"
    "安全意识，落实安全职责，确保员工生命财产安全，根据《{company}生产安全"
    "事故应急预案》等相关文件要求，特此组织{scenario}应急处置演练，并制定"
    "《{title}》。"
)

GUIDING_THOUGHT_TEMPLATE = (
    "本方案按照《安全生产法》{chem_regulation}等国家相关法律、法规、标准和"
    "公司应急预案的要求，遵守“安全第一、预防为主、综合治理”的方针和"
    "“救护优先、防止和控制事故扩大优先、保护环境优先”的原则，策划了"
    "{scenario}事故启动{scope}应急程序的演练，在组织实施过程中，结合实际、"
    "突出重点、周密组织、统一指挥、讲究实效，保证本次演练活动取得预期效果，"
    "以达到演练目的。"
)

PURPOSE_TEMPLATE = (
    "本方案的主要目的是评估我公司针对{scenario}事故的应急准备状态，发现并"
    "及时修改应急预案的缺陷和不足；评估公司的应急能力，识别资源需求，明确"
    "相关部门和人员的应急职责，增强应急救援队伍之间的协调配合能力；检验应急"
    "响应人员对应急预案、执行程序的了解程度和实际操作技能，评估应急培训效果、"
    "分析培训需求；同时，作为一种培训手段，通过调整演练难度，进一步提高应急"
    "响应人员的业务素质和能力。"
)

RESPONSIBILITIES_TEMPLATE = "\n".join(
    [
        "（一）指挥领导小组：",
        "1、负责审核本公司《{title}》的制定、修订。",
        "2、组织建立应急救援专门队伍，并组织实施和演练。",
        "3、检查督促做好{scenario}事故的预防措施和应急救援的各项准备工作。",
        "（二）应急指挥部：",
        "1、负责现场应急指挥工作。",
        "2、收集现场信息，核实现场情况，针对事态发展，制定和调整现场应急处置"
        "方案并组织实施。",
        "3、组织协调各应急组、生产辅助车间及外部应急救援力量开展应急救援工作。",
        "4、及时向公司汇报应急处置情况。",
        "5、收集整理应急处置过程的有关资料，核实应急终止条件，并下达应急终止指令。",
    ]
)
RESPONSIBILITIES_STRUCTURED_HEADING = "（三）指挥部人员职责分工"

DEBRIEF_TEMPLATE = "\n".join(
    ["1、总指挥宣布演练结束。", "2、公司各应急组及总指挥对演练情况进行点评。"]
)

ATTACHMENT_ITEMS: tuple[str, ...] = (
    "应急响应流程",
    "公司应急组成员通讯录{department_contacts}",
    "{location}及周边应急疏散逃生路线图",
    "{location}建筑标识图",
    "{location}抢险救援布置图",
    "应急演练装备器材清单",
    "应急演练方案审核意见表",
    "应急演练培训照片",
    "应急演练现场参演人员签到表",
    "演练现场照片",
    "演练总结",
    "应急演练缺陷及整改记录",
)

COMMANDER_DUTIES = (
    "负责人员、资源配置和应急队伍的调动；对生产安全事故进行研判，批准本预案"
    "的启动和终止；授权事故状态下各级人员的职责；负责事故信息的上报工作，"
    "接受政府的指令和调动。"
)
DEPUTY_DUTIES = (
    "协助总指挥开展应急救援工作，参与生产安全事故的研判；核实现场人员伤亡和"
    "损失情况，及时向总指挥汇报抢险救援及事故应急处置的进展情况；总指挥不在"
    "时代替总指挥负责指挥救援；及时落实总指挥的应急处置指示。"
)

STANDARD_GROUP_DUTIES: dict[str, str] = {
    "应急处置组": (
        "负责事故现场工艺设备和管道的风险分析，组织切断相关物料来源；负责事故"
        "现场人员搜救，将被困、受伤人员转移至安全地点；负责火灾事故现场的灭火"
        "及其他事故的应急处置，协助查明事故原因，并协助做好现场保护与警戒。"
    ),
    "工程抢险组": (
        "根据事故破坏情况对现场实施紧急修复及断电等工作；组织调动、协调公司"
        "内外应急协作的检维修力量，负责损坏设施设备的维修、检验和恢复。"
    ),
    "设备抢险组": (
        "根据事故破坏情况对现场实施紧急修复及断电等工作，负责损坏设施设备的"
        "检查、维修和恢复。"
    ),
    "医疗救护组": (
        "负责组织对受伤、中毒人员的紧急医疗处置和转运，掌握伤员的医疗救治情况。"
    ),
    "环境监测组": (
        "负责对事故现场周边大气有毒有害物质及排水系统水体污染进行监测，对事故"
        "现场周围开展不间断监测，将监测结果及时报告现场指挥部，并组织对污染物"
        "（水）进行收集处理。"
    ),
    "警戒疏散组": (
        "负责确定事故现场周边的安全距离范围，设置警戒区域，禁止无关人员进入"
        "警戒区，并对现场道路交通进行指挥；协助有关部门做好事故现场保护和调查"
        "工作；公司大门不对外界无关人员开放（外来应急救援力量及政府部门除外）。"
    ),
    "应急资源保障组": ("负责协调和调动应急物资，保障应急物资快速采购和运送渠道畅通。"),
    "公共关系与后勤组": (
        "负责协调公共关系、提供法律支持，做好应急过程中的后勤保障；收集、跟踪"
        "新闻媒体、网络、社会公众等舆论信息，负责信息发布材料和上报材料的起草，"
        "并按照指令组织信息发布；负责与媒体、内部员工及利益相关方的沟通和告知；"
        "分析事故处置法律责任并提供法律支持；及时记录事故处置情况，保持事故"
        "处置信息畅通。"
    ),
    "通讯联络组": (
        "负责事故信息的接收、传递与上报，保持各应急小组之间及与公司应急指挥部"
        "的通讯畅通。"
    ),
}

COMPANY_GROUP_NAMES: tuple[str, ...] = (
    "应急处置组",
    "工程抢险组",
    "医疗救护组",
    "环境监测组",
    "警戒疏散组",
    "应急资源保障组",
    "公共关系与后勤组",
)
WORKSHOP_GROUP_NAMES: tuple[str, ...] = (
    "应急处置组",
    "警戒疏散组",
    "医疗救护组",
    "设备抢险组",
    "通讯联络组",
)

_CHINESE_DIGITS = "零一二三四五六七八九"


@dataclass(frozen=True)
class TemplateKeywords:
    company: str
    title: str
    location: str
    substance: str
    accident: str
    scenario: str
    level_label: str
    department: str
    has_substance: bool
    is_company_level: bool


def chinese_numeral(number: int) -> str:
    """1~99 转中文数字（十、十一、二十三）。"""
    if number <= 0 or number >= 100:
        return str(number)
    tens, ones = divmod(number, 10)
    if tens == 0:
        return _CHINESE_DIGITS[ones]
    prefix = "" if tens == 1 else _CHINESE_DIGITS[tens]
    return f"{prefix}十{_CHINESE_DIGITS[ones] if ones else ''}"


def accident_label(value: str) -> str:
    return ACCIDENT_TYPE_LABELS.get(value, value.strip())


def level_label(level: str) -> str:
    return LEVEL_LABELS.get(level, level)


def build_keywords(
    params: EmergencyPlanGenerateRequest, plan_name: str
) -> TemplateKeywords:
    substance = "、".join(item.name.strip() for item in params.substances if item.name)
    accident = accident_label(params.accident_type)
    location = params.location.strip()
    department = params.archive_department.strip() or next(
        (dept.strip() for dept in params.participating_departments if dept.strip()),
        "",
    )
    return TemplateKeywords(
        company=params.company.strip() or DEFAULT_COMPANY,
        title=plan_name.strip(),
        location=location,
        substance=substance,
        accident=accident,
        scenario=f"{location}{substance}{accident}",
        level_label=level_label(params.level),
        department=department,
        has_substance=bool(substance),
        is_company_level=params.level == "company",
    )


def chapter_title(key: str, keywords: TemplateKeywords) -> str:
    spec = _SPEC_BY_KEY[key]
    if spec.substance_title and keywords.has_substance:
        first_substance = keywords.substance.split("、")[0]
        return spec.substance_title.format(substance=first_substance)
    return spec.title


def render_fixed_chapter(key: str, keywords: TemplateKeywords) -> str:
    values = {
        "company": keywords.company,
        "title": keywords.title,
        "location": keywords.location,
        "scenario": keywords.scenario,
        "chem_regulation": "《危险化学品安全管理条例》"
        if keywords.has_substance
        else "",
        "scope": "公司内全面" if keywords.is_company_level else "车间",
    }
    if key == "guiding_thought":
        return GUIDING_THOUGHT_TEMPLATE.format(**values)
    if key == "purpose":
        return PURPOSE_TEMPLATE.format(**values)
    if key == "responsibilities":
        return RESPONSIBILITIES_TEMPLATE.format(**values)
    if key == "debrief":
        return DEBRIEF_TEMPLATE
    if key == "attachments":
        contacts = f"、{keywords.department}人员通讯录" if keywords.department else ""
        return "\n".join(
            f"{index}、"
            + item.format(location=keywords.location, department_contacts=contacts)
            for index, item in enumerate(ATTACHMENT_ITEMS, 1)
        )
    return ""


def render_preface(keywords: TemplateKeywords) -> str:
    return PREFACE_TEMPLATE.format(
        location=keywords.location,
        company=keywords.company,
        scenario=keywords.scenario,
        title=keywords.title,
    )


def default_organization(level: str) -> PlanOrganization:
    names = COMPANY_GROUP_NAMES if level == "company" else WORKSHOP_GROUP_NAMES
    return PlanOrganization(
        commander_duties=COMMANDER_DUTIES,
        deputy_duties=DEPUTY_DUTIES,
        groups=[
            OrgGroup(name=name, duties=STANDARD_GROUP_DUTIES.get(name, ""))
            for name in names
        ],
    )


def default_workshop_organization(department: str = "") -> WorkshopOrganization:
    return WorkshopOrganization(
        department=department,
        groups=[OrgGroup(name=name) for name in WORKSHOP_GROUP_NAMES],
    )


def fill_standard_duties(organization: PlanOrganization) -> PlanOrganization:
    """为空的职责补公司标准原文（不覆盖已有内容）。"""
    groups = [
        group.model_copy(
            update={"duties": group.duties or STANDARD_GROUP_DUTIES.get(group.name, "")}
        )
        for group in organization.groups
    ]
    return organization.model_copy(
        update={
            "commander_duties": organization.commander_duties or COMMANDER_DUTIES,
            "deputy_duties": organization.deputy_duties or DEPUTY_DUTIES,
            "groups": groups,
        }
    )


def merge_organization_patch(
    organization: PlanOrganization, patch: OrganizationPatch
) -> PlanOrganization:
    """按组名合并组织机构补丁（None 字段不改，新组名追加）。"""
    groups = {group.name: group for group in organization.groups}
    order = [group.name for group in organization.groups]
    for group_patch in patch.groups or []:
        existing = groups.get(group_patch.name)
        if existing is None:
            groups[group_patch.name] = OrgGroup(
                name=group_patch.name,
                leader=group_patch.leader or "",
                members=group_patch.members or "",
                duties=group_patch.duties or "",
            )
            order.append(group_patch.name)
        else:
            updates = {
                key: value
                for key, value in (
                    ("leader", group_patch.leader),
                    ("members", group_patch.members),
                    ("duties", group_patch.duties),
                )
                if value is not None
            }
            if updates:
                groups[group_patch.name] = existing.model_copy(update=updates)
    merged_deputies = (
        patch.deputy_commanders
        if patch.deputy_commanders is not None
        else organization.deputy_commanders
    )
    return organization.model_copy(
        update={
            "commander": (
                patch.commander
                if patch.commander is not None
                else organization.commander
            ),
            "commander_duties": (
                patch.commander_duties
                if patch.commander_duties is not None
                else organization.commander_duties
            ),
            "deputy_commanders": [name for name in merged_deputies if name.strip()],
            "deputy_duties": (
                patch.deputy_duties
                if patch.deputy_duties is not None
                else organization.deputy_duties
            ),
            "groups": [groups[name] for name in order],
        }
    )


def merge_workshop_patch(
    workshop: WorkshopOrganization | None, patch: WorkshopPatch
) -> WorkshopOrganization:
    base = workshop or WorkshopOrganization()
    groups = {group.name: group for group in base.groups}
    order = [group.name for group in base.groups]
    for group_patch in patch.groups or []:
        existing = groups.get(group_patch.name)
        if existing is None:
            groups[group_patch.name] = OrgGroup(
                name=group_patch.name,
                leader=group_patch.leader or "",
                members=group_patch.members or "",
                duties=group_patch.duties or "",
            )
            order.append(group_patch.name)
        else:
            updates = {
                key: value
                for key, value in (
                    ("leader", group_patch.leader),
                    ("members", group_patch.members),
                    ("duties", group_patch.duties),
                )
                if value is not None
            }
            if updates:
                groups[group_patch.name] = existing.model_copy(update=updates)
    return base.model_copy(
        update={
            "department": (
                patch.department if patch.department is not None else base.department
            ),
            "commander": (
                patch.commander if patch.commander is not None else base.commander
            ),
            "deputy_commander": (
                patch.deputy_commander
                if patch.deputy_commander is not None
                else base.deputy_commander
            ),
            "groups": [groups[name] for name in order],
        }
    )


def build_skeleton(
    params: EmergencyPlanGenerateRequest, plan_name: str
) -> EmergencyPlanDocument:
    """按模板搭好整份预案骨架：固定章节填标准原文，AI 章节留空。"""
    keywords = build_keywords(params, plan_name)
    chapters: list[PlanChapter] = []
    for spec in CHAPTER_SPECS:
        content = (
            render_fixed_chapter(spec.key, keywords) if spec.kind == "fixed" else ""
        )
        chapters.append(
            PlanChapter(
                key=spec.key, title=chapter_title(spec.key, keywords), content=content
            )
        )
    drill_date = (
        f"{params.drill_date.year}年{params.drill_date.month}月{params.drill_date.day}日"
        if params.drill_date
        else ""
    )
    archive_date = (
        f"{params.drill_date.year}年{params.drill_date.month}月"
        if params.drill_date
        else ""
    )
    organization = params.organization
    if not organization.groups:
        organization = default_organization(params.level).model_copy(
            update={
                "commander": organization.commander,
                "deputy_commanders": organization.deputy_commanders,
            }
        )
    return EmergencyPlanDocument(
        cover=PlanCover(
            company=keywords.company,
            title=keywords.title,
            level=keywords.level_label,
            drill_date=drill_date,
            archive_date=archive_date,
            archive_department=params.archive_department.strip(),
        ),
        preface=render_preface(keywords),
        organization=fill_standard_duties(organization),
        workshop_organization=params.workshop_organization,
        chapters=chapters,
    )


# ---------- 结构化章节渲染（预览、校验、AI 摘要与 Word 导出共用） ----------


def _value(text: str, placeholder: str) -> str:
    return text.strip() or placeholder


def render_organization_text(
    organization: PlanOrganization, *, placeholder: str = PENDING
) -> str:
    lines = [
        f"总 指 挥：{_value(organization.commander, placeholder)}",
        "副总指挥："
        + _value(
            "、".join(d for d in organization.deputy_commanders if d.strip()),
            placeholder,
        ),
    ]
    for group in organization.groups:
        lines.append(f"**{group.name}：**")
        lines.append(f"组长：{_value(group.leader, placeholder)}")
        lines.append(f"成员：{_value(group.members, placeholder)}")
    return "\n".join(lines)


def render_structured_duties(organization: PlanOrganization) -> str:
    lines = [RESPONSIBILITIES_STRUCTURED_HEADING]
    if organization.commander_duties.strip():
        lines.append(f"**总指挥：**{organization.commander_duties.strip()}")
    if organization.deputy_duties.strip():
        lines.append(f"**副总指挥：**{organization.deputy_duties.strip()}")
    for group in organization.groups:
        if group.duties.strip():
            lines.append(f"**{group.name}：**{group.duties.strip()}")
    return "\n".join(lines)


def render_workshop_text(
    workshop: WorkshopOrganization | None, *, placeholder: str = ""
) -> str:
    workshop = workshop or default_workshop_organization()
    department = workshop.department.strip()
    lines = [
        f"1、{department}应急组成员：" if department else "1、车间应急组成员：",
        "应急指挥组",
        f"总指挥：{_value(workshop.commander, placeholder)}",
        f"副指挥：{_value(workshop.deputy_commander, placeholder)}",
    ]
    for group in workshop.groups:
        lines.append(f"{group.name}：")
        lines.append(f"组长：{_value(group.leader, placeholder)}")
        if group.members.strip() or not group.leader.strip():
            lines.append(f"成员：{_value(group.members, placeholder)}")
    return "\n".join(lines)


def render_chapter_text(
    document: EmergencyPlanDocument,
    chapter: PlanChapter,
    *,
    placeholder: str = PENDING,
) -> str:
    """章节完整正文：结构化章节由组织机构渲染，其余直接返回正文。"""
    if chapter.key == "organization":
        extra = chapter.content.strip()
        body = render_organization_text(document.organization, placeholder=placeholder)
        return f"{body}\n{extra}" if extra else body
    if chapter.key == "responsibilities":
        parts = [
            chapter.content.strip(),
            render_structured_duties(document.organization),
        ]
        return "\n".join(part for part in parts if part)
    if chapter.key == "workshop_organization":
        extra = chapter.content.strip()
        body = render_workshop_text(
            document.workshop_organization,
            placeholder="" if placeholder == PENDING else placeholder,
        )
        return f"{body}\n{extra}" if extra else body
    return chapter.content


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def strip_markup(text: str) -> str:
    return _BOLD_RE.sub(r"\1", text)


def split_bold_segments(text: str) -> list[tuple[str, bool]]:
    """把 ``**加粗**`` 标记拆成 (文本, 是否加粗) 片段。"""
    segments: list[tuple[str, bool]] = []
    cursor = 0
    for match in _BOLD_RE.finditer(text):
        if match.start() > cursor:
            segments.append((text[cursor : match.start()], False))
        segments.append((match.group(1), True))
        cursor = match.end()
    if cursor < len(text):
        segments.append((text[cursor:], False))
    return [segment for segment in segments if segment[0]]


def document_sections(
    document: EmergencyPlanDocument,
) -> list[tuple[str, str, str]]:
    """(章节标识, 编号标题, 纯文本正文) 列表，供校验与 AI 摘要使用。"""
    sections: list[tuple[str, str, str]] = [("preface", "引言", document.preface)]
    for index, chapter in enumerate(document.chapters, 1):
        sections.append(
            (
                chapter.key,
                f"{chinese_numeral(index)}、{chapter.title}",
                strip_markup(render_chapter_text(document, chapter)),
            )
        )
    return sections
