"""仪器台账 Excel 批量导入：列头自动识别 -> 预览 -> 确认写入飞书。

两段式（与 CPV 导入一致）：preview 只解析不写库；confirm 用同一文件重传，
按「设备编号」判新增/更新逐行写飞书（走通用 CRUD，自带审计），结束后
全量刷新一次本地镜像。负责人列按姓名匹配人事-飞书联系人换 open_id，
匹配不到的行记告警并跳过该字段，不阻断导入。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from io import BytesIO
from typing import Any

from openpyxl import load_workbook  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.service.inspection_feishu_crud import (
    create_inspection_feishu_record,
    update_inspection_feishu_record,
)
from app.modules.quality.service.inspection_instrument_mirror import (
    list_instrument_mirror,
    sync_instrument_page,
)
from app.modules.quality.service.person_directory import resolve_person_by_name

logger = logging.getLogger(__name__)

ENTITY = "qc_instr_equipment"
_MAX_ROWS = 500

# 飞书字段 -> 可识别列头（归一化空白后精确匹配 + 常用别名 + 包含匹配兜底）
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "设备编号": (
        "设备编号",
        "编号",
        "仪器编号",
        "仪器、设备编号",
        "设备号",
        "器具编号",
    ),
    "设备名称": (
        "设备名称",
        "名称",
        "仪器名称",
        "仪器、设备名称",
        "仪器设备名称",
        "器具名称",
    ),
    "设备品牌": ("设备品牌", "品牌", "厂家", "生产厂家", "制造商", "生产厂商"),
    "规格型号": ("规格型号", "型号", "型号规格", "规格"),
    "用途": ("用途", "用途说明"),
    "设备安装地点": (
        "设备安装地点",
        "安装地点",
        "安装位置",
        "使用地点",
        "存放地点",
        "安装地",
        "位置",
    ),
    "使用负责人": ("使用负责人", "负责人", "使用人", "责任人", "保管人"),
    "入厂日期": (
        "入厂日期",
        "入场日期",
        "启用日期",
        "购买日期",
        "购置日期",
        "入厂时间",
    ),
}

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d")
_PERSON_SEPARATORS = ("、", ",", "，", ";", "；", "/", " ")


def _normalize_header(value: Any) -> str:
    return "".join(str(value or "").split())


def _cell_str(value: Any) -> str:
    """单元格文本：数字编号避免浮点尾巴（1916001004291.0 -> ...291）。"""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _parse_date_value(value: Any) -> str | None:
    """日期单元格 -> 'YYYY-MM-DD'；兼容 openpyxl datetime 与常见文本格式。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise AppException(
        message=f"日期格式无法识别：{text}（支持 2026-01-31 / 2026/1/31 / 20260131）",
        status_code=400,
    )


def _split_person_names(value: Any) -> list[str]:
    text = _cell_str(value)
    if not text:
        return []
    names: list[str] = []
    for token in text.split("、"):
        for part in token.replace("，", ",").replace("；", ";").split(";"):
            for piece in part.replace("，", ",").split(","):
                piece = piece.strip().strip("/")
                if piece:
                    names.append(piece)
    # 去重保序
    seen: set[str] = set()
    result = []
    for name in names:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _parse_workbook(content: bytes) -> tuple[list[str], list[list[Any]]]:
    """取第一个 sheet，返回 (表头行, 数据行)。表头=第一个存在非空单元格的行。"""
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise AppException(
            message="Excel 文件解析失败，请确认是有效的 .xlsx", status_code=400
        ) from exc
    sheet = workbook.active
    if sheet is None:
        workbook.close()
        raise AppException(message="Excel 文件没有工作表", status_code=400)
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    workbook.close()
    header_index = next(
        (
            index
            for index, row in enumerate(rows)
            if any(cell not in (None, "") for cell in row)
        ),
        None,
    )
    if header_index is None:
        raise AppException(message="Excel 文件为空", status_code=400)
    headers = [_normalize_header(cell) for cell in rows[header_index]]
    data_rows = rows[header_index + 1 :]
    return headers, data_rows


def _build_column_map(
    headers: list[str],
) -> tuple[dict[str, int], list[str]]:
    """列头 -> 飞书字段。精确名/别名优先，退化为「表头包含字段名」。"""
    column_map: dict[str, int] = {}
    matched_headers: set[int] = set()
    for field, aliases in _COLUMN_ALIASES.items():
        normalized_aliases = {_normalize_header(alias) for alias in aliases}
        for index, header in enumerate(headers):
            if index in matched_headers or not header:
                continue
            if header in normalized_aliases:
                column_map[field] = index
                matched_headers.add(index)
                break
    for field in _COLUMN_ALIASES:
        if field in column_map:
            continue
        for index, header in enumerate(headers):
            if index in matched_headers or not header:
                continue
            if field in header:
                column_map[field] = index
                matched_headers.add(index)
                break
    unmatched = [
        headers[index]
        for index, header in enumerate(headers)
        if header and index not in matched_headers
    ]
    return column_map, unmatched


async def _load_code_index(db: AsyncSession) -> dict[str, str]:
    """已同步设备的 设备编号 -> record_id（判新增/更新）。"""
    page = await list_instrument_mirror(db, ENTITY, page=1, page_size=_MAX_ROWS)
    index: dict[str, str] = {}
    for row in page.get("items") or []:
        code = _cell_str(row.get("设备编号"))
        record_id = str(row.get("record_id") or "")
        if code and record_id:
            index.setdefault(code, record_id)
    return index


def _build_write_fields(
    entry: dict[str, Any],
    values: dict[str, str],
    column_map: dict[str, int],
    row: list[Any],
    person_ids: dict[str, str | None],
) -> str | None:
    """行值 -> 写飞书字段字典；返回错误信息（人员告警写入 entry.warnings）。"""
    fields: dict[str, Any] = {}
    for field, text in values.items():
        if field == "入厂日期":
            try:
                parsed = _parse_date_value(row[column_map[field]])
            except AppException as exc:
                return str(exc.message)
            if parsed:
                fields[field] = parsed
            continue
        if field == "使用负责人":
            ids: list[dict[str, str]] = []
            for name in _split_person_names(text):
                resolved = person_ids.get(name)
                if resolved:
                    ids.append({"id": resolved})
                else:
                    entry["warnings"].append(f"负责人「{name}」未匹配到在职人员，已跳过")
            if ids:
                fields[field] = ids
            continue
        fields[field] = text
    entry["fields"] = fields
    return None


async def _parse_import_rows(
    db: AsyncSession, content: bytes
) -> dict[str, Any]:
    headers, data_rows = _parse_workbook(content)
    column_map, unmatched_columns = _build_column_map(headers)
    if "设备编号" not in column_map:
        raise AppException(
            message='未识别到「设备编号」列，请在表头保留"设备编号"（或"编号/仪器编号"）',
            status_code=400,
        )

    # 人员姓名先收集去重，统一解析（同人只查一次目录）
    person_names: set[str] = set()
    for row in data_rows[:_MAX_ROWS]:
        if "使用负责人" in column_map:
            person_names.update(_split_person_names(row[column_map["使用负责人"]]))
    person_ids: dict[str, str | None] = {}
    person_unresolved: list[str] = []
    for name in sorted(person_names):
        try:
            person = await resolve_person_by_name(db, name)
        except Exception as exc:  # noqa: BLE001 - 目录不可用时不阻断导入
            logger.warning("person directory lookup failed for %s: %s", name, exc)
            person = None
        person_ids[name] = str(person.get("open_id") or "") if person else None
        if person_ids[name] is None:
            person_unresolved.append(name)

    code_index = await _load_code_index(db)

    parsed_rows: list[dict[str, Any]] = []
    create_count = 0
    update_count = 0
    error_count = 0
    skipped_empty = 0

    for offset, row in enumerate(data_rows[:_MAX_ROWS]):
        row_number = offset + 2  # 表头占第 1 行
        values: dict[str, str] = {}
        for field, index in column_map.items():
            text = _cell_str(row[index]) if index < len(row) else ""
            if text:
                values[field] = text
        if not values:
            skipped_empty += 1
            continue

        entry: dict[str, Any] = {
            "row_number": row_number,
            "values": values,
            "warnings": [],
            "error": None,
            "mode": "create",
            "record_id": None,
            "fields": {},
        }

        code = values.get("设备编号", "")
        if not code:
            entry["error"] = "设备编号为空"
            error_count += 1
            parsed_rows.append(entry)
            continue

        record_id = code_index.get(code)
        if record_id:
            entry["mode"] = "update"
            entry["record_id"] = record_id
            update_count += 1
        else:
            create_count += 1

        build_error = _build_write_fields(entry, values, column_map, row, person_ids)
        if build_error is None:
            entry["fields"] = {
                key: value
                for key, value in entry["fields"].items()
                if value not in (None, [], "")
            }
            parsed_rows.append(entry)
            continue
        entry["error"] = build_error
        error_count += 1
        parsed_rows.append(entry)

    return {
        "column_map": {field: headers[index] for field, index in column_map.items()},
        "unmatched_columns": unmatched_columns,
        "rows": parsed_rows,
        "create_count": create_count,
        "update_count": update_count,
        "error_count": error_count,
        "skipped_empty": skipped_empty,
        "person_unresolved": person_unresolved,
    }


async def preview_instrument_import(db: AsyncSession, content: bytes) -> dict[str, Any]:
    """解析并返回导入预览（不写任何数据）。"""
    return await _parse_import_rows(db, content)


async def confirm_instrument_import(
    db: AsyncSession, content: bytes, operator_user_id: Any = None
) -> dict[str, Any]:
    """按预览同样的解析结果逐行写飞书（新增/更新），完成后全量刷镜像。"""
    parsed = await _parse_import_rows(db, content)
    success = 0
    failed = 0
    created = 0
    updated = 0
    error_details: list[dict[str, Any]] = []

    for row in parsed["rows"]:
        if row["error"]:
            failed += 1
            error_details.append(
                {"row_number": row["row_number"], "message": row["error"]}
            )
            continue
        try:
            if row["mode"] == "update" and row["record_id"]:
                await update_inspection_feishu_record(
                    db,
                    ENTITY,
                    row["record_id"],
                    row["fields"],
                    actor_user_id=operator_user_id,
                )
                updated += 1
            else:
                await create_inspection_feishu_record(
                    db, ENTITY, row["fields"], actor_user_id=operator_user_id
                )
                created += 1
            success += 1
        except Exception as exc:  # noqa: BLE001 - 逐行容错，不中断整批
            failed += 1
            message = getattr(exc, "message", None) or str(exc)
            error_details.append(
                {"row_number": row["row_number"], "message": message[:200]}
            )
            logger.warning(
                "instrument import row %s failed: %s", row["row_number"], exc
            )

    synced = 0
    if success:
        try:
            result = await sync_instrument_page(db, ENTITY, incremental=False)
            synced = int(result.get("synced") or 0)
        except Exception as exc:  # noqa: BLE001 - 镜像刷新失败不影响导入结果
            logger.warning("instrument import mirror refresh failed: %s", exc)

    return {
        "total_rows": len(parsed["rows"]),
        "success": success,
        "failed": failed,
        "created": created,
        "updated": updated,
        "error_details": error_details[:100],
        "skipped_empty": parsed["skipped_empty"],
        "mirror_synced": synced,
    }
