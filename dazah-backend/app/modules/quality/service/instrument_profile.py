"""仪器台账「仪器档案」：一台设备的维保/维修/校验/合同情况。

匹配规则：以设备数据管理行的「设备编号」为准，到各子表镜像里匹配编号列
（各表编号列名不同；部分表一格多编号用顿号分隔，按编号分词后精确匹配，
退化为子串匹配）。维保合同按「涉及仪器及编号」列匹配（同样支持一格多
编号），未填写该列的合同不会出现在任何仪器档案里。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality.service.inspection_instrument_mirror import (
    list_instrument_mirror,
)

_PAGE_SIZE = 500

# 子表 -> 编号列
_PROFILE_MATCH_COLUMNS: dict[str, str] = {
    "qc_instr_maintenance": "仪器编号",
    "qc_instr_repair": "设备编号",
    "qc_instr_calibration": "仪器、设备编号",
    "qc_instr_cal_plan": "仪器、设备编号",
    "qc_instr_cal_external": "器具编号",
    # 维保合同：涉及仪器及编号（一格可写多台，顿号分隔）
    "qc_instr_contracts": "涉及仪器及编号",
}

# 编号分隔符：顿号/逗号/分号/斜杠/空白
_CODE_SEPARATORS = re.compile(r"[、,，;；/\s]+")


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "")
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or item.get("text") or ""))
            elif item is not None:
                parts.append(str(item))
        return "、".join(part for part in parts if part)
    return str(value)


def _code_matches(cell_value: Any, code: str) -> bool:
    """编号匹配：单元格按分隔符分词后精确匹配任一编号；否则退化为子串匹配。"""
    if not code:
        return False
    text = _cell_text(cell_value)
    if not text:
        return False
    tokens = {token.strip() for token in _CODE_SEPARATORS.split(text) if token.strip()}
    if code in tokens:
        return True
    return code in text


async def _load_rows(db: AsyncSession, entity_code: str) -> list[dict[str, Any]]:
    page = await list_instrument_mirror(db, entity_code, page=1, page_size=_PAGE_SIZE)
    return list(page.get("items") or [])


async def get_instrument_profile(db: AsyncSession, record_id: str) -> dict[str, Any]:
    """仪器档案：设备基本信息 + 按设备编号匹配的维保/维修/校验/合同。"""
    equipment_rows = await _load_rows(db, "qc_instr_equipment")
    equipment = next(
        (row for row in equipment_rows if str(row.get("record_id") or "") == record_id),
        None,
    )
    if equipment is None:
        raise NotFoundException(resource="仪器台账记录", resource_id=str(record_id))

    code = _cell_text(equipment.get("设备编号")).strip()

    rows_by_entity = {
        entity_code: await _load_rows(db, entity_code)
        for entity_code in _PROFILE_MATCH_COLUMNS
    }

    def _matched(entity_code: str) -> list[dict[str, Any]]:
        column = _PROFILE_MATCH_COLUMNS[entity_code]
        return [
            row for row in rows_by_entity[entity_code]
            if _code_matches(row.get(column), code)
        ]

    async def _matched_with_schedule(entity_code: str) -> list[dict[str, Any]]:
        matched = _matched(entity_code)
        if entity_code == "qc_instr_maintenance":
            from app.modules.quality.service.maintenance_schedule import (
                enrich_maintenance_schedule,
            )

            matched = await enrich_maintenance_schedule(db, matched)
        return matched

    return {
        "equipment": equipment,
        "matched_code": code,
        "maintenance": await _matched_with_schedule("qc_instr_maintenance"),
        "repairs": _matched("qc_instr_repair"),
        "calibration": {
            "internal_summary": _matched("qc_instr_calibration"),
            "internal_plan": _matched("qc_instr_cal_plan"),
            "external": _matched("qc_instr_cal_external"),
        },
        # 维保合同：按「涉及仪器及编号」匹配；未填写该列的合同不会命中任何仪器
        "contracts": _matched("qc_instr_contracts"),
        "contracts_total": len(rows_by_entity["qc_instr_contracts"]),
    }
