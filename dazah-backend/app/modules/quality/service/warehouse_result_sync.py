"""质量固体/液体物料检验结果 → 仓储入库台账 即时联动。

质量检验记录新增/修改「结果判断」后，把结果同步到仓储入库台账：
- 固体实体（qc_solid_*）→ 入库总账（inbound-ledger），按 厂内代码+厂内批号 匹配
  （质量批号 "YS606-2609017" 拆成 代码+批号 两段）
- 液体实体（qc_liquid_*）→ 液体原辅料入库（liquid-raw-inbound），按 入库批号
  匹配（质量批号整串，如 "YL007-2609001"）
- 台账「检测结果」待验（空）→ 合格/不合格；不合格时写入「不合格项目」，
  合格不动该列；只更新已存在行（多行取最新），不新建
- best-effort：仓储侧任何失败只记日志，绝不影响质量检验写入
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 触发联动的结果判断取值（其他取值如空/待判定不同步）
_RESULT_TRIGGER_VALUES = {"合格", "不合格"}

# 钩子触发关注的质量字段（字段含其一才读回记录联动）
_RESULT_WATCH_FIELDS = {"结果判断", "不合格项目"}


def _is_material_entity(entity_code: str) -> bool:
    return entity_code.startswith("qc_solid_") or entity_code.startswith(
        "qc_liquid_"
    )


def _material_module(entity_code: str) -> str:
    return "solid" if entity_code.startswith("qc_solid_") else "liquid"


def _as_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


async def sync_record_result_to_warehouse(
    db: AsyncSession, *, entity_code: str, record_id: str
) -> dict[str, Any] | None:
    """读回质量检验记录，把结果判断联动到仓储入库台账。

    使用独立 DB 会话承载仓储侧操作，避免仓储镜像写库影响质量请求会话。
    返回仓储侧结果；未触发（无批号/结果无效等）返回 None。
    """
    # 延迟导入避免与 crud 模块循环依赖
    from app.modules.quality.service.inspection_feishu_crud import (
        get_inspection_feishu_record,
    )

    record = await get_inspection_feishu_record(db, entity_code, record_id)
    result = _as_text(record.get("结果判断"))
    if result not in _RESULT_TRIGGER_VALUES:
        return None

    batch_no = _as_text(record.get("批号"))
    if not batch_no:
        logger.warning(
            "warehouse result sync: %s/%s 无批号，跳过联动", entity_code, record_id
        )
        return None

    module = _material_module(entity_code)
    if module == "solid":
        # 固体批号 "YS606-2609017" → 厂内代码 + 厂内批号
        if "-" not in batch_no:
            logger.warning(
                "warehouse result sync: 固体批号 %r 无物料代码前缀，跳过联动",
                batch_no,
            )
            return None
        material_code, _, batch_seq = batch_no.rpartition("-")
    else:
        # 液体批号整串即液体入库台账「入库批号」
        material_code, batch_seq = "", batch_no

    # 读回的是归一化后的文本值；不合格项目可能是结构化数组经归一化的字符串
    unqualified_items = _as_text(record.get("不合格项目"))

    # 独立会话承载仓储侧定位+写回+镜像刷新（经仓储模块 public_api 调用）
    from app.core.database import async_session_factory
    from app.modules.warehouse.public_api import update_inbound_inspection_result

    async with async_session_factory() as wh_db:
        try:
            outcome = await update_inbound_inspection_result(
                wh_db,
                material_module=module,
                material_code=material_code,
                batch_no=batch_seq,
                result=result,
                unqualified_items=unqualified_items,
            )
        except Exception:
            # 仓储侧异常：不提交，回滚本会话内已 flush 的镜像写入后向上抛
            # （由 maybe_sync_result_to_warehouse 记 warning，best-effort）
            await wh_db.rollback()
            raise
        # 镜像刷新链路只 flush 不 commit（历史调用方依赖外层提交），
        # 成功路径显式提交，否则刷新写入随会话关闭回滚
        await wh_db.commit()
        return outcome


async def maybe_sync_result_to_warehouse(
    db: AsyncSession,
    *,
    entity_code: str,
    record_id: str,
    fields: dict[str, Any] | None,
) -> None:
    """质量检验记录写入成功后的联动入口（best-effort，失败只记日志）。

    仅物料实体且本次写入涉及 结果判断/不合格项目 时触发。
    """
    if not _is_material_entity(entity_code):
        return
    if not _RESULT_WATCH_FIELDS.intersection(set(fields or {})):
        return
    try:
        outcome = await sync_record_result_to_warehouse(
            db, entity_code=entity_code, record_id=record_id
        )
        if outcome is not None:
            logger.info(
                "warehouse result sync done: %s record=%s -> %s",
                entity_code,
                record_id,
                outcome,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "warehouse result sync failed (best-effort): %s/%s %s",
            entity_code,
            record_id,
            exc,
        )
