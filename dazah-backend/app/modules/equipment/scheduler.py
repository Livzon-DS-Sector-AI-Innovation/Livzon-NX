"""Maintenance plan auto-generation background scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.database import async_session_factory

logger = logging.getLogger(__name__)

# 中国标准时间 UTC+8
CST = timezone(timedelta(hours=8))

stop_maintenance_plan_flag = asyncio.Event()


async def maintenance_plan_loop() -> None:
    """每天 00:05 CST 扫描到期的维护计划并自动生成工单。

    选择 00:05 而非 00:00 是为了避开飞书成员同步（00:00）的执行窗口，
    减少并发数据库连接压力。
    """
    settings = get_settings()
    if not settings.MAINTENANCE_PLAN_AUTO_ENABLED:
        logger.info(
            "维护计划自动生成功能已关闭（MAINTENANCE_PLAN_AUTO_ENABLED=false），跳过启动"
        )
        return

    logger.info("维护计划自动生成任务已启动（每天 00:05 CST）")

    while not stop_maintenance_plan_flag.is_set():
        # 计算到下一个 00:05 CST 的等待秒数
        now = datetime.now(CST)
        next_run = (now + timedelta(days=1)).replace(
            hour=0, minute=5, second=0, microsecond=0,
        )
        # 如果当前时间还没过今天的 00:05，则设为今天
        if now.hour == 0 and now.minute < 5:
            next_run = now.replace(
                hour=0, minute=5, second=0, microsecond=0,
            )
        wait_seconds = (next_run - now).total_seconds()

        logger.info(
            "下次维护计划扫描将在 %.0f 分钟后（%s）",
            wait_seconds / 60,
            next_run.strftime("%Y-%m-%d %H:%M"),
        )

        try:
            await asyncio.wait_for(
                stop_maintenance_plan_flag.wait(),
                timeout=wait_seconds,
            )
            break  # stop flag 被设置，退出循环
        except TimeoutError:
            pass

        if stop_maintenance_plan_flag.is_set():
            break

        # 每次 tick 重新读取配置，支持运行时动态开关
        if not get_settings().MAINTENANCE_PLAN_AUTO_ENABLED:
            logger.debug("维护计划自动生成已关闭，跳过本轮")
            continue

        try:
            async with async_session_factory() as db:
                from app.modules.equipment.service.maintenance_plan import (
                    generate_due_work_orders,
                )

                created_count, skipped_count = await generate_due_work_orders(
                    db
                )
                await db.commit()

                logger.info(
                    "维护计划自动生成完成: 创建 %d 个工单, 跳过 %d 个计划",
                    created_count,
                    skipped_count,
                )
        except Exception:
            logger.exception("维护计划自动生成循环异常")

    logger.info("维护计划自动生成任务已停止")


# ── Timeout scanning ────────────────────────────────────────────────

stop_timeout_flag = asyncio.Event()


async def scan_timeout_work_orders() -> None:
    """扫描超时未接单的工单"""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.database import async_session_factory
    from app.modules.equipment.models.work_order import WorkOrder
    from app.platform.integrations.feishu.contact import get_department_leader
    from app.platform.integrations.feishu.message import send_timeout_notification

    settings = get_settings()
    dept_id = settings.FEISHU_EQUIPMENT_DEPT_ID
    if not dept_id:
        return

    async with async_session_factory() as db:
        try:
            from app.modules.equipment.service.maintenance_config import (
                get_claim_timeout_config,
            )

            config = await get_claim_timeout_config(db)
            result = await db.execute(
                select(WorkOrder).where(
                    WorkOrder.status == "待处理",
                    WorkOrder.is_deleted == False,  # noqa: E712
                )
            )
            pending_orders = result.scalars().all()

            now = datetime.now(UTC)
            priority_map = {
                "紧急": "emergency", "高": "high",
                "中": "medium", "低": "low",
            }
            for order in pending_orders:
                attr = priority_map.get(order.priority, "medium")
                timeout_minutes = getattr(config, attr, 60)
                elapsed = (now - order.reported_at).total_seconds() / 60
                if elapsed > timeout_minutes:
                    leader = await get_department_leader(dept_id)
                    leader_name = (
                        leader.get("name", "主管") if leader else "主管"
                    )
                    await send_timeout_notification(
                        order.work_order_no, "设备", leader_name,
                    )
                    logger.info(
                        "Timeout WO %s (%.0f min > %d min)",
                        order.work_order_no, elapsed, timeout_minutes,
                    )
        except Exception:
            logger.exception("Timeout scan error")
        finally:
            await db.rollback()


async def timeout_scan_loop() -> None:
    """每60秒扫描超时工单"""
    logger.info("工单超时扫描任务已启动（每60秒）")
    while not stop_timeout_flag.is_set():
        try:
            await scan_timeout_work_orders()
        except Exception:
            logger.exception("Timeout scan error")
        try:
            await asyncio.wait_for(
                stop_timeout_flag.wait(), timeout=60,
            )
        except TimeoutError:
            pass
    logger.info("工单超时扫描任务已停止")
