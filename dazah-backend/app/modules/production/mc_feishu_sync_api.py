"""MC 霉酚酸 — 飞书电子表格同步 API

提供从飞书电子表格同步 MC 台账数据的 HTTP 接口。
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production.mc_feishu_sheets_sync import run_mc_sync, SYNC_HANDLERS
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])

# 上次同步时间的内存记录
_last_sync: dict[str, str] = {}


class SyncTriggerRequest(BaseModel):
    modules: list[str] = Field(
        default=["crude", "extraction", "refinement", "blending", "qc", "ba"],
        description="要同步的模块列表",
    )


@router.post("/mc/sync/trigger", summary="从飞书电子表格同步MC台账数据")
async def trigger_mc_sync(
    body: SyncTriggerRequest,
    session: AsyncSession = Depends(get_db),
):
    """触发从飞书电子表格 "2026年生产台账-mc" 同步数据到本地数据库。

    支持的模块:
    - crude: 粗提
    - extraction: 提取
    - refinement: 二次精制
    - blending: 混粉杂质计算
    - qc: 混粉入库
    - ba: 丁酯盘点
    """
    valid_modules = [m for m in body.modules if m in SYNC_HANDLERS]
    invalid = [m for m in body.modules if m not in SYNC_HANDLERS]

    if not valid_modules:
        return success_response(
            {"error": "没有有效的模块", "invalid": invalid},
            message="请指定至少一个有效模块",
            status_code=400,
        )

    results = await run_mc_sync(valid_modules, session)

    # 更新最后同步时间
    now_iso = datetime.now(timezone.utc).isoformat()
    for m in valid_modules:
        _last_sync[m] = now_iso

    total_created = sum(
        r.get("created_fl", 0) + r.get("created_rb", 0) +
        r.get("created_st", 0) + r.get("created_sodium", 0) +
        r.get("created_acid", 0) + r.get("created_records", 0) +
        r.get("created_inputs", 0)
        for r in results.values() if "error" not in r
    )
    total_updated = sum(
        r.get("updated_records", 0) + r.get("updated_inputs", 0)
        for r in results.values() if "error" not in r
    )

    return success_response({
        "results": results,
        "invalid": invalid,
        "total_created": total_created,
        "total_updated": total_updated,
        "synced_at": now_iso,
    }, message=f"同步完成，共创建 {total_created} 条记录，更新 {total_updated} 条记录")


@router.get("/mc/sync/status", summary="查看MC飞书同步状态")
async def get_mc_sync_status():
    """返回各模块的上次同步时间"""
    return success_response({
        "spreadsheet": "2026年生产台账-mc",
        "modules": {
            mod: {
                "label": label,
                "last_sync": _last_sync.get(mod),
            }
            for mod, label in [
                ("crude", "粗提"),
                ("extraction", "提取"),
                ("refinement", "二次精制"),
                ("blending", "混粉杂质计算"),
                ("qc", "混粉入库"),
                ("ba", "丁酯盘点"),
            ]
        },
    })


# 模块名 → 中文标签映射
MODULE_LABELS = {
    "crude": "粗提",
    "extraction": "提取",
    "refinement": "二次精制",
    "blending": "混粉杂质计算",
    "qc": "混粉入库",
    "ba": "丁酯盘点",
}
