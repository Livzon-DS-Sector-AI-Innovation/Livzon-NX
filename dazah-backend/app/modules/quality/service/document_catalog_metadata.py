"""从页眉和正文封面提取元数据，保留表格标签和值的位置关系。"""

import re
import unicodedata
from typing import Any

CODE_VALUE = r"[A-Za-z]{2,8}[0-9]*(?:-[A-Za-z0-9（）()]+)+[/_-]\d{1,3}"
DATE_VALUE = r"\d{4}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?"
LABELS = {
    "code": r"(?:文件\s*编[号码]|(?:Document|File)\s*(?:No\.?|Number|Code))",
    "date": r"(?:生效\s*日期|Effective\s*Date)",
    "name": r"(?:文件\s*名称|(?:Document|File)\s*(?:Name|Title))",
}
CANONICAL = {"code": "文件编号", "date": "生效日期", "name": "文件名称"}
BOUNDARY = re.compile(
    r"^(?:目\s*录|修订|修改记录|变更历史|Revision|[一二三四五六七八九十0-9]+[.、]?\s*(?:目的|范围|职责|程序|产品概况))",
    re.I,
)


def _visible_text(element: Any) -> str:
    """读取修订后的可见文字，包括插入文字，排除删除文字；不修改 XML。"""
    pieces: list[str] = []
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for node in element.iter():
        if any(
            parent.tag in {namespace + "del", namespace + "moveFrom"}
            for parent in node.iterancestors()
        ):
            continue
        if node.tag == namespace + "t":
            pieces.append(node.text or "")
        elif node.tag in {namespace + "p", namespace + "br", namespace + "tab"}:
            pieces.append("\n")
    return "".join(pieces).strip()


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("–", "-").replace("－", "-")
    text = re.sub(r"(?<=\d)[ \t]+(?=\d)", "", text)
    return re.sub(r"[ \t]*([/_-])[ \t]*", r"\1", text)


def extract_field(text: str, field: str) -> str:
    """仅接受明确标签后的值；不同来源发生冲突时不猜测。"""
    value = {"code": CODE_VALUE, "date": DATE_VALUE, "name": r"[^\n|]+"}[field]
    pattern = (
        rf"{LABELS[field]}[\s*:：|/]*(?:{LABELS[field]}[\s*:：|/]*)?"
        rf"({value})(?![\dA-Za-z])"
    )
    if field == "name":
        pattern = rf"{LABELS[field]}[ \t*:：|]+([^\n|]+)"
    values = {v.strip() for v in re.findall(pattern, _clean(text), re.I)}
    return next(iter(values)) if len(values) == 1 else ""


def _label(text: str, field: str) -> bool:
    lines = [line.strip() for line in _clean(text).splitlines() if line.strip()]
    # 中文标签独立成行时，它本身足以确定字段；旧格式的英文翻译可能缺字。
    if (
        lines
        and re.fullmatch(LABELS[field], lines[0], re.I)
        and re.search(r"[\u4e00-\u9fff]", lines[0])
        and all(not re.search(r"[\d\u4e00-\u9fff]", line) for line in lines[1:])
    ):
        return True
    remaining = re.sub(LABELS[field], "", _clean(text), flags=re.I)
    return bool(text.strip()) and not remaining.strip(" \t\n*:：|/")


def _value(text: str, field: str) -> str:
    text = _clean(text).strip()
    if any(re.search(pattern, text, re.I) for pattern in LABELS.values()):
        return ""
    if field == "name":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if re.fullmatch(CODE_VALUE, text, re.I):
            return ""
        return lines[0] if lines and len(lines[0]) <= 500 else ""
    if field == "code":
        text = re.sub(r"\s+", "", text)
    pattern = CODE_VALUE if field == "code" else DATE_VALUE
    return text if re.fullmatch(pattern, text, re.I) else ""


def _table_fields(table: Any, row_limit: int | None = None) -> list[str]:
    """支持右侧值、下一行同列值及合并单元格，不跨字段拼接。"""
    rows = list(table.rows)[:row_limit]
    fields = []
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row.cells):
            cell_text = _visible_text(cell._tc)
            for field, label in CANONICAL.items():
                inline = extract_field(cell_text, field)
                if inline:
                    fields.append(f"{label}: {inline}")
                if not _label(cell_text, field):
                    continue
                candidates = []
                # 跳过合并单元格产生的重复引用。
                for right in row.cells[ci + 1 :]:
                    if right._tc is not cell._tc:
                        candidates.append(_visible_text(right._tc))
                        break
                if ri + 1 < len(rows) and ci < len(rows[ri + 1].cells):
                    below = rows[ri + 1].cells[ci]
                    if below._tc is not cell._tc:
                        candidates.append(_visible_text(below._tc))
                for candidate in candidates:
                    value = _value(candidate, field)
                    if value:
                        fields.append(f"{label}: {value}")
    return fields


def docx_metadata_text(doc: Any) -> str:
    """按文档顺序读取封面；遇到正文/目录/修订历史即停止，不改原文档。"""
    from docx.table import Table

    fields = []
    cover_lines: list[str] = []
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for child in list(doc.element.body)[:60]:
        if any(
            node.get(namespace + "val") not in {"0", "false"}
            for node in child.iter(namespace + "pageBreakBefore")
        ):
            break
        if child.tag.endswith("}p"):
            text = _visible_text(child)
            if BOUNDARY.match(text):
                break
            cover_lines.extend(
                line.strip() for line in text.splitlines() if line.strip()
            )
            for field, label in CANONICAL.items():
                value = extract_field(text, field)
                if value:
                    fields.append(f"{label}: {value}")
        elif child.tag.endswith("}tbl"):
            table = Table(child, doc)
            # 有些旧版 Word 将分发页、正文和修订历史连在同一张表内。
            boundary_row = None
            for index, row in enumerate(table.rows):
                texts = [_visible_text(cell._tc) for cell in row.cells]
                if texts and (
                    BOUNDARY.match(" ".join(texts))
                    or re.fullmatch(r"\d+(?:[.、]\d*)*", texts[0])
                ):
                    boundary_row = index
                    break
            fields.extend(_table_fields(table, boundary_row))
            if boundary_row is not None:
                break
        if any(
            node.tag in {namespace + "lastRenderedPageBreak", namespace + "sectPr"}
            or (node.tag == namespace + "br" and node.get(namespace + "type") == "page")
            for node in child.iter()
        ):
            break
    # 只读取首页实际使用的页眉；首页不同开启时不混入后续页的常规页眉。
    for section in doc.sections[:1]:
        for header in (
            section.first_page_header
            if section.different_first_page_header_footer
            else section.header,
        ):
            if not header._has_definition:
                continue
            header_start = len(fields)
            for field in ("code", "date"):
                value = extract_field(_visible_text(header._element), field)
                if value:
                    fields.append(f"{CANONICAL[field]}: {value}")
            for paragraph in header.paragraphs:
                for field, label in CANONICAL.items():
                    value = extract_field(_visible_text(paragraph._p), field)
                    if value:
                        fields.append(f"{label}: {value}")
            # Word/WPS 可将页眉表格放在文本框中，header.tables 不包含这类后代。
            for element in header._element.xpath(".//w:tbl"):
                fields.extend(_table_fields(Table(element, header)))
            if not any(line.startswith("文件编号:") for line in fields[header_start:]):
                # 有些页眉只印编号，或浮动文本框使标签和值顺序交错。
                # 仅接受页眉中独占一行的完整版本编号；多个候选仍保留为冲突。
                for line in _visible_text(header._element).splitlines():
                    code = _value(line, "code")
                    if code and not re.match(r"(?:QR|APP)\d*-", code, re.I):
                        fields.append(f"文件编号: {code}")
    # 工艺规程封面标题通常没有“文件名称”标签，位于编号前。
    if not any(line.startswith("文件名称:") for line in fields):
        for index, text in enumerate(cover_lines):
            if extract_field(text, "code"):
                for title in reversed(cover_lines[:index]):
                    if re.search(r"[\u4e00-\u9fff]", title) and not re.search(
                        r"[:：]|日期|签名|颁发|批准|起草|审核", title
                    ):
                        fields.append(f"文件名称: {title}")
                        break
                break
    return "\n".join(dict.fromkeys(fields))
