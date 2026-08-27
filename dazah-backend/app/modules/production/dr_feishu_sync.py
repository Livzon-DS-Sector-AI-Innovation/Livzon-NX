"""DR 多拉菌素 — 飞书电子表格同步（过滤萃取工段）"""

import logging
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_models import ProductionFeishuConfig
from app.platform.integrations.feishu.utils import OPEN_API_BASE_URL

logger = logging.getLogger(__name__)

DR_PRODUCT = "多拉菌素"
SHEET_RANGE = "A4:AH5000"
DATA_START_ROW = 4

COL = {
    "tank_date": 0,
    "batch_no": 1,
    "tank_no": 2,
    "handover_unit": 3,
    "handover_volume": 4,
    "product_qty": 5,
    "actual_product_qty": 6,
    "handover_product_qty": 7,
    "bacteria_plates": 8,
    "feeding_time": 9,
    "extraction_batch_no": 10,
    "feeding_plates": 11,
    "extraction_pq": 12,
    "filtrate_tank": 13,
    "filtrate_volume": 14,
    "filtrate_potency": 15,
    "filtrate_pq": 16,
    "total_qty": 17,
    "fl_yield": 18,
    "single_yield": 19,
    "dw_volume": 20,
    "dw_potency": 21,
    "dw_pq": 22,
    "impurity_6": 23,
    "impurity_1": 24,
    "impurity_2": 25,
    "impurity_7": 26,
    "impurity_3": 27,
    "impurity_4": 28,
    "impurity_5": 29,
    "rrt_068": 30,
    "unknown_max": 31,
    "total_impurities": 32,
    "purity": 33,
}

IMPURITY_MAP = {
    "rrt_068": "rrt_068",
    "unknown_max": "unknown_max_single",
    "total_impurities": "total_impurities",
}

_token_cache: dict[str, str] = {}


# ── 工具 ─────────────────────────────────────────────────


async def _get_token(app_id: str, app_secret: str) -> str:
    k = f"dr_sync:{app_id}"
    if k in _token_cache:
        return _token_cache[k]
    async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=30) as c:
        r = await c.post(
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        r.raise_for_status()
        token = r.json()["tenant_access_token"]
        _token_cache[k] = token
        return str(token)


async def _read_sheet(
    token: str, sheet_id: str, spreadsheet_token: str
) -> list[list[str]]:
    """读取飞书电子表格"""
    path = (
        f"/sheets/v2/spreadsheets/{spreadsheet_token}/values/{sheet_id}!{SHEET_RANGE}"
    )
    async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=60) as c:
        r = await c.get(
            path,
            params={
                "valueRenderOption": "ToString",
                "dateTimeRenderOption": "FormattedString",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            raise RuntimeError(f"飞书 API HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 API code={data.get('code')}: {data.get('msg')}")
    values = data.get("data", {}).get("valueRange", {}).get("values", [])
    return [[str(c) if c is not None else "" for c in row] for row in values]


def _g(row: list[str], key: str) -> str:
    idx = COL[key]
    return str(row[idx]).strip() if idx < len(row) and row[idx] else ""


def _f(row: list[str], key: str) -> float | None:
    s = _g(row, key)
    if not s or s == "-" or s.startswith("#"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _i(row: list[str], key: str) -> int | None:
    s = _g(row, key)
    if not s or s == "-":
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _is_empty(row: list[str]) -> bool:
    return all(not c or c.strip() == "" for c in row)


# ═══════════════════════════════════════════════════════════
# 同步主逻辑
# ═══════════════════════════════════════════════════════════


async def sync_dr_extraction(
    config: ProductionFeishuConfig, session: AsyncSession
) -> dict[str, Any]:
    app_secret = decrypt_secret(config.encrypted_app_secret)
    token = await _get_token(config.app_id, app_secret)
    logger.info("[DR同步] 读取飞书表格...")
    rows = await _read_sheet(token, config.table_id, config.bitable_app_token)

    stats = {
        "created_batches": 0,
        "created_tanks": 0,
        "created_extractions": 0,
        "created_filtrates": 0,
        "updated_batches": 0,
        "updated_tanks": 0,
        "updated_extractions": 0,
        "updated_filtrates": 0,
        "skipped": 0,
        "errors": 0,
    }

    # 合并单元格继承
    cur_batch_no = ""
    cur_batch_id = ""
    cur_tank_no = ""
    cur_tank_id = ""
    cur_extr_no = ""
    cur_extr_id = ""

    for ri, row in enumerate(rows):
        if _is_empty(row):
            stats["skipped"] += 1
            continue

        try:
            # ─ 合并单元格继承：空值沿用上一个 ─
            bno = _g(row, "batch_no")
            tno = _g(row, "tank_no")
            eno = _g(row, "extraction_batch_no")

            if bno:
                cur_batch_no = bno
            if tno:
                cur_tank_no = tno
            if eno:
                cur_extr_no = eno

            if not cur_batch_no:
                stats["skipped"] += 1
                continue

            # ─ 1. 批次 ─
            if bno:  # 新批次行
                batch_data = {
                    "batch_no": cur_batch_no,
                    "workshop": "201-3",
                    "tank_date": _g(row, "tank_date") or None,
                }
                cur_batch_id = await _upsert(
                    session,
                    "production.dr_fermentation_batches",
                    batch_data,
                    ["batch_no"],
                    stats,
                    "batches",
                )

            # ─ 2. 发酵罐 ─
            if tno:  # 新罐行
                tank_data = {
                    "fermentation_batch_id": cur_batch_id,
                    "tank_no": cur_tank_no,
                    "handover_unit": _f(row, "handover_unit"),
                    "handover_volume": _f(row, "handover_volume"),
                    "fermentation_product_qty": _f(row, "product_qty"),
                    "actual_product_qty": _f(row, "actual_product_qty"),
                    "handover_product_qty": _f(row, "handover_product_qty"),
                    "bacteria_residue_plates": _i(row, "bacteria_plates"),
                }
                cur_tank_id = await _upsert(
                    session,
                    "production.dr_fermentation_tanks",
                    tank_data,
                    ["tank_no", "fermentation_batch_id"],
                    stats,
                    "tanks",
                )

            if not cur_tank_id:
                stats["skipped"] += 1
                continue

            # ─ 3. 萃取批次 ─
            if eno:  # 新萃取行
                extr_data = {
                    "fermentation_tank_id": cur_tank_id,
                    "feeding_time": _g(row, "feeding_time") or None,
                    "extraction_batch_no": cur_extr_no,
                    "feeding_plates": _i(row, "feeding_plates"),
                    "extraction_product_qty": _f(row, "extraction_pq"),
                    "total_qty": _f(row, "total_qty"),
                    "fermentation_liquid_yield": _f(row, "fl_yield"),
                    "single_batch_yield": _f(row, "single_yield"),
                }
                cur_extr_id = await _upsert(
                    session,
                    "production.dr_extractions",
                    extr_data,
                    ["extraction_batch_no", "fermentation_tank_id"],
                    stats,
                    "extractions",
                )

            if not cur_extr_id:
                stats["skipped"] += 1
                continue

            # ─ 4. 滤液 ─
            ft = _g(row, "filtrate_tank")
            if ft:
                filtr_data = {
                    "extraction_id": cur_extr_id,
                    "tank_no": ft,
                    "volume": _f(row, "filtrate_volume"),
                    "potency": _f(row, "filtrate_potency"),
                    "product_qty": _f(row, "filtrate_pq"),
                    "dilute_wash_volume": _f(row, "dw_volume"),
                    "dilute_wash_potency": _f(row, "dw_potency"),
                    "dilute_wash_product_qty": _f(row, "dw_pq"),
                }
                await _upsert(
                    session,
                    "production.dr_filtrates",
                    filtr_data,
                    ["extraction_id", "tank_no"],
                    stats,
                    "filtrates",
                )

            # ─ 5. 杂质（仅在该行有值时更新） ─
            if cur_batch_id:
                imp_updates: dict[str, Any] = {}
                imp_params: dict[str, Any] = {}
                for field in [
                    "impurity_6",
                    "impurity_1",
                    "impurity_2",
                    "impurity_7",
                    "impurity_3",
                    "impurity_4",
                    "impurity_5",
                    "rrt_068",
                    "unknown_max",
                    "total_impurities",
                    "purity",
                ]:
                    val = _f(row, field)
                    if val is not None:
                        db_col = IMPURITY_MAP.get(field, field)
                        imp_updates[db_col] = val
                        imp_params[db_col] = val
                if imp_updates:
                    set_sql = ", ".join(f"{k} = :{k}" for k in imp_updates)
                    imp_params["bid"] = cur_batch_id
                    await session.execute(
                        text(
                            f"UPDATE production.dr_fermentation_batches SET {set_sql} WHERE id = :bid"  # noqa: E501
                        ),
                        imp_params,
                    )

            await session.flush()

        except Exception as e:
            logger.warning(f"[DR同步] 行 {ri + DATA_START_ROW}: {e}")
            stats["errors"] += 1
            try:
                await session.rollback()
            except Exception:
                pass

    await session.commit()
    logger.info("[DR同步] 完成: %s", stats)
    return stats


# ── upsert 通用函数 ──────────────────────────────────────


async def _upsert(
    session: AsyncSession,
    table: str,
    data: dict[str, Any],
    unique_keys: list[str],
    stats: dict[str, Any],
    stat_key: str,
) -> str:
    """按 unique_keys 去重 upsert，返回记录 UUID"""
    # 查现有
    where = " AND ".join(f"{k} = :{k}" for k in unique_keys)
    params = {k: data[k] for k in unique_keys}
    result = await session.execute(
        text(f"SELECT id FROM {table} WHERE {where} AND is_deleted = false"),
        params,
    )
    row = result.fetchone()

    if row:
        rid = str(row[0])
        set_parts = []
        up_params = {}
        for k, v in data.items():
            if k not in unique_keys and v is not None:
                set_parts.append(f"{k} = :{k}")
                up_params[k] = v
        if set_parts:
            up_params["id"] = rid
            await session.execute(
                text(f"UPDATE {table} SET {', '.join(set_parts)} WHERE id = :id"),
                up_params,
            )
        stats[f"updated_{stat_key}"] += 1
        return rid
    else:
        cols = ", ".join(data.keys())
        vals = ", ".join(f":{k}" for k in data)
        await session.execute(
            text(
                f"INSERT INTO {table} (id, {cols}) VALUES (gen_random_uuid(), {vals})"
            ),
            data,
        )
        # 再次查询获取新 ID
        result2 = await session.execute(
            text(f"SELECT id FROM {table} WHERE {where} AND is_deleted = false"),
            {k: data[k] for k in unique_keys},
        )
        rid = str(result2.scalar_one())
        stats[f"created_{stat_key}"] += 1
        return rid


# ── DR 定时同步调度 ──────────────────────────────────────

DR_PRODUCT_NAME = "多拉菌素"


async def run_dr_sync(session: AsyncSession) -> dict[str, Any]:
    """遍历 DR 全部启用配置并同步（对齐 MC/FA 的 run_*_sync 统一入口）。

    注意：sync_dr_extraction 会顺带 upsert dr_fermentation_batches（发酵批次），
    因此无需单独的发酵批次同步配置；定时跑本函数即可让发酵批次持续更新。
    """
    from app.modules.production.production_plan_service import sync_config_by_target

    result = await session.execute(
        select(ProductionFeishuConfig)
        .where(
            ProductionFeishuConfig.product_name == DR_PRODUCT_NAME,
            ProductionFeishuConfig.is_active,
            ProductionFeishuConfig.is_deleted.is_(False),
        )
        .order_by(ProductionFeishuConfig.sync_target)
    )
    configs = result.scalars().all()
    if not configs:
        logger.warning("[DR同步] 未找到多拉菌素的飞书同步配置")
        return {"error": "未找到多拉菌素飞书同步配置"}

    results = {}
    for cfg in configs:
        try:
            logger.info("[DR同步] 开始同步 %s ...", cfg.sync_target)
            stats = await sync_config_by_target(cfg, session)
            results[cfg.sync_target] = stats
            logger.info("[DR同步] %s 完成", cfg.sync_target)
        except Exception as e:
            logger.exception("[DR同步] %s 失败: %s", cfg.sync_target, e)
            results[cfg.sync_target] = {"error": str(e)}
            try:
                await session.rollback()
            except Exception:
                pass
    return results


_dr_sync_scheduler: Any = None
DR_SYNC_INTERVAL_MINUTES = 10


async def _dr_scheduled_sync_job() -> Any:
    """定时同步任务：每 10 分钟从飞书同步 DR 多拉菌素全部工段（含发酵批次）。"""
    logger.info("⏰ [DR飞书同步] 定时任务触发")
    try:
        from app.core.database import async_session_factory

        async with async_session_factory() as session:
            results = await run_dr_sync(session)
        errors = [k for k, r in results.items() if isinstance(r, dict) and "error" in r]
        if errors:
            logger.warning("[DR飞书同步] %d 个同步目标失败: %s", len(errors), errors)
    except Exception:
        logger.exception("[DR飞书同步] 定时任务异常")


def start_dr_sync_scheduler() -> Any:
    """启动 DR 飞书同步定时任务（每 10 分钟，与 MC/FA 对齐）。"""
    global _dr_sync_scheduler
    from apscheduler.schedulers.asyncio import (  # type: ignore[import-untyped]
        AsyncIOScheduler,
    )
    from apscheduler.triggers.interval import (  # type: ignore[import-untyped]
        IntervalTrigger,
    )

    if _dr_sync_scheduler is not None:
        return
    _dr_sync_scheduler = AsyncIOScheduler()
    _dr_sync_scheduler.add_job(
        _dr_scheduled_sync_job,
        trigger=IntervalTrigger(minutes=DR_SYNC_INTERVAL_MINUTES),
        id="dr_feishu_sync",
        name="DR 多拉菌素飞书电子表格定时同步",
        replace_existing=True,
    )
    _dr_sync_scheduler.start()
    logger.info("[DR飞书同步] 定时任务已启动，间隔 %d 分钟", DR_SYNC_INTERVAL_MINUTES)


def stop_dr_sync_scheduler() -> Any:
    """停止 DR 飞书同步定时任务。"""
    global _dr_sync_scheduler
    if _dr_sync_scheduler is not None:
        _dr_sync_scheduler.shutdown(wait=False)
        _dr_sync_scheduler = None
        logger.info("[DR飞书同步] 定时任务已停止")
