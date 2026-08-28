"""Quality scheduled generators."""

from __future__ import annotations

from typing import Any

from app.modules.quality.service.change_action_plan import (
    find_due_change_action_plan_reminders,
    send_change_action_plan_reminder,
)
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator


class ChangeActionPlanReminderGenerator(TaskGenerator):
    """Daily reminder generator for change action plans."""

    name = "quality.change_action_plan_reminders"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="09:00",
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await find_due_change_action_plan_reminders(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await send_change_action_plan_reminder(session, item)
