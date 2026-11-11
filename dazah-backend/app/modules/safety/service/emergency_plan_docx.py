"""应急预案 Word 导出：按公司模板母版填充结构化正文。

母版 ``templates/emergency_plan_template.docx`` 由公司标准演练方案派生：
保留封面 LOGO、页面设置、页脚页码与宋体/仿宋样式，正文只留两个样板段落
（``{{HEADING}}`` 章标题、``{{BODY}}`` 正文）。导出时深拷贝样板段落逐行
插入以继承样式；组织架构图以表格框图绘制，适配任意小组数量。
"""

from __future__ import annotations

import copy
import io
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from lxml.etree import _Element  # type: ignore[import-untyped]

from app.modules.safety.schemas.emergency_plan_ai import (
    EmergencyPlanDocument,
    PlanOrganization,
)
from app.modules.safety.service.emergency_plan_template import (
    PENDING,
    chinese_numeral,
    render_chapter_text,
    split_bold_segments,
)

TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / "emergency_plan_template.docx"
)
BODY_FONT = "仿宋"
_TEXT_WIDTH_TWIPS = 8640  # A4 减去母版正文页边距后的可用宽度（约 15.2cm）


class EmergencyPlanTemplateMissingError(RuntimeError):
    """预案母版文件缺失。"""


def _find_paragraph(doc: DocxDocument, marker: str) -> Paragraph:
    for paragraph in doc.paragraphs:
        if paragraph.text.strip() == marker:
            return paragraph
    raise EmergencyPlanTemplateMissingError(f"预案母版缺少样板段落 {marker}")


def _replace_in_paragraph(paragraph: Paragraph, values: dict[str, str]) -> None:
    for run in paragraph.runs:
        text = run.text
        for key, value in values.items():
            text = text.replace("{{" + key + "}}", value)
        run.text = text


def _set_bold(run_element: _Element, bold: bool) -> None:
    rpr = run_element.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        run_element.insert(0, rpr)
    for tag in ("w:b", "w:bCs"):
        existing = rpr.find(qn(tag))
        if existing is not None:
            rpr.remove(existing)
        if bold:
            element = OxmlElement(tag)
            rpr.append(element)


def _clone_with_text(
    prototype: _Element, line: str, *, force_bold: bool | None = None
) -> _Element:
    """深拷贝样板段落，用首个 run 的格式写入可含 **加粗** 的一行文本。"""
    paragraph = copy.deepcopy(prototype)
    runs = paragraph.findall(qn("w:r"))
    base_run = copy.deepcopy(runs[0]) if runs else OxmlElement("w:r")
    for run in runs:
        paragraph.remove(run)
    segments = split_bold_segments(line) or [("", False)]
    for text, bold in segments:
        run = copy.deepcopy(base_run)
        for child in list(run):
            if child.tag != qn("w:rPr"):
                run.remove(child)
        text_element = OxmlElement("w:t")
        text_element.set(qn("xml:space"), "preserve")
        text_element.text = text
        run.append(text_element)
        _set_bold(run, bold if force_bold is None else force_bold)
        paragraph.append(run)
    return paragraph


def _cell_border(cell_pr: _Element) -> None:
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        element = OxmlElement(f"w:{side}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "8")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "000000")
        borders.append(element)
    cell_pr.append(borders)


def _org_cell(
    text: str, width: int, *, span: int = 1, vertical: bool = False, bold: bool = True
) -> _Element:
    cell = OxmlElement("w:tc")
    cell_pr = OxmlElement("w:tcPr")
    tc_w = OxmlElement("w:tcW")
    tc_w.set(qn("w:w"), str(width))
    tc_w.set(qn("w:type"), "dxa")
    cell_pr.append(tc_w)
    if span > 1:
        grid_span = OxmlElement("w:gridSpan")
        grid_span.set(qn("w:val"), str(span))
        cell_pr.append(grid_span)
    _cell_border(cell_pr)
    v_align = OxmlElement("w:vAlign")
    v_align.set(qn("w:val"), "center")
    cell_pr.append(v_align)
    cell.append(cell_pr)

    paragraph = OxmlElement("w:p")
    p_pr = OxmlElement("w:pPr")
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    p_pr.append(jc)
    paragraph.append(p_pr)
    lines = list(text) if vertical else [text]
    for index, line in enumerate(lines):
        run = OxmlElement("w:r")
        r_pr = OxmlElement("w:rPr")
        fonts = OxmlElement("w:rFonts")
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia"):
            fonts.set(qn(attr), BODY_FONT)
        r_pr.append(fonts)
        if bold:
            r_pr.append(OxmlElement("w:b"))
        size = OxmlElement("w:sz")
        size.set(qn("w:val"), str(int(Pt(12).pt * 2)))
        r_pr.append(size)
        run.append(r_pr)
        if index > 0:
            run.append(OxmlElement("w:br"))
        text_element = OxmlElement("w:t")
        text_element.set(qn("xml:space"), "preserve")
        text_element.text = line
        run.append(text_element)
        paragraph.append(run)
    cell.append(paragraph)
    return cell


def _org_row(cells: list[_Element], height: int | None = None) -> _Element:
    row = OxmlElement("w:tr")
    row_pr = OxmlElement("w:trPr")
    cant_split = OxmlElement("w:cantSplit")
    row_pr.append(cant_split)
    if height:
        tr_height = OxmlElement("w:trHeight")
        tr_height.set(qn("w:val"), str(height))
        tr_height.set(qn("w:hRule"), "atLeast")
        row_pr.append(tr_height)
    row.append(row_pr)
    for cell in cells:
        row.append(cell)
    return row


def build_org_chart_table(organization: PlanOrganization) -> _Element:
    """组织架构框图：总指挥 → 副总指挥 → 各小组（组名竖排）。"""
    groups = [group.name for group in organization.groups] or [PENDING]
    columns = len(groups)
    column_width = _TEXT_WIDTH_TWIPS // columns

    table = OxmlElement("w:tbl")
    tbl_pr = OxmlElement("w:tblPr")
    tbl_w = OxmlElement("w:tblW")
    tbl_w.set(qn("w:w"), str(column_width * columns))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_pr.append(tbl_w)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    tbl_pr.append(jc)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)
    table.append(tbl_pr)

    grid = OxmlElement("w:tblGrid")
    for _ in range(columns):
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(column_width))
        grid.append(grid_col)
    table.append(grid)

    full_width = column_width * columns
    commander = organization.commander.strip() or PENDING
    deputies = "、".join(d for d in organization.deputy_commanders if d.strip())
    table.append(
        _org_row([_org_cell(f"总指挥：{commander}", full_width, span=columns)], 560)
    )
    table.append(
        _org_row(
            [_org_cell(f"副总指挥：{deputies or PENDING}", full_width, span=columns)],
            560,
        )
    )
    longest = max(len(name) for name in groups)
    table.append(
        _org_row(
            [_org_cell(name, column_width, vertical=True) for name in groups],
            max(1600, longest * 330),
        )
    )
    return table


def _document_lines(
    document: EmergencyPlanDocument,
) -> list[tuple[str, str | None]]:
    """导出顺序的 (类型, 文本)：heading/body/org_chart。"""
    lines: list[tuple[str, str | None]] = []
    for paragraph in document.preface.splitlines():
        if paragraph.strip():
            lines.append(("body", paragraph))
    for index, chapter in enumerate(document.chapters, 1):
        lines.append(("heading", f"{chinese_numeral(index)}、{chapter.title}"))
        if chapter.key == "organization":
            lines.append(("org_chart", None))
        text = render_chapter_text(document, chapter)
        for paragraph in text.splitlines():
            if paragraph.strip():
                lines.append(("body", paragraph))
    return lines


def build_plan_docx(document: EmergencyPlanDocument) -> bytes:
    """渲染预案为 docx 字节（同步阻塞，调用方放线程池执行）。"""
    if not TEMPLATE_PATH.exists():
        raise EmergencyPlanTemplateMissingError("预案母版文件不存在")
    doc = Document(str(TEMPLATE_PATH))
    cover = document.cover
    values = {
        "company": cover.company,
        "title": cover.title,
        "level": cover.level,
        "drill_date": cover.drill_date,
        "archive_date": cover.archive_date,
        "archive_department": cover.archive_department,
    }
    heading = _find_paragraph(doc, "{{HEADING}}")
    body = _find_paragraph(doc, "{{BODY}}")
    prototypes = (heading._p, body._p)
    for paragraph in doc.paragraphs:
        if paragraph._p in prototypes:
            continue
        if "{{level}}" in paragraph.text and not cover.level.strip():
            paragraph._p.getparent().remove(paragraph._p)
            continue
        if "{{" in paragraph.text:
            _replace_in_paragraph(paragraph, values)

    anchor = heading._p
    for kind, text in _document_lines(document):
        if kind == "heading" and text is not None:
            anchor.addprevious(_clone_with_text(heading._p, text, force_bold=True))
        elif kind == "body" and text is not None:
            anchor.addprevious(_clone_with_text(body._p, text))
        elif kind == "org_chart":
            anchor.addprevious(build_org_chart_table(document.organization))
            spacer = _clone_with_text(body._p, "")
            anchor.addprevious(spacer)
    for prototype in (heading._p, body._p):
        prototype.getparent().remove(prototype)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def export_filename(document: EmergencyPlanDocument, fallback: str) -> str:
    title = document.cover.title.strip() or fallback.strip() or "应急预案"
    level = document.cover.level.strip()
    name = f"{title}({level})" if level and level not in title else title
    safe = "".join(char for char in name if char not in '\\/:*?"<>|\r\n')
    return f"{safe[:120]}.docx"
