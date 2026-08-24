"""Registration scheduled generators."""

from __future__ import annotations

from typing import Any

from app.modules.registration.service.certificate import (
    find_due_certificate_reminder_batches,
    send_certificate_reminder_batch,
)
from app.platform.scheduler import ScheduleConfig, ScheduleStrategy, TaskGenerator


class CertificateReminderGenerator(TaskGenerator):
    """Daily reminder generator for certificate expirations."""

    name = "registration.certificate_reminders"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.FIXED_TIME,
        time_of_day="09:00",
        timezone="Asia/Shanghai",
    )

    async def find_due(self, session: Any) -> Any:
        return await find_due_certificate_reminder_batches(session)

    async def execute_one(self, session: Any, item: Any) -> None:
        await send_certificate_reminder_batch(session, item)
