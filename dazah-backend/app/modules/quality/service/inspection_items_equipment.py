"""Inspection Feishu pages service - items CRUD.

物品管理 (lab items) 子模块的实时读写服务。

仪器管理（设备/维保/维修/合同/校验计划 8 张子表）不再使用硬编码字段清单，
改为：本地镜像（service.inspection_instrument_mirror）+ 实时动态列兜底
（inspection_helpers._list_feishu_dynamic），列完全跟随飞书表真实字段。
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
