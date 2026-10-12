"""设备台账 Excel 导入。

按工厂标准台账列（设备编号/设备名称/规格型号/技术参数/生产厂家/
出厂日期/出厂编号/入厂日期/安装地点/备注）解析 .xlsx 并按设备编号
增量导入：已存在则更新台账字段，否则新建（可暂不挂分类）。

兼容真实台账的常见形态：
- 合并单元格：合并区域的锚点值填充到区域内所有行；
- 同一设备编号占多行：按编号分组合并取值（一般列取首个非空，
  技术参数/备注按行拼接去重）；
- 日期支持 Excel 日期单元格、日期序列号（如 46023）、年.月数值
  （2017.11）与 2024-05-01 / 2024/5/1 / 2024.5.1 / 2024年5月1日 /
  2024年5月 等写法，「-」「无」等占位符视为无日期；
- 安装地点按名称匹配位置树，匹配不上自动新建位置。

数据质量容错：字段缺失（编号/名称为空）或日期无法解析的行不再
拒收，照常导入并把问题原文记入 data_issue_note，页面标红提示
人工修正（在编辑抽屉保存后清除）。
"""
from __future__ import annotations

import hashlib
import io
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment import repository as repo
from app.modules.equipment.models.equipment import Location

# 台账模板列（序号仅占位，导入时忽略）
LEDGER_COLUMNS = [
    "设备编号",
    "设备名称",
    "规格型号",
    "技术参数",
    "生产厂家",
    "出厂日期",
    "出厂编号",
    "入厂日期",
    "安装地点",
    "备注",
]

_TEMPLATE_EXAMPLE_ROW = [
    "SB-0001",
    "发酵罐",
    "PJ-500L 不锈钢",
    "功率：3kW；容积：500L",
    "温州设备厂",
    "2024-05-01",
    "CC-2024-118",
    "2024-06-15",
    "201二车间",
    "示例行，导入前请删除",
]

MAX_IMPORT_ROWS = 1000

# 字段长度上限与 EquipmentCreate 保持一致
_LEN_LIMITS = {
    "equipment_no": 50,
    "name": 200,
    "model": 100,
    "manufacturer": 200,
    "factory_no": 100,
}

_DATE_PATTERNS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d")
# Excel 日期序列号区间：1954-01-01 ~ 2064-01-24，覆盖台账合理年份
_EXCEL_SERIAL_MIN = 20000
_EXCEL_SERIAL_MAX = 60000
_EXCEL_EPOCH = date(1899, 12, 30)
# 台账常见的「无日期」占位符
_DATE_PLACEHOLDERS = {"-", "—", "–", "―", "/", "无", "不详", "不祥", "未知"}
_YEAR_MONTH_PATTERN = re.compile(r"^(\d{4})\s*[.\-/年]\s*(\d{1,2})月?$")
_YEAR_MONTH_DAY_PATTERN = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?$")

# 同编号多行合并时按行拼接的列（技术参数/备注）
_CONCAT_FIELD_NAMES = {"技术参数", "备注"}


def _from_year_month_number(value: float) -> date | None:
    """数值型「年.月」（如 2017.11）→ 当月 1 日。

    Excel 把 2017.11 存为数值 2017.11；尾零月份（2012.10）会被存成
    2012.1，按小数位×100 还原为 10 月——与两位月份书写习惯一致。
    纯整数年份视为当年 1 月。
    """
    if not 1900 <= value <= 2100:
        return None
    year = int(value)
    month = round((value - year) * 100)
    if month == 0:
        return date(year, 1, 1)
    if 1 <= month <= 12:
        return date(year, month, 1)
    return None


def parse_date_cell(value: Any) -> date | None:
    """解析出厂/入厂日期单元格；空返回 None，无法识别抛 ValueError。

    支持真日期单元格、Excel 日期序列号（数字）、8 位 YYYYMMDD、
    以及常见分隔符文本与「2024年5月1日 / 2024年5月」写法
    （月份粒度取当月 1 日）。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        raise ValueError(f"日期格式无法识别：{value}")
    if isinstance(value, (int, float)):
        if isinstance(value, int) and 19000101 <= value <= 29991231:
            try:
                return datetime.strptime(str(value), "%Y%m%d").date()
            except ValueError:
                pass
        year_month = _from_year_month_number(float(value))
        if year_month is not None:
            return year_month
        serial = int(value)
        if _EXCEL_SERIAL_MIN <= serial <= _EXCEL_SERIAL_MAX:
            return _EXCEL_EPOCH + timedelta(days=serial)
        raise ValueError(
            f"日期数值无法识别：{value}（应为 Excel 日期或 2024-05-01、2017.11 等写法）"
        )
    text = str(value).strip()
    if text in _DATE_PLACEHOLDERS:
        return None
    text = text.rstrip("。.、，,")
    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    year_month_day = _YEAR_MONTH_DAY_PATTERN.match(text)
    if year_month_day:
        return date(
            int(year_month_day.group(1)),
            int(year_month_day.group(2)),
            int(year_month_day.group(3)),
        )
    year_month = _YEAR_MONTH_PATTERN.match(text)
    if year_month:
        return date(int(year_month.group(1)), int(year_month.group(2)), 1)
    raise ValueError(
        f"日期格式无法识别：{text}（支持 2024-05-01 / 2024/5/1 / 2024.5.1 / "
        f"2024年5月1日 / 2024年5月 / 2017.11 及 Excel 日期单元格，"
        f"“-”视为无日期）"
    )


def parse_tech_params_cell(value: Any) -> dict[str, str] | None:
    """技术参数文本（如「功率：3kW；容积：500L」）→ JSON 对象。

    按 ；/; 换行拆分后逐段取「名：值」；无分隔符的段落以
    「参数N」为名保留原文，避免导入时丢内容。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    fragments = re.split(r"[；;\n]+", text)
    params: dict[str, str] = {}
    auto_index = 0
    for fragment in fragments:
        fragment = fragment.strip()
        if not fragment:
            continue
        match = re.match(r"^([^:=：]+)[:：=](.*)$", fragment)
        if match:
            params[match.group(1).strip()] = match.group(2).strip()
        else:
            auto_index += 1
            params[f"参数{auto_index}"] = fragment
    return params or None


def build_ledger_template() -> bytes:
    """生成含表头与示例行的导入模板。"""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "设备台账"
    sheet.append(["序号", *LEDGER_COLUMNS])
    sheet.append([1, *_TEMPLATE_EXAMPLE_ROW])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_header(value: Any) -> str:
    return _cell_text(value).replace(" ", "").replace("\u3000", "")


def _collect_location_names(locations: list[Location]) -> dict[str, uuid.UUID]:
    """位置树名称 → id（同名时先遍历者优先，导入按名称精确匹配）。"""
    name_map: dict[str, uuid.UUID] = {}

    def walk(nodes: list[Location]) -> None:
        for node in nodes:
            if node.name not in name_map:
                name_map[node.name] = node.id
            children = getattr(node, "children", None) or []
            walk(children)

    walk(locations)
    return name_map


def _merged_value_map(sheet: Any) -> dict[tuple[int, int], Any]:
    """合并单元格锚点值 → 区域内所有 (行, 列) 的填充映射。"""
    fill: dict[tuple[int, int], Any] = {}
    for cell_range in sheet.merged_cells.ranges:
        anchor = sheet.cell(cell_range.min_row, cell_range.min_col).value
        for row in range(cell_range.min_row, cell_range.max_row + 1):
            for col in range(cell_range.min_col, cell_range.max_col + 1):
                fill[(row, col)] = anchor
    return fill


class _RowError(Exception):
    """单行数据错误：记录行号与原因，不中断整体导入。"""


async def import_equipment_ledger(
    db: AsyncSession,
    data: bytes,
    *,
    default_category_id: uuid.UUID | None = None,
    default_location_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """解析并增量导入设备台账。

    按设备编号 upsert：已存在则更新台账字段（分类等系统字段不动），
    不存在则新建（给了默认分类则挂载，暂不分类可不传）。
    同一编号占多行时先合并（一般列取首个非空，技术参数/备注拼接）。
    返回总数/新建/更新/失败行明细。
    """
    try:
        # 非 read_only 才能读取 merged_cells；台账 ≤2MB/1000 行内存可承受
        workbook = load_workbook(io.BytesIO(data), data_only=True)
    except Exception as error:  # openpyxl 对损坏文件抛多种异常
        raise AppException(
            status_code=400, message=f"无法读取 Excel 文件：{error}"
        ) from error
    sheet = workbook.active
    if sheet is None:
        raise AppException(status_code=400, message="Excel 中没有工作表")

    grid = list(sheet.iter_rows(values_only=True))
    merged_fill = _merged_value_map(sheet)
    header_index = next(
        (
            i
            for i, row in enumerate(grid)
            if any(_normalize_header(cell) == "设备编号" for cell in row)
        ),
        None,
    )
    if header_index is None:
        raise AppException(
            status_code=400,
            message="未找到台账表头（首列需含「设备编号」），请先下载模板核对格式",
        )
    header_map = {
        _normalize_header(cell): column
        for column, cell in enumerate(grid[header_index])
        if _normalize_header(cell)
    }
    for required in ("设备编号", "设备名称"):
        if required not in header_map:
            raise AppException(
                status_code=400, message=f"台账表头缺少必填列「{required}」"
            )

    if default_category_id is not None:
        await repo.get_equipment_category_by_id(db, default_category_id)
    if default_location_id is not None:
        await repo.get_location_by_id(db, default_location_id)
    location_names = _collect_location_names(await repo.get_location_tree(db))

    data_rows = grid[header_index + 1 :]
    if len(data_rows) > MAX_IMPORT_ROWS:
        raise AppException(
            status_code=400, message=f"单次导入不能超过 {MAX_IMPORT_ROWS} 行"
        )

    # ── 第一阶段：逐行提取原始值（含合并单元格填充），数据问题记入待修正说明 ──
    row_records: list[dict[str, Any]] = []

    for offset, row in enumerate(data_rows):
        excel_row = header_index + offset + 2  # Excel 实际行号（1 起，含表头）

        def cell(column_name: str) -> Any:
            column = header_map.get(column_name)
            if column is None or column >= len(row):
                return None
            value = row[column]
            if value is None or (isinstance(value, str) and not value.strip()):
                value = merged_fill.get((excel_row, column + 1))
            return value

        row_cells = {name: cell(name) for name in LEDGER_COLUMNS}
        if not any(_cell_text(v) for v in row_cells.values()):
            continue  # 整行为空（含合并填充后仍为空）跳过

        record: dict[str, Any] = {"excel_row": excel_row, "issues": [], **row_cells}
        for field in ("出厂日期", "入厂日期"):
            try:
                record[field] = parse_date_cell(row_cells[field])
            except ValueError:
                # 日期无法解析：置空待修正，保留原文便于人工核对；
                # 「【字段】」前缀供前端定位到具体单元格标红
                raw = _cell_text(row_cells[field])
                record[field] = None
                record["issues"].append(
                    f"【{field}】原文「{raw}」无法识别，已置空待修正"
                )
        row_records.append(record)

    # ── 第二阶段：同一设备编号占多行时合并取值；编号为空的行各自成组 ──
    grouped: dict[str, list[dict[str, Any]]] = {}
    empty_no_records: list[dict[str, Any]] = []
    for record in row_records:
        equipment_no = _cell_text(record["设备编号"])
        if equipment_no:
            grouped.setdefault(equipment_no, []).append(record)
        else:
            empty_no_records.append(record)

    # ── 第三阶段：逐组校验并 upsert（数据缺失尽量导入，问题记入待修正说明） ──
    existing_by_no: dict[str, Any] = {}
    created = 0
    updated = 0
    locations_created = 0
    failures: list[dict[str, Any]] = []

    async def _upsert_records(records: list[dict[str, Any]]) -> None:
        nonlocal created, updated, locations_created

        first_row = records[0]["excel_row"]
        merged_row: dict[str, Any] = {}
        for name in LEDGER_COLUMNS:
            if name in _CONCAT_FIELD_NAMES:
                fragments: list[str] = []
                for record in records:
                    text = _cell_text(record.get(name))
                    if text and text not in fragments:
                        fragments.append(text)
                merged_row[name] = "；".join(fragments) or None
            else:
                merged_row[name] = next(
                    (
                        record.get(name)
                        for record in records
                        if _cell_text(record.get(name))
                        or isinstance(record.get(name), (date, datetime))
                    ),
                    None,
                )
        issues: list[str] = []
        for record in records:
            for issue in record.get("issues", []):
                if issue not in issues:
                    issues.append(issue)

        try:
            equipment_no = _cell_text(merged_row["设备编号"])
            if not equipment_no:
                # 编号为空：按内容生成确定性临时编号（重导同文件不产生重复）
                basis = "|".join(
                    _cell_text(merged_row.get(key) or "")
                    for key in ("设备名称", "规格型号", "生产厂家", "安装地点")
                )
                equipment_no = (
                    f"WB-{hashlib.md5(basis.encode('utf-8')).hexdigest()[:8].upper()}"
                )
                issues.append("【设备编号】为空，已生成临时编号待修正")
            if len(equipment_no) > _LEN_LIMITS["equipment_no"]:
                raise _RowError(
                    "设备编号超过 "
                    f"{_LEN_LIMITS['equipment_no']} 字：{equipment_no[:20]}…"
                )

            name = _cell_text(merged_row["设备名称"])
            if not name:
                name = "未命名设备"
                issues.append("【设备名称】为空")

            payload: dict[str, Any] = {
                "equipment_no": equipment_no,
                "name": name,
                "model": _cell_text(merged_row["规格型号"]) or None,
                "manufacturer": _cell_text(merged_row["生产厂家"]) or None,
                "factory_no": _cell_text(merged_row["出厂编号"]) or None,
                "description": _cell_text(merged_row["备注"]) or None,
                "technical_params": parse_tech_params_cell(
                    merged_row["技术参数"]
                ),
                "production_date": merged_row["出厂日期"],
                "arrival_date": merged_row["入厂日期"],
                "data_issue_note": "；".join(issues) or None,
            }
            # 超长截断的问题说明用中文列名，便于页面定位标红
            _issue_column_names = {
                "name": "设备名称",
                "model": "规格型号",
                "manufacturer": "生产厂家",
                "factory_no": "出厂编号",
            }
            for field, limit in _LEN_LIMITS.items():
                if field == "equipment_no":
                    continue
                value = payload[field]
                if value and len(str(value)) > limit:
                    payload[field] = str(value)[:limit]
                    issues.append(
                        f"【{_issue_column_names.get(field, field)}】超长已截断"
                    )
                    payload["data_issue_note"] = "；".join(issues)

            location_text = _cell_text(merged_row["安装地点"])
            if location_text and location_text in location_names:
                payload["location_id"] = location_names[location_text]
            elif location_text:
                # 安装地点是台账自由文本（如「2#萃取滤液罐上安装」），
                # 匹配不上时自动新建为顶层位置，保留原始安装位置描述
                location = await repo.create_location(
                    db,
                    {
                        "name": location_text[:100],
                        "code": f"LOC-IMP-{uuid.uuid4().hex[:8].upper()}",
                    },
                )
                location_names[location_text] = location.id
                payload["location_id"] = location.id
                locations_created += 1
            elif default_location_id is not None:
                payload["location_id"] = default_location_id
            else:
                raise _RowError("安装地点为空，且未指定默认安装地点")

            if equipment_no in existing_by_no:
                equipment = existing_by_no[equipment_no]
                await repo.update_equipment(
                    db,
                    equipment.id,
                    {
                        key: value
                        for key, value in payload.items()
                        if key != "equipment_no"
                    },
                )
                updated += 1
            else:
                existing = await repo.get_equipment_by_no(db, equipment_no)
                if existing is not None:
                    await repo.update_equipment(
                        db,
                        existing.id,
                        {
                            key: value
                            for key, value in payload.items()
                            if key != "equipment_no"
                        },
                    )
                    existing_by_no[equipment_no] = existing
                    updated += 1
                else:
                    equipment = await repo.create_equipment(
                        db,
                        payload,
                        category_ids=[default_category_id]
                        if default_category_id is not None
                        else [],
                    )
                    existing_by_no[equipment_no] = equipment
                    created += 1
        except _RowError as error:
            failures.append(
                {
                    "row": first_row,
                    "equipment_no": _cell_text(merged_row["设备编号"]) or None,
                    "reason": str(error),
                }
            )

    for equipment_no in grouped:
        await _upsert_records(grouped[equipment_no])
    for record in empty_no_records:
        await _upsert_records([record])

    return {
        "total_rows": len(data_rows),
        "created": created,
        "updated": updated,
        "failed": len(failures),
        "flagged": sum(
            1
            for equipment in existing_by_no.values()
            if getattr(equipment, "data_issue_note", None)
        ),
        "locations_created": locations_created,
        "failures": failures,
    }
