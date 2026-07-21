"""Generate change ledger exports from the local Word template."""

from __future__ import annotations

import copy
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn


_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "templates" / "变更台账-模板.docx"
)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _format_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y.%m.%d")
    if isinstance(value, date):
        return value.strftime("%Y.%m.%d")

    text = _safe_str(value).strip()
    if not text:
        return ""

    normalized = text.replace("/", "-").replace(".", "-").replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    for parser in (datetime.fromisoformat,):
        try:
            return parser(normalized).strftime("%Y.%m.%d")
        except ValueError:
            continue

    return text.replace("-", ".").replace("/", ".")


def _clear_text_in_paragraph(paragraph_elem: Any) -> None:
    for run_elem in paragraph_elem.findall(qn("w:r")):
        for text_elem in run_elem.findall(qn("w:t")):
            text_elem.text = ""


def _set_cell_text(cell_elem: Any, text: str) -> None:
    lines = (text or "").split("\n")
    paragraph_elems = cell_elem.findall(qn("w:p"))

    if not paragraph_elems:
        paragraph_elem = cell_elem.makeelement(qn("w:p"), {})
        cell_elem.append(paragraph_elem)
        paragraph_elems = [paragraph_elem]

    while len(paragraph_elems) > len(lines):
        paragraph_elems[-1].getparent().remove(paragraph_elems[-1])
        paragraph_elems = cell_elem.findall(qn("w:p"))

    while len(paragraph_elems) < len(lines):
        new_paragraph = copy.deepcopy(paragraph_elems[0])
        _clear_text_in_paragraph(new_paragraph)
        cell_elem.append(new_paragraph)
        paragraph_elems = cell_elem.findall(qn("w:p"))

    for index, line in enumerate(lines):
        paragraph_elem = paragraph_elems[index]
        run_elems = paragraph_elem.findall(qn("w:r"))
        for run_elem in run_elems:
            for text_elem in run_elem.findall(qn("w:t")):
                text_elem.text = ""

        if not run_elems:
            run_elem = paragraph_elem.makeelement(qn("w:r"), {})
            paragraph_elem.append(run_elem)
            run_elems = [run_elem]

        text_elems = run_elems[0].findall(qn("w:t"))
        if not text_elems:
            text_elem = run_elems[0].makeelement(qn("w:t"), {})
            run_elems[0].append(text_elem)
            text_elems = [text_elem]

        text_elems[0].text = line


def _resolve_serial_number(item: dict[str, Any], index: int) -> str:
    serial_number = _safe_str(item.get("serial_number")).strip()
    return serial_number or str(index)


def _resolve_closure_value(item: dict[str, Any]) -> str:
    closure_date = _format_date(item.get("closure_date"))
    if closure_date:
        return closure_date
    return _safe_str(item.get("status")).strip()


def generate_change_ledger_export_docx(items: list[dict[str, Any]]) -> bytes:
    """Render change ledger records into the local Word template."""
    doc = Document(_TEMPLATE_PATH)
    if not doc.tables:
        raise ValueError("变更台账模板中未找到表格")

    table = doc.tables[0]
    table_element = table._tbl
    row_elements = table_element.findall(qn("w:tr"))
    if len(row_elements) < 2:
        raise ValueError("变更台账模板缺少可复用的数据行")

    template_row = copy.deepcopy(row_elements[1])
    for row_elem in list(row_elements[1:]):
        table_element.remove(row_elem)

    for index, item in enumerate(items, start=1):
        row_elem = copy.deepcopy(template_row)
        table_element.append(row_elem)
        cell_elems = row_elem.findall(qn("w:tc"))

        values = [
            _resolve_serial_number(item, index),
            _safe_str(item.get("change_code")).strip(),
            _safe_str(item.get("applicant_department")).strip(),
            _safe_str(item.get("change_object")).strip(),
            _safe_str(item.get("change_content")).strip(),
            _safe_str(item.get("change_level")).strip(),
            _format_date(item.get("application_date")),
            _format_date(item.get("planned_approval_date")),
            _format_date(item.get("execution_date")),
            _resolve_closure_value(item),
        ]

        for cell_index, value in enumerate(values):
            if cell_index >= len(cell_elems):
                break
            _set_cell_text(cell_elems[cell_index], value)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
