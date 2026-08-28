"""MC 霉酚酸 — 收率异常自动检测 API

提供手动触发和状态查询端点。
"""
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production.mc_yield_anomaly_detector import run_anomaly_detection
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])

_last_run_result: dict[str, Any] | None = None
_last_run_time: str | None = None


@router.post("/mc/anomaly/run", summary="手动触发MC收率异常自动检测")
async def trigger_anomaly_detection(session: AsyncSession = Depends(get_db)) -> Any:
    """无需等待飞书同步，手动触发一次收率异常检测。
    返回扫描批次数、检测到的异常数(high/medium)、跳过的正常批次数。
    """
    global _last_run_result, _last_run_time
    try:
        result = await run_anomaly_detection(session)
        _last_run_result = result
        _last_run_time = datetime.now(UTC).isoformat()
        logger.info(
            "[异常检测API] 手动触发完成 — scanned=%d detected=%d high=%d medium=%d",
            result.get("scanned", 0),
            result.get("detected", 0),
            result.get("high", 0),
            result.get("medium", 0),
        )
        return success_response(
            result,
            message=(
                f"扫描 {result['scanned']} 批, 检测到 {result['detected']} 个异常 "
                f"(high={result['high']} medium={result['medium']}), "
                f"正常 {result['skipped_normal']} 批"
            ),
        )
    except Exception as e:
        logger.exception("[异常检测API] 手动触发失败")
        return success_response(
            {"error": str(e)},
            message="异常检测执行失败",
            status_code=500,
        )


@router.get("/mc/anomaly/status", summary="查看最近一次自动检测结果")
async def get_anomaly_detection_status() -> Any:
    """返回最近一次异常检测的运行时间和汇总结果（内存缓存）。"""
    if _last_run_result is None:
        return success_response(
            {"last_run": None, "last_result": None}, message="尚未执行过异常检测"
        )
    return success_response(
        {
            "last_run": _last_run_time,
            "last_result": _last_run_result,
        }
    )
