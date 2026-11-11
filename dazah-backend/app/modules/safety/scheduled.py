"""安全模块定时任务（平台调度器接入）。

- 法规雷达：每周一 08:00（北京时间）自动扫描一次，手动触发走 API。
- 页面镜像同步：每 15 分钟同步启用的镜像页（本地全量副本），
  手动触发走「安全飞书设置」页的立即同步按钮。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from app.core.maintenance import MaintenanceActiveError, business_activity
from app.modules.safety.models import SafetyPageFeishuConfig
from app.modules.safety.service import (
    hazard_due_reminder,
    page_table,
    regulation_radar,
)
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator

logger = logging.getLogger(__name__)

MIRROR_SYNC_INTERVAL = timedelta(minutes=15)
_MIRROR_SYNC_RETRY_SECONDS = 5


class SafetyRegulationRadarGenerator(TaskGenerator):
    """每周一 08:00 扫描官方栏目页，发现新法规与已修订法规。"""

    name = "safety.regulation_radar_weekly"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.CRON,
        # 分 时 日 月 周 —— 每周一 08:00
        expression="0 8 * * 1",
        timezone="Asia/Shanghai",
    )
    # 抓取 5 个站点 + AI 过滤 + 写入飞书，放宽超时
    timeout_seconds = 1800

    async def find_due(self, session: Any) -> list[Any]:
        # 尊重设置页的「自动扫描」开关（safety.feishu_app_settings.radar_scan_enabled）
        from app.modules.safety.models import SafetyFeishuAppSettings

        row = (
            await session.execute(
                select(SafetyFeishuAppSettings)
                .where(SafetyFeishuAppSettings.is_deleted.is_(False))
                .order_by(SafetyFeishuAppSettings.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None or not row.radar_scan_enabled:
            logger.info("法规雷达自动扫描已关闭（radar_scan_enabled=false），本轮跳过")
            return []
        return [True]

    async def execute_one(self, session: Any, item: Any) -> None:
        result = await regulation_radar.run_radar(
            session, dry_run=False, trigger="schedule"
        )
        logger.info(
            "法规雷达周扫完成: 状态=%s 新=%s 修订=%s 跳过=%s 错误=%s",
            result.get("status"),
            result.get("new_count"),
            result.get("revised_count"),
            result.get("skipped_count"),
            len(result.get("errors", [])),
        )


class SafetyHazardDueReminderGenerator(TaskGenerator):
    """每天 08:00 检查隐患台账：进入提醒节点（如到期前一个月/半个月/一周）
    或逾期的未关闭隐患推送提醒，同一节点只推一次。

    尊重设置页的开关与提前天数（safety.feishu_app_settings.hazard_due_*）；
    无临期/逾期项时静默跳过。手动测试走设置页「测试发送」。
    """

    name = "safety.hazard_due_daily"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.CRON,
        # 分 时 日 月 周 —— 每天 08:00
        expression="0 8 * * *",
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 300

    async def find_due(self, session: Any) -> list[Any]:
        from app.core.config import get_settings
        from app.modules.safety.models import SafetyFeishuAppSettings

        # 开发环境的定时任务不自动推送真实飞书消息（开发栈热重载/重启
        # 频繁，且推送目标常指向真实群）；验证发送走设置页「发送测试提醒」。
        if get_settings().APP_ENV != "production":
            logger.info("非生产环境（APP_ENV!=production），到期提醒自动推送跳过")
            return []

        row = (
            await session.execute(
                select(SafetyFeishuAppSettings)
                .where(SafetyFeishuAppSettings.is_deleted.is_(False))
                .order_by(SafetyFeishuAppSettings.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None or not row.hazard_due_notify_enabled:
            logger.info(
                "隐患到期提醒未启用（hazard_due_notify_enabled=false），本轮跳过"
            )
            return []
        return [True]

    async def execute_one(self, session: Any, item: Any) -> None:
        sent, errors = await hazard_due_reminder.send_hazard_due_notifications(
            session
        )
        logger.info(
            "隐患到期提醒推送完成: 成功=%s 错误=%s", sent, errors or "无"
        )


class SafetyPageMirrorSyncGenerator(TaskGenerator):
    """每 15 分钟同步启用的页面镜像（飞书多维表格 → 本地全量副本）。

    只挑「绑定完整、镜像开启、距上次同步超过间隔」的页面；同步失败
    状态回写绑定行，不影响其他页面。手动触发走设置页「立即同步」。
    """

    name = "safety.page_table_mirror_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=int(MIRROR_SYNC_INTERVAL.total_seconds()),
        timezone="Asia/Shanghai",
    )
    # 全量翻页拉取大表可能较慢，放宽超时
    timeout_seconds = 30 * 60

    async def find_due(self, session: Any) -> list[Any]:
        cutoff = datetime.now(UTC) - MIRROR_SYNC_INTERVAL
        result = await session.execute(
            select(SafetyPageFeishuConfig.page_key).where(
                SafetyPageFeishuConfig.is_deleted.is_(False),
                SafetyPageFeishuConfig.is_enabled.is_(True),
                SafetyPageFeishuConfig.is_mirrored.is_(True),
                SafetyPageFeishuConfig.app_token.isnot(None),
                SafetyPageFeishuConfig.table_id.isnot(None),
                or_(
                    SafetyPageFeishuConfig.last_synced_at.is_(None),
                    SafetyPageFeishuConfig.last_synced_at <= cutoff,
                ),
            )
        )
        return [str(key) for key in result.scalars().all()]

    async def execute_one(self, session: Any, item: Any) -> None:
        page_key = str(item)
        count = await page_table.sync_page_table_mirror(session, page_key)
        logger.info("页面镜像定时同步完成: page=%s 记录=%s", page_key, count)


class SafetyFireExpiryReminderGenerator(TaskGenerator):
    """每天 08:20 检查消防器材台账：有效日期进入提醒节点（如还剩一个月/
    半个月/一周）或已过期时推送飞书提醒，同一台器材同一节点只推一次。

    尊重设置页的开关与节点天数（safety.feishu_app_settings.fire_expiry_*）；
    无新触发节点时静默跳过。手动测试走设置页「测试发送」。
    """

    name = "safety.fire_expiry_daily"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.CRON,
        # 分 时 日 月 周 —— 每天 08:20（错开隐患提醒的 08:00）
        expression="20 8 * * *",
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 300

    async def find_due(self, session: Any) -> list[Any]:
        from app.modules.safety.models import SafetyFeishuAppSettings

        row = (
            await session.execute(
                select(SafetyFeishuAppSettings)
                .where(SafetyFeishuAppSettings.is_deleted.is_(False))
                .order_by(SafetyFeishuAppSettings.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None or not row.fire_expiry_notify_enabled:
            logger.info(
                "消防器材有效期提醒未启用（fire_expiry_notify_enabled=false），本轮跳过"
            )
            return []
        return [True]

    async def execute_one(self, session: Any, item: Any) -> None:
        from app.modules.safety.service import fire_expiry_reminder

        sent, errors = (
            await fire_expiry_reminder.send_fire_expiry_notifications(session)
        )
        logger.info(
            "消防器材有效期提醒推送完成: 成功=%s 错误=%s", sent, errors or "无"
        )


class SafetyWorkPermitGasDueGenerator(TaskGenerator):
    """每 15 分钟扫描「作业中」的动火/受限空间作业票：气体复检到期或
    超期时向监护人与作业负责人推送飞书催办（同一到期窗口只催一次）。

    尊重设置页开关（permit_notify_enabled）；复检间隔可经
    work_permit_settings 覆盖（默认动火 60 分钟、受限空间 120 分钟）。
    """

    name = "safety.work_permit_gas_due"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=15 * 60,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 120

    async def find_due(self, session: Any) -> list[Any]:
        from app.core.config import get_settings
        from app.modules.safety.models import SafetyFeishuAppSettings

        # 非生产环境不自动推送真实飞书消息（护栏同隐患到期提醒）
        if get_settings().APP_ENV != "production":
            logger.info(
                "非生产环境（APP_ENV!=production），作业票复检催办跳过"
            )
            return []

        row = (
            await session.execute(
                select(SafetyFeishuAppSettings)
                .where(SafetyFeishuAppSettings.is_deleted.is_(False))
                .order_by(SafetyFeishuAppSettings.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None or not row.permit_notify_enabled:
            logger.info(
                "作业票飞书通知未启用（permit_notify_enabled=false），本轮跳过"
            )
            return []
        return [True]

    async def execute_one(self, session: Any, item: Any) -> None:
        from app.modules.safety.service.work_permit_reminders import (
            send_gas_due_reminders,
        )

        sent, errors = await send_gas_due_reminders(session)
        if errors:
            logger.warning("作业票复检催办存在失败: %s", errors)


class SafetyCertificateExpiryReminderGenerator(TaskGenerator):
    """每天 08:40 检查特种作业证件台账：有效期进入提醒节点（默认
    30/15/7 天）或已过期时推送飞书提醒，同一证件同一节点只推一次。

    尊重设置页的开关与节点天数（safety.feishu_app_settings.cert_expiry_*）。
    """

    name = "safety.cert_expiry_daily"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.CRON,
        # 分 时 日 月 周 —— 每天 08:40（错开消防提醒的 08:20）
        expression="40 8 * * *",
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 300

    async def find_due(self, session: Any) -> list[Any]:
        from app.core.config import get_settings
        from app.modules.safety.models import SafetyFeishuAppSettings

        if get_settings().APP_ENV != "production":
            logger.info(
                "非生产环境（APP_ENV!=production），证件到期提醒自动推送跳过"
            )
            return []

        row = (
            await session.execute(
                select(SafetyFeishuAppSettings)
                .where(SafetyFeishuAppSettings.is_deleted.is_(False))
                .order_by(SafetyFeishuAppSettings.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None or not row.cert_expiry_notify_enabled:
            logger.info(
                "证件到期提醒未启用（cert_expiry_notify_enabled=false），本轮跳过"
            )
            return []
        return [True]

    async def execute_one(self, session: Any, item: Any) -> None:
        from app.modules.safety.service.work_permit_reminders import (
            send_certificate_expiry_notifications,
        )

        sent, errors = await send_certificate_expiry_notifications(session)
        if errors:
            logger.warning("证件到期提醒存在失败: %s", errors)


class SafetyCommitmentPushGenerator(TaskGenerator):
    """每 15 分钟检查安全承诺填报推送：到达设置页配置的推送时间
    （commitment_push_time，默认 08:30）后，向填报人员推送当日填报
    提醒卡（同一自然日只推一次，Redis 当日去重）。

    尊重设置页开关（commitment_notify_enabled）；首次触发会惰性初始化
    当日日报（继承上一日 + 自动 AI 研判）。非生产环境直接跳过。
    """

    name = "safety.commitment_daily_push"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=15 * 60,
        timezone="Asia/Shanghai",
    )
    timeout_seconds = 300

    async def find_due(self, session: Any) -> list[Any]:
        from datetime import datetime, timedelta, timezone

        from app.core.config import get_settings
        from app.core.redis import cache_get
        from app.modules.safety.models import SafetyFeishuAppSettings

        if get_settings().APP_ENV != "production":
            logger.info(
                "非生产环境（APP_ENV!=production），安全承诺填报推送跳过"
            )
            return []

        cn_tz = timezone(timedelta(hours=8))
        now_local = datetime.now(cn_tz)
        report_date = now_local.date().isoformat()
        if await cache_get(f"commitment_push_done:{report_date}"):
            return []

        row = (
            await session.execute(
                select(SafetyFeishuAppSettings)
                .where(SafetyFeishuAppSettings.is_deleted.is_(False))
                .order_by(SafetyFeishuAppSettings.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None or not row.commitment_notify_enabled:
            return []
        if not (row.commitment_user_ids or []):
            return []

        push_time = str(row.commitment_push_time or "08:30")
        try:
            hour, minute = (int(part) for part in push_time.split(":", 1))
        except ValueError:
            logger.warning("commitment_push_time 格式无效: %s", push_time)
            return []
        now_minutes = now_local.hour * 60 + now_local.minute
        if now_minutes < hour * 60 + minute:
            return []
        return [report_date]

    async def execute_one(self, session: Any, item: Any) -> None:

        from app.core.redis import cache_set
        from app.modules.safety.service.commitment_notify import (
            push_fill_cards,
        )
        from app.modules.safety.service.safety_commitment import (
            get_or_create_report,
        )

        report_date = str(item)
        report, _created = await get_or_create_report(session, report_date)
        sent, failed = await push_fill_cards(session, report_date, report)
        if sent > 0 or failed > 0:
            await cache_set(
                f"commitment_push_done:{report_date}",
                "1",
                ex=20 * 60 * 60,
            )
            logger.info(
                "安全承诺填报提醒推送完成: date=%s 成功=%s 失败=%s",
                report_date,
                sent,
                failed,
            )


# ── 独立同步循环（自建，不依赖平台调度引擎） ──
# 平台 SchedulerEngine 的循环协程缺少外层异常保护，曾被其它模块的异常
# 静默杀死（循环停止推进所有 generator）。镜像同步是安全模块的核心数据
# 链路，这里按本模块 scheduled_task_loop 的先例自建循环兜底：单轮失败只
# 记日志、循环永不退出；与共享引擎并存时由 Redis 锁防止同一页面重入。

_mirror_sync_stop = asyncio.Event()


async def mirror_sync_loop() -> None:
    """每 15 分钟同步到期的页面镜像；循环内任何异常都不终止循环。

    特殊危险作业页同步成功后自动转录进特殊作业台账并重算关键作业，
    台账与镜像保持同节奏更新，无需人工触发。
    """
    from app.modules.safety.service.fire_equipment import (
        FIRE_EQUIPMENT_PAGE_KEY as fire_equipment_page_key,  # noqa: N811
    )
    from app.modules.safety.service.fire_equipment import (
        retry_pending_inspection_writebacks,
        sync_fire_equipment_ledger,
    )
    from app.modules.safety.service.special_operation_transcription import (
        SOURCE_PAGE_KEY as special_danger_page_key,  # noqa: N811 —— 原名语义即常量
    )
    from app.modules.safety.service.special_operation_transcription import (
        sync_special_operation_ledger,
    )

    logger.info(
        "页面镜像独立同步循环已启动 (间隔=%ds)",
        int(MIRROR_SYNC_INTERVAL.total_seconds()),
    )
    generator = SafetyPageMirrorSyncGenerator()
    while not _mirror_sync_stop.is_set():
        delay = MIRROR_SYNC_INTERVAL.total_seconds()
        try:
            # 启动阶段放行数据库会话用于初始化；镜像同步须先按调度任务准入。
            async with (
                business_activity("scheduler"),
                page_table.async_session_factory() as session,
            ):
                due = await generator.find_due(session)
                synced: list[str] = []
                for page_key in due:
                    if _mirror_sync_stop.is_set():
                        break
                    try:
                        await generator.execute_one(session, page_key)
                        synced.append(page_key)
                    except Exception:
                        logger.exception(
                            "页面镜像独立同步单页失败: page=%s", page_key
                        )
                await session.commit()
                if special_danger_page_key in synced:
                    try:
                        await sync_special_operation_ledger(session)
                    except Exception:
                        logger.exception("特殊作业台账自动转录失败，等待下一轮")
                if fire_equipment_page_key in synced:
                    try:
                        await sync_fire_equipment_ledger(session)
                    except Exception:
                        logger.exception("消防器材台账投影失败，等待下一轮")
                    try:
                        await retry_pending_inspection_writebacks(session)
                    except Exception:
                        logger.exception("点检记录回写补写失败，等待下一轮")
        except MaintenanceActiveError:
            # 维护结束后尽快重试，到期判断仍由 find_due 执行。
            delay = _MIRROR_SYNC_RETRY_SECONDS
        except Exception:
            logger.exception("页面镜像独立同步本轮失败，等待下一轮")
        try:
            await asyncio.wait_for(_mirror_sync_stop.wait(), timeout=delay)
        except TimeoutError:
            pass  # 正常到点进入下一轮
