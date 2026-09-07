"""Quality scheduled generators."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.modules.quality.models.feishu_settings import QualityFeishuEntitySetting
from app.modules.quality.service.change_action_plan import (
    find_due_change_action_plan_reminders,
    send_change_action_plan_reminder,
)
from app.modules.quality.service.quality_feishu_supplier_mirror import (
    ENTITY_SUPPLIER_QUALIFICATION,
    pull_supplier_qualification_mirror,
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
