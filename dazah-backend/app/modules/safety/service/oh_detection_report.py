"""职业健康检测报告导入：PDF 解析引擎与导入/查询服务。

解析策略（与仓库 LLM 边界一致）：
1. pdfplumber 网格级提取表格（数字不会幻觉）；
2. 已知版式走确定性规则映射（silica / dust / MAC / TWA-STEL /
   noise / field / heat）；
3. 未知版式调用 ``llm_client.chat_json`` 兜底，输出经 Pydantic 草稿
   校验与「数字回查」（数值必须能在源表格单元格中找到）；
4. LLM 未配置时未知版式表跳过并告警，导入不因此整体失败。
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.core.llm import llm_client
from app.core.llm.exceptions import LLMConfigError, LLMOutputError
from app.modules.safety.models import (
    OhDetectionReport,
    OhDetectionResult,
    OhHazardMonitor,
)
from app.modules.safety.schemas.oh_detection_reports import (
    OhDetectionParsePreview,
    OhDetectionResultDraft,
    OhDetectionTableSummary,
)
from app.platform.audit.service import record_audit_log

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 30 * 1024 * 1024
_ALLOWED_EXT = ".pdf"
_UPLOAD_DIR = os.path.join("uploads", "safety", "oh-detection")
# 同一份 PDF「预览 → 确认导入」复用解析结果，避免 LLM 二次调用不确定性
_PARSE_CACHE_MAX = 16
_PARSE_CACHE: OrderedDict[str, ParsedReport] = OrderedDict()
# 单次导入 LLM 兜底表格数上限（防 200 页全未知版式时雪崩）
_LLM_FALLBACK_TABLE_LIMIT = 20

_TABLE_CAPTION_RE = re.compile(r"表\s*(\d+[-–]\d+)")
_REPORT_NO_RE = re.compile(r"\b([A-Z][A-Z0-9]{0,11}(?:-[A-Z0-9]{1,12}){1,6})\b")
_COMPANY_RE = re.compile(r"^(.{2,40}?公司)")
_REPORT_NAME_RE = re.compile(r"(职业病危害[^\s，,。;；]{0,12}报告|检测报告|评价报告)")
_AGENCY_KEYWORDS = ("检测", "技术", "安全")
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")

# 表头行特征：命中任一关键词视为表头（数据行不含这些词）
_HEADER_KEYWORDS = (
    "序号",
    "PC-TWA",
    "PC-STEL",
    "MAC",
    "结果判定",
    "判定结果",
    "检测项目",
    "取样点",
    "粉尘类别",
    "测量地点",
    "测量值",
    "LEX",
    "职业接触限值",
    "WBGT",
    "接触时间率",
    "体力劳动强度",
    "E（V/m）",
    "C（%）",
    "（mg/m3）",
    "dB（A）",
    "（V/m）",
    "（℃）",
    "（%）",
    "（h）",
)


class OhDetectionParseError(AppException):
    """检测报告解析失败（可预期的 4xx 业务错误）。"""

    def __init__(self, message: str) -> None:
        super().__init__(status_code=422, message=message)


@dataclass
class ParsedTable:
    table_ref: str = ""
    table_title: str = ""
    layout: str = "unknown"
    mode: str = "rules"  # rules / llm / skipped
    rows: list[OhDetectionResultDraft] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skip_reason: str = ""
    # 跨页续表传递的组上下文（噪声/工频电场的岗位组）
    last_group: dict[str, Any] | None = None


@dataclass
class ParsedReport:
    report_no: str = ""
    report_name: str = ""
    company_name: str = ""
    detection_agency: str = ""
    file_sha256: str = ""
    tables: list[ParsedTable] = field(default_factory=list)

    @property
    def parse_mode(self) -> str:
        modes = {t.mode for t in self.tables if t.mode != "skipped"}
        if modes == {"llm"}:
            return "llm"
        if modes == {"rules"}:
            return "rules"
        if modes:
            return "mixed"
        return "rules"

    @property
    def rows(self) -> list[OhDetectionResultDraft]:
        return [row for table in self.tables for row in table.rows]

    @property
    def total_points(self) -> int:
        return len(self.rows)

    @property
    def exceed_points(self) -> int:
        return sum(1 for r in self.rows if r.verdict == "exceed")

    @property
    def noise_post_points(self) -> int:
        return sum(1 for r in self.rows if r.is_noise_post)

    @property
    def skipped_tables(self) -> list[dict[str, str]]:
        return [
            {"table": f"{t.table_ref} {t.table_title}".strip(), "reason": t.skip_reason}
            for t in self.tables
            if t.mode == "skipped"
        ]


@dataclass
class _TableFragment:
    """pdfplumber 从单页提取的表格片段。"""

    caption: str = ""
    grid: list[list[str]] = field(default_factory=list)


@dataclass
class _ExtractedDoc:
    first_page_text: str = ""
    page_texts: list[str] = field(default_factory=list)
    fragments: list[_TableFragment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 单元格与数值处理
# ---------------------------------------------------------------------------


def _clean_cell(value: Any) -> str:
    """清洗单元格：去换行/空白，保留全角符号。"""
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value))


def _is_below_detection(value: str) -> bool:
    return "＜" in value or "<" in value


def _parse_number(value: str) -> float | None:
    match = _NUM_RE.search(value)
    return float(match.group()) if match else None


def _measured(value: str) -> tuple[str, float | None]:
    """检测值原文 + 数值。检出限表达（＜0.44）只保留原文、数值置空。"""
    value = value.strip()
    if not value:
        return "", None
    if _is_below_detection(value):
        return value, None
    return value, _parse_number(value)


def _map_verdict(raw: str) -> tuple[str, bool]:
    """判定文本 → (verdict, 是否噪声作业岗位)。"""
    raw = raw.strip()
    is_noise = "噪声作业岗位" in raw
    if "未超标" in raw:
        return "compliant", is_noise
    if "超标" in raw:
        return "exceed", is_noise
    return "unknown", is_noise


def _parse_limit(raw: str) -> float | None:
    """限值文本 → 数值。取最后一个数字（"40h等效声级85dB(A)"→85）。"""
    matches = _NUM_RE.findall(raw.strip())
    return float(matches[-1]) if matches else None


def _workshop_continuation(cell: str, previous: str) -> str:
    """跨页合并单元格残片（如上一行"102-1车间"、本行"间"）回退为上一个值。"""
    if (
        previous
        and cell
        and len(cell) <= 2
        and cell != previous
        and cell in previous
    ):
        return previous
    return cell


# ---------------------------------------------------------------------------
# PDF 提取（同步，服务层用 asyncio.to_thread 调用）
# ---------------------------------------------------------------------------


def _extract_pdf(pdf_bytes: bytes) -> _ExtractedDoc:
    import pdfplumber

    doc = _ExtractedDoc()
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                doc.page_texts.append(page_text)
                if not doc.first_page_text:
                    doc.first_page_text = page_text
                try:
                    lines = page.extract_text_lines() or []
                except Exception:  # noqa: BLE001 - 个别页面行提取失败不影响表格
                    lines = []
                caption_above: dict[float, str] = {}
                for line in lines:
                    text = str(line.get("text") or "").strip()
                    if _TABLE_CAPTION_RE.search(text):
                        caption_above[float(line.get("bottom", 0.0))] = text
                for table in page.find_tables():
                    grid = table.extract() or []
                    if not grid:
                        continue
                    caption = ""
                    if caption_above:
                        # 取表格上边缘之上最近的表标题行
                        above = [
                            (bottom, text)
                            for bottom, text in caption_above.items()
                            if bottom <= table.bbox[1] + 2
                        ]
                        if above:
                            caption = max(above, key=lambda item: item[0])[1]
                    doc.fragments.append(
                        _TableFragment(
                            caption=caption,
                            grid=[[_clean_cell(c) for c in row] for row in grid],
                        )
                    )
    except OhDetectionParseError:
        raise
    except Exception as exc:  # noqa: BLE001 - pdfplumber 解析失败统一转业务错误
        raise OhDetectionParseError(f"PDF 解析失败：{exc}") from exc
    return doc


def _extract_metadata(doc: _ExtractedDoc) -> tuple[str, str, str, str]:
    """从首页与页脚提取报告编号/名称/企业/机构（尽力识别，可由用户修正）。"""
    report_no = ""
    for text in doc.page_texts[:3]:
        for line in (text or "").splitlines():
            match = _REPORT_NO_RE.search(line)
            if match:
                report_no = match.group(1)
                break
        if report_no:
            break
    first_lines = [
        line.strip()
        for line in (doc.first_page_text or "").splitlines()
        if line.strip()
    ]
    header = first_lines[0] if first_lines else ""
    company = ""
    report_name = ""
    if header:
        name_match = _REPORT_NAME_RE.search(header)
        if name_match:
            report_name = name_match.group(1)
        company_match = _COMPANY_RE.search(header)
        if company_match:
            company = company_match.group(1)
    agency = ""
    for text in doc.page_texts:
        for line in (text or "").splitlines():
            line = line.strip()
            if "有限公司" not in line:
                continue
            if company and company[:6] in line:
                continue
            if any(word in line for word in _AGENCY_KEYWORDS):
                match = re.search(r"([\u4e00-\u9fa5（）()]+有限公司)", line)
                if match:
                    agency = match.group(1)
                    break
        if agency:
            break
    return report_no, report_name, company, agency


# ---------------------------------------------------------------------------
# 版式识别与规则映射
# ---------------------------------------------------------------------------


def _detect_layout(caption: str, header_text: str) -> str:
    if "游离二氧化硅" in caption or "游离二氧化硅" in header_text:
        return "silica"
    if "噪声" in caption or ("测量地点" in header_text and "LEX" in header_text):
        return "noise"
    if "工频电场" in caption or "电场" in header_text:
        return "field"
    if "高温" in caption or "WBGT" in header_text:
        return "heat"
    if "MAC" in header_text:
        return "mac_single"
    if "PC-TWA" in header_text and "PC-STEL" in header_text:
        return "twa_stel"
    if "PC-TWA" in header_text and "PE" in header_text:
        return "dust"
    if "呼尘" in caption or "粉尘" in caption:
        return "dust"
    return "unknown"


def _split_header(grid: list[list[str]]) -> tuple[list[list[str]], list[list[str]]]:
    """切分表头行与数据行：命中表头关键词的行为表头，判定依据行为备注丢弃。"""
    header: list[list[str]] = []
    body: list[list[str]] = []
    for row in grid:
        joined = "".join(row)
        if not joined:
            continue
        if "判定依据" in joined:
            continue
        if any(keyword in joined for keyword in _HEADER_KEYWORDS):
            header.append(row)
        else:
            body.append(row)
    return header, body


def _column_contain(
    header_rows: list[list[str]], include: str, exclude: str = ""
) -> int:
    """按关键词包含匹配定位列（合并表头逐列拼接）。"""
    width = max((len(r) for r in header_rows), default=0)
    for col in range(width):
        cell = "".join((row[col] if col < len(row) else "") for row in header_rows)
        if include and include in cell and (not exclude or exclude not in cell):
            return col
    return -1


def _column_leaf_prefix(header_rows: list[list[str]], prefix: str) -> int:
    """按末行叶子表头前缀定位列（区分 CPE/PE、CSTE/PC-STEL 等包含歧义）。"""
    if not header_rows:
        return -1
    leaf = header_rows[-1]
    width = max((len(r) for r in header_rows), default=0)
    for col in range(width):
        cell = leaf[col] if col < len(leaf) else ""
        if cell.startswith(prefix):
            return col
    # 单行表头时退回包含匹配
    if len(header_rows) == 1:
        return _column_contain(header_rows, prefix)
    return -1


def _column_contain_all(header_rows: list[list[str]], include: str) -> list[int]:
    width = max((len(r) for r in header_rows), default=0)
    result: list[int] = []
    for col in range(width):
        cell = "".join((row[col] if col < len(row) else "") for row in header_rows)
        if include in cell:
            result.append(col)
    return result


def _factor_from_caption(caption: str) -> str:
    """从表标题提取危害因素名（"表 5-4 氢氧化钠检测结果一览表"→氢氧化钠）。"""
    text = _TABLE_CAPTION_RE.sub("", caption)
    text = re.sub(r"(检测结果|测量结果|结果)一览表$", "", text)
    text = re.sub(r"(检测结果|测量结果|结果)$", "", text)
    return text.strip()


def _fill_down(
    rows: list[list[str]], columns: list[int], workshop_col: int = -1
) -> None:
    """纵向合并单元格前向填充（车间/岗位/检测项目等）。"""
    last: dict[int, str] = {}
    for row in rows:
        for col in columns:
            if col >= len(row):
                continue
            cell = row[col]
            if col == workshop_col and last.get(col):
                cell = _workshop_continuation(cell, last[col])
            if cell:
                last[col] = cell
                row[col] = cell
            elif last.get(col):
                row[col] = last[col]


def _draft(
    *,
    table_ref: str,
    table_title: str,
    factor_category: str,
    factor_name: str,
    record_type: str = "point",
    workshop: str = "",
    post: str = "",
    sample_point: str = "",
    measured_value: str = "",
    measured_value_num: float | None = None,
    unit: str = "",
    limit_type: str = "none",
    limit_value_num: float | None = None,
    verdict: str = "unknown",
    is_noise_post: bool = False,
    verdict_raw: str = "",
    extra: dict[str, Any] | None = None,
) -> OhDetectionResultDraft:
    return OhDetectionResultDraft(
        table_ref=table_ref,
        table_title=table_title,
        factor_category=factor_category,
        factor_name=factor_name,
        record_type=record_type,
        workshop=workshop[:255],
        post=post[:255],
        sample_point=sample_point[:255],
        measured_value=measured_value[:64],
        measured_value_num=measured_value_num,
        unit=unit[:32],
        limit_type=limit_type,
        limit_value_num=limit_value_num,
        verdict=verdict,
        is_noise_post=is_noise_post,
        verdict_raw=verdict_raw[:128],
        extra=extra,
    )


def _make_cell_getter(cols: dict[str, int]) -> Callable[[list[str], str], str]:
    def _cell(row: list[str], key: str) -> str:
        col = cols.get(key, -1)
        return row[col] if 0 <= col < len(row) else ""

    return _cell


def _map_dual_table(
    fragment: _TableFragment,
    table_ref: str,
    table_title: str,
    factor_category: str,
) -> ParsedTable:
    """双子表版式（粉尘 TWA/PE、化学 TWA/STEL）：岗位接触 + 采样点两类记录。"""
    warnings: list[str] = []
    header, body = _split_header(fragment.grid)
    cols = {
        "workshop": _column_contain(header, "车间"),
        "post": _column_contain(header, "岗位"),
        "factor": _column_contain(header, "检测项目"),
        "post_value": _column_leaf_prefix(header, "CTWA"),
        "post_limit": _column_leaf_prefix(header, "PC-TWA"),
        "sample_point": _column_contain(header, "采样点"),
        "point_value": max(
            _column_leaf_prefix(header, "CPE"), _column_leaf_prefix(header, "CSTE")
        ),
        "point_limit": max(
            _column_leaf_prefix(header, "PE"), _column_leaf_prefix(header, "PC-STEL")
        ),
    }
    verdict_cols = _column_contain_all(header, "结果判定")
    if len(verdict_cols) >= 2:
        cols["post_verdict"] = verdict_cols[0]
        cols["point_verdict"] = verdict_cols[1]
    elif verdict_cols:
        cols["post_verdict"] = verdict_cols[0]
        cols["point_verdict"] = -1
    else:
        cols["post_verdict"] = -1
        cols["point_verdict"] = -1
    point_limit_type = "PC-STEL" if factor_category == "chemical" else "PE"
    fill_cols = [cols[k] for k in ("workshop", "post", "factor") if cols[k] >= 0]
    _fill_down(body, fill_cols, workshop_col=cols["workshop"])

    rows: list[OhDetectionResultDraft] = []
    factor_default = _factor_from_caption(table_title)
    _cell = _make_cell_getter(cols)
    for idx, row in enumerate(body):
        workshop = _cell(row, "workshop")
        post = _cell(row, "post")
        factor = _cell(row, "factor") or factor_default
        if not factor:
            warnings.append(f"第 {idx + 1} 行缺少检测项目，已跳过")
            continue
        post_value_raw = _cell(row, "post_value")
        if post_value_raw and post:
            value_text, value_num = _measured(post_value_raw)
            verdict, _noise = _map_verdict(_cell(row, "post_verdict"))
            rows.append(
                _draft(
                    table_ref=table_ref,
                    table_title=table_title,
                    factor_category=factor_category,
                    factor_name=factor,
                    record_type="post",
                    workshop=workshop,
                    post=post,
                    measured_value=value_text,
                    measured_value_num=value_num,
                    unit="mg/m³",
                    limit_type="PC-TWA",
                    limit_value_num=_parse_limit(_cell(row, "post_limit")),
                    verdict=verdict,
                    verdict_raw=_cell(row, "post_verdict"),
                )
            )
        point_raw = _cell(row, "point_value")
        sample_point = _cell(row, "sample_point")
        if point_raw and sample_point:
            value_text, value_num = _measured(point_raw)
            verdict, _noise = _map_verdict(_cell(row, "point_verdict"))
            rows.append(
                _draft(
                    table_ref=table_ref,
                    table_title=table_title,
                    factor_category=factor_category,
                    factor_name=factor,
                    record_type="point",
                    workshop=workshop,
                    post=post,
                    sample_point=sample_point,
                    measured_value=value_text,
                    measured_value_num=value_num,
                    unit="mg/m³",
                    limit_type=point_limit_type,
                    limit_value_num=_parse_limit(_cell(row, "point_limit")),
                    verdict=verdict,
                    verdict_raw=_cell(row, "point_verdict"),
                )
            )
    return ParsedTable(
        table_ref=table_ref,
        table_title=table_title,
        layout=factor_category,
        mode="rules",
        rows=rows,
        warnings=warnings,
    )


def _map_mac_table(
    fragment: _TableFragment, table_ref: str, table_title: str
) -> ParsedTable:
    """MAC 单列版式（氢氧化钠/硫化氢/臭氧）：采样点短时接触记录。"""
    warnings: list[str] = []
    header, body = _split_header(fragment.grid)
    cols = {
        "workshop": _column_contain(header, "车间"),
        "post": _column_contain(header, "岗位"),
        "sample_point": _column_contain(header, "采样点"),
        "value": _column_leaf_prefix(header, "CME"),
        "limit": _column_leaf_prefix(header, "MAC"),
        "verdict": _column_contain(header, "判定"),
    }
    _fill_down(
        body,
        [cols[k] for k in ("workshop", "post") if cols[k] >= 0],
        workshop_col=cols["workshop"],
    )
    factor = _factor_from_caption(table_title) or "化学因素"
    _cell = _make_cell_getter(cols)
    rows: list[OhDetectionResultDraft] = []
    for idx, row in enumerate(body):
        sample_point = _cell(row, "sample_point")
        value_raw = _cell(row, "value")
        if not sample_point or not value_raw:
            warnings.append(f"第 {idx + 1} 行缺少采样点或检测值，已跳过")
            continue
        value_text, value_num = _measured(value_raw)
        verdict, _noise = _map_verdict(_cell(row, "verdict"))
        rows.append(
            _draft(
                table_ref=table_ref,
                table_title=table_title,
                factor_category="chemical",
                factor_name=factor,
                record_type="point",
                workshop=_cell(row, "workshop"),
                post=_cell(row, "post"),
                sample_point=sample_point,
                measured_value=value_text,
                measured_value_num=value_num,
                unit="mg/m³",
                limit_type="MAC",
                limit_value_num=_parse_limit(_cell(row, "limit")),
                verdict=verdict,
                verdict_raw=_cell(row, "verdict"),
            )
        )
    return ParsedTable(
        table_ref=table_ref,
        table_title=table_title,
        layout="mac_single",
        mode="rules",
        rows=rows,
        warnings=warnings,
    )


def _map_noise_table(
    fragment: _TableFragment,
    table_ref: str,
    table_title: str,
    initial_group: dict[str, Any] | None = None,
) -> tuple[ParsedTable, dict[str, Any] | None]:
    """噪声版式：岗位组行（LEX,8h/LEX,40h/限值/判定）+ 多个测量地点行。

    组行可能出现在成员行之后（如「化验室」组），成员行先缓冲，
    遇到组行后回填归属再落草稿。跨页续表经 ``initial_group`` 传入上一
    片段的组上下文，返回本片段末尾的组上下文。
    """
    warnings: list[str] = []
    header, body = _split_header(fragment.grid)
    cols = {
        "workshop": _column_contain(header, "车间"),
        "post": _column_contain(header, "岗位"),
        "location": _column_contain(header, "测量地点"),
        "value": _column_contain(header, "测量值"),
        "lex8": _column_contain(header, "LEX,8h"),
        "lex40": _column_contain(header, "LEX,40h"),
        "limit": _column_contain(header, "职业接触限值"),
        "verdict": _column_contain(header, "判定"),
    }
    _fill_down(body, [cols["workshop"]], workshop_col=cols["workshop"])
    rows: list[OhDetectionResultDraft] = []
    _cell = _make_cell_getter(cols)

    def _point_row(location: str, value_raw: str, group: dict[str, Any]) -> None:
        value_text, value_num = _measured(value_raw)
        rows.append(
            _draft(
                table_ref=table_ref,
                table_title=table_title,
                factor_category="noise",
                factor_name="噪声",
                record_type="point",
                workshop=group["workshop"],
                post=group["post"],
                sample_point=location,
                measured_value=value_text,
                measured_value_num=value_num,
                unit="dB(A)",
                limit_type="LEX-40h",
                limit_value_num=group["limit_num"],
                verdict=group["verdict"],
                is_noise_post=group["is_noise"],
                verdict_raw=group["verdict_raw"],
                extra=dict(group["extra"]) or None,
            )
        )

    pending: list[tuple[str, str]] = []
    group: dict[str, Any] | None = initial_group
    for row in body:
        location = _cell(row, "location")
        value_raw = _cell(row, "value")
        lex8_raw = _cell(row, "lex8")
        lex40_raw = _cell(row, "lex40") or lex8_raw
        verdict_raw = _cell(row, "verdict")
        if lex8_raw or verdict_raw:
            # 岗位组行（可能同时携带本组第一个测量地点）
            verdict, is_noise = _map_verdict(verdict_raw)
            extra: dict[str, Any] = {}
            lex8_num = _parse_number(lex8_raw) if lex8_raw else None
            lex40_num = _parse_number(lex40_raw) if lex40_raw else None
            if lex8_num is not None:
                extra["lex8h"] = lex8_num
            if lex40_num is not None:
                extra["lex40h"] = lex40_num
            new_group: dict[str, Any] = {
                "workshop": _cell(row, "workshop"),
                "post": _cell(row, "post"),
                "verdict": verdict,
                "is_noise": is_noise,
                "verdict_raw": verdict_raw,
                "limit_num": _parse_limit(_cell(row, "limit")),
                "extra": extra,
            }
            # 新组行前缓冲的成员行归属本组
            for pending_location, pending_value in pending:
                _point_row(pending_location, pending_value, new_group)
            pending = []
            group = new_group
            if lex40_raw:
                lex40_text, lex40_value = _measured(lex40_raw)
                rows.append(
                    _draft(
                        table_ref=table_ref,
                        table_title=table_title,
                        factor_category="noise",
                        factor_name="噪声",
                        record_type="post",
                        workshop=group["workshop"],
                        post=group["post"],
                        measured_value=lex40_text,
                        measured_value_num=lex40_value,
                        unit="dB(A)",
                        limit_type="LEX-40h",
                        limit_value_num=group["limit_num"],
                        verdict=verdict,
                        is_noise_post=is_noise,
                        verdict_raw=verdict_raw,
                        extra=extra or None,
                    )
                )
            if location and value_raw:
                _point_row(location, value_raw, group)
        elif location and value_raw:
            if group is not None:
                _point_row(location, value_raw, group)
            else:
                pending.append((location, value_raw))
        elif location:
            warnings.append(f"测量地点「{location}」缺少测量值，已跳过")
    if pending:
        for pending_location, _pending_value in pending:
            warnings.append(
                f"测量地点「{pending_location}」缺少岗位组信息，已跳过"
            )
    return (
        ParsedTable(
            table_ref=table_ref,
            table_title=table_title,
            layout="noise",
            mode="rules",
            rows=rows,
            warnings=warnings,
        ),
        group,
    )


def _map_field_table(
    fragment: _TableFragment,
    table_ref: str,
    table_title: str,
    initial_group: dict[str, Any] | None = None,
) -> tuple[ParsedTable, dict[str, Any] | None]:
    """工频电场版式：岗位组行（E8/限值/判定）+ 多个采样点行。

    组行可能出现在成员行之后，也可能自带第一个采样点；成员行先缓冲，
    遇到组行后回填归属。跨页续表经 ``initial_group`` 传入上一片段的
    组上下文，返回本片段末尾的组上下文。
    """
    warnings: list[str] = []
    header, body = _split_header(fragment.grid)
    cols = {
        "workshop": _column_contain(header, "车间"),
        "post": _column_contain(header, "岗位"),
        "sample_point": _column_contain(header, "采样点"),
        "value": _column_contain(header, "测量结果"),
        "e8": _column_contain(header, "E（V/m）", "接触限值"),
        "limit": _column_contain(header, "职业接触限值"),
        "verdict": _column_contain(header, "判定"),
    }
    if cols["e8"] < 0:
        cols["e8"] = _column_contain(header, "E8")
    _fill_down(body, [cols["workshop"]], workshop_col=cols["workshop"])
    rows: list[OhDetectionResultDraft] = []
    _cell = _make_cell_getter(cols)

    def _point_row(sample_point: str, value_raw: str, group: dict[str, Any]) -> None:
        value_text, value_num = _measured(value_raw)
        rows.append(
            _draft(
                table_ref=table_ref,
                table_title=table_title,
                factor_category="power_frequency_field",
                factor_name="工频电场",
                record_type="point",
                workshop=group["workshop"],
                post=group["post"],
                sample_point=sample_point,
                measured_value=value_text,
                measured_value_num=value_num,
                unit="V/m",
                limit_type="E8",
                limit_value_num=group["limit_num"],
                verdict=group["verdict"],
                verdict_raw=group["verdict_raw"],
            )
        )

    pending: list[tuple[str, str]] = []
    group: dict[str, Any] | None = initial_group
    for row in body:
        sample_point = _cell(row, "sample_point")
        value_raw = _cell(row, "value")
        e8_raw = _cell(row, "e8")
        verdict_raw = _cell(row, "verdict")
        if e8_raw and verdict_raw:
            verdict, _noise = _map_verdict(verdict_raw)
            new_group: dict[str, Any] = {
                "workshop": _cell(row, "workshop"),
                "post": _cell(row, "post"),
                "verdict": verdict,
                "verdict_raw": verdict_raw,
                "limit_num": _parse_limit(_cell(row, "limit")),
            }
            for pending_point, pending_value in pending:
                _point_row(pending_point, pending_value, new_group)
            pending = []
            group = new_group
            value_text, value_num = _measured(e8_raw)
            rows.append(
                _draft(
                    table_ref=table_ref,
                    table_title=table_title,
                    factor_category="power_frequency_field",
                    factor_name="工频电场",
                    record_type="post",
                    workshop=group["workshop"],
                    post=group["post"],
                    measured_value=value_text,
                    measured_value_num=value_num,
                    unit="V/m",
                    limit_type="E8",
                    limit_value_num=group["limit_num"],
                    verdict=verdict,
                    verdict_raw=verdict_raw,
                )
            )
            if sample_point and value_raw:
                _point_row(sample_point, value_raw, group)
        elif sample_point and value_raw:
            if group is not None:
                _point_row(sample_point, value_raw, group)
            else:
                pending.append((sample_point, value_raw))
        elif sample_point:
            warnings.append(f"采样点「{sample_point}」缺少测量结果，已跳过")
    if pending:
        for pending_point, _pending_value in pending:
            warnings.append(f"采样点「{pending_point}」缺少岗位组信息，已跳过")
    return (
        ParsedTable(
            table_ref=table_ref,
            table_title=table_title,
            layout="field",
            mode="rules",
            rows=rows,
            warnings=warnings,
        ),
        group,
    )


def _map_heat_table(
    fragment: _TableFragment, table_ref: str, table_title: str
) -> ParsedTable:
    """高温（WBGT）版式：判定行为岗位级记录，其余为测量地点行。"""
    warnings: list[str] = []
    header, body = _split_header(fragment.grid)
    cols = {
        "workshop": _column_contain(header, "车间"),
        "post": _column_contain(header, "岗位"),
        "location": _column_contain(header, "测量地点"),
        "hours": _column_contain(header, "接触时间", "率"),
        "rate": _column_contain(header, "接触时间率"),
        "intensity": _column_contain(header, "体力劳动强度"),
        "value": _column_contain(header, "WBGT指数平均", "接触限值"),
        "limit": _column_contain(header, "接触限值"),
        "verdict": _column_contain(header, "判定"),
    }
    _fill_down(
        body,
        [cols[k] for k in ("workshop", "post") if cols[k] >= 0],
        workshop_col=cols["workshop"],
    )
    rows: list[OhDetectionResultDraft] = []
    current: dict[str, Any] = {}
    _cell = _make_cell_getter(cols)
    for idx, row in enumerate(body):
        location = _cell(row, "location")
        value_raw = _cell(row, "value")
        verdict_raw = _cell(row, "verdict")
        if verdict_raw:
            verdict, _noise = _map_verdict(verdict_raw)
            extra: dict[str, Any] = {}
            if _cell(row, "hours"):
                extra["exposure_hours"] = _parse_number(_cell(row, "hours"))
            if _cell(row, "rate"):
                extra["exposure_rate"] = _cell(row, "rate")
            if _cell(row, "intensity"):
                extra["labor_intensity"] = _cell(row, "intensity")
            current = {
                "verdict": verdict,
                "verdict_raw": verdict_raw,
                "limit": _parse_limit(_cell(row, "limit")),
            }
            value_text, value_num = _measured(value_raw)
            rows.append(
                _draft(
                    table_ref=table_ref,
                    table_title=table_title,
                    factor_category="heat",
                    factor_name="高温",
                    record_type="post",
                    workshop=_cell(row, "workshop"),
                    post=_cell(row, "post"),
                    sample_point=location,
                    measured_value=value_text,
                    measured_value_num=value_num,
                    unit="℃",
                    limit_type="WBGT",
                    limit_value_num=current["limit"],
                    verdict=verdict,
                    verdict_raw=verdict_raw,
                    extra=extra or None,
                )
            )
        elif location:
            value_text, value_num = _measured(value_raw) if value_raw else ("", None)
            if not value_text and not current:
                warnings.append(f"第 {idx + 1} 行缺少测量值，已跳过")
                continue
            rows.append(
                _draft(
                    table_ref=table_ref,
                    table_title=table_title,
                    factor_category="heat",
                    factor_name="高温",
                    record_type="point",
                    workshop=_cell(row, "workshop"),
                    post=_cell(row, "post"),
                    sample_point=location,
                    measured_value=value_text,
                    measured_value_num=value_num,
                    unit="℃",
                    limit_type="WBGT",
                    limit_value_num=current.get("limit"),
                    verdict=current.get("verdict", "unknown"),
                    verdict_raw=current.get("verdict_raw", ""),
                )
            )
    return ParsedTable(
        table_ref=table_ref,
        table_title=table_title,
        layout="heat",
        mode="rules",
        rows=rows,
        warnings=warnings,
    )


def _map_silica_table(
    fragment: _TableFragment, table_ref: str, table_title: str
) -> ParsedTable:
    """游离二氧化硅版式：取样点 + 含量(%) + 粉尘类别判定。"""
    warnings: list[str] = []
    header, body = _split_header(fragment.grid)
    sample_point = max(
        _column_contain(header, "取样点"), _column_contain(header, "采样点")
    )
    cols = {
        "sample_point": sample_point,
        "value": _column_contain(header, "C（%）"),
        "class": _column_contain(header, "粉尘类别"),
    }
    if cols["value"] < 0:
        cols["value"] = _column_contain(header, "含量", "粉尘类别")
    _cell = _make_cell_getter(cols)
    rows: list[OhDetectionResultDraft] = []
    for idx, row in enumerate(body):
        point = _cell(row, "sample_point")
        value_raw = _cell(row, "value")
        if not point or not value_raw:
            warnings.append(f"第 {idx + 1} 行缺少取样点或含量，已跳过")
            continue
        value_text, value_num = _measured(value_raw)
        rows.append(
            _draft(
                table_ref=table_ref,
                table_title=table_title,
                factor_category="free_silica",
                factor_name="游离二氧化硅",
                record_type="point",
                sample_point=point,
                measured_value=value_text,
                measured_value_num=value_num,
                unit="%",
                verdict="unknown",
                verdict_raw=_cell(row, "class"),
                extra=(
                    {"dust_class": _cell(row, "class")} if _cell(row, "class") else None
                ),
            )
        )
    return ParsedTable(
        table_ref=table_ref,
        table_title=table_title,
        layout="silica",
        mode="rules",
        rows=rows,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# LLM 兜底解析（未知版式）
# ---------------------------------------------------------------------------

_LLM_TABLE_INSTRUCTION = """你是职业病危害因素检测报告的表格解析助手。
输入是一张检测结果表的标题和网格数据（第一组为表头行，单元格已去除空白）。
请把每个检测记录提取为一行 JSON，字段如下：
- factor_category: 危害因素类别，只能是
  dust_total/dust_respirable/free_silica/chemical/noise/power_frequency_field/heat 之一
- factor_name: 危害因素名称（如 谷物粉尘、氢氧化钠、噪声），取自表标题或检测项目列
- record_type: post（岗位时间加权/汇总接触记录）或 point（采样点/测量地点单点记录）
- workshop: 车间；post: 岗位；sample_point: 采样点或测量地点（post 记录可为空）
- measured_value: 检测值原文，必须与单元格文本完全一致
  （如 "＜0.44"、"89.9"），禁止计算或推断
- unit: 单位（mg/m³、dB(A)、V/m、℃、%），按表头判断
- limit_type: PC-TWA/PC-STEL/MAC/PE/LEX-40h/E8/WBGT/none 之一
- limit_value_num: 限值数值，必须来自表格单元格；没有则为 null
- verdict: compliant（未超标）/exceed（超标）/unknown（未判定）
- is_noise_post: 判定文本包含"噪声作业岗位"时为 true，否则 false
- verdict_raw: 判定列原文
纵向合并单元格（车间/岗位/检测项目为空）表示沿用上一行，请填充后再输出。
无法识别的行直接省略，禁止编造。
输出 JSON：{"rows": [上述字段对象列表]}"""


def _grid_cell_values(grid: list[list[str]]) -> set[float]:
    values: set[float] = set()
    for row in grid:
        for cell in row:
            num = _parse_number(cell)
            if num is not None:
                values.add(num)
    return values


def _grid_cell_texts(grid: list[list[str]]) -> list[str]:
    return [cell for row in grid for cell in row if cell]


def _validate_llm_row(
    row: dict[str, Any],
    cell_values: set[float],
    cell_texts: list[str],
) -> OhDetectionResultDraft | None:
    """校验 LLM 输出行：Pydantic 草稿 + 数字回查 + 文本来源检查。"""
    try:
        draft = OhDetectionResultDraft.model_validate(row)
    except Exception:  # noqa: BLE001 - 非法行直接丢弃
        return None
    # 数字回查：数值必须能在源表格单元格中找到（含纯数字字符串形态）
    nums: list[float | None] = [draft.measured_value_num, draft.limit_value_num]
    if draft.measured_value_num is None and not _is_below_detection(
        draft.measured_value
    ):
        nums.append(_parse_number(draft.measured_value))
    for num in nums:
        if num is not None and num not in cell_values:
            return None
    if _is_below_detection(draft.measured_value):
        below_num = _parse_number(draft.measured_value)
        if below_num is not None and below_num not in cell_values:
            return None
    # 文本来源检查：车间/岗位/采样点需能在数据单元格中找到
    # （对照方至少 3 字，避免被"车间/地点"这类短表头误匹配）
    for value in (draft.workshop, draft.post, draft.sample_point):
        if value and not any(
            value == cell or (len(cell) >= 3 and (value in cell or cell in value))
            for cell in cell_texts
        ):
            return None
    if not (draft.workshop or draft.post or draft.sample_point):
        return None
    return draft


async def _llm_parse_table(
    caption: str, grid: list[list[str]]
) -> tuple[list[OhDetectionResultDraft], list[str]]:
    """LLM 兜底解析未知版式表格；返回 (草稿行, 警告)。调用方处理 LLM 异常。"""
    payload = {"title": caption or "（无标题）", "grid": grid}
    messages = [
        {
            "role": "user",
            "content": _LLM_TABLE_INSTRUCTION
            + "\n\n输入数据：\n"
            + json.dumps(payload, ensure_ascii=False),
        }
    ]
    raw = await llm_client.chat_json(messages, expected_keys=["rows"])
    raw_rows = raw.get("rows")
    if not isinstance(raw_rows, list):
        raise LLMOutputError("AI 表格识别结果缺少 rows")
    cell_values = _grid_cell_values(grid)
    cell_texts = _grid_cell_texts(grid)
    drafts: list[OhDetectionResultDraft] = []
    dropped = 0
    for item in raw_rows:
        if not isinstance(item, dict):
            dropped += 1
            continue
        draft = _validate_llm_row(item, cell_values, cell_texts)
        if draft is None:
            dropped += 1
            continue
        drafts.append(draft)
    warnings = [f"{dropped} 行未通过来源校验被丢弃"] if dropped else []
    return drafts, warnings


# ---------------------------------------------------------------------------
# 报告级解析
# ---------------------------------------------------------------------------


def _table_ref_of(caption: str) -> str:
    match = _TABLE_CAPTION_RE.search(caption)
    return f"表{match.group(1).replace('–', '-')}" if match else ""


_WORKSHOP_TAIL_SUFFIXES = ("车间", "室", "部", "房", "站")


def _heal_continuation_workshops(
    last_table: ParsedTable, fragment_table: ParsedTable
) -> None:
    """跨页续表的车间列修复。

    1. 残片拼接：上片段末行车间被截断（如"102-1车"）、下片段首行
       是尾巴（"间"）时，拼接为完整车间名；
    2. 开头回填：续表开头连续缺失车间的行，沿用上一片段末行车间。
    """
    tail_ws = last_table.rows[-1].workshop if last_table.rows else ""
    if not tail_ws or not fragment_table.rows:
        return
    fill_value = tail_ws
    head_ws = fragment_table.rows[0].workshop
    if (
        head_ws
        and len(head_ws) <= 2
        and head_ws != tail_ws
        and not tail_ws.endswith(_WORKSHOP_TAIL_SUFFIXES)
    ):
        fill_value = (tail_ws + head_ws)[:255]
        last_table.rows[-1].workshop = fill_value
        fragment_table.rows[0].workshop = fill_value
    for row in fragment_table.rows:
        if not row.workshop:
            row.workshop = fill_value
        elif row.workshop == fill_value:
            continue
        else:
            break


def _caption_title(caption: str) -> str:
    return _TABLE_CAPTION_RE.sub("", caption).strip()


async def parse_report(pdf_bytes: bytes, file_name: str) -> ParsedReport:
    """解析检测报告 PDF：已知版式规则映射，未知版式 LLM 兜底。"""
    if not file_name.lower().endswith(_ALLOWED_EXT):
        raise OhDetectionParseError("仅支持 PDF 格式的检测报告")
    if not pdf_bytes:
        raise OhDetectionParseError("上传文件为空")
    if len(pdf_bytes) > _MAX_FILE_BYTES:
        raise OhDetectionParseError("检测报告文件不能超过 30MB")

    file_sha = sha256(pdf_bytes).hexdigest()
    cached = _PARSE_CACHE.get(file_sha)
    if cached is not None:
        _PARSE_CACHE.move_to_end(file_sha)
        return cached

    doc = await asyncio.to_thread(_extract_pdf, pdf_bytes)
    if not any(text.strip() for text in doc.page_texts) and not doc.fragments:
        raise OhDetectionParseError(
            "未识别到文本内容，疑似扫描件，暂不支持（请提供文本版 PDF）"
        )
    if not doc.fragments:
        raise OhDetectionParseError("未在 PDF 中识别到检测表格")

    report_no, report_name, company, agency = _extract_metadata(doc)
    parsed = ParsedReport(
        report_no=report_no,
        report_name=report_name,
        company_name=company,
        detection_agency=agency,
        file_sha256=file_sha,
    )

    llm_budget = _LLM_FALLBACK_TABLE_LIMIT
    last_table: ParsedTable | None = None
    for fragment in doc.fragments:
        caption = fragment.caption
        header_rows, _body = _split_header(fragment.grid)
        header_text = "".join("".join(row) for row in header_rows)
        caption_title = _caption_title(caption)
        table_ref = _table_ref_of(caption)
        if caption:
            layout = _detect_layout(caption, header_text)
        else:
            # 跨页续表：沿用上一表的版式与标题
            layout = last_table.layout if last_table else "unknown"
            caption_title = last_table.table_title if last_table else ""

        if layout == "unknown":
            if llm_budget <= 0:
                parsed.tables.append(
                    ParsedTable(
                        table_ref=table_ref,
                        table_title=caption_title,
                        layout="unknown",
                        mode="skipped",
                        skip_reason="版式未识别且 AI 兜底额度已用尽",
                    )
                )
                last_table = None
                continue
            llm_budget -= 1
            try:
                drafts, warnings = await _llm_parse_table(
                    caption or caption_title, fragment.grid
                )
                table = ParsedTable(
                    table_ref=table_ref,
                    table_title=caption_title,
                    layout="llm",
                    mode="llm",
                    rows=drafts,
                    warnings=warnings,
                )
            except LLMConfigError:
                table = ParsedTable(
                    table_ref=table_ref,
                    table_title=caption_title,
                    layout="unknown",
                    mode="skipped",
                    skip_reason="版式未识别且未配置 AI 模型",
                )
            parsed.tables.append(table)
            last_table = table
            continue

        if layout == "silica":
            table = _map_silica_table(fragment, table_ref, caption_title)
        elif layout in {"dust", "twa_stel"}:
            if layout == "twa_stel":
                category = "chemical"
            elif last_table is not None and not caption and last_table.rows:
                # 续表沿用上一片段的粉尘类别（总尘/呼尘）
                category = last_table.rows[0].factor_category
            elif "呼尘" in caption:
                category = "dust_respirable"
            else:
                category = "dust_total"
            table = _map_dual_table(fragment, table_ref, caption_title, category)
            table.layout = "dust" if layout == "dust" else "twa_stel"
        elif layout == "mac_single":
            table = _map_mac_table(fragment, table_ref, caption_title)
        elif layout == "noise":
            initial = (
                last_table.last_group
                if not caption and last_table and last_table.layout == "noise"
                else None
            )
            table, trailing = _map_noise_table(
                fragment, table_ref, caption_title, initial
            )
            table.last_group = trailing
        elif layout == "field":
            initial = (
                last_table.last_group
                if not caption and last_table and last_table.layout == "field"
                else None
            )
            table, trailing = _map_field_table(
                fragment, table_ref, caption_title, initial
            )
            table.last_group = trailing
        else:  # heat
            table = _map_heat_table(fragment, table_ref, caption_title)

        # 跨页续表并入上一张表
        if (
            not caption
            and last_table is not None
            and last_table.mode == table.mode
            and last_table.layout == table.layout
        ):
            _heal_continuation_workshops(last_table, table)
            last_table.rows.extend(table.rows)
            last_table.warnings.extend(table.warnings)
            last_table.last_group = table.last_group
        else:
            parsed.tables.append(table)
            last_table = table

    if not parsed.rows and parsed.tables and all(
        table.mode == "skipped" for table in parsed.tables
    ):
        raise OhDetectionParseError(
            "未能识别任何检测数据：表格版式未知且未配置 AI 模型"
        )
    if not parsed.rows:
        raise OhDetectionParseError("未能从报告表格中识别出检测数据")

    _PARSE_CACHE[file_sha] = parsed
    if len(_PARSE_CACHE) > _PARSE_CACHE_MAX:
        _PARSE_CACHE.popitem(last=False)
    return parsed


def clear_parse_cache() -> None:
    """清空解析缓存（测试用）。"""
    _PARSE_CACHE.clear()


def _build_preview(
    parsed: ParsedReport,
    file_name: str,
    existing: OhDetectionReport | None,
    existing_points: int,
) -> OhDetectionParsePreview:
    tables = [
        OhDetectionTableSummary(
            table_ref=table.table_ref,
            table_title=table.table_title,
            layout=table.layout,
            mode=table.mode,
            row_count=len(table.rows),
            warnings=table.warnings[:10],
            sample_rows=table.rows[:5],
        )
        for table in parsed.tables
    ]
    return OhDetectionParsePreview(
        report_no=parsed.report_no,
        report_name=parsed.report_name or "职业病危害因素检测报告",
        company_name=parsed.company_name,
        detection_agency=parsed.detection_agency,
        file_name=file_name,
        file_sha256=parsed.file_sha256,
        parse_mode=parsed.parse_mode,
        table_count=sum(1 for t in parsed.tables if t.mode != "skipped"),
        total_points=parsed.total_points,
        exceed_points=parsed.exceed_points,
        noise_post_points=parsed.noise_post_points,
        warnings=[w for t in parsed.tables for w in t.warnings][:20],
        tables=tables,
        existing_report_id=existing.id if existing else None,
        existing_total_points=existing_points,
    )


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------


class OhDetectionReportService:
    """检测报告导入与台账查询服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _audit(
        self,
        action: str,
        resource_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        try:
            await record_audit_log(
                self.session,
                action=action,
                user_id=user_id,
                resource_type="oh_detection_report",
                resource_id=resource_id,
                extra=extra,
            )
        except Exception:  # noqa: BLE001 - 审计失败不阻断业务
            logger.exception("审计日志记录失败 (oh_detection_report:%s)", action)

    async def _find_by_report_no(self, report_no: str) -> OhDetectionReport | None:
        stmt = select(OhDetectionReport).where(
            OhDetectionReport.report_no == report_no,
            OhDetectionReport.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def parse_preview(
        self, pdf_bytes: bytes, file_name: str
    ) -> OhDetectionParsePreview:
        parsed = await parse_report(pdf_bytes, file_name)
        existing: OhDetectionReport | None = None
        existing_points = 0
        if parsed.report_no:
            existing = await self._find_by_report_no(parsed.report_no)
            if existing:
                count_stmt = (
                    select(func.count())
                    .select_from(OhDetectionResult)
                    .where(
                        OhDetectionResult.report_id == existing.id,
                        OhDetectionResult.is_deleted.is_(False),
                    )
                )
                existing_points = (
                    (await self.session.execute(count_stmt)).scalar() or 0
                )
        return _build_preview(parsed, file_name, existing, existing_points)

    async def import_report(
        self,
        pdf_bytes: bytes,
        file_name: str,
        *,
        report_no: str,
        report_name: str = "",
        company_name: str = "",
        detection_agency: str = "",
        detection_date: date | None = None,
        remark: str = "",
        user_id: uuid.UUID | None = None,
    ) -> tuple[OhDetectionReport, int, bool, int]:
        """导入（或覆盖同编号重导）检测报告。调用方负责事务提交。

        返回 ``(报告, 导入结果行数, 是否覆盖重导, 同步监测记录数)``。
        """
        parsed = await parse_report(pdf_bytes, file_name)
        report_no = (report_no or parsed.report_no).strip()
        if not report_no:
            raise OhDetectionParseError("未能识别报告编号，请在导入时填写报告编号")
        rows = parsed.rows
        if not rows:
            raise OhDetectionParseError("报告未解析出任何检测数据，已取消导入")

        # 保存原始文件（大文件写盘移出事件循环）
        safe_no = re.sub(r"[^\w.-]", "_", report_no)
        file_path = os.path.join(
            _UPLOAD_DIR, f"{safe_no}_{int(datetime.now().timestamp())}.pdf"
        )

        def _save_pdf() -> None:
            os.makedirs(_UPLOAD_DIR, exist_ok=True)
            with open(file_path, "wb") as fh:
                fh.write(pdf_bytes)

        await asyncio.to_thread(_save_pdf)

        warnings_json: list[dict[str, str]] = []
        for table in parsed.tables:
            reasons = [table.skip_reason] if table.skip_reason else table.warnings[:5]
            for reason in reasons:
                warnings_json.append(
                    {
                        "table": f"{table.table_ref} {table.table_title}".strip(),
                        "reason": reason,
                    }
                )

        values: dict[str, Any] = {
            "report_no": report_no,
            "report_name": report_name or parsed.report_name or file_name,
            "company_name": company_name or parsed.company_name,
            "detection_agency": detection_agency or parsed.detection_agency,
            "detection_date": detection_date,
            "table_count": sum(1 for t in parsed.tables if t.mode != "skipped"),
            "total_points": parsed.total_points,
            "exceed_points": parsed.exceed_points,
            "noise_post_points": parsed.noise_post_points,
            "source_file_name": file_name,
            "source_file_path": file_path,
            "source_file_sha256": parsed.file_sha256,
            "parse_mode": parsed.parse_mode,
            "parse_warnings": warnings_json or None,
            "remark": remark,
            "search_text": " ".join(
                filter(
                    None,
                    [
                        report_no,
                        report_name or parsed.report_name,
                        company_name or parsed.company_name,
                        detection_agency or parsed.detection_agency,
                        remark,
                    ],
                )
            ),
        }

        existing = await self._find_by_report_no(report_no)
        replaced = existing is not None
        if existing is None:
            report = OhDetectionReport(**values, created_by=user_id)
            self.session.add(report)
            await self.session.flush()
            await self._audit(
                "import",
                resource_id=report.id,
                user_id=user_id,
                extra={"report_no": report_no, "count": len(rows)},
            )
        else:
            await self.session.execute(
                delete(OhDetectionResult).where(
                    OhDetectionResult.report_id == existing.id
                )
            )
            for key, value in values.items():
                setattr(existing, key, value)
            existing.updated_by = user_id
            report = existing
            await self.session.flush()
            await self._audit(
                "reimport",
                resource_id=report.id,
                user_id=user_id,
                extra={"report_no": report_no, "count": len(rows)},
            )

        for seq, row in enumerate(rows, start=1):
            data = row.model_dump()
            self.session.add(
                OhDetectionResult(
                    report_id=report.id, seq=seq, created_by=user_id, **data
                )
            )
        monitors_synced = await self._sync_monitors_from_report(
            report, rows, user_id=user_id
        )
        return report, len(rows), replaced, monitors_synced

    @staticmethod
    def _coarse_factor_category(factor_category: str) -> str:
        """细分类别 → 监测记录的粗分类别（dust/chemical/physical）。"""
        if factor_category in {"dust_total", "dust_respirable", "free_silica"}:
            return "dust"
        if factor_category == "chemical":
            return "chemical"
        return "physical"

    @staticmethod
    def _verdict_to_compliance(verdict: str) -> str:
        """报告判定 → 监测记录合规状态（对齐 OELComplianceStatusEnum）。"""
        if verdict == "exceed":
            return "exceeding"
        if verdict == "compliant":
            return "compliant"
        return "unknown"

    @staticmethod
    def _group_rows_for_monitors(
        rows: list[OhDetectionResultDraft],
    ) -> OrderedDict[str, list[OhDetectionResultDraft]]:
        """按车间（缺失时用采样点）分组，并归并跨页截断的残片组名。

        如"102-1车"+"间"两个残片组合并为"102-1车间"：残片 = 不以
        完整场所后缀结尾的短组名，与另一组名拼接后能补全后缀。
        """
        groups: OrderedDict[str, list[OhDetectionResultDraft]] = OrderedDict()
        for row in rows:
            key = row.workshop or row.sample_point or "未标注车间"
            groups.setdefault(key, []).append(row)

        rename: dict[str, str] = {}
        names = list(groups)
        for frag in names:
            if len(frag) < 1 or len(frag) > 3 or frag.endswith(
                _WORKSHOP_TAIL_SUFFIXES
            ):
                continue
            for full in names:
                if full == frag or len(full) < 4:
                    continue
                if full.endswith(_WORKSHOP_TAIL_SUFFIXES):
                    continue
                candidate = full + frag
                if candidate.endswith(_WORKSHOP_TAIL_SUFFIXES):
                    rename[frag] = candidate
                    rename[full] = candidate
                    break
        # 规则二：残组名是某完整组名的前缀且只差 1-2 个字（如"102-1车" ⊂ "102-1车间"）
        for name in names:
            if name in rename or name.endswith(_WORKSHOP_TAIL_SUFFIXES):
                continue
            for full in names:
                if full == name or not full.endswith(_WORKSHOP_TAIL_SUFFIXES):
                    continue
                if full.startswith(name) and 0 < len(full) - len(name) <= 2:
                    rename[name] = full
                    break
        if rename:
            merged: OrderedDict[str, list[OhDetectionResultDraft]] = OrderedDict()
            for name, items in groups.items():
                merged.setdefault(rename.get(name, name), []).extend(items)
            return merged
        return groups

    async def _sync_monitors_from_report(
        self,
        report: OhDetectionReport,
        rows: list[OhDetectionResultDraft],
        *,
        user_id: uuid.UUID | None,
    ) -> int:
        """按车间/点位分组生成危害因素监测记录（同报告重导时刷新）。

        监测编号取 ``{报告编号}-M{序号}``，状态直接置 completed
        （委托检测报告已出，结果随记录带入）。
        """
        groups = self._group_rows_for_monitors(rows)

        prefix = f"{report.report_no}-M"
        existing = (
            (
                await self.session.execute(
                    select(OhHazardMonitor).where(
                        OhHazardMonitor.monitor_no.like(f"{prefix}%"),
                        OhHazardMonitor.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        for monitor in existing:
            monitor.is_deleted = True
            monitor.updated_by = user_id

        source_note = f"来源检测报告: {report.report_no}（导入自动生成）"
        for idx, (workplace, group_rows) in enumerate(groups.items(), start=1):
            results = [
                {
                    "factor_name": row.factor_name,
                    "factor_category": self._coarse_factor_category(
                        row.factor_category
                    ),
                    "detection_value": row.measured_value,
                    "unit": row.unit,
                    "oel_limit": row.limit_value_num,
                    "compliance_status": self._verdict_to_compliance(row.verdict),
                    "sampling_method": (
                        "post" if row.record_type == "post" else "point"
                    ),
                    "standard_ref": (
                        f"{row.table_ref} {row.table_title}".strip()
                    ),
                    "post": row.post,
                    "sample_point": row.sample_point,
                }
                for row in group_rows
            ]
            self.session.add(
                OhHazardMonitor(
                    monitor_no=f"{prefix}{idx:02d}"[:64],
                    workplace=workplace[:255],
                    detection_type="commissioned",
                    detection_date=report.detection_date,
                    detection_agency=report.detection_agency or None,
                    status="completed",
                    detection_results=results,
                    notes=source_note,
                    created_by=user_id,
                )
            )
        return len(groups)

    async def list_reports(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        year: int | None = None,
    ) -> tuple[list[OhDetectionReport], dict[str, int]]:
        stmt = select(OhDetectionReport).where(OhDetectionReport.is_deleted.is_(False))
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    OhDetectionReport.report_no.ilike(like),
                    OhDetectionReport.report_name.ilike(like),
                    OhDetectionReport.company_name.ilike(like),
                    OhDetectionReport.detection_agency.ilike(like),
                    OhDetectionReport.search_text.ilike(like),
                )
            )
        if year:
            stmt = stmt.where(
                func.extract("year", OhDetectionReport.detection_date) == year
            )
        stmt = stmt.order_by(
            OhDetectionReport.detection_date.desc().nullslast(),
            OhDetectionReport.created_at.desc(),
        )
        items = (
            (
                await self.session.execute(
                    stmt.offset((page - 1) * page_size).limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        stats_stmt = select(
            func.count(OhDetectionReport.id),
            func.coalesce(func.sum(OhDetectionReport.total_points), 0),
            func.coalesce(func.sum(OhDetectionReport.exceed_points), 0),
            func.coalesce(func.sum(OhDetectionReport.noise_post_points), 0),
        ).where(OhDetectionReport.is_deleted.is_(False))
        stats = (await self.session.execute(stats_stmt)).one()
        meta = {
            "report_count": stats[0],
            "total_points": stats[1],
            "exceed_points": stats[2],
            "noise_post_points": stats[3],
        }
        return list(items), meta

    async def get_report(self, report_id: uuid.UUID) -> OhDetectionReport:
        stmt = select(OhDetectionReport).where(
            OhDetectionReport.id == report_id,
            OhDetectionReport.is_deleted.is_(False),
        )
        report = (await self.session.execute(stmt)).scalar_one_or_none()
        if report is None:
            raise NotFoundException("检测报告")
        return report

    async def list_results(
        self,
        report_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        factor_category: str | None = None,
        record_type: str | None = None,
        workshop: str | None = None,
        verdict: str | None = None,
        is_noise_post: bool | None = None,
        keyword: str | None = None,
    ) -> tuple[list[OhDetectionResult], int]:
        stmt = select(OhDetectionResult).where(
            OhDetectionResult.report_id == report_id,
            OhDetectionResult.is_deleted.is_(False),
        )
        if factor_category:
            stmt = stmt.where(OhDetectionResult.factor_category == factor_category)
        if record_type:
            stmt = stmt.where(OhDetectionResult.record_type == record_type)
        if workshop:
            stmt = stmt.where(OhDetectionResult.workshop.ilike(f"%{workshop.strip()}%"))
        if verdict:
            stmt = stmt.where(OhDetectionResult.verdict == verdict)
        if is_noise_post is not None:
            stmt = stmt.where(OhDetectionResult.is_noise_post.is_(is_noise_post))
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    OhDetectionResult.factor_name.ilike(like),
                    OhDetectionResult.workshop.ilike(like),
                    OhDetectionResult.post.ilike(like),
                    OhDetectionResult.sample_point.ilike(like),
                    OhDetectionResult.table_ref.ilike(like),
                )
            )
        stmt = stmt.order_by(OhDetectionResult.seq)
        total = (
            await self.session.execute(
                select(func.count()).select_from(stmt.subquery())
            )
        ).scalar() or 0
        items = (
            (
                await self.session.execute(
                    stmt.offset((page - 1) * page_size).limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return list(items), total

    async def delete_report(
        self, report_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> OhDetectionReport:
        report = await self.get_report(report_id)
        report.is_deleted = True
        report.updated_by = user_id
        await self.session.execute(
            update(OhDetectionResult)
            .where(OhDetectionResult.report_id == report_id)
            .values(is_deleted=True, updated_by=user_id)
        )
        # 同步软删该报告生成的危害因素监测记录，避免来源丢失后残留孤儿台账
        await self.session.execute(
            update(OhHazardMonitor)
            .where(
                OhHazardMonitor.monitor_no.like(f"{report.report_no}-M%"),
                OhHazardMonitor.is_deleted.is_(False),
            )
            .values(is_deleted=True, updated_by=user_id)
        )
        await self._audit(
            "delete",
            resource_id=report_id,
            user_id=user_id,
            extra={"report_no": report.report_no},
        )
        return report
