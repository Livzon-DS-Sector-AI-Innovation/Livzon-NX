"""监护人考试合格名单 Excel 批量导入：解析预览与整表替换落库。

面向《YYYY年MM月监护人考试合格名单.xlsx》类工作簿：同一批人通常同时出现在
「汇总/Worksheet/按车间分表」多个子表中，列结构统一为
姓名/联系电话/部门/岗位/分数/题目数量/考试名称/考试时长/考试时间，
车间以「部门」列取值为准（分表标题与部门列可能不一致，如 QC→实验室）。

解析为纯结构化函数（不依赖数据库），便于单测；落库由
``GuardianImportService`` 承接：跨子表按（姓名+电话，缺电话按姓名+车间）
合并重复人员（保留最新一次考试），随后**整表替换**现有名单（软删全部
旧行 + 批量插入，单事务），并写审计、归档原文件。

工作簿加载复用本模块 hazard_ledger_import 的 xls/xlsx + 合并单元格展开实现，
日期解析复用 work_certificate_import 的 parse_date_cell。
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import GuardianRoster
from app.modules.safety.service.hazard_ledger_import import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_SIZE,
    SheetMatrix,
    load_workbook_matrices,
)
from app.modules.safety.service.work_certificate_import import parse_date_cell
from app.platform.audit.service import record_audit_log

logger = logging.getLogger(__name__)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "MAX_UPLOAD_SIZE",
    "GuardianImportService",
    "ParsedGuardian",
    "SheetParseResult",
    "merge_records",
    "parse_guardian_workbook",
    "parse_sheet",
]


# ── 表头列名 → 字段（中文别名自动识别） ──

COLUMN_LABELS: dict[str, str] = {
    "姓名": "person_name",
    "监护人姓名": "person_name",
    "人员姓名": "person_name",
    "名字": "person_name",
    "车间": "workshop",
    "部门": "workshop",
    "所属车间": "workshop",
    "所属部门": "workshop",
    "车间/部门": "workshop",
    "部门/车间": "workshop",
    "单位": "workshop",
    "联系电话": "phone",
    "电话": "phone",
    "手机": "phone",
    "手机号": "phone",
    "手机号码": "phone",
    "联系方式": "phone",
    "岗位": "position",
    "职务": "position",
    "工种": "position",
    "分数": "score",
    "成绩": "score",
    "考试分数": "score",
    "考试成绩": "score",
    "考试得分": "score",
    "考试名称": "exam_name",
    "考试": "exam_name",
    "考试时间": "exam_date",
    "考试日期": "exam_date",
    "合格日期": "exam_date",
    "考试合格时间": "exam_date",
    "合格时间": "exam_date",
    "备注": "remark",
}

# 「汇总」类子表名（同名人员在不同子表重复，默认数据源优先取这类子表）
_SUMMARY_SHEET_KEYWORDS = ("汇总", "总表", "合计表")

_FOOTER_KEYWORDS = ("合计", "制表", "填表", "审核", "注：", "备注：")

_FIELD_LIMITS = {
    "person_name": 100,
    "workshop": 100,
    "phone": 32,
    "position": 100,
    "exam_name": 100,
    "remark": 200,
}


def _fit(field_name: str, value: str | None) -> str | None:
    if value is None:
        return None
    limit = _FIELD_LIMITS.get(field_name)
    if limit and len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _norm_label(value: Any) -> str:
    return re.sub(r"[\s\u3000]+", "", _cell_text(value))


def _norm_person_name(value: str) -> str:
    """姓名列常见全角/连续空格（如「刘  冬」）压缩为单空格。"""
    return re.sub(r"[\s\u3000]+", " ", value).strip()


def _parse_score(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        score = int(value)
        return score if 0 <= score <= 1000 else None
    # 文本必须整体是数字（可带 %/分），避免「103车间」这类合并单元格
    # 展开文本被提取出 103 之类的假分数
    text = str(value).strip().rstrip("%分")
    if not re.fullmatch(r"\d{1,4}(\.\d+)?", text):
        return None
    try:
        score = int(float(text))
    except ValueError:
        return None
    return score if 0 <= score <= 1000 else None


_ISO_DATE_RE = re.compile(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")


def _parse_exam_date(value: Any) -> date | None:
    """考试时间列解析：优先 ISO/中文日期文本（源表常存为文本
    「2026-10-22 00:00:00」），其余格式（点分/串行数）复用 parse_date_cell。
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    match = _ISO_DATE_RE.match(str(value).strip())
    if match:
        try:
            return date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            return None
    return parse_date_cell(value, month_end=False)


# ── 解析结果结构 ──


@dataclass
class ParsedGuardian:
    sheet: str
    row_index: int  # Excel 1-based 行号（用于错误提示）
    person_name: str
    workshop: str
    phone: str | None = None
    position: str | None = None
    score: int | None = None
    exam_name: str | None = None
    exam_date: date | None = None
    remark: str | None = None

    @property
    def merge_key(self) -> tuple[str, str]:
        if self.phone:
            return ("phone", f"{self.person_name}|{self.phone}")
        return ("workshop", f"{self.person_name}|{self.workshop}")


@dataclass
class SheetParseResult:
    name: str
    records: list[ParsedGuardian] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_preview(self, sample_limit: int = 3) -> dict[str, Any]:
        workshops = list(dict.fromkeys(item.workshop for item in self.records))
        return {
            "sheet": self.name,
            "row_count": len(self.records),
            "workshops": workshops[:20],
            "sample": [
                {
                    "person_name": item.person_name,
                    "workshop": item.workshop,
                    "phone": item.phone,
                    "position": item.position,
                    "score": item.score,
                    "exam_date": item.exam_date.isoformat() if item.exam_date else None,
                }
                for item in self.records[:sample_limit]
            ],
            "errors": self.errors[:5],
        }


# ── 子表解析 ──


def _find_header_row(matrix: SheetMatrix) -> int | None:
    for row_index, row in enumerate(matrix.rows[:10]):
        labels = {_norm_label(value) for value in row}
        if "姓名" not in labels:
            continue
        mapped = {COLUMN_LABELS[label] for label in labels if label in COLUMN_LABELS}
        if len(mapped) >= 2:
            return row_index
    return None


def _map_columns(matrix: SheetMatrix, header_row: int) -> dict[str, int]:
    columns: dict[str, int] = {}
    for col_index, value in enumerate(matrix.rows[header_row]):
        field_name = COLUMN_LABELS.get(_norm_label(value))
        if field_name and field_name not in columns:
            columns[field_name] = col_index
    return columns


def parse_sheet(matrix: SheetMatrix) -> SheetParseResult:
    result = SheetParseResult(name=matrix.name)
    header_row = _find_header_row(matrix)
    if header_row is None:
        result.errors.append({"row": 0, "reason": "未找到包含「姓名」的表头行"})
        return result
    columns = _map_columns(matrix, header_row)
    if "person_name" not in columns:
        result.errors.append({"row": 0, "reason": "表头缺少「姓名」列"})
        return result

    for row_index in range(header_row + 1, len(matrix.rows)):
        row = matrix.rows[row_index]
        excel_row = row_index + 1
        name = _norm_person_name(_cell_text(row[columns["person_name"]]))
        if not name:
            joined = "".join(_cell_text(value) for value in row)
            if not joined:
                continue  # 整行空
            if any(keyword in joined for keyword in _FOOTER_KEYWORDS):
                continue  # 尾注/制表行
            result.errors.append({"row": excel_row, "reason": "缺少姓名，已跳过"})
            continue

        def col_text(field_name: str) -> str:
            col = columns.get(field_name)
            if col is None or col >= len(row):
                return ""
            return _cell_text(row[col])

        score = _parse_score(
            row[columns["score"]]
            if "score" in columns and columns["score"] < len(row)
            else None
        )
        # 车间分组标题行两种形态：
        # 1) 标题独占首列，其余业务列全空（普通写法）；
        # 2) 标题跨列合并，加载时合并展开后每列都是同一文本——
        #    特征是 ≥3 个单元格等于姓名列文本（真实人员行不会如此）。
        raw_name_text = _cell_text(row[columns["person_name"]])
        repeat_count = sum(1 for value in row if _cell_text(value) == raw_name_text)
        business_values = (
            col_text("workshop")
            + col_text("phone")
            + col_text("position")
            + col_text("exam_name")
            + col_text("exam_date")
        )
        if repeat_count >= 3 or (not business_values and score is None):
            continue  # 分组标题行，静默跳过

        workshop = _fit("workshop", col_text("workshop") or None)
        if not workshop:
            result.errors.append(
                {
                    "row": excel_row,
                    "reason": "缺少车间/部门，已跳过",
                }
            )
            continue

        phone = _fit("phone", col_text("phone") or None)
        position = _fit("position", col_text("position") or None)
        exam_name = _fit("exam_name", col_text("exam_name") or None)
        exam_date: date | None = None
        if "exam_date" in columns and columns["exam_date"] < len(row):
            exam_date = _parse_exam_date(row[columns["exam_date"]])
        remark = _fit("remark", col_text("remark") or None)

        result.records.append(
            ParsedGuardian(
                sheet=matrix.name,
                row_index=excel_row,
                person_name=_fit("person_name", name) or name,
                workshop=workshop,
                phone=phone,
                position=position,
                score=score,
                exam_name=exam_name,
                exam_date=exam_date,
                remark=remark,
            )
        )
    return result


def merge_records(
    records: list[ParsedGuardian],
) -> tuple[list[ParsedGuardian], int]:
    """跨子表合并重复人员：键为（姓名+电话），缺电话按（姓名+车间）。

    空字段互补填充；考试信息（考试日期/分数/考试名称）取最新一次考试。
    返回（合并后列表，被合并掉的重复行数）。
    """
    merged: dict[tuple[str, str], ParsedGuardian] = {}
    order: list[tuple[str, str]] = []
    duplicates = 0
    for record in records:
        key = record.merge_key
        base = merged.get(key)
        if base is None:
            merged[key] = record
            order.append(key)
            continue
        duplicates += 1
        for field_name in ("phone", "position", "remark"):
            if getattr(base, field_name) is None:
                setattr(base, field_name, getattr(record, field_name))
        newer = record.exam_date is not None and (
            base.exam_date is None or record.exam_date > base.exam_date
        )
        if newer:
            base.exam_date = record.exam_date
            base.score = record.score
            base.exam_name = record.exam_name
        elif record.score is not None and base.score is None:
            base.score = record.score
            base.exam_name = base.exam_name or record.exam_name
    return [merged[key] for key in order], duplicates


def _pick_default_sheets(parsed: list[SheetParseResult]) -> set[str]:
    """默认勾选：优先「汇总」类子表，否则取行数最多的子表。"""
    candidates = [item for item in parsed if item.records]
    if not candidates:
        return set()
    for item in candidates:
        if any(keyword in (item.name or "") for keyword in _SUMMARY_SHEET_KEYWORDS):
            return {item.name}
    best = max(candidates, key=lambda item: len(item.records))
    return {best.name}


def parse_guardian_workbook(content: bytes, filename: str) -> dict[str, Any]:
    """解析工作簿：每个子表独立解析行；全部子表均列入预览（可勾选）。"""
    matrices = load_workbook_matrices(content, filename)
    parsed = [parse_sheet(matrix) for matrix in matrices]
    defaults = _pick_default_sheets(parsed)
    sheets = []
    for item in parsed:
        preview = item.to_preview()
        preview["default_selected"] = item.name in defaults
        sheets.append(preview)
    return {"sheets": sheets}


# ── 落库服务 ──


class GuardianImportService:
    """监护人名单导入：解析预览与整表替换。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def preview(
        self, filename: str, content: bytes, selected_sheets: list[str] | None
    ) -> dict[str, Any]:
        if len(content) > MAX_UPLOAD_SIZE:
            raise ValueError("文件大小超过 10MB 限制")
        data = parse_guardian_workbook(content, filename)
        records, duplicates, _row_errors = self._collect_records(
            content, filename, selected_sheets
        )
        current_total = await self.session.scalar(
            select(func.count(GuardianRoster.id)).where(
                GuardianRoster.is_deleted.is_(False)
            )
        )
        data["duplicate_across_sheets"] = duplicates
        data["current_total"] = current_total or 0
        data["merged_total"] = len(records)
        return data

    async def commit(
        self,
        filename: str,
        content: bytes,
        selected_sheets: list[str] | None,
        user: uuid.UUID | None,
    ) -> dict[str, Any]:
        if len(content) > MAX_UPLOAD_SIZE:
            raise ValueError("文件大小超过 10MB 限制")
        records, duplicates, row_errors = self._collect_records(
            content, filename, selected_sheets
        )
        source_filename = os.path.basename(filename or "")

        replaced = await self.session.scalar(
            select(func.count(GuardianRoster.id)).where(
                GuardianRoster.is_deleted.is_(False)
            )
        )
        replaced = replaced or 0
        await self.session.execute(
            update(GuardianRoster)
            .where(GuardianRoster.is_deleted.is_(False))
            .values(is_deleted=True, updated_by=user)
        )
        for record in records:
            self.session.add(
                GuardianRoster(
                    person_name=record.person_name,
                    workshop=record.workshop,
                    phone=record.phone,
                    position=record.position,
                    score=record.score,
                    exam_name=record.exam_name,
                    exam_date=record.exam_date,
                    remark=record.remark,
                    source_file=source_filename or None,
                    created_by=user,
                    updated_by=user,
                )
            )
        await self.session.flush()

        archive_path = self._archive_file(source_filename, content)
        await self._audit_import(
            user,
            filename=source_filename,
            replaced=replaced,
            imported=len(records),
            duplicates_merged=duplicates,
        )
        return {
            "replaced": replaced,
            "imported": len(records),
            "duplicates_merged": duplicates,
            "skipped_sheets": [],
            "row_errors": row_errors[:10],
            "archive_path": archive_path,
        }

    def _collect_records(
        self,
        content: bytes,
        filename: str,
        selected_sheets: list[str] | None,
    ) -> tuple[list[ParsedGuardian], int, list[dict[str, Any]]]:
        """解析（可仅选部分子表）并跨子表合并重复人员。"""
        matrices = load_workbook_matrices(content, filename)
        selected = set(selected_sheets) if selected_sheets else None
        records: list[ParsedGuardian] = []
        row_errors: list[dict[str, Any]] = []
        for matrix in matrices:
            if selected is not None and matrix.name not in selected:
                continue
            result = parse_sheet(matrix)
            row_errors.extend(
                {"sheet": matrix.name, **error} for error in result.errors
            )
            records.extend(result.records)
        merged, duplicates = merge_records(records)
        return merged, duplicates, row_errors

    def _archive_file(self, filename: str, content: bytes) -> str:
        upload_dir = os.path.join("uploads", "safety", "guardian-import")
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = re.sub(
            r'[\\/:*?"<>|]', "_", os.path.basename(filename) or "import.xls"
        )
        stamped = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
        path = os.path.join(upload_dir, stamped)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    async def _audit_import(
        self,
        user: uuid.UUID | None,
        *,
        filename: str,
        replaced: int,
        imported: int,
        duplicates_merged: int,
    ) -> None:
        try:
            await record_audit_log(
                self.session,
                action="import",
                user_id=user,
                resource_type="guardian_roster",
                extra={
                    "filename": filename,
                    "replaced": replaced,
                    "imported": imported,
                    "duplicates_merged": duplicates_merged,
                },
            )
        except Exception:  # pragma: no cover - 审计失败不阻塞导入
            logger.exception("监护人名单导入审计写入失败")
