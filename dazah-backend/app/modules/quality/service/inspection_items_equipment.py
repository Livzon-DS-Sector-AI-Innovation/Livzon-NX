"""Inspection Feishu pages service - items and equipment CRUD.

物品管理 (lab items) / 仪器管理 (lab instruments) sub-modules.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service.inspection_helpers import (
    _get_feishu_one,
    _get_item_record_with_inventory,
    _list_feishu,
    _list_item_records_with_inventory,
    _pull_count,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  物品管理 (lab items)
# ═══════════════════════════════════════════

ITEMS_FIELDS = [
    "物资名称",
    "物资名（规格）",
    "规格型号",
    "存放位置",
    "单位",
    "当前库存",
    "警戒库存",
    "库存报警",
    "出库量",
    "入库量",
    "备注",
]
ITEMS_KEYWORD_FIELDS = ["物资名称", "规格型号", "物资名（规格）", "备注"]


async def list_items(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_feishu(
        db,
        "qc_items_inventory",
        ITEMS_FIELDS,
        ITEMS_KEYWORD_FIELDS,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def get_item(db: AsyncSession, record_id: str) -> dict[str, Any]:
    return await _get_feishu_one(db, "qc_items_inventory", ITEMS_FIELDS, record_id)


async def pull_items(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_items_inventory")


# ── 入库明细 ──

INBOUND_FIELDS = ["物资名称", "规格型号", "入库数量"]
INBOUND_KEYWORD_FIELDS = ["物资名称"]


async def list_inbounds(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_item_records_with_inventory(
        db,
        "qc_items_inbound",
        INBOUND_FIELDS,
        INBOUND_KEYWORD_FIELDS,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def get_inbound(db: AsyncSession, record_id: str) -> dict[str, Any]:
    return await _get_item_record_with_inventory(
        db, "qc_items_inbound", INBOUND_FIELDS, record_id
    )


async def pull_inbounds(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_items_inbound")


# ── 领用明细 ──

OUTBOUND_FIELDS = ["物资名称", "规格型号", "领取数量", "当前库存", "领用人"]
OUTBOUND_KEYWORD_FIELDS = ["物资名称", "领用人"]


async def list_outbounds(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_item_records_with_inventory(
        db,
        "qc_items_outbound",
        OUTBOUND_FIELDS,
        OUTBOUND_KEYWORD_FIELDS,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def get_outbound(db: AsyncSession, record_id: str) -> dict[str, Any]:
    return await _get_item_record_with_inventory(
        db, "qc_items_outbound", OUTBOUND_FIELDS, record_id
    )


async def pull_outbounds(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_items_outbound")


# ═══════════════════════════════════════════
#  仪器管理 (lab instruments)
# ═══════════════════════════════════════════

EQUIPMENT_FIELDS = [
    "设备信息",
    "设备名称",
    "设备编号",
    "设备类型",
    "安装日期",
    "设备状态",
    "设备品牌",
    "规格型号",
    "用途",
    "设备安装地点",
    "使用负责人",
    "校验有效期",
    "设备保养记录",
    "设备维修记录",
    "当前价值",
    "设备变更记录",
    "设备维保合同",
]
EQUIPMENT_KEYWORD_FIELDS = [
    "设备信息",
    "设备名称",
    "设备编号",
    "设备品牌",
    "规格型号",
    "用途",
    "使用负责人",
]


async def list_equipment(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_feishu(
        db,
        "qc_instr_equipment",
        EQUIPMENT_FIELDS,
        EQUIPMENT_KEYWORD_FIELDS,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def get_equipment(db: AsyncSession, record_id: str) -> dict[str, Any]:
    return await _get_feishu_one(db, "qc_instr_equipment", EQUIPMENT_FIELDS, record_id)


async def pull_equipment(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_instr_equipment")


# ── 维护保养记录 ──

MAINTENANCE_FIELDS = [
    "维护保养编号",
    "维护保养设备",
    "维护保养内容",
    "完成日期",
    "下次维保时间",
    "剩余天数",
    "维保人",
]
MAINTENANCE_KEYWORD_FIELDS = ["维护保养编号", "维护保养设备", "维护保养内容", "维保人"]


async def list_maintenance(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_feishu(
        db,
        "qc_instr_maintenance",
        MAINTENANCE_FIELDS,
        MAINTENANCE_KEYWORD_FIELDS,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def get_maintenance(db: AsyncSession, record_id: str) -> dict[str, Any]:
    return await _get_feishu_one(
        db, "qc_instr_maintenance", MAINTENANCE_FIELDS, record_id
    )


async def pull_maintenance(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_instr_maintenance")


# ── 校验记录 ──

CALIBRATION_FIELDS = [
    "校验有效期",
    "设备名称",
    "设备编号",
    "剩余天数（天）",
    "设备数据管理",
]
CALIBRATION_KEYWORD_FIELDS = ["设备名称", "设备编号"]


async def list_calibrations(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_feishu(
        db,
        "qc_instr_calibration",
        CALIBRATION_FIELDS,
        CALIBRATION_KEYWORD_FIELDS,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def get_calibration(db: AsyncSession, record_id: str) -> dict[str, Any]:
    return await _get_feishu_one(
        db, "qc_instr_calibration", CALIBRATION_FIELDS, record_id
    )


async def pull_calibrations(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_instr_calibration")


# ── 维修记录 ──

REPAIR_FIELDS = [
    "维修内容",
    "设备名称",
    "设备编号",
    "设备",
    "维修原因",
    "当前价值",
    "维修费用",
    "维修建议",
    "维修状态",
    "维修时间",
    "次数",
    "维修人",
]
REPAIR_KEYWORD_FIELDS = ["维修内容", "设备名称", "维修原因", "维修人"]


async def list_repairs(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_feishu(
        db,
        "qc_instr_repair",
        REPAIR_FIELDS,
        REPAIR_KEYWORD_FIELDS,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def get_repair(db: AsyncSession, record_id: str) -> dict[str, Any]:
    return await _get_feishu_one(db, "qc_instr_repair", REPAIR_FIELDS, record_id)


async def pull_repairs(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_instr_repair")


# ── 变更记录 / 维保合同 / 维保方案 / 固资台账 ──

CHANGE_FIELDS = ["变更号", "涉及设备", "变更时间", "变更原因", "变更状态", "责任人"]
CHANGE_KW = ["变更号", "涉及设备", "变更原因", "责任人"]

CONTRACT_FIELDS = [
    "设备维保合同",
    "涉及设备",
    "购买维保合同时间",
    "有效期",
    "到期提醒",
    "责任人",
]
CONTRACT_KW = ["设备维保合同", "涉及设备", "责任人"]

PLAN_FIELDS = [
    "维护保养内容",
    "设备名称",
    "维保周期（月）",
    "维护保养周期",
    "设备保养记录",
]
PLAN_KW = ["维护保养内容", "设备名称"]

ASSET_FIELDS = [
    "当前价值",
    "设备",
    "原始价值",
    "当前已折旧",
    "当前价值1",
    "月平均折旧",
    "残值",
    "启用日期",
    "使用寿命（月）",
    "已使用时长（月）",
]
ASSET_KW = ["设备", "原始价值"]


async def list_instr_changes(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_feishu(
        db,
        "qc_instr_change",
        CHANGE_FIELDS,
        CHANGE_KW,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def pull_instr_changes(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_instr_change")


async def list_instr_contracts(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_feishu(
        db,
        "qc_instr_contracts",
        CONTRACT_FIELDS,
        CONTRACT_KW,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def pull_instr_contracts(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_instr_contracts")


async def list_instr_plans(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_feishu(
        db,
        "qc_instr_plans",
        PLAN_FIELDS,
        PLAN_KW,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def pull_instr_plans(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_instr_plans")


async def list_instr_assets(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    return await _list_feishu(
        db,
        "qc_instr_assets",
        ASSET_FIELDS,
        ASSET_KW,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def pull_instr_assets(db: AsyncSession) -> dict[str, int]:
    return await _pull_count(db, "qc_instr_assets")
