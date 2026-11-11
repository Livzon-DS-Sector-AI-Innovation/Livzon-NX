"""应急预案 docx 导入：按公司模板结构确定性解析为结构化预案。

解析规则：
- 第一个“一、”标题之前：封面（公司、标题、级别、演练/建档信息）与引言；
- 以“X、标题”切分章节，按标题关键词映射到模板章节；
- 第三章解析组织机构（总指挥/副总指挥/各组组长与成员），第四章“（三）”
  之后解析指挥部人员职责，第九章解析车间应急组；无法识别的行原样保留在
  对应章节正文中，不丢内容。
识别出的模板章节少于 ``MIN_TEMPLATE_HEADINGS`` 时判定为非模板文档，由
AI 编排层改用 LLM 结构化。
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.modules.safety.schemas.emergency_plan_ai import (
    EmergencyPlanDocument,
    OrgGroup,
    PlanChapter,
    PlanCover,
    PlanOrganization,
    WorkshopOrganization,
)
from app.modules.safety.service.emergency_plan_template import (
    CHAPTER_KEYS,
    CHAPTER_SPECS,
    RESPONSIBILITIES_STRUCTURED_HEADING,
)

MIN_TEMPLATE_HEADINGS = 6

_HEADING_RE = re.compile(r"^\s*([一二三四五六七八九十]{1,3})\s*、\s*(.+?)\s*$")
_META_RE = re.compile(r"^\s*(演练时间|建档时间|建档部门)\s*[:：]\s*(.*?)\s*$")
_LEVEL_RE = re.compile(r"^\s*[（(]\s*([^）)]{1,10}级)\s*[）)]\s*$")
_COMMANDER_RE = re.compile(r"^\s*总\s*指\s*挥\s*[:：]\s*(.*?)\s*$")
_DEPUTY_RE = re.compile(r"^\s*副\s*总\s*指\s*挥\s*[:：]\s*(.*?)\s*$")
_WORKSHOP_DEPUTY_RE = re.compile(r"^\s*副\s*指\s*挥\s*[:：]\s*(.*?)\s*$")
_LEADER_RE = re.compile(r"^\s*组\s*长\s*[:：]\s*(.*?)\s*$")
_MEMBERS_RE = re.compile(r"^\s*(?:组\s*员|成\s*员)\s*[:：]\s*(.*?)\s*$")
_GROUP_HEADER_RE = re.compile(r"^\s*([\u4e00-\u9fa5]{2,12}组)\s*[:：]?\s*$")
_DUTY_LINE_RE = re.compile(r"^\s*([\u4e00-\u9fa5]{2,12})\s*[:：]\s*(.+?)\s*$")
_WORKSHOP_DEPT_RE = re.compile(r"^\s*\d+\s*、\s*(.+?)应急组成员\s*[:：]?\s*$")

_CHAPTER_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("workshop_organization", ("车间应急组", "车间应急")),
    ("guiding_thought", ("指导思想",)),
    ("purpose", ("目的",)),
    ("organization", ("组织架构", "组织机构")),
    ("responsibilities", ("职责",)),
    ("hazard_analysis", ("危险源", "风险分析")),
    ("properties", ("理化", "特性")),
    ("protection", ("防护",)),
    ("handling", ("处理", "处置措施")),
    ("scenario", ("情景",)),
    ("debrief", ("讲评", "点评", "评估")),
    ("attachments", ("附件",)),
)
_DEFAULT_TITLES = {spec.key: spec.title for spec in CHAPTER_SPECS}


@dataclass
class ImportedPlan:
    document: EmergencyPlanDocument
    template_headings: int
    warnings: list[str] = field(default_factory=list)

    @property
    def is_template_like(self) -> bool:
        return self.template_headings >= MIN_TEMPLATE_HEADINGS


@dataclass
class _Line:
    text: str
    bold: bool


def _paragraph_line(paragraph: Paragraph) -> _Line:
    text = paragraph.text.replace("\u3000", " ").strip()
    runs = [run for run in paragraph.runs if run.text.strip()]
    bold = bool(runs) and all(bool(run.bold) for run in runs)
    return _Line(text=text, bold=bold)


def _read_lines(content: bytes) -> list[_Line]:
    document = Document(io.BytesIO(content))
    lines: list[_Line] = []
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            line = _paragraph_line(Paragraph(child, document))
            if line.text:
                lines.append(line)
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            for row in table.rows:
                cells: list[str] = []
                for cell in row.cells:
                    text = cell.text.strip()
                    if text and (not cells or cells[-1] != text):
                        cells.append(text)
                if cells:
                    lines.append(_Line(text=" | ".join(cells), bold=False))
    return lines


def map_chapter_key(title: str) -> str | None:
    for key, keywords in _CHAPTER_KEYWORDS:
        if any(keyword in title for keyword in keywords):
            return key
    return None


def _split_names(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[、，,]+", value) if part.strip()]


def _parse_organization(lines: list[str]) -> tuple[PlanOrganization, list[str]]:
    commander = ""
    deputies: list[str] = []
    groups: list[OrgGroup] = []
    extra: list[str] = []
    for line in lines:
        if match := _DEPUTY_RE.match(line):
            deputies = _split_names(match.group(1))
        elif match := _COMMANDER_RE.match(line):
            commander = match.group(1)
        elif match := _LEADER_RE.match(line):
            if groups:
                groups[-1] = groups[-1].model_copy(update={"leader": match.group(1)})
            else:
                extra.append(line)
        elif match := _MEMBERS_RE.match(line):
            if groups:
                groups[-1] = groups[-1].model_copy(update={"members": match.group(1)})
            else:
                extra.append(line)
        elif match := _GROUP_HEADER_RE.match(line):
            groups.append(OrgGroup(name=match.group(1)))
        else:
            extra.append(line)
    return (
        PlanOrganization(
            commander=commander, deputy_commanders=deputies, groups=groups
        ),
        extra,
    )


def _parse_workshop(lines: list[str]) -> tuple[WorkshopOrganization, list[str]]:
    workshop = WorkshopOrganization()
    groups: list[OrgGroup] = []
    extra: list[str] = []
    for line in lines:
        if match := _WORKSHOP_DEPT_RE.match(line):
            workshop.department = match.group(1).strip()
        elif match := _WORKSHOP_DEPUTY_RE.match(line):
            workshop.deputy_commander = match.group(1)
        elif match := _COMMANDER_RE.match(line):
            workshop.commander = match.group(1)
        elif match := _LEADER_RE.match(line):
            if groups:
                groups[-1] = groups[-1].model_copy(update={"leader": match.group(1)})
            else:
                extra.append(line)
        elif match := _MEMBERS_RE.match(line):
            if groups:
                groups[-1] = groups[-1].model_copy(update={"members": match.group(1)})
            else:
                extra.append(line)
        elif match := _GROUP_HEADER_RE.match(line):
            name = match.group(1)
            if name != "应急指挥组":
                groups.append(OrgGroup(name=name))
        else:
            extra.append(line)
    workshop.groups = groups
    return workshop, extra


def _apply_duties(
    organization: PlanOrganization, lines: list[str]
) -> tuple[PlanOrganization, list[str]]:
    """解析“（三）指挥部人员职责分工”之后的“角色：职责”行。"""
    groups = {group.name: group for group in organization.groups}
    updates: dict[str, str] = {}
    unmatched: list[str] = []
    for line in lines:
        match = _DUTY_LINE_RE.match(line)
        if not match:
            unmatched.append(line)
            continue
        role, duties = match.group(1).replace(" ", ""), match.group(2)
        if role == "总指挥":
            updates["commander_duties"] = duties
        elif role == "副总指挥":
            updates["deputy_duties"] = duties
        elif role in groups:
            groups[role] = groups[role].model_copy(update={"duties": duties})
        else:
            unmatched.append(line)
    updated = organization.model_copy(
        update={
            **updates,
            "groups": [groups[group.name] for group in organization.groups],
        }
    )
    return updated, unmatched


def _parse_cover(lines: list[_Line]) -> tuple[PlanCover, str]:
    cover = PlanCover()
    preface_parts: list[str] = []
    for line in lines:
        text = line.text
        if match := _META_RE.match(text):
            label, value = match.group(1), match.group(2)
            if label == "演练时间":
                cover.drill_date = value
            elif label == "建档时间":
                cover.archive_date = value
            else:
                cover.archive_department = value
        elif match := _LEVEL_RE.match(text):
            cover.level = cover.level or match.group(1)
        elif text.endswith("有限公司") and len(text) <= 40:
            cover.company = cover.company or text
        elif (
            ("方案" in text or "预案" in text)
            and len(text) <= 80
            and not text.endswith("。")
        ):
            if not cover.title:
                cover.title = text
            elif text != cover.title:
                preface_parts.append(text)
        else:
            preface_parts.append(text)
    return cover, "\n".join(preface_parts)


def _ordered_chapters(parsed: list[PlanChapter]) -> list[PlanChapter]:
    """按模板顺序补齐缺失章节，自定义章节保持原相对位置。"""
    present = {chapter.key for chapter in parsed}
    result: list[PlanChapter] = []
    added: set[str] = set()

    def add_missing_before(key: str) -> None:
        for template_key in CHAPTER_KEYS:
            if template_key == key:
                break
            if template_key not in present and template_key not in added:
                result.append(
                    PlanChapter(key=template_key, title=_DEFAULT_TITLES[template_key])
                )
                added.add(template_key)

    for chapter in parsed:
        if chapter.key in CHAPTER_KEYS:
            add_missing_before(chapter.key)
        result.append(chapter)
        added.add(chapter.key)
    for template_key in CHAPTER_KEYS:
        if template_key not in added:
            result.append(
                PlanChapter(key=template_key, title=_DEFAULT_TITLES[template_key])
            )
    return result


def parse_plan_docx(content: bytes) -> ImportedPlan:
    """解析 docx 字节为结构化预案（同步阻塞，调用方放线程池执行）。"""
    lines = _read_lines(content)
    first_heading = next(
        (index for index, line in enumerate(lines) if _HEADING_RE.match(line.text)),
        len(lines),
    )
    cover, preface = _parse_cover(lines[:first_heading])

    sections: list[tuple[str, list[str]]] = []
    for line in lines[first_heading:]:
        if match := _HEADING_RE.match(line.text):
            sections.append((match.group(2).rstrip("：:").strip(), []))
        elif sections:
            sections[-1][1].append(line.text)

    organization = PlanOrganization()
    workshop: WorkshopOrganization | None = None
    chapters: list[PlanChapter] = []
    used_keys: set[str] = set()
    custom_index = 0
    template_headings = 0
    warnings: list[str] = []
    pending_duties: list[str] = []
    responsibilities_index: int | None = None

    for title, body in sections:
        key = map_chapter_key(title)
        if key is None or key in used_keys:
            custom_index += 1
            key = f"custom_{custom_index}"
        else:
            template_headings += 1
        used_keys.add(key)
        content_lines = body
        if key == "organization":
            organization, content_lines = _parse_organization(body)
        elif key == "workshop_organization":
            workshop, content_lines = _parse_workshop(body)
        elif key == "responsibilities":
            split_at = next(
                (
                    index
                    for index, text in enumerate(body)
                    if text.replace(" ", "").startswith("（三）")
                ),
                None,
            )
            if split_at is not None:
                content_lines = body[:split_at]
                pending_duties = body[split_at + 1 :]
                responsibilities_index = len(chapters)
        chapters.append(
            PlanChapter(key=key, title=title[:100], content="\n".join(content_lines))
        )

    if pending_duties and responsibilities_index is not None:
        organization, unmatched = _apply_duties(organization, pending_duties)
        if unmatched:
            chapter = chapters[responsibilities_index]
            chapters[responsibilities_index] = chapter.model_copy(
                update={
                    "content": "\n".join(
                        [
                            chapter.content,
                            RESPONSIBILITIES_STRUCTURED_HEADING,
                            *unmatched,
                        ]
                    ).strip()
                }
            )
            warnings.append("职责分工中有部分条目未能匹配到组织机构，已保留为正文")

    if template_headings < MIN_TEMPLATE_HEADINGS:
        warnings.append("文档结构与公司模板差异较大，需要 AI 辅助整理章节")

    document = EmergencyPlanDocument(
        cover=cover,
        preface=preface,
        organization=organization,
        workshop_organization=workshop,
        chapters=_ordered_chapters(chapters),
    )
    return ImportedPlan(
        document=document, template_headings=template_headings, warnings=warnings
    )


def extract_plain_text(content: bytes, max_chars: int = 30000) -> str:
    """非模板文档的纯文本（供 LLM 结构化）。"""
    text = "\n".join(line.text for line in _read_lines(content))
    return text if len(text) <= max_chars else text[:max_chars]
