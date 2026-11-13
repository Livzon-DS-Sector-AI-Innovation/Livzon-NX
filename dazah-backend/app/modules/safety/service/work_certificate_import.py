"""持证人员汇总表 Excel 批量导入：解析预览与证件台账落库。

面向《YYYY年持证人员汇总表》类台账：一个工作簿按证件种类拆分为多个子表
（管理人员/电焊/高处/受限空间/电工（高/低）/仪表/司炉工/水质化验/叉车/
压力容器/特种设备管理人员（A证）/起重），表头在第 1~2 行、列名各子表不一。

解析为纯结构化函数（不依赖数据库），便于单测；落库由
``CertificateImportService`` 承接：同类别内按证件号（无证件号按姓名）合并
文件内重复行（高低压电工同证号合并为一条），与库内已有记录匹配后
更新或新建，直接批量 session 操作（不走单条 create，避免逐行审计与 409）。

工作簿加载复用本模块 hazard_ledger_import 的 xls/xlsx + 合并单元格展开实现。
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import xlrd  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import SpecialWorkCertificate
from app.modules.safety.service.hazard_ledger_import import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_SIZE,
    SheetMatrix,
    load_workbook_matrices,
)
from app.modules.safety.service.work_certificate import compute_status
from app.modules.safety.service.work_permit_templates import (
    CERTIFICATE_CATEGORY_LABELS,
)
from app.platform.audit.service import record_audit_log

logger = logging.getLogger(__name__)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "MAX_UPLOAD_SIZE",
    "CertificateImportService",
    "ParsedCertificate",
    "SheetParseResult",
    "match_sheet_rule",
    "normalize_department",
    "parse_certificate_workbook",
    "parse_date_cell",
    "parse_sheet",
]

# ── 子表 → 证件类别规则（顺序敏感：特种设备管理人员须先于管理人员命中） ──


@dataclass(frozen=True)
class SheetCategoryRule:
    keywords: tuple[str, ...]
    category: str
    default_scope: str | None = None
    # 子表内统一补充的准操项目（如电工高/低压）；None 表示按行内列取值
    fixed_scope: bool = False


SHEET_RULES: tuple[SheetCategoryRule, ...] = (
    SheetCategoryRule(
        keywords=("特种设备", "A证"),
        category="special_equipment_management",
        default_scope="特种设备安全管理",
        fixed_scope=True,
    ),
    SheetCategoryRule(
        keywords=("管理人员",),
        category="hazmat_safety_manager",
    ),
    SheetCategoryRule(
        keywords=("焊",),
        category="welding_cutting",
        default_scope="焊接与热切割作业",
        fixed_scope=True,
    ),
    SheetCategoryRule(
        keywords=("高处",),
        category="high_altitude_maintenance",
        default_scope="高处作业",
        fixed_scope=True,
    ),
    SheetCategoryRule(
        keywords=("受限",),
        category="confined_space",
        default_scope="受限空间作业",
        fixed_scope=True,
    ),
    SheetCategoryRule(
        keywords=("高压", "电工（高", "电工(高"),
        category="electrician",
        default_scope="高压电工作业",
        fixed_scope=True,
    ),
    SheetCategoryRule(
        keywords=("低压", "电工（低", "电工(低"),
        category="electrician",
        default_scope="低压电工作业",
        fixed_scope=True,
    ),
    SheetCategoryRule(keywords=("电工",), category="electrician"),
    SheetCategoryRule(keywords=("仪表",), category="instrument"),
    SheetCategoryRule(keywords=("司炉",), category="boiler_operator"),
    SheetCategoryRule(keywords=("水质", "化验"), category="water_quality_analyst"),
    SheetCategoryRule(keywords=("叉车",), category="forklift"),
    SheetCategoryRule(
        keywords=("压力容器",),
        category="pressure_vessel",
        default_scope="压力容器作业",
        fixed_scope=True,
    ),
    SheetCategoryRule(
        keywords=("起重",),
        category="crane_operator",
        default_scope="起重机司机",
        fixed_scope=True,
    ),
)


def _canonical_sheet_key(text: str) -> str:
    """子表名归一比较键：去空白并统一全/半角括号。"""
    return re.sub(r"[\s（）()]+", "", text or "")


# 类别中文 label 归一键 → 类别 code（导出子表名回导时精确命中）
_LABEL_TO_CATEGORY: dict[str, str] = {
    _canonical_sheet_key(label): category
    for category, label in CERTIFICATE_CATEGORY_LABELS.items()
}


def match_sheet_rule(sheet_name: str) -> SheetCategoryRule | None:
    """子表名 → 类别规则。

    先按证件类别中文 label 精确匹配（导出文件的子表名即类别 label，
    保证导出台账再导入时类别 100% 准确，也覆盖「起重司索工」这类
    会被「起重」关键词误判的表名），未命中再走关键词规则。
    """
    normalized = _canonical_sheet_key(sheet_name)
    category = _LABEL_TO_CATEGORY.get(normalized)
    if category:
        return SheetCategoryRule(keywords=(normalized,), category=category)
    compact = re.sub(r"\s+", "", sheet_name or "")
    for rule in SHEET_RULES:
        if any(keyword in compact for keyword in rule.keywords):
            return rule
    return None


# ── 车间名称归一化（汇总表车间列常见数字简写/括号变体） ──

# 阿拉伯序号 → 中文序号（201-1 → 201一车间）
_SEQ_DIGITS = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五"}

# 数字车间简写：101 / 201一 / 201-1（可带「车间」尾缀）
_DEPT_NUMERIC_RE = re.compile(r"^(\d{2,4})(?:[-—/])?([一二三四五1-5])?(?:车间)?$")
# 括号变体：201二（多拉）→ 核心词归一 + 括号内容保留
_DEPT_PAREN_RE = re.compile(r"^([^（(]+)([（(][^）)]*[）)])$")


def normalize_department(raw: str | None) -> tuple[str | None, bool]:
    """归一化车间名称，返回 (归一值, 是否发生变化)。

    口径（对齐真实《持证人员汇总表》车间列写法）：
    - 数字简写补全：``101`` → ``101车间``、``201一`` → ``201一车间``、
      ``201-1`` → ``201一车间``（阿拉伯序号转中文）；
    - 括号内容是车间区分标识（201二车间实际存在多拉等多个车间），
      必须保留：``201二（多拉）`` → ``201二车间（多拉）``（括号统一全角）；
    - ``机修工``/``机修班长`` 等机修前缀统一 ``机修``（仅无括号时）；
    - 已是标准写法（``101车间``）不变；``动力科``/``热动站``/``QC``/
      ``102预混剂`` 等无法判断的保留原值（仅去空白）。

    仅内容变化计入 changed（去空白不算），供调用方把原始写法记入备注。
    """
    text = re.sub(r"[\s\u3000]+", "", raw or "")
    if not text:
        return None, False

    suffix = ""
    core = text
    paren = _DEPT_PAREN_RE.match(text)
    if paren:
        core = paren.group(1)
        inner = paren.group(2)[1:-1]
        if inner:
            suffix = f"（{inner}）"

    numeric = _DEPT_NUMERIC_RE.match(core)
    if numeric:
        number, seq = numeric.group(1), numeric.group(2) or ""
        seq = _SEQ_DIGITS.get(seq, seq)
        normalized = f"{number}{seq}车间{suffix}"
        return normalized, normalized != text

    if not suffix and core.startswith("机修") and core != "机修":
        return "机修", True

    return text, False


# ── 表头列名 → 字段 ──

COLUMN_LABELS: dict[str, str] = {
    "姓名": "person_name",
    "车间": "department",
    "部门/车间": "department",
    "部门": "department",
    "岗位": "position",
    "职务": "position",
    "初领日期": "issue_date",
    "取证日期": "issue_date",
    "发证日期": "issue_date",
    "领证日期": "issue_date",
    "有效日期": "expiry_date",
    "有效期": "expiry_date",
    "有效期（复审）": "expiry_date",
    "证书编号": "certificate_no",
    "高压证书编号": "certificate_no",
    "低压证书编号": "certificate_no",
    "复审日期": "review_date",
    "复审": "review_date",
    "备注": "note",
    "技能证书": "scope_extra",
    "等级": "scope_extra",
    "从业类别": "work_type",
    "证件类型": "cert_type",
}

# 车间列常见的纵向合并/留空表示"同上"；仅当该列存在合并单元格时已由
# _build_matrix 展开，此处不做盲目向下填充，避免把空车间误归到上一组。

_FOOTER_KEYWORDS = ("合计", "制表", "填表", "审核", "注：", "备注：")

_FIELD_LIMITS = {
    "person_name": 100,
    "department": 100,
    "certificate_no": 100,
    "qualification_scope": 2000,
    "remark": 2000,
}


def _fit(field_name: str, value: str | None) -> str | None:
    if value is None:
        return None
    limit = _FIELD_LIMITS.get(field_name)
    if limit and len(value) > limit:
        return value[: limit - 1] + "…"
    return value


# ── 单元格工具 ──


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _norm_label(value: Any) -> str:
    return re.sub(r"[\s\u3000]+", "", _cell_text(value))


def _parse_year_month(year: int, month: int, *, month_end: bool) -> date | None:
    try:
        if not month_end:
            return date(year, month, 1)
        if month == 12:
            return date(year, 12, 31)
        return date(year, month + 1, 1) - timedelta(days=1)
    except ValueError:
        return None


def parse_date_cell(value: Any, *, month_end: bool) -> date | None:
    """解析台账日期单元格；失败返回 None。

    支持：datetime/date 实例、Excel 串行数（41410）、误存为小数的
    "YYYY.MM"（2022.08，串行口径下小于 10000 与真实日期天然区分）、
    "2025.11.26"、"2013.7.12"、"2022..09.02"（双点容错）、"2017.05."
    （尾点）、"2028.05"（月精度，expiry 取月末 / issue 取月初）、
    "2025.11.26-2028.11.25"（区间取截止）。
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        serial = float(value)
        if 10000 <= serial < 2958465:  # Excel 1900 日期系（1927 年起）
            return _from_xldate(serial)
        if 1900 <= serial < 10000:  # 误存为小数的 "YYYY.MM" / "YYYY"
            year = int(serial)
            month = round((serial - year) * 100)
            if month == 0:
                return date(year, 12 if month_end else 1, 31 if month_end else 1)
            if 1 <= month <= 12:
                return _parse_year_month(year, month, month_end=month_end)
        return None
    text = str(value).strip()
    if not text or text in {"-", "—", "无"}:
        return None
    # 区间 "A-B" 取截止端
    for sep in ("—", "~", "-"):
        if sep in text:
            right = text.rsplit(sep, 1)[1].strip()
            if right:
                text = right
            break
    text = re.sub(r"\.{2,}", ".", text)
    parts = [p for p in text.split(".") if p]
    try:
        if len(parts) >= 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            return _parse_year_month(int(parts[0]), int(parts[1]), month_end=month_end)
    except ValueError:
        return None
    return None


def _from_xldate(serial: float) -> date | None:
    try:
        parsed = xlrd.xldate_as_datetime(serial, 0)
    except Exception:
        return None
    if isinstance(parsed, datetime):
        return parsed.date()
    return None


# ── 解析结果结构 ──


@dataclass
class ParsedCertificate:
    sheet: str
    row_index: int  # Excel 1-based 行号（用于错误提示）
    person_name: str
    certificate_category: str
    certificate_no: str | None = None
    department: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    qualification_scope: str | None = None
    remark: str | None = None

    @property
    def merge_key(self) -> tuple[str, str]:
        if self.certificate_no:
            return (self.certificate_category, f"no:{self.certificate_no}")
        return (self.certificate_category, f"name:{self.person_name}")


@dataclass
class SheetParseResult:
    name: str
    category: str
    category_label: str
    records: list[ParsedCertificate] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_preview(self, sample_limit: int = 3) -> dict[str, Any]:
        return {
            "sheet": self.name,
            "certificate_category": self.category,
            "certificate_category_label": self.category_label,
            "row_count": len(self.records),
            "sample": [
                {
                    "person_name": item.person_name,
                    "certificate_no": item.certificate_no,
                    "department": item.department,
                    "issue_date": item.issue_date.isoformat()
                    if item.issue_date
                    else None,
                    "expiry_date": item.expiry_date.isoformat()
                    if item.expiry_date
                    else None,
                    "qualification_scope": item.qualification_scope,
                }
                for item in self.records[:sample_limit]
            ],
            "errors": self.errors[:5],
        }


# ── 子表解析 ──


def _find_header_row(matrix: SheetMatrix) -> int | None:
    for row_index, row in enumerate(matrix.rows[:10]):
        if "姓名" in {_norm_label(value) for value in row}:
            return row_index
    return None


def _map_columns(matrix: SheetMatrix, header_row: int) -> dict[str, list[int]]:
    """表头列名 → 字段的列号列表（同类标签可出现多列，如技能证书+等级）。"""
    columns: dict[str, list[int]] = {}
    for col_index, value in enumerate(matrix.rows[header_row]):
        field_name = COLUMN_LABELS.get(_norm_label(value))
        if field_name:
            columns.setdefault(field_name, []).append(col_index)
    return columns


def parse_sheet(matrix: SheetMatrix, rule: SheetCategoryRule) -> SheetParseResult:
    result = SheetParseResult(
        name=matrix.name,
        category=rule.category,
        category_label=CERTIFICATE_CATEGORY_LABELS.get(rule.category, ""),
    )
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
        name = _cell_text(row[columns["person_name"][0]])
        if not name:
            joined = "".join(_cell_text(value) for value in row)
            if not joined:
                continue  # 整行空
            if any(keyword in joined for keyword in _FOOTER_KEYWORDS):
                continue  # 尾注/制表行
            result.errors.append({"row": excel_row, "reason": "缺少姓名，已跳过"})
            continue

        department: str | None = None
        department_note: str | None = None
        if "department" in columns:
            raw_department = _cell_text(row[columns["department"][0]]) or None
            if raw_department:
                department, dept_changed = normalize_department(raw_department)
                if dept_changed:
                    # 归一化改变了原表写法（如 201二（多拉）→201二车间），留痕备查
                    department_note = f"车间原值{raw_department}"

        expiry_raw = ""
        expiry_date: date | None = None
        if "expiry_date" in columns:
            expiry_raw = _cell_text(row[columns["expiry_date"][0]])
            expiry_date = parse_date_cell(expiry_raw, month_end=True)
            if expiry_date is None:
                # 文本化失败的原始值（如 Excel 串行数）再试一次
                expiry_date = parse_date_cell(
                    row[columns["expiry_date"][0]], month_end=True
                )
        if expiry_date is None:
            result.errors.append(
                {
                    "row": excel_row,
                    "reason": f"有效日期无法解析：{expiry_raw or '空'}，已跳过",
                }
            )
            continue

        issue_date: date | None = None
        if "issue_date" in columns:
            issue_date = parse_date_cell(row[columns["issue_date"][0]], month_end=False)

        certificate_no = None
        if "certificate_no" in columns:
            certificate_no = (
                _fit(
                    "certificate_no",
                    _cell_text(row[columns["certificate_no"][0]]) or None,
                )
                or None
            )

        scope_parts: list[str] = []
        if rule.default_scope and rule.fixed_scope:
            scope_parts.append(rule.default_scope)
        if "scope_extra" in columns:
            for col in columns["scope_extra"]:
                extra = _cell_text(row[col])
                if extra:
                    scope_parts.append(extra)
        if "work_type" in columns or "cert_type" in columns:
            work_type = ""
            cert_type = ""
            if "work_type" in columns:
                work_type = _cell_text(row[columns["work_type"][0]])
            if "cert_type" in columns:
                cert_type = _cell_text(row[columns["cert_type"][0]])
            combined = " ".join(part for part in (work_type, cert_type) if part)
            if combined:
                scope_parts.append(combined)
        scope = "、".join(dict.fromkeys(scope_parts)) or None
        scope = _fit("qualification_scope", scope)

        remark_parts: list[str] = []
        if department_note:
            remark_parts.append(department_note)
        if "position" in columns:
            position = _cell_text(row[columns["position"][0]])
            if position:
                remark_parts.append(f"岗位{position}")
        if "review_date" in columns:
            review = _cell_text(row[columns["review_date"][0]])
            if review:
                review = re.sub(r"\.{2,}", ".", review)
                remark_parts.append(f"复审{review}")
        if "note" in columns:
            note = _cell_text(row[columns["note"][0]])
            if note:
                remark_parts.append(note)
        remark = _fit("remark", "；".join(remark_parts) or None)

        result.records.append(
            ParsedCertificate(
                sheet=matrix.name,
                row_index=excel_row,
                person_name=_fit("person_name", name) or name,
                certificate_category=rule.category,
                certificate_no=certificate_no,
                department=_fit("department", department),
                issue_date=issue_date,
                expiry_date=expiry_date,
                qualification_scope=scope,
                remark=remark,
            )
        )
    return result


def merge_records(records: list[ParsedCertificate]) -> list[ParsedCertificate]:
    """同类别内同证件号（无证件号按姓名）合并为一条。

    准操项目并集（"、"连接）、发证/有效期取更早值（保守口径）、
    其余成员的有效期差异写入备注。
    """
    merged: dict[tuple[str, str], ParsedCertificate] = {}
    order: list[tuple[str, str]] = []
    for record in records:
        key = record.merge_key
        base = merged.get(key)
        if base is None:
            merged[key] = record
            order.append(key)
            continue
        scopes = [
            part
            for part in (base.qualification_scope, record.qualification_scope)
            if part
        ]
        base.qualification_scope = _fit(
            "qualification_scope", "、".join(dict.fromkeys(scopes)) or None
        )
        if base.issue_date is None or (
            record.issue_date and record.issue_date < base.issue_date
        ):
            base.issue_date = record.issue_date
        # 有效期取更早值（保守），被替换/更晚的一侧记入备注备查
        if record.expiry_date is not None:
            if base.expiry_date is None or record.expiry_date < base.expiry_date:
                if base.expiry_date is not None:
                    note = f"{base.sheet}有效期至{base.expiry_date.isoformat()}"
                    base.remark = _fit(
                        "remark",
                        "；".join(part for part in (base.remark, note) if part),
                    )
                base.expiry_date = record.expiry_date
            elif record.expiry_date > base.expiry_date:
                note = f"{record.sheet}有效期至{record.expiry_date.isoformat()}"
                base.remark = _fit(
                    "remark",
                    "；".join(part for part in (base.remark, note) if part),
                )
        base.department = base.department or record.department
    return [merged[key] for key in order]


def parse_certificate_workbook(content: bytes, filename: str) -> dict[str, Any]:
    """解析工作簿：每个子表映射到证件类别并解析行；未识别子表列入跳过。"""
    matrices = load_workbook_matrices(content, filename)
    sheets: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for matrix in matrices:
        rule = match_sheet_rule(matrix.name)
        if rule is None:
            skipped.append({"sheet": matrix.name, "reason": "未识别的子表"})
            continue
        result = parse_sheet(matrix, rule)
        sheets.append(result.to_preview())
    return {"sheets": sheets, "skipped_sheets": skipped}


# ── 落库服务 ──


class CertificateImportService:
    """持证人员汇总表导入：解析预览与证件台账 upsert。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def preview(self, filename: str, content: bytes) -> dict[str, Any]:
        if len(content) > MAX_UPLOAD_SIZE:
            raise ValueError("文件大小超过 10MB 限制")
        return parse_certificate_workbook(content, filename)

    async def commit(
        self,
        filename: str,
        content: bytes,
        selected_sheets: list[str] | None,
        user: uuid.UUID | None,
    ) -> dict[str, Any]:
        if len(content) > MAX_UPLOAD_SIZE:
            raise ValueError("文件大小超过 10MB 限制")
        matrices = load_workbook_matrices(content, filename)
        selected = set(selected_sheets) if selected_sheets else None
        source_filename = os.path.basename(filename or "")

        created = 0
        updated = 0
        unchanged = 0
        row_errors: list[dict[str, Any]] = []
        skipped_sheets: list[dict[str, str]] = []

        records: list[ParsedCertificate] = []
        for matrix in matrices:
            rule = match_sheet_rule(matrix.name)
            if rule is None:
                skipped_sheets.append({"sheet": matrix.name, "reason": "未识别的子表"})
                continue
            if selected is not None and matrix.name not in selected:
                continue
            result = parse_sheet(matrix, rule)
            row_errors.extend(
                {"sheet": matrix.name, **error} for error in result.errors
            )
            records.extend(result.records)

        merged = merge_records(records)

        existing_certs = await self._load_existing()
        by_no_category: dict[tuple[str, str], SpecialWorkCertificate] = {}
        by_name_category: dict[tuple[str, str], SpecialWorkCertificate] = {}
        for cert in existing_certs:
            if cert.certificate_no:
                by_no_category.setdefault(
                    (cert.certificate_no, cert.certificate_category), cert
                )
            by_name_category.setdefault(
                (cert.person_name, cert.certificate_category), cert
            )

        archive_path = self._archive_file(source_filename, content)

        for record in merged:
            matched: SpecialWorkCertificate | None = None
            if record.certificate_no:
                matched = by_no_category.get(
                    (record.certificate_no, record.certificate_category)
                )
            if matched is None:
                matched = by_name_category.get(
                    (record.person_name, record.certificate_category)
                )
            if matched is None:
                cert = SpecialWorkCertificate(
                    person_name=record.person_name,
                    certificate_category=record.certificate_category,
                    certificate_no=record.certificate_no,
                    department=record.department,
                    issue_date=record.issue_date,
                    expiry_date=record.expiry_date,
                    qualification_scope=record.qualification_scope,
                    remark=record.remark,
                    status=compute_status(record.expiry_date),
                    created_by=user,
                    updated_by=user,
                )
                self.session.add(cert)
                if record.certificate_no:
                    by_no_category[
                        (record.certificate_no, record.certificate_category)
                    ] = cert
                by_name_category.setdefault(
                    (record.person_name, record.certificate_category), cert
                )
                created += 1
                continue
            if self._apply_update(matched, record, user):
                updated += 1
            else:
                unchanged += 1

        await self.session.flush()
        await self._audit_import(
            user,
            filename=source_filename,
            created=created,
            updated=updated,
            unchanged=unchanged,
        )
        return {
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "total_parsed": len(merged),
            "skipped_sheets": skipped_sheets,
            "row_errors": row_errors[:10],
            "archive_path": archive_path,
        }

    async def _load_existing(self) -> list[SpecialWorkCertificate]:
        result = await self.session.execute(
            select(SpecialWorkCertificate).where(
                SpecialWorkCertificate.is_deleted.is_(False)
            )
        )
        return list(result.scalars().all())

    def _apply_update(
        self,
        cert: SpecialWorkCertificate,
        record: ParsedCertificate,
        user: uuid.UUID | None,
    ) -> bool:
        """以台账为准更新已有记录；无变化返回 False。"""
        changed = False
        if cert.person_name != record.person_name:
            cert.person_name = record.person_name
            changed = True
        if record.department and cert.department != record.department:
            cert.department = record.department
            changed = True
        if record.certificate_no and (cert.certificate_no != record.certificate_no):
            cert.certificate_no = record.certificate_no
            changed = True
        if record.issue_date and cert.issue_date != record.issue_date:
            cert.issue_date = record.issue_date
            changed = True
        if cert.expiry_date != record.expiry_date:
            cert.expiry_date = record.expiry_date
            changed = True
        scopes = [
            part
            for part in (cert.qualification_scope, record.qualification_scope)
            if part
        ]
        merged_scope = "、".join(dict.fromkeys(scopes)) or None
        if merged_scope != cert.qualification_scope:
            cert.qualification_scope = _fit("qualification_scope", merged_scope)
            changed = True
        if record.remark:
            existing_remark = cert.remark or ""
            if record.remark not in existing_remark:
                cert.remark = _fit(
                    "remark",
                    "；".join(
                        part for part in (existing_remark, record.remark) if part
                    ),
                )
                changed = True
        new_status = compute_status(
            cert.expiry_date, "revoked" if cert.status == "revoked" else ""
        )
        if cert.status != new_status:
            cert.status = new_status
            changed = True
        if changed:
            cert.updated_by = user
        return changed

    def _archive_file(self, filename: str, content: bytes) -> str:
        upload_dir = os.path.join("uploads", "safety", "certificate-import")
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
        created: int,
        updated: int,
        unchanged: int,
    ) -> None:
        try:
            await record_audit_log(
                self.session,
                action="import",
                user_id=user,
                resource_type="special_work_certificate",
                extra={
                    "filename": filename,
                    "created": created,
                    "updated": updated,
                    "unchanged": unchanged,
                },
            )
        except Exception:  # pragma: no cover - 审计失败不阻塞导入
            logger.exception("持证人员汇总表导入审计写入失败")
