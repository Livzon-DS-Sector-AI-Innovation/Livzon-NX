"""Generate deviation ledger exports from a local Word template."""

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
    Path(__file__).resolve().parent.parent / "templates" / "偏差登记表-模板.docx"
)

# 台账日期区按国内工作日口径取"当天"
_LEDGER_TIMEZONE = ZoneInfo("Asia/Shanghai")


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
    """通用是/否转换（用于是否关闭等列）。"""
    if isinstance(value, bool):
        return "是" if value else "否"

    text = _safe_str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "是", "已关闭", "closed"}:
        return "是"
    if text in {"0", "false", "no", "n", "否", "未关闭", "draft", "open"}:
        return "否"
    return ""


# 模板勾选写法：已勾选为 Wingdings 2 符号（0052），未勾选为文字方框
_CHECKED_MARKER_FONT = "Wingdings 2"
_CHECKED_MARKER_CHAR = "0052"
_UNCHECKED_MARKER_TEXT = "□"
_MARKER_CHARS = {"checked": "☑", "unchecked": "□", "none": ""}


def _run_text(run_elem: Any) -> str:
    return "".join(t.text or "" for t in run_elem.findall(qn("w:t")))


def _is_checked_marker_run(run_elem: Any) -> bool:
    sym = run_elem.find(qn("w:sym"))
    if sym is None:
        return False
    return sym.get(qn("w:font")) == _CHECKED_MARKER_FONT and (
        (sym.get(qn("w:char")) or "").upper() == _CHECKED_MARKER_CHAR
    )


def _is_unchecked_marker_run(run_elem: Any) -> bool:
    if run_elem.find(qn("w:sym")) is not None:
        return False
    return _run_text(run_elem).strip() == _UNCHECKED_MARKER_TEXT


def _set_run_text(run_elem: Any, text: str) -> None:
    """写入 run 文本，只保留一个 w:t，并按需声明 xml:space。"""
    text_elems = run_elem.findall(qn("w:t"))
    if not text_elems:
        text_elem = run_elem.makeelement(qn("w:t"), {})
        run_elem.append(text_elem)
        text_elems = [text_elem]
    for extra_elem in text_elems[1:]:
        run_elem.remove(extra_elem)

    text_elems[0].text = text
    if text != text.strip():
        text_elems[0].set(qn("xml:space"), "preserve")


def _occurred_column_lines(
    has_occurred_before: Any, previous_occurrence_code: Any
) -> list[tuple[str, str]]:
    """按台账勾选写法拆分"偏差是否曾发生"列：每行返回 (标记, 文本)。

    未发生/未知：'□是 编号：' / '☑否'；曾发生的首行勾选"是"并带编号，
    其余编号各占一行（不带标记），末行为未勾选的'□否'。
    """
    code_lines = [
        line.strip()
        for line in _safe_str(previous_occurrence_code).splitlines()
        if line.strip()
    ]
    if has_occurred_before is True:
        first_line = f"是 编号：{code_lines[0]}" if code_lines else "是 编号："
        lines: list[tuple[str, str]] = [("checked", first_line)]
        lines.extend(("none", line) for line in code_lines[1:])
        lines.append(("unchecked", "否"))
        return lines
    # 页面把未发生与未知呈现为同一种勾选状态，导出保持同一口径
    return [("unchecked", "是 编号："), ("checked", "否")]


def _occurred_plain_text(
    has_occurred_before: Any, previous_occurrence_code: Any
) -> str:
    """模板勾选符号缺失时的兜底文本写法。"""
    return "\n".join(
        f"{_MARKER_CHARS[marker]}{text}"
        for marker, text in _occurred_column_lines(
            has_occurred_before, previous_occurrence_code
        )
    )


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


# 导出字体要求：中文（eastAsia）宋体，数字/英文（ascii/hAnsi/cs）Times New Roman
_REQUIRED_FONT_ATTRS = (
    ("w:ascii", "Times New Roman"),
    ("w:hAnsi", "Times New Roman"),
    ("w:eastAsia", "宋体"),
    ("w:cs", "Times New Roman"),
)


def _ensure_run_fonts(run_elem: Any, paragraph_elem: Any) -> None:
    """保证承载文本的 run 满足导出字体要求（宋体 + Times New Roman）。

    run 无 rPr 时优先继承段落 rPr（保留模板字号等格式），
    再强制 rFonts 四属性符合导出字体要求，避免依赖文档默认样式。
    """
    rpr_elem = run_elem.find(qn("w:rPr"))
    if rpr_elem is None:
        ppr_elem = paragraph_elem.find(qn("w:pPr"))
        src_rpr = ppr_elem.find(qn("w:rPr")) if ppr_elem is not None else None
        rpr_elem = (
            copy.deepcopy(src_rpr)
            if src_rpr is not None
            else run_elem.makeelement(qn("w:rPr"), {})
        )
        run_elem.insert(0, rpr_elem)
    fonts_elem = rpr_elem.find(qn("w:rFonts"))
    if fonts_elem is None:
        fonts_elem = rpr_elem.makeelement(qn("w:rFonts"), {})
        rpr_elem.insert(0, fonts_elem)
    for attr, value in _REQUIRED_FONT_ATTRS:
        fonts_elem.set(qn(attr), value)


def _remove_symbol_runs(paragraph_elem: Any) -> None:
    """移除符号 run（w:sym，如模板勾选符号），避免残留符号混进新文本。"""
    for run_elem in list(paragraph_elem.findall(qn("w:r"))):
        if run_elem.find(qn("w:sym")) is not None:
            paragraph_elem.remove(run_elem)


def _clear_text_in_paragraph(paragraph_elem: Any) -> None:
    _remove_symbol_runs(paragraph_elem)
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
        _remove_symbol_runs(paragraph_elem)
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
        _ensure_run_fonts(run_elems[0], paragraph_elem)


def _set_occurred_cell(
    cell_elem: Any, has_occurred_before: Any, previous_occurrence_code: Any
) -> None:
    """填充"偏差是否曾发生"列，沿用模板的勾选符号。

    模板用两种标记：已勾选是 Wingdings 2 勾选框 run，未勾选是文字方框 run。
    直接写文本会留下孤立符号（符号跑到编号前面），因此按行重建段落，
    由标记类型决定挂哪个 run。
    """
    paragraph_elems = cell_elem.findall(qn("w:p"))
    base_paragraph = copy.deepcopy(paragraph_elems[0]) if paragraph_elems else None
    checked_run = next(
        (
            copy.deepcopy(run_elem)
            for run_elem in cell_elem.iter(qn("w:r"))
            if _is_checked_marker_run(run_elem)
        ),
        None,
    )
    unchecked_run = next(
        (
            copy.deepcopy(run_elem)
            for run_elem in cell_elem.iter(qn("w:r"))
            if _is_unchecked_marker_run(run_elem)
        ),
        None,
    )
    text_run = next(
        (
            copy.deepcopy(run_elem)
            for run_elem in cell_elem.iter(qn("w:r"))
            if run_elem.find(qn("w:sym")) is None
            and not _is_unchecked_marker_run(run_elem)
            and run_elem.findall(qn("w:t"))
        ),
        None,
    )

    if (
        base_paragraph is None
        or checked_run is None
        or unchecked_run is None
        or text_run is None
    ):
        # 模板勾选符号结构变化时退回纯文本写法
        _set_cell_text(
            cell_elem,
            _occurred_plain_text(has_occurred_before, previous_occurrence_code),
        )
        return

    for paragraph_elem in list(paragraph_elems):
        cell_elem.remove(paragraph_elem)

    for marker, text in _occurred_column_lines(
        has_occurred_before, previous_occurrence_code
    ):
        new_paragraph = copy.deepcopy(base_paragraph)
        for run_elem in new_paragraph.findall(qn("w:r")):
            new_paragraph.remove(run_elem)

        if marker == "checked":
            new_paragraph.append(copy.deepcopy(checked_run))
        elif marker == "unchecked":
            new_paragraph.append(copy.deepcopy(unchecked_run))

        new_run = copy.deepcopy(text_run)
        _set_run_text(new_run, text)
        new_paragraph.append(new_run)
        cell_elem.append(new_paragraph)


def _strip_auto_numbering(elem: Any) -> None:
    """移除元素内各段落的 w:numPr（Word 自动编号）。

    模板数据行单元格文本为空、部分列依赖自动编号；
    拷贝行写入手动文本后，Word 会叠加渲染自动编号，导致导出内容重复。
    """
    for p_elem in elem.iter(qn("w:p")):
        ppr_elem = p_elem.find(qn("w:pPr"))
        if ppr_elem is not None:
            num_pr = ppr_elem.find(qn("w:numPr"))
            if num_pr is not None:
                ppr_elem.remove(num_pr)


def _find_max_perm_id(doc: Any) -> int:
    """查找文档中已有的最大 permStart/permEnd id（标题区 id=0/1 等）。"""
    max_id = -1
    body = doc.element.body
    for perm_elem in body.iter(qn("w:permStart")):
        id_str = perm_elem.get(qn("w:id"))
        if id_str:
            max_id = max(max_id, int(id_str))
    for perm_elem in body.iter(qn("w:permEnd")):
        id_str = perm_elem.get(qn("w:id"))
        if id_str:
            max_id = max(max_id, int(id_str))
    return max_id


def _remove_table_perm_markers(doc: Any) -> None:
    """移除表格数据区的 permStart/permEnd，保留模板正文段落的标记。

    模板首页日期区、年份抬头的 permStart/permEnd 是 Word/飞书中的可编辑
    区域（渲染为黄色底纹），导出件必须原样保留；表格数据区的标记随行重建，
    避免删除数据行后留下无配对的标记。
    """
    body = doc.element.body
    for tag in ("w:permStart", "w:permEnd"):
        for perm_elem in list(body.iter(qn(tag))):
            parent = perm_elem.getparent()
            if parent is None:
                continue
            in_table = any(
                ancestor.tag == qn("w:tbl") for ancestor in perm_elem.iterancestors()
            )
            if in_table or parent.tag != qn("w:p"):
                parent.remove(perm_elem)


def _remove_perm_markers(row_elem: Any) -> None:
    """移除行内所有 permStart/permEnd（直接子级 + 单元格后代）。"""
    for perm_elem in list(row_elem):
        tag = perm_elem.tag.split("}")[-1] if "}" in perm_elem.tag else perm_elem.tag
        if tag in ("permStart", "permEnd"):
            row_elem.remove(perm_elem)
    for perm_elem in list(row_elem.iter(qn("w:permStart"))):
        perm_elem.getparent().remove(perm_elem)
    for perm_elem in list(row_elem.iter(qn("w:permEnd"))):
        perm_elem.getparent().remove(perm_elem)


def _insert_perm_markers(row_elem: Any, perm_id: int) -> None:
    """在行内插入一对 permStart（cell#0 之后）与 permEnd（行尾），标记可编辑范围。"""
    cells = row_elem.findall(qn("w:tc"))
    if not cells:
        return

    perm_start = row_elem.makeelement(
        qn("w:permStart"),
        {
            qn("w:id"): str(perm_id),
            qn("w:edGrp"): "everyone",
        },
    )
    first_cell = cells[0]
    next_sibling = first_cell.getnext()
    if next_sibling is not None:
        next_sibling.addprevious(perm_start)
    else:
        row_elem.append(perm_start)

    perm_end = row_elem.makeelement(
        qn("w:permEnd"),
        {
            qn("w:id"): str(perm_id),
        },
    )
    row_elem.append(perm_end)


_DIGIT_RUN_PATTERN = re.compile(r"^(?P<lead>\s*)(?P<digits>\d+)(?P<trail>\s*)$")


def _write_run_text(text_elem: Any, text: str) -> None:
    """写入 run 文本，并按需声明 xml:space 以保留首尾空白。"""
    text_elem.text = text
    if text != text.strip():
        text_elem.set(qn("xml:space"), "preserve")


def _set_cover_period_end_date(doc: Any, end_date: date) -> None:
    """把首页日期区的截止日期写成导出当天（期间起始日期保持模板值）。

    模板首页日期区形如"2026 年 01 月 01 日－ 2026 年 06 月 15 日"，
    年/月/日各自是只含数字的 run；只改写末尾三组数字，并保留 run 内原有空白。
    """
    for paragraph_elem in doc.element.body.findall(qn("w:p")):
        text = "".join(t.text or "" for t in paragraph_elem.iter(qn("w:t")))
        if "年" not in text or "月" not in text:
            continue

        digit_runs: list[tuple[Any, str, str, str]] = []
        for run_elem in paragraph_elem.findall(qn("w:r")):
            text_elems = run_elem.findall(qn("w:t"))
            if len(text_elems) != 1:
                continue
            match = _DIGIT_RUN_PATTERN.match(text_elems[0].text or "")
            if match is None:
                continue
            digit_runs.append(
                (
                    text_elems[0],
                    match.group("lead"),
                    match.group("digits"),
                    match.group("trail"),
                )
            )

        # 日期区含年/月/日两组共 6 个数字 run，末三组即截止日期
        if len(digit_runs) < 6:
            continue

        for (text_elem, lead, digits, trail), value in zip(
            digit_runs[-3:], (end_date.year, end_date.month, end_date.day)
        ):
            _write_run_text(text_elem, f"{lead}{value:0{len(digits)}d}{trail}")
        return


def _set_enforcement(doc: Any) -> None:
    """确保文档保护强制启用（enforcement=1）。"""
    settings_elem = doc.element.body.getparent().find(".//" + qn("w:settings"))
    if settings_elem is None:
        return
    protection = settings_elem.find(qn("w:documentProtection"))
    if protection is not None:
        protection.set(qn("w:enforcement"), "1")


def generate_deviation_ledger_export_docx(
    items: list[dict[str, Any]], end_date: date | None = None
) -> bytes:
    """Render deviation ledger records into the local Word template.

    end_date 为首页日期区的截止日期；未传入时取国内当天。
    """
    doc = Document(str(_TEMPLATE_PATH))
    if not doc.tables:
        raise AppException(message="偏差台账模板中未找到表格")

    table = doc.tables[0]
    table_element = table._tbl
    row_elements = table_element.findall(qn("w:tr"))
    if len(row_elements) < 2:
        raise AppException(message="偏差台账模板缺少可复用的数据行")

    # 模板数据行带自动编号，先整体清理，避免导出内容重复渲染
    _strip_auto_numbering(table_element)

    # 先记录模板中已有的最大 perm id（首页日期区 1-6、年份抬头 7、数据区 8），
    # 新 id 从其后递增
    max_perm_id = _find_max_perm_id(doc)

    # 找到第一个数据行作为模板行
    template_row = copy.deepcopy(row_elements[1])

    # 删除所有数据行（保留表头行）
    for row_elem in list(row_elements[1:]):
        table_element.remove(row_elem)

    # 清除表格数据区的 permStart/permEnd（表级残留），首页日期等正文可编辑区保留
    _remove_table_perm_markers(doc)

    for index, item in enumerate(items, start=1):
        row_elem = copy.deepcopy(template_row)

        # 移除拷贝行中的 permStart/permEnd 标记
        _remove_perm_markers(row_elem)

        table_element.append(row_elem)
        cell_elems = row_elem.findall(qn("w:tc"))

        values = [
            str(index),
            _safe_str(item.get("deviation_code")).strip(),
            _build_product_batch(item),
            _safe_str(item.get("description") or item.get("title")).strip(),
            None,  # 勾选列单独处理：需要保留模板的勾选符号 run
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
            if cell_index >= len(cell_elems) or value is None:
                continue
            _set_cell_text(cell_elems[cell_index], value)

        if len(cell_elems) > 4:
            _set_occurred_cell(
                cell_elems[4],
                item.get("has_occurred_before"),
                item.get("previous_occurrence_code"),
            )

        # 为拷贝行插入新的 permStart/permEnd 标记（唯一 id）
        max_perm_id += 1
        _insert_perm_markers(row_elem, max_perm_id)

    # 首页日期区的截止日期跟随本次导出时间
    _set_cover_period_end_date(doc, end_date or datetime.now(_LEDGER_TIMEZONE).date())

    # 确保文档保护启用
    _set_enforcement(doc)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
