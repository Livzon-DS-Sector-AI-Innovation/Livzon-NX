"""报修工单 → 飞书多维表格台账（平台 → 飞书方向的实时镜像）。

工单状态每次变化后按工单号 upsert 一行，供管理层在飞书侧直接做
筛选与仪表盘统计（按车间/设备/维修工的故障率、MTTR 等）。

设计约束：
- 台账是"展示镜像"不是数据源：任何失败只记日志，绝不影响工单主流程；
- 未配置（app_token/table_id 为空）时整体停用，静默跳过；
- 同步任务延迟 1 秒启动，错开调用方（get_db / WS 会话）的事务提交窗口。
"""

import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_factory

logger = logging.getLogger(__name__)
settings = get_settings()

FEISHU_DOMAIN = "https://open.feishu.cn"
# 同步任务引用，防止被 GC 中断
_sync_tasks: set[asyncio.Task[None]] = set()


def ledger_enabled() -> bool:
    return bool(
        getattr(settings, "REPAIR_LEDGER_APP_TOKEN", "")
        and getattr(settings, "REPAIR_LEDGER_TABLE_ID", "")
    )


async def _ledger_token() -> str:
    """用应用库第一个应用的凭据取 tenant_access_token。"""
    from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
    from app.modules.equipment.service.feishu_app import decrypt_app_secret

    async with async_session_factory() as db:
        app = (
            (
                await db.execute(
                    select(EquipmentFeishuApp)
                    .where(EquipmentFeishuApp.is_deleted == False)  # noqa: E712
                    .order_by(EquipmentFeishuApp.created_at)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if app is None:
            raise RuntimeError("应用库为空，无法同步报修台账")
        app_id = app.app_id
        secret = decrypt_app_secret(app.app_secret)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{FEISHU_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": secret},
        )
        token = str(resp.json().get("tenant_access_token", ""))
    if not token:
        raise RuntimeError("报修台账 token 获取失败")
    return token


def _fields_payload(
    wo: Any, equipment: Any, reporter: str, assignee: str
) -> dict[str, Any]:
    def ms(dt: Any) -> int | None:
        return int(dt.timestamp() * 1000) if dt else None

    duration = None
    reported_at = getattr(wo, "reported_at", None) or wo.created_at
    if wo.completed_at and reported_at:
        duration = max(int((wo.completed_at - reported_at).total_seconds() // 60), 0)
    return {
        "工单号": wo.work_order_no,
        "车间": equipment.workshop_code if equipment else "",
        "设备": (
            f"{equipment.name}（{equipment.equipment_no}）" if equipment else ""
        ),
        "故障描述": wo.fault_description or "",
        "紧急度": wo.priority or "高",
        "状态": wo.status,
        "报修人": reporter,
        "维修人": assignee,
        "报修时间": ms(reported_at),
        "接单时间": ms(wo.started_at),
        "完工时间": ms(wo.completed_at),
        "修复耗时分钟": duration,
    }


async def _find_record_id(
    client: httpx.AsyncClient,
    token: str,
    value: str,
    *,
    table_id: str | None = None,
    field_name: str = "工单号",
) -> str:
    """按字段值搜索表格记录，返回 record_id（无则空串）。

    主台账按「工单号」upsert；车间汇总表按「车间」upsert，
    因此表和匹配字段由调用方指定，默认主台账 + 工单号。
    """
    table = table_id or settings.REPAIR_LEDGER_TABLE_ID
    resp = await client.post(
        f"{FEISHU_DOMAIN}/open-apis/bitable/v1/apps/"
        f"{settings.REPAIR_LEDGER_APP_TOKEN}/tables/"
        f"{table}/records/search?page_size=20",
        headers={"Authorization": f"Bearer {token}"},
        json={"filter": {"conjunction": "and", "conditions": []},
              "field_names": [field_name]},
    )
    data = resp.json()
    for item in (data.get("data") or {}).get("items", []) or []:
        if (item.get("fields") or {}).get(field_name) == value:
            return str(item.get("record_id", ""))
    # search 接口拿不到时兜底拉全量字段比对
    resp = await client.get(
        f"{FEISHU_DOMAIN}/open-apis/bitable/v1/apps/"
        f"{settings.REPAIR_LEDGER_APP_TOKEN}/tables/"
        f"{table}/records?page_size=500",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    for item in (data.get("data") or {}).get("items", []) or []:
        if (item.get("fields") or {}).get(field_name) == value:
            return str(item.get("record_id", ""))
    return ""


async def _upsert_ledger(wo_no: str) -> None:
    """读库取工单最新状态，按工单号 upsert 台账行。"""
    from app.modules.equipment.models.equipment import Equipment
    from app.modules.equipment.models.work_order import WorkOrder
    from app.platform.identity.models import User

    await asyncio.sleep(1)  # 错开调用方事务提交
    async with async_session_factory() as db:
        wo = (
            (
                await db.execute(
                    select(WorkOrder).where(WorkOrder.work_order_no == wo_no)
                )
            )
            .scalars()
            .first()
        )
        if wo is None:
            logger.warning("台账同步：工单 %s 不存在", wo_no)
            return
        equipment = (
            (
                await db.execute(
                    select(Equipment).where(Equipment.id == wo.equipment_id)
                )
            )
            .scalars()
            .first()
        )
        user_rows = (
            await db.execute(select(User.id, User.name))
        ).all()
        names = {uid: name for uid, name in user_rows}
        reporter = names.get(wo.reporter_id, "") if wo.reporter_id else ""
        assignee = names.get(wo.assignee_id, "") if wo.assignee_id else ""

    fields = _fields_payload(wo, equipment, reporter, assignee)
    token = await _ledger_token()
    async with httpx.AsyncClient(timeout=15) as client:
        record_id = await _find_record_id(client, token, wo_no)
        if record_id:
            resp = await client.put(
                f"{FEISHU_DOMAIN}/open-apis/bitable/v1/apps/"
                f"{settings.REPAIR_LEDGER_APP_TOKEN}/tables/"
                f"{settings.REPAIR_LEDGER_TABLE_ID}/records/{record_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"fields": fields},
            )
        else:
            resp = await client.post(
                f"{FEISHU_DOMAIN}/open-apis/bitable/v1/apps/"
                f"{settings.REPAIR_LEDGER_APP_TOKEN}/tables/"
                f"{settings.REPAIR_LEDGER_TABLE_ID}/records",
                headers={"Authorization": f"Bearer {token}"},
                json={"fields": fields},
            )
        data = resp.json()
        ok = resp.status_code == 200 and data.get("code") == 0
    if not ok:
        logger.warning(
            "报修台账同步失败: %s code=%s msg=%s",
            wo_no, data.get("code"), data.get("msg"),
        )
        return
    logger.info("报修台账已同步: %s → %s", wo_no, fields.get("状态"))
    if equipment is not None and settings.REPAIR_LEDGER_SUMMARY_TABLE_ID:
        async with httpx.AsyncClient(timeout=15) as client:
            await _refresh_workshop_summary(
                client, token, str(equipment.workshop_code)
            )


async def _refresh_workshop_summary(
    client: httpx.AsyncClient, token: str, workshop_code: str
) -> None:
    """按车间聚合工单统计，upsert 到「车间汇总」表（一车间一行）。"""
    from app.modules.equipment.models.equipment import Equipment
    from app.modules.equipment.models.work_order import WorkOrder

    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(WorkOrder, Equipment)
                    .join(Equipment, WorkOrder.equipment_id == Equipment.id)
                    .where(
                        Equipment.workshop_code == workshop_code,
                        WorkOrder.is_deleted == False,  # noqa: E712
                    )
                )
            )
            .all()
        )
    by_status: dict[str, int] = {}
    urgent = 0
    durations: list[int] = []
    latest: Any = None
    for wo, _eq in rows:
        by_status[wo.status] = by_status.get(wo.status, 0) + 1
        if wo.priority == "紧急":
            urgent += 1
        reported_at = getattr(wo, "reported_at", None) or wo.created_at
        if wo.completed_at and reported_at:
            durations.append(
                max(int((wo.completed_at - reported_at).total_seconds() // 60), 0)
            )
        if reported_at and (latest is None or reported_at > latest):
            latest = reported_at

    fields = {
        "车间": workshop_code,
        "工单总数": len(rows),
        "待处理": by_status.get("待处理", 0),
        "执行中": by_status.get("执行中", 0),
        "待验收": by_status.get("待验收", 0),
        "已关闭": by_status.get("已关闭", 0) + by_status.get("已完成", 0),
        "紧急工单数": urgent,
        "平均修复分钟": round(sum(durations) / len(durations)) if durations else None,
        "最近报修": int(latest.timestamp() * 1000) if latest else None,
    }

    table = settings.REPAIR_LEDGER_SUMMARY_TABLE_ID
    record_id = await _find_record_id(
        client, token, workshop_code, table_id=table, field_name="车间"
    )
    if record_id:
        resp = await client.put(
            f"{FEISHU_DOMAIN}/open-apis/bitable/v1/apps/"
            f"{settings.REPAIR_LEDGER_APP_TOKEN}/tables/{table}/records/{record_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": fields},
        )
    else:
        resp = await client.post(
            f"{FEISHU_DOMAIN}/open-apis/bitable/v1/apps/"
            f"{settings.REPAIR_LEDGER_APP_TOKEN}/tables/{table}/records",
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": fields},
        )
    data = resp.json()
    if resp.status_code != 200 or data.get("code") != 0:
        logger.warning(
            "车间汇总同步失败: %s code=%s msg=%s",
            workshop_code, data.get("code"), data.get("msg"),
        )
    else:
        logger.info("车间汇总已同步: %s（共 %d 单）", workshop_code, len(rows))


def schedule_ledger_sync(wo_no: str) -> None:
    """工单状态变化后调用：后台延迟同步台账，失败不影响主流程。"""
    if not ledger_enabled():
        return
    try:
        task = asyncio.create_task(_upsert_ledger(wo_no))
        _sync_tasks.add(task)
        task.add_done_callback(_sync_tasks.discard)
    except Exception:
        logger.warning("报修台账任务调度失败", exc_info=True)
