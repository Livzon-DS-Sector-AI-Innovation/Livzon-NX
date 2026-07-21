"""Generate Feishu deviation ledger exports from a local Word template."""

from __future__ import annotations

import copy
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn


_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "templates" / "偏差登记表-模板.docx"
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


def _normalize_yes_no(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"

    text = _safe_str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "是", "已关闭", "closed"}:
        return "是"
    if text in {"0", "false", "no", "n", "否", "未关闭", "draft", "open"}:
        return "否"
    return ""


def _normalize_level(value: Any) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""

    mapping = {
        "major": "重大",
        "moderate": "次要",
        "minor": "微小",
        "严重偏差": "重大",
        "中等偏差": "次要",
        "次要偏差": "微小",
    }
    return mapping.get(text.lower(), mapping.get(text, text))


def _build_product_batch(item: dict[str, Any]) -> str:
    product_batch = _safe_str(item.get("product_batch")).strip()
    if product_batch:
        return product_batch

    affected_items = _safe_str(item.get("affected_items")).strip()
    batch_number = _safe_str(item.get("batch_number")).strip()
    if affected_items and batch_number:
        return f"{affected_items}\n{batch_number}"
    return affected_items or batch_number


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


def generate_deviation_ledger_export_docx(items: list[dict[str, Any]]) -> bytes:
    """Render deviation ledger records into the local Word template."""
    doc = Document(_TEMPLATE_PATH)
    if not doc.tables:
        raise ValueError("偏差台账模板中未找到表格")

    table = doc.tables[0]
    table_element = table._tbl
    row_elements = table_element.findall(qn("w:tr"))
    if len(row_elements) < 2:
        raise ValueError("偏差台账模板缺少可复用的数据行")

    template_row = copy.deepcopy(row_elements[1])
    for row_elem in list(row_elements[1:]):
        table_element.remove(row_elem)

    for index, item in enumerate(items, start=1):
        row_elem = copy.deepcopy(template_row)
        table_element.append(row_elem)
        cell_elems = row_elem.findall(qn("w:tc"))

        values = [
            str(index),
            _safe_str(item.get("deviation_code")).strip(),
            _build_product_batch(item),
            _safe_str(item.get("description") or item.get("title")).strip(),
            _normalize_yes_no(item.get("has_occurred_before")),
            _safe_str(item.get("root_cause_analysis")).strip(),
            _normalize_level(item.get("level")),
            _format_date(item.get("investigation_completed_at")),
            _safe_str(item.get("corrective_actions")).strip(),
            _safe_str(item.get("material_disposition")).strip(),
            _normalize_yes_no(
                item.get("is_closed")
                if item.get("is_closed") is not None
                else item.get("status")
            ),
        ]

        for cell_index, value in enumerate(values):
            if cell_index >= len(cell_elems):
                break
            _set_cell_text(cell_elems[cell_index], value)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
