"""Generate CAPA ledger exports from the local Word template."""

from __future__ import annotations

import copy
import logging
import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from docx import Document
from docx.oxml.ns import qn

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / "CAPA登记汇总表-模板.docx"
)

# 台账日期区按国内工作日口径取"当天"
_LEDGER_TIMEZONE = ZoneInfo("Asia/Shanghai")

_DATE_DIGITS_PATTERN = re.compile(r"\d+")
_DATE_SEPARATOR_PATTERN = re.compile(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})")


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _format_date(value: Any) -> str:
    """统一为台账使用的 YYYY.MM.DD；带时区的时间先换算到国内日期。

    台账日期字段混用两种存储口径：只记日期的值存为 UTC 零点，
    同步自飞书"启动日期"的值存为国内零点（UTC 16:00），
    统一按 Asia/Shanghai 取日期才能都还原成台账当天。
    """
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(_LEDGER_TIMEZONE)
        return str(value.strftime("%Y.%m.%d"))
    if isinstance(value, date):
        return value.strftime("%Y.%m.%d")

    text = _safe_str(value).strip()
    if not text:
        return ""

    # 只规范日期分隔符，保留时间部分的毫秒与偏移写法
    normalized = _DATE_SEPARATOR_PATTERN.sub(r"\1-\2-\3", text)
    normalized = normalized.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return _DATE_SEPARATOR_PATTERN.sub(r"\1.\2.\3", text)

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_LEDGER_TIMEZONE)
    return parsed.strftime("%Y.%m.%d")


def _format_start_date(item: dict[str, Any]) -> str:
    """"启动日期"取同步自飞书的启动日期，缺失时退回记录创建日期。"""
    return _format_date(item.get("expected_completion_date") or item.get("created_at"))


def _format_qa_confirmer(item: dict[str, Any]) -> str:
    """合并"QA质量员/日期"列：姓名与确认日期连写，与台账一致。"""
    name = _safe_str(item.get("qa_confirmer")).strip()
    confirmed_at = _format_date(item.get("qa_confirm_date"))
    return f"{name}{confirmed_at}"


def _format_closure_date(item: dict[str, Any]) -> str:
    """关闭日期；效果评价仍在进行中的记录按台账写法记为"进行中"。

    台账把未关闭记录的关闭日期写成"进行中"，本地该列是日期字段无法保存文本，
    因此以效果评估结果为准回填同一写法，其余空值保持为空。
    """
    closed_at = _format_date(item.get("closure_date"))
    if closed_at:
        return closed_at
    if _safe_str(item.get("evaluation_result")).strip() == "进行中":
        return "进行中"
    return ""


def _row_values(item: dict[str, Any]) -> list[str]:
    """按台账 9 列顺序取值。

    编号、启动日期、事件部门、涉及产品、来源编号、CAPA简述、
    CAPA效果评估、关闭日期、QA质量员/日期。
    """
    return [
        _safe_str(item.get("capa_code")).strip(),
        _format_start_date(item),
        _safe_str(item.get("department")).strip(),
        _safe_str(item.get("affected_product")).strip(),
        _safe_str(item.get("source_code")).strip(),
        _safe_str(item.get("title")).strip(),
        _safe_str(item.get("evaluation_result")).strip(),
        _format_closure_date(item),
        _format_qa_confirmer(item),
    ]


def _clear_text_in_paragraph(paragraph_elem: Any) -> None:
    for run_elem in paragraph_elem.findall(qn("w:r")):
        for text_elem in run_elem.findall(qn("w:t")):
            text_elem.text = ""


def _set_cell_text(cell_elem: Any, text: str) -> None:
    """把文本写入单元格，按换行拆分为段落，保留模板首段的段落与字符格式。

    段落数不足时深拷贝首段补齐，多余段落删除，避免残留模板内容。
    """
    lines = (text or "").split("\n")
    paragraph_elems = cell_elem.findall(qn("w:p"))

    if not paragraph_elems:
        paragraph_elem = cell_elem.makeelement(qn("w:p"), {})
        cell_elem.append(paragraph_elem)
        paragraph_elems = [paragraph_elem]

    while len(paragraph_elems) > len(lines):
        last_elem = paragraph_elems[-1]
        last_elem.getparent().remove(last_elem)
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


def _strip_auto_numbering(row_elem: Any) -> None:
    """移除行内段落的 w:numPr（Word 自动编号）。

    模板部分段落的编号来自自动编号；逐行复制的行共用同一 numId，会跨行连续
    编号。导出按表格存储的文本呈现，编号一律由文本自身承载。
    """
    for paragraph_elem in row_elem.iter(qn("w:p")):
        ppr_elem = paragraph_elem.find(qn("w:pPr"))
        if ppr_elem is None:
            continue
        num_pr = ppr_elem.find(qn("w:numPr"))
        if num_pr is not None:
            ppr_elem.remove(num_pr)


def _remove_perm_markers(row_elem: Any) -> None:
    """移除拷贝行内的 permStart/permEnd，避免与模板表头的可编辑标记重复。"""
    for perm_elem in list(row_elem.iter(qn("w:permStart"))):
        perm_elem.getparent().remove(perm_elem)
    for perm_elem in list(row_elem.iter(qn("w:permEnd"))):
        perm_elem.getparent().remove(perm_elem)


def _write_run_text(text_elem: Any, text: str) -> None:
    """写入 run 文本，并按需声明 xml:space 以保留首尾空白。"""
    text_elem.text = text
    if text != text.strip():
        text_elem.set(qn("xml:space"), "preserve")


def _set_cover_period_end_date(doc: Any, end_date: date) -> None:
    """把首页日期区的截止日期写成导出当天（期间起始日期保持模板值）。

    模板日期区形如"2026年 01 月 01 日－ 2026 年 06 月 15 日"，只改写
    分隔符之后的年/月/日，并保留原有的空白与字号格式。
    """
    replacements = [
        f"{end_date.year:04d}",
        f"{end_date.month:02d}",
        f"{end_date.day:02d}",
    ]

    for paragraph_elem in doc.element.body.findall(qn("w:p")):
        text = "".join(t.text or "" for t in paragraph_elem.iter(qn("w:t")))
        if "－" not in text or "年" not in text or "月" not in text:
            continue

        run_elems = paragraph_elem.findall(qn("w:r"))
        separator_index = next(
            (
                index
                for index, run_elem in enumerate(run_elems)
                if "－" in "".join(t.text or "" for t in run_elem.findall(qn("w:t")))
            ),
            None,
        )
        if separator_index is None:
            continue

        cursor = 0

        def _replace(match: re.Match[str]) -> str:
            nonlocal cursor
            if cursor >= len(replacements):
                return match.group(0)
            value = replacements[cursor]
            cursor += 1
            return value

        for run_elem in run_elems[separator_index + 1 :]:
            if cursor >= len(replacements):
                break
            for text_elem in run_elem.findall(qn("w:t")):
                _write_run_text(
                    text_elem, _DATE_DIGITS_PATTERN.sub(_replace, text_elem.text or "")
                )
        return


def generate_capa_ledger_export_docx(
    items: list[dict[str, Any]], end_date: date | None = None
) -> bytes:
    """Render CAPA ledger records into the local Word template.

    end_date 为首页日期区的截止日期；未传入时取国内当天。
    """
    doc = Document(str(_TEMPLATE_PATH))
    if not doc.tables:
        raise AppException(message="CAPA台账模板中未找到表格")

    table = doc.tables[0]
    table_element = table._tbl
    row_elements = table_element.findall(qn("w:tr"))
    if len(row_elements) < 2:
        raise AppException(message="CAPA台账模板缺少可复用的数据行")

    # 首个数据行作为格式模板行（保留列宽、字体与单元格格式）
    template_row = copy.deepcopy(row_elements[1])

    # 删除模板数据行；表头行与其可编辑标记保持原样
    for row_elem in list(row_elements[1:]):
        table_element.remove(row_elem)

    for item in items:
        row_elem = copy.deepcopy(template_row)
        _remove_perm_markers(row_elem)
        _strip_auto_numbering(row_elem)
        table_element.append(row_elem)

        cell_elems = row_elem.findall(qn("w:tc"))
        for cell_index, value in enumerate(_row_values(item)):
            if cell_index >= len(cell_elems):
                break
            _set_cell_text(cell_elems[cell_index], value)

    # 首页日期区的截止日期跟随本次导出时间
    _set_cover_period_end_date(doc, end_date or datetime.now(_LEDGER_TIMEZONE).date())

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
