from __future__ import annotations

import io
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from docx import Document
from docx.oxml.ns import qn

from app.modules.quality.service import deviation_ledger_export

_LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _body_paragraph_texts(doc: Document) -> list[str]:
    return [
        "".join(t.text or "" for t in paragraph.iter(qn("w:t")))
        for paragraph in doc.element.body.findall(qn("w:p"))
    ]


def _cover_edit_regions(doc: Document) -> list[tuple[str, str]]:
    """返回正文段落内的可编辑区域 (perm id, 区域文本)。

    仅统计起止标记位于同一段落内的区域，即模板首页日期区/年份抬头的写法。
    """
    regions: list[tuple[str, str]] = []
    for paragraph in doc.element.body.findall(qn("w:p")):
        open_ids: list[str] = []
        buffer: dict[str, list[str]] = {}
        for child in paragraph:
            tag = child.tag.split("}")[-1]
            if tag == "permStart":
                perm_id = child.get(qn("w:id")) or ""
                open_ids.append(perm_id)
                buffer.setdefault(perm_id, [])
            elif tag == "permEnd":
                perm_id = child.get(qn("w:id")) or ""
                if perm_id in open_ids:
                    open_ids.remove(perm_id)
                    regions.append((perm_id, "".join(buffer.pop(perm_id, []))))
            elif tag == "r":
                text = "".join(t.text or "" for t in child.findall(qn("w:t")))
                for perm_id in open_ids:
                    buffer[perm_id].append(text)
    return regions


def _cover_date_numbers(doc: Document) -> list[str]:
    """返回首页日期区可编辑区域内的数字（年/月/日 × 起始/截止）。"""
    return [
        text.strip() for _, text in _cover_edit_regions(doc) if text.strip()
    ]


def _row_has_edit_region(row: Any) -> bool:
    tags = {child.tag.split("}")[-1] for child in row._tr}
    return "permStart" in tags and "permEnd" in tags


def _export(items: list[dict[str, Any]], end_date: date | None = None) -> Document:
    docx_bytes = deviation_ledger_export.generate_deviation_ledger_export_docx(
        items, end_date
    )
    return Document(io.BytesIO(docx_bytes))


def test_generate_deviation_ledger_export_docx_uses_template_layout() -> None:
    doc = _export(
        [
            {
                "deviation_code": "PC-2607001",
                "affected_items": "原料A",
                "batch_number": "BATCH-001",
                "description": "洁净区压差异常",
                "has_occurred_before": True,
                "root_cause_analysis": "空调机组波动",
                "level": "major",
                "investigation_completed_at": datetime(2026, 7, 4, 10, 30, tzinfo=UTC),
                "corrective_actions": "复核空调系统参数",
                "material_disposition": "隔离待评估",
                "status": "closed",
            },
            {
                "deviation_code": "PC-2607002",
                "product_batch": "原料B\nBATCH-002",
                "description": "称量记录缺页",
                "has_occurred_before": False,
                "root_cause_analysis": "记录回收不完整",
                "level": "微小",
                "investigation_completed_at": "2026-07-05T08:00:00+00:00",
                "corrective_actions": "补充培训",
                "material_disposition": "已补录",
                "is_closed": False,
            },
        ]
    )

    assert len(doc.tables) == 1

    table = doc.tables[0]
    assert len(table.rows) == 3
    assert table.cell(1, 0).text == "1"
    assert table.cell(1, 1).text == "PC-2607001"
    assert table.cell(1, 2).text == "原料A\nBATCH-001"
    assert table.cell(1, 6).text == "重大"
    assert table.cell(1, 7).text == "2026.07.04"
    assert table.cell(1, 10).text == "是"

    assert table.cell(2, 0).text == "2"
    assert table.cell(2, 1).text == "PC-2607002"
    assert table.cell(2, 2).text == "原料B\nBATCH-002"
    assert table.cell(2, 6).text == "微小"
    assert table.cell(2, 7).text == "2026.07.05"
    assert table.cell(2, 10).text == "否"

    # 数据行仍为可编辑区域，导出后可以直接补填
    assert all(_row_has_edit_region(row) for row in table.rows[1:])


def _occurred_cell_lines(doc: Document, row_index: int) -> list[tuple[str, str]]:
    """返回 [(勾选标记, 文本)]，标记为 checked/unchecked/none。

    勾选标记不是文字：模板用 Wingdings 2 符号 run 表示已勾选，
    用文字方框 run 表示未勾选，因此必须按 run 判断而不是按 cell.text。
    """
    cell = doc.tables[0]._tbl.findall(qn("w:tr"))[row_index].findall(qn("w:tc"))[4]
    lines: list[tuple[str, str]] = []
    for paragraph in cell.findall(qn("w:p")):
        marker = "none"
        parts: list[str] = []
        for run_elem in paragraph.findall(qn("w:r")):
            sym = run_elem.find(qn("w:sym"))
            if sym is not None:
                marker = "checked"
                continue
            text = "".join(t.text or "" for t in run_elem.findall(qn("w:t")))
            if text.strip() == "□":
                marker = "unchecked"
                continue
            if text:
                parts.append(text)
        lines.append((marker, "".join(parts)))
    return lines


def test_occurred_column_keeps_template_checkbox_markers() -> None:
    doc = _export(
        [
            {
                "deviation_code": "PC-2607001",
                "has_occurred_before": True,
                "previous_occurrence_code": "PC-2502001\nPC-2502003",
                "status": "open",
            },
            {
                "deviation_code": "PC-2607002",
                "has_occurred_before": True,
                "status": "open",
            },
            {
                "deviation_code": "PC-2607003",
                "has_occurred_before": False,
                "status": "open",
            },
            {
                "deviation_code": "PC-2607004",
                "has_occurred_before": None,
                "status": "open",
            },
        ]
    )

    assert _occurred_cell_lines(doc, 1) == [
        ("checked", "是 编号：PC-2502001"),
        ("none", "PC-2502003"),
        ("unchecked", "否"),
    ]
    assert _occurred_cell_lines(doc, 2) == [
        ("checked", "是 编号："),
        ("unchecked", "否"),
    ]
    # 页面把未知与"未发生"呈现为同一种勾选状态
    expected_not_occurred = [("unchecked", "是 编号："), ("checked", "否")]
    assert _occurred_cell_lines(doc, 3) == expected_not_occurred
    assert _occurred_cell_lines(doc, 4) == expected_not_occurred


def test_occurred_column_has_no_orphan_checkbox_symbols() -> None:
    doc = _export(
        [
            {"deviation_code": "A", "has_occurred_before": True},
            {"deviation_code": "B", "has_occurred_before": False},
        ]
    )

    # 每行只保留一个勾选符号（勾在"是"或"否"上），不残留模板符号
    symbols = [
        sym
        for sym in doc.element.body.iter(qn("w:sym"))
        if sym.get(qn("w:font")) == "Wingdings 2"
    ]
    assert len(symbols) == 2
    assert [line[0] for line in _occurred_cell_lines(doc, 1)] == [
        "checked",
        "unchecked",
    ]
    assert [line[0] for line in _occurred_cell_lines(doc, 2)] == [
        "unchecked",
        "checked",
    ]


def test_cover_date_keeps_editable_regions_and_ends_on_export_date() -> None:
    doc = _export(
        [{"deviation_code": "PC-2607001", "has_occurred_before": False}],
        date(2026, 9, 23),
    )

    numbers = _cover_date_numbers(doc)
    # 期间起始日期保持模板值，截止日期为导出当天；年/月/日都落在可编辑区域内
    assert numbers[:6] == ["2026", "01", "01", "2026", "09", "23"]


def test_cover_date_defaults_to_local_export_day() -> None:
    before = datetime.now(_LOCAL_TIMEZONE).date()
    doc = _export([{"deviation_code": "PC-2607001"}])
    after = datetime.now(_LOCAL_TIMEZONE).date()

    year, month, day = (int(value) for value in _cover_date_numbers(doc)[3:6])
    exported = date(year, month, day)
    assert before <= exported <= after


def test_export_document_is_titled_deviation_ledger() -> None:
    doc = _export([{"deviation_code": "PC-2607001"}])

    paragraphs = _body_paragraph_texts(doc)
    assert "偏 差 台 账" in paragraphs
    assert "偏差台账" in paragraphs
    assert all("登记表" not in text for text in paragraphs)
