"""Feishu CAPA ledger export — fill data into local template .docx."""

from __future__ import annotations

import copy
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn


_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / "CAPA登记汇总表-模板.docx"
)


def _date_dot(value: str | None) -> str:
    """Convert YYYY-MM-DD -> YYYY.MM.DD"""
    if not value:
        return ""
    return value.replace("-", ".")


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _set_cell_text(cell: Any, text: str) -> None:
    """Replace text in first paragraph of a cell, preserving formatting."""
    p = cell.paragraphs[0]
    # preserve formatting from the first run if exists
    existing_runs = p.runs
    if existing_runs:
        # keep style, just replace text
        for run in existing_runs:
            run.text = ""
        existing_runs[0].text = text
    else:
        p.add_run(text)


def _set_cell_multiline(cell: Any, text: str) -> None:
    """Handle multiline text. Preserve styling of existing first paragraph,
    add extra paragraphs for additional lines."""
    lines = text.split("\n")
    paras = cell.paragraphs

    # first line -> reuse first paragraph, preserve style
    if paras:
        p0 = paras[0]
        for run in p0.runs:
            run.text = ""
        if p0.runs:
            p0.runs[0].text = lines[0]
        else:
            p0.add_run(lines[0])
    else:
        cell.add_paragraph(lines[0])

    # remove extra paragraphs beyond needed
    needed = len(lines)
    while len(cell.paragraphs) > needed:
        p_elem = cell.paragraphs[-1]._element
        p_elem.getparent().remove(p_elem)

    # add missing paragraphs, copying style from first
    template_elem = cell.paragraphs[0]._element if cell.paragraphs else None
    for i in range(len(cell.paragraphs), needed):
        if template_elem is not None:
            new_elem = copy.deepcopy(template_elem)
            # add after last paragraph
            cell.paragraphs[-1]._element.addnext(new_elem)
        else:
            cell.add_paragraph(lines[i])

    # set text
    for i, line in enumerate(lines):
        p = cell.paragraphs[i]
        for run in p.runs:
            run.text = ""
        if p.runs:
            p.runs[0].text = line
        else:
            p.add_run(line)


def generate_capa_export_docx(items: list[dict[str, Any]]) -> bytes:
    """Open the local template, replace table data with Feishu records, save to bytes."""
    doc = Document(str(_TEMPLATE_PATH))
    table = doc.tables[0]

    # ── 1. Remove all existing data rows (keep only header row 0) ──
    tbl_element = table._tbl
    row_elements = tbl_element.findall(qn("w:tr"))
    header_elem = row_elements[0] if row_elements else None
    # delete everything after header
    for elem in list(row_elements[1:]):
        tbl_element.remove(elem)

    # ── 2. Copy header row style as template for data rows ──
    def _clone_row(src_elem: Any) -> Any:
        new_elem = copy.deepcopy(src_elem)
        # clear cell texts in cloned row
        for tc in new_elem.findall(qn("w:tc")):
            for p_elem in tc.findall(qn("w:p")):
                for r_elem in p_elem.findall(qn("w:r")):
                    for t_elem in r_elem.findall(qn("w:t")):
                        t_elem.text = ""
        return new_elem

    header_row_elem = copy.deepcopy(header_elem) if header_elem is not None else None

    # ── 3. Add data rows ──
    for item in items:
        # clone header row for styling
        row_elem = copy.deepcopy(header_row_elem) if header_row_elem is not None else _clone_row(header_elem)
        tbl_element.append(row_elem)

        # now write data into cells
        cells = row_elem.findall(qn("w:tc"))

        capa_code = _safe_str(item.get("CAPA编号"))
        start_date = _date_dot(_safe_str(item.get("启动日期")))
        department = _safe_str(item.get("事件部门"))
        product = _safe_str(item.get("涉及产品"))
        summary = _safe_str(item.get("CAPA简述"))
        evaluation = _safe_str(item.get("CAPA效果评估"))
        close_date = _date_dot(_safe_str(item.get("关闭日期")))
        qa_name = _safe_str(item.get("QA质量员"))
        qa_date = _date_dot(_safe_str(item.get("QA质量员确认日期")))
        qa_combined = f"{qa_name}{qa_date}" if qa_name or qa_date else ""

        col_values = [capa_code, start_date, department, product, "", summary, evaluation, close_date, qa_combined]

        for ci, val in enumerate(col_values):
            if ci >= len(cells):
                continue
            tc = cells[ci]
            p_elems = tc.findall(qn("w:p"))
            if not p_elems:
                continue

            if ci == 5 and "\n" in val:  # CAPA简述 - multiline
                lines = val.split("\n")
                # first line in first paragraph
                r_elems_0 = p_elems[0].findall(qn("w:r"))
                for r in r_elems_0:
                    for t in r.findall(qn("w:t")):
                        t.text = ""
                if r_elems_0:
                    for t in r_elems_0[0].findall(qn("w:t")):
                        t.text = lines[0]
                else:
                    new_r = p_elems[0].makeelement(qn("w:r"), {})
                    new_t = new_r.makeelement(qn("w:t"), {})
                    new_t.text = lines[0]
                    new_r.append(new_t)
                    p_elems[0].append(new_r)

                # remove extra paragraphs beyond needed
                while len(p_elems) > len(lines):
                    p_elems[-1].getparent().remove(p_elems[-1])

                # add missing paragraphs, clone style from first
                for i in range(len(p_elems), len(lines)):
                    new_p = copy.deepcopy(p_elems[0])
                    for r in new_p.findall(qn("w:r")):
                        for t in r.findall(qn("w:t")):
                            t.text = ""
                    if new_p.findall(qn("w:r")):
                        for t in new_p.findall(qn("w:r"))[0].findall(qn("w:t")):
                            t.text = lines[i]
                    tc.append(new_p)
                for i, line in enumerate(lines):
                    if i < len(p_elems):
                        r_list = p_elems[i].findall(qn("w:r"))
                        if r_list:
                            for t in r_list[0].findall(qn("w:t")):
                                t.text = line
                        else:
                            new_r = p_elems[i].makeelement(qn("w:r"), {})
                            new_t = new_r.makeelement(qn("w:t"), {})
                            new_t.text = line
                            new_r.append(new_t)
                            p_elems[i].append(new_r)
            else:
                # Single line cell
                r_elems = p_elems[0].findall(qn("w:r"))
                for r in r_elems:
                    for t in r.findall(qn("w:t")):
                        t.text = ""
                if r_elems:
                    for t in r_elems[0].findall(qn("w:t")):
                        t.text = val
                else:
                    new_r = p_elems[0].makeelement(qn("w:r"), {})
                    new_t = new_r.makeelement(qn("w:t"), {})
                    new_t.text = val
                    new_r.append(new_t)
                    p_elems[0].append(new_r)

    # ── 4. Save ──
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
