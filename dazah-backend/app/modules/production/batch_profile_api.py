"""批次全貌查询 API — 跨模块按批号聚合所有记录"""

import logging

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])


@router.get("/batch-profile/{batch_no}", summary="批次全貌 — 按批号聚合所有模块记录")
async def get_batch_profile(
    batch_no: str,
    session: AsyncSession = Depends(get_db),
):
    """根据批号查询所有关联数据：菌种、发酵、非密事件"""
    result: dict = {
        "batch_no": batch_no,
        "seed_culture": None,
        "fermentation": None,
        "events": [],
    }

    # 1. 菌种记录
    sc_rows = await session.execute(
        text(
            "SELECT * FROM production.seed_cultures WHERE batch_no = :bn AND is_deleted = false"  # noqa: E501
        ),
        {"bn": batch_no},
    )
    sc = sc_rows.first()
    if sc:
        cols = sc_rows.keys()
        result["seed_culture"] = {
            k: str(v) if hasattr(v, "isoformat") else v
            for k, v in zip(cols, sc)
            if k not in ("created_by", "updated_by", "is_deleted")
        }

    # 2. 发酵记录
    ferm_rows = await session.execute(
        text(
            "SELECT * FROM production.fermentation_records WHERE batch_no = :bn AND is_deleted = false ORDER BY entry_date DESC"  # noqa: E501
        ),
        {"bn": batch_no},
    )
    ferm_list = []
    for row in ferm_rows:
        cols = ferm_rows.keys()
        ferm_list.append(
            {
                k: str(v) if hasattr(v, "isoformat") else v
                for k, v in zip(cols, row)
                if k not in ("created_by", "updated_by", "is_deleted")
            }
        )
    result["fermentation"] = ferm_list

    # 3. 关联的非密事件（通过发酵记录）
    event_rows = await session.execute(
        text("""
            SELECT DISTINCT e.* FROM production.non_conforming_events e
            JOIN production.nce_batch_links l ON l.nce_id = e.id
            JOIN production.fermentation_records f ON f.id = l.batch_id
            WHERE f.batch_no = :bn AND e.is_deleted = false
            ORDER BY e.event_time DESC
        """),
        {"bn": batch_no},
    )
    events = []
    for row in event_rows:
        cols = event_rows.keys()
        events.append(
            {
                k: str(v) if hasattr(v, "isoformat") else v
                for k, v in zip(cols, row)
                if k not in ("created_by", "updated_by", "is_deleted")
            }
        )
    result["events"] = events

    # 4. 提炼车间 — 遍历所有关联表
    refinery_tables = {
        "broth_receive": ("production.broth_receives", "received_batch"),
        "pretreatment": ("production.pretreatments", "received_batch"),
        "ceramic_feed": ("production.ceramic_feeds", "batch_no"),
        "ceramic_ops": ("production.ceramic_membrane_ops", "batch_no"),
        "ceramic_clean": ("production.ceramic_membrane_cleans", "membrane_no"),
        "ceramic_sep": ("production.ceramic_material_separations", "batch_no"),
        "ceramic_equip": ("production.ceramic_equipment_logs", "equipment_no"),
        "decolor1": ("production.decolor1", "batch_no"),
    }
    result["refinery"] = {}
    for key, (table, col) in refinery_tables.items():
        rows = await session.execute(
            text(
                f"SELECT * FROM {table} WHERE {col} = :bn AND is_deleted = false ORDER BY created_at DESC"  # noqa: E501
            ),
            {"bn": batch_no},
        )
        items = []
        for row in rows:
            cols = rows.keys()
            items.append(
                {
                    k: str(v) if hasattr(v, "isoformat") else v
                    for k, v in zip(cols, row)
                    if k not in ("created_by", "updated_by", "is_deleted")
                }
            )
        result["refinery"][key] = items

    if (
        not result["seed_culture"]
        and not result["fermentation"]
        and not any(result["refinery"].values())
    ):
        return success_response(None, message="未找到该批号的相关记录", status_code=404)

    return success_response(result)
