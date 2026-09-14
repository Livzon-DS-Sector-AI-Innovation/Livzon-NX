"""Quality scheduled generators."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.modules.quality.models.feishu_settings import QualityFeishuEntitySetting
from app.modules.quality.service.change_action_plan import (
    find_due_change_action_plan_reminders,
    send_change_action_plan_reminder,
)
from app.modules.quality.service.inspection_finished_mirror import (
    FINISHED_MIRROR_ENTITIES,
    sync_finished_page,
)
from app.modules.quality.service.inspection_items_mirror import (
    ITEMS_MIRROR_PAGES,
    sync_items_page,
)
from app.modules.quality.service.inspection_material_mirror import (
    MATERIAL_MIRROR_ENTITIES,
    sync_material_page,
)
from app.modules.quality.service.items_dashboard import push_low_stock_alert
from app.modules.quality.service.quality_feishu_supplier_mirror import (
    ENTITY_SUPPLIER_QUALIFICATION,
    pull_supplier_qualification_mirror,
)
from app.modules.quality.service.quality_notification_settings import (
    load_items_stock_alert_config,
)
from app.modules.quality.service.trend_alert_escalation import (
    find_due_trend_alert_escalations,
    process_trend_alert_escalation,
)
from app.modules.quality.service.trend_monthly_analysis import (
    find_due_trend_monthly_analysis,
    run_trend_monthly_analysis,
)
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator


class ChangeActionPlanReminderGenerator(TaskGenerator):
    """Hourly scanner for change action plan due reminders.

    提前天数/重复间隔/每天发送时间由通知设置（quality_notification_settings）
    驱动；find_due 内部按设置的 send_time（Asia/Shanghai）判断当天是否已到发送时间。
    """

    name = "quality.change_action_plan_reminders"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=3600,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await find_due_change_action_plan_reminders(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await send_change_action_plan_reminder(session, item)


async def _supplier_pull_enabled(session: Any) -> bool:
    """实体启用且回拉开关打开时才调度供应商资质镜像回拉。"""
    model = (
        await session.execute(
            select(QualityFeishuEntitySetting).where(
                QualityFeishuEntitySetting.entity_code
                == ENTITY_SUPPLIER_QUALIFICATION,
                QualityFeishuEntitySetting.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    return bool(
        model is not None and model.is_enabled and model.enable_pull_from_feishu
    )


class SupplierQualificationMirrorSyncGenerator(TaskGenerator):
    """供应商资质镜像高频增量回拉（默认 60s）。

    失败（凭证/权限/配置）由镜像服务转成 AppException，引擎捕获记录，
    "最近状态"同步标红，供设置页诊断。
    """

    name = "quality.supplier_qualification_mirror_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=60,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        if not await _supplier_pull_enabled(session):
            return []
        return [ENTITY_SUPPLIER_QUALIFICATION]

    async def execute_one(self, session: Any, item: Any) -> None:
        await pull_supplier_qualification_mirror(session, full=False)


class SupplierQualificationMirrorFullSyncGenerator(TaskGenerator):
    """供应商资质镜像每日全量兜底（凌晨 02:30）。

    增量轮按 last_modified_time 单页取数，超过 500 条的历史修改与远端
    删除依赖本全量轮对账（对齐仓储"增量 + 每日全量兜底"模式）。
    """

    name = "quality.supplier_qualification_mirror_full_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="02:30",
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        if not await _supplier_pull_enabled(session):
            return []
        return [ENTITY_SUPPLIER_QUALIFICATION]

    async def execute_one(self, session: Any, item: Any) -> None:
        await pull_supplier_qualification_mirror(session, full=True)


class TrendAlertEscalationGenerator(TaskGenerator):
    """成品/纯化水异常升级推送扫描（60s）。

    首波告警（超 均值±3σ/OOT 限度线）成功通知后入队；到点复检该批次，
    仍异常则升级推送各部门负责人（提炼负责人 + 该产品QA）。
    """

    name = "quality.trend_alert_escalations"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=60,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await find_due_trend_alert_escalations(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await process_trend_alert_escalation(session, item)


async def _mirror_entities_pull_enabled(
    session: Any, entities: tuple[str, ...]
) -> list[str]:
    """实体启用且回拉开关打开时才调度镜像同步（物品/物料/成品共用）。"""
    models = (
        await session.execute(
            select(QualityFeishuEntitySetting).where(
                QualityFeishuEntitySetting.entity_code.in_(entities),
                QualityFeishuEntitySetting.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    enabled = {
        model.entity_code
        for model in models
        if model.is_enabled and model.enable_pull_from_feishu
    }
    return [entity_code for entity_code in entities if entity_code in enabled]


async def _items_pages_pull_enabled(session: Any) -> list[str]:
    """物品三实体启用且回拉开关打开时才调度镜像同步。"""
    return await _mirror_entities_pull_enabled(session, ITEMS_MIRROR_PAGES)


class InspectionItemsMirrorSyncGenerator(TaskGenerator):
    """物品管理镜像高频增量同步（600s）。

    对齐供应商资质镜像模式：增量轮全量翻页 + last_modified_time 水位只写变更行，
    失败由镜像服务转 AppException，引擎记录并标红设置页"最近状态"。
    """

    name = "quality.inspection_items_mirror_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=600,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await _items_pages_pull_enabled(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await sync_items_page(session, item, incremental=True)


class InspectionItemsMirrorFullSyncGenerator(TaskGenerator):
    """物品管理镜像每日全量兜底（凌晨 02:40），做删除对账与列结构刷新。"""

    name = "quality.inspection_items_mirror_full_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="02:40",
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await _items_pages_pull_enabled(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await sync_items_page(session, item, incremental=False)


async def _material_pull_enabled(session: Any) -> list[str]:
    """固体/液体物料实体启用且回拉开关打开时才调度镜像同步。"""
    return await _mirror_entities_pull_enabled(session, MATERIAL_MIRROR_ENTITIES)


class InspectionMaterialMirrorSyncGenerator(TaskGenerator):
    """固体/液体物料镜像增量同步（每 10 分钟）。

    对齐物料镜像模式：按批号降序逐页拉取 + 批号/内容比对只写变更行，
    失败由镜像服务转 AppException，引擎记录并标红设置页"最近状态"。
    """

    name = "quality.inspection_material_mirror_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=600,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await _material_pull_enabled(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await sync_material_page(session, item, incremental=True)


class InspectionMaterialMirrorFullSyncGenerator(TaskGenerator):
    """固体/液体物料镜像每日全量兜底（凌晨 02:20 错峰），做删除对账与列结构刷新。"""

    name = "quality.inspection_material_mirror_full_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="02:20",
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await _material_pull_enabled(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await sync_material_page(session, item, incremental=False)


async def _finished_pull_enabled(session: Any) -> list[str]:
    """成品检验实体启用且回拉开关打开时才调度镜像同步。"""
    return await _mirror_entities_pull_enabled(session, FINISHED_MIRROR_ENTITIES)


class InspectionFinishedMirrorSyncGenerator(TaskGenerator):
    """成品检验镜像批号驱动增量同步（每 10 分钟）。

    对齐物料镜像模式：按批号降序逐页拉取，只写新批号/内容有变化的行，
    失败由镜像服务转 AppException，引擎记录并标红设置页"最近状态"。
    """

    name = "quality.inspection_finished_mirror_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=600,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await _finished_pull_enabled(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await sync_finished_page(session, item, incremental=True)


class InspectionFinishedMirrorFullSyncGenerator(TaskGenerator):
    """成品检验镜像每日全量兜底（凌晨 02:50），做删除对账与列结构刷新。"""

    name = "quality.inspection_finished_mirror_full_sync"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="02:50",
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await _finished_pull_enabled(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await sync_finished_page(session, item, incremental=False)


class ItemsStockAlertPushGenerator(TaskGenerator):
    """物品库存不足预警每日定时推送（每小时扫描一次）。

    到配置的发送时间（Asia/Shanghai 当日小时）触发；push_low_stock_alert 按
    (物料, 接收人, 当日 period) 幂等，同一小时窗口内重复扫描不会重复推送。
    """

    name = "quality.items_stock_alert_push"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=3600,
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        config = await load_items_stock_alert_config(session)
        if not config.is_enabled:
            return []
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        send_hour = int((config.send_time or "09:00").split(":")[0])
        if now.hour != send_hour:
            return []
        return ["items_stock_alert"]

    async def execute_one(self, session: Any, item: Any) -> None:
        period = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
        await push_low_stock_alert(session, period_key=period)


class TrendAlertMonthlyAnalysisGenerator(TaskGenerator):
    """趋势 AI 月度定时分析（每日 09:00 检查，每月 ≥monthly_day 触发一次）。

    触发后对所有已启用产品线的全部指标全量跑趋势 AI 并推送（必发，不受
    手动重分析开关影响）；同月通过 quality_trend_monthly_runs 去重，
    不依赖有人打开页面。
    """

    name = "quality.trend_monthly_analysis"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="09:00",
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await find_due_trend_monthly_analysis(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await run_trend_monthly_analysis(session, item)
