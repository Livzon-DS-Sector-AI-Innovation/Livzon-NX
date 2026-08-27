"""HR module scheduler — periodic task generators registered with SchedulerEngine."""

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.modules.hr.models import HrReminderConfig, OffboardingRecord
from app.platform.integrations.feishu import notification as feishu_notification
from app.platform.scheduler.registry import ScheduleConfig, ScheduleStrategy
from app.platform.scheduler.registry import TaskGenerator as SchedulerTaskGenerator

logger = logging.getLogger(__name__)


class ResumeFolderScanner(SchedulerTaskGenerator):
    """Every 30 seconds scan the resume watch folder for new PDF files."""

    name = "hr.resume_folder_scanner"
    schedule = ScheduleConfig(strategy=ScheduleStrategy.INTERVAL, interval_seconds=30)

    async def find_due(self, session: Any) -> list[None]:
        return [None]

    async def execute_one(self, session: Any, item: Any) -> None:
        from app.modules.hr.resume_watcher import scan_watched_folder

        result = await scan_watched_folder()
        if result["new_files"] > 0:
            logger.info(
                "resume scan complete", extra={"new_files": result["new_files"]}
            )


class MailFetchScanner(SchedulerTaskGenerator):
    """Every 10 minutes scan the configured IMAP mailbox for resume PDFs."""

    name = "hr.mail_fetch_scanner"
    schedule = ScheduleConfig(strategy=ScheduleStrategy.INTERVAL, interval_seconds=600)

    async def find_due(self, session: Any) -> list[None]:
        return [None]

    async def execute_one(self, session: Any, item: Any) -> None:
        from app.modules.hr.mail_fetcher import fetch_resumes_from_mail

        result = await fetch_resumes_from_mail()
        if result.get("fetched", 0) > 0:
            logger.info("mail fetch complete", extra=result)


class OffboardingReminderGenerator(SchedulerTaskGenerator):
    """离职提醒 - 离职记录创建后按配置的小时数提醒，支持自定义消息模板。

    标准 find_due/execute_one 接口（SchedulerEngine 每 tick 调 find_due，
    对每个到期项调 execute_one，最后统一 commit）。
    """

    name = "hr.offboarding_reminder"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=3600,
    )

    async def find_due(self, session: Any) -> list[Any]:
        """到达触发时间（trigger_hour）时返回待提醒的离职记录。"""
        from datetime import datetime, timedelta

        from app.core.redis import cache_get

        now = datetime.now()
        today = now.date()

        # 1. 读取所有 offboarding 配置
        all_configs = (
            (
                await session.execute(
                    select(HrReminderConfig).where(
                        HrReminderConfig.entity_code == "offboarding",
                        HrReminderConfig.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not all_configs:
            return []

        # 2. 判断是否到达触发时间（Redis 当天去重）
        should_trigger = False
        trigger_hour = 9
        notify_hours = 24
        message_template = ""
        for c in all_configs:
            if not c.is_enabled:
                continue
            trigger_hour = c.trigger_hour or 9
            notify_hours = c.notify_hours or 24
            message_template = c.message_template or ""

            trigger_key = f"hr:offboarding:triggered:{today.isoformat()}"
            already_triggered = await cache_get(trigger_key)
            if already_triggered:
                return []  # 今天已触发过

            if now.hour == trigger_hour:
                should_trigger = True
                break

        if not should_trigger:
            return []

        # 3. 查找需要提醒的离职记录（创建时间 + notify_hours <= 当前时间）
        threshold_time = now - timedelta(hours=notify_hours)
        records = (
            (
                await session.execute(
                    select(OffboardingRecord).where(
                        OffboardingRecord.created_at <= threshold_time,
                        OffboardingRecord.handover_status != "已完成",
                        OffboardingRecord.reminder_sent.is_(False),
                        OffboardingRecord.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )

        # 4. 跨天去重
        dedup_key = f"hr:offboarding:notified:{today.isoformat()}"
        already_raw = await cache_get(dedup_key)
        already_notified: set[str] = set()
        if already_raw:
            import json

            already_notified = set(json.loads(already_raw))
        new_records = [r for r in records if str(r.id) not in already_notified]
        if not new_records:
            logger.info("离职提醒：今日已通知过所有待提醒记录，跳过")
            return []

        return [
            {
                "type": "offboarding_reminder",
                "records": new_records,
                "recipient_open_ids": list(
                    dict.fromkeys(
                        oid
                        for c in all_configs
                        if c.is_enabled and c.recipient_open_ids
                        for oid in c.recipient_open_ids
                    )
                ),
                "message_template": message_template,
                "today": today.isoformat(),
            }
        ]

    async def execute_one(self, session: Any, item: Any) -> None:
        """发送离职提醒卡片并标记 reminder_sent（引擎统一 commit）。"""
        import json
        from datetime import datetime

        from app.core.redis import cache_get, cache_set

        records = item["records"]
        recipient_open_ids = item["recipient_open_ids"]
        message_template = item["message_template"]
        today = item["today"]
        now = datetime.now()

        if not recipient_open_ids:
            logger.warning("离职提醒：接收人未配置，跳过")
            return

        for record in records:
            # 使用自定义模板或默认模板
            if message_template:
                content = message_template.replace("{姓名}", record.name or "未知")
                content = content.replace("{工号}", record.employee_number or "未知")
                content = content.replace("{部门}", record.department or "未知")
                content = content.replace(
                    "{离职日期}",
                    str(record.offboarding_date) if record.offboarding_date else "未知",
                )
                content = content.replace(
                    "{离职类型}", record.offboarding_type or "未知"
                )
            else:
                content = f"""离职手续未办结提醒

员工：{record.name or "未知"}
工号：{record.employee_number or "未知"}
部门：{record.department or "未知"}
离职日期：{record.offboarding_date}
离职类型：{record.offboarding_type or "未知"}

该员工离职手续尚未办结，请及时跟进。"""

            title = f"离职提醒 - {record.name or '未知'}"

            sent_open_ids: set[str] = set()
            for open_id in recipient_open_ids:
                if open_id in sent_open_ids:
                    continue
                sent_open_ids.add(open_id)
                try:
                    await feishu_notification.send_user_card(
                        open_id=open_id,
                        title=title,
                        content=content,
                    )
                except Exception:
                    logger.exception(
                        "发送离职提醒失败",
                        extra={
                            "record_id": str(record.id),
                            "open_id": open_id,
                            "hr_module": "hr",
                        },
                    )

            # 标记已发送
            record.reminder_sent = True
            record.reminder_sent_at = now

        # 记录今日已通知（跨天去重）
        dedup_key = f"hr:offboarding:notified:{today}"
        already_raw = await cache_get(dedup_key)
        already_notified: set[str] = set()
        if already_raw:
            already_notified = set(json.loads(already_raw))
        already_notified.update(str(r.id) for r in records)
        await cache_set(dedup_key, json.dumps(list(already_notified)), ex=86400)

        logger.info(
            "离职提醒发送完成",
            extra={
                "total_records": len(records),
                "recipients": len(recipient_open_ids),
                "hr_module": "hr",
            },
        )


class ContractSignReminderGenerator(SchedulerTaskGenerator):
    """合同签署催签 - 审批通过后按 sign_reminder_days 间隔提醒办事员通知员工签署。

    实现标准 find_due/execute_one 接口（SchedulerEngine 每 tick 调 find_due，
    对每个到期项调 execute_one，最后统一 commit）。
    """

    name = "hr.contract_sign_reminder"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=3600,
    )

    async def find_due(self, session: Any) -> list[Any]:
        """返回待催签合同：审批通过 + 待签署 + 超过催签间隔。"""
        from datetime import datetime, timedelta

        from app.core.redis import cache_get
        from app.modules.hr.models import ContractManagement, HrReminderConfig

        configs = (
            (
                await session.execute(
                    select(HrReminderConfig).where(
                        HrReminderConfig.entity_code == "contract_renewal",
                        HrReminderConfig.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not configs:
            return []

        reminder_days = 7
        for c in configs:
            reminder_days = c.sign_reminder_days or 7

        now = datetime.now()
        threshold = now - timedelta(days=reminder_days)
        records = (
            (
                await session.execute(
                    select(ContractManagement).where(
                        ContractManagement.is_deleted.is_(False),
                        ContractManagement.approval_status == "approved",
                        ContractManagement.signed_status == "待签署",
                        ContractManagement.supervisor_approved_at.isnot(None),
                        ContractManagement.supervisor_approved_at <= threshold,
                    )
                )
            )
            .scalars()
            .all()
        )

        # 跨天去重：今日已通知过的记录不再催签
        today = now.date().isoformat()
        dedup_key = f"hr:contract:sign:notified:{today}"
        already_raw = await cache_get(dedup_key)
        already: set[str] = set()
        if already_raw:
            import json

            already = set(json.loads(already_raw))
        return [r for r in records if str(r.id) not in already]

    async def execute_one(self, session: Any, item: Any) -> None:
        """给办事员发送催签卡片并更新 sign_reminded_at（引擎统一 commit）。"""
        import json
        from datetime import datetime

        from app.core.redis import cache_get, cache_set
        from app.modules.hr.models import HrReminderConfig

        configs = (
            (
                await session.execute(
                    select(HrReminderConfig).where(
                        HrReminderConfig.entity_code == "contract_renewal",
                        HrReminderConfig.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )

        clerk_open_ids: list[str] = []
        hr_open_ids: list[str] = []
        for c in configs:
            if c.sign_clerk_open_ids:
                clerk_open_ids.extend(c.sign_clerk_open_ids)
            if c.recipient_open_ids:
                hr_open_ids.extend(c.recipient_open_ids)
        # 按员工部门解析办事员（部门配置优先，回退全局办事员，再回退 HR 接收人）
        from app.modules.hr.contract_api import _resolve_contract_clerk_ids

        clerk_open_ids = await _resolve_contract_clerk_ids(
            session,
            configs,
            item.dept_level1 or "",
            list(dict.fromkeys(clerk_open_ids)),
            list(dict.fromkeys(hr_open_ids)),
        )
        if not clerk_open_ids:
            logger.warning(
                "合同签署催签：办事员接收人未配置，跳过 %s", item.employee_number
            )
            return

        approved_date = (
            item.supervisor_approved_at.strftime("%Y-%m-%d")
            if item.supervisor_approved_at
            else "-"
        )
        content = (
            f"合同签署催签提醒：\n\n"
            f"- **{item.name}**（工号：{item.employee_number}）\n"
            f"- 部门：{item.dept_level1 or ''} / {item.dept_level2 or ''}\n"
            f"- 审批通过时间：{approved_date}\n\n"
            f"该员工合同审批已通过但尚未签署，请通知其尽快到人事签署合同。"
        )
        title = f"合同签署催签 - {item.name or '未知'}"

        for open_id in clerk_open_ids:
            try:
                await feishu_notification.send_user_card(
                    open_id=open_id,
                    title=title,
                    content=content,
                )
            except Exception:
                logger.exception(
                    "发送合同签署催签失败",
                    extra={
                        "record_id": str(item.id),
                        "open_id": open_id,
                        "hr_module": "hr",
                    },
                )

        # 更新上次催签时间
        item.sign_reminded_at = datetime.now()

        # 记录今日已催签（跨天去重）
        today = datetime.now().date().isoformat()
        dedup_key = f"hr:contract:sign:notified:{today}"
        already_raw = await cache_get(dedup_key)
        already: set[str] = set()
        if already_raw:
            already = set(json.loads(already_raw))
        already.add(str(item.id))
        await cache_set(dedup_key, json.dumps(list(already)), ex=86400)

        logger.info(
            "合同签署催签已发送: %s (%s)",
            item.name,
            item.employee_number,
        )


class ContractExpiryReminderGenerator(SchedulerTaskGenerator):
    """合同到期自动提醒 - 按配置频率（daily/monthly/quarterly）+ 时间点触发，
    给 HR 接收人推送到期人员汇总卡片（部门负责人由手动推送发送）。"""

    name = "hr.contract_expiry_reminder"
    schedule = ScheduleConfig(
        strategy=ScheduleStrategy.INTERVAL,
        interval_seconds=3600,
    )

    async def find_due(self, session: Any) -> list[Any]:
        """到达触发时间时返回汇总推送项（每小时检查一次）。"""
        from datetime import datetime

        from app.core.redis import cache_get
        from app.modules.hr.repository import EmployeeRepository

        now = datetime.now()
        today = now.date()

        # 1. 读取所有 contract_renewal 配置
        all_configs = (
            (
                await session.execute(
                    select(HrReminderConfig).where(
                        HrReminderConfig.entity_code == "contract_renewal",
                        HrReminderConfig.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not all_configs:
            return []

        # 2. 判断是否到达触发时间（Redis 当天去重）
        should_trigger = False
        trigger_freq = "monthly"
        trigger_day = 1
        trigger_hour = 9
        for c in all_configs:
            if not c.is_enabled:
                continue
            trigger_freq = c.trigger_frequency or "monthly"
            trigger_day = c.trigger_day or 1
            trigger_hour = c.trigger_hour or 9

            trigger_key = f"hr:contract:triggered:{today.isoformat()}"
            already_triggered = await cache_get(trigger_key)
            if already_triggered:
                return []  # 今天已触发过

            if trigger_freq == "daily":
                should_trigger = True
            elif trigger_freq == "monthly":
                should_trigger = today.day == trigger_day
            elif trigger_freq == "quarterly":
                should_trigger = (
                    today.month in (1, 4, 7, 10) and today.day == trigger_day
                )

            if should_trigger and now.hour != trigger_hour:
                should_trigger = False
            if should_trigger:
                break

        if not should_trigger:
            return []

        # 3. 合并配置
        reminder_days: list[int] = []
        recipient_open_ids: list[str] = []
        for c in all_configs:
            if not c.is_enabled:
                continue
            if c.reminder_days:
                reminder_days.extend(c.reminder_days)
            if c.recipient_open_ids:
                recipient_open_ids.extend(c.recipient_open_ids)
        reminder_days = list(dict.fromkeys(reminder_days)) or [30]
        recipient_open_ids = list(dict.fromkeys(recipient_open_ids))
        if not recipient_open_ids:
            logger.warning("合同到期提醒：HR接收人未配置，跳过")
            return []

        # 4. 按提醒天数收集到期人员
        all_expiring: list[dict[str, Any]] = []
        seen_employee_ids: set[str] = set()
        for days_ahead in reminder_days:
            target_date = today + timedelta(days=days_ahead)
            employees, _ = await EmployeeRepository(session).list_contract_expiring(
                start_date=target_date,
                end_date=target_date,
                page=1,
                page_size=500,
            )
            for emp in employees:
                eid = emp.get("employee_id", "")
                if eid and eid not in seen_employee_ids:
                    seen_employee_ids.add(eid)
                    all_expiring.append(emp)
        if not all_expiring:
            return []

        # 5. 跨天去重
        dedup_key = f"hr:contract:notified:{today.isoformat()}"
        already_raw = await cache_get(dedup_key)
        already_notified: set[str] = set()
        if already_raw:
            import json

            already_notified = set(json.loads(already_raw))
        new_expiring = [
            e for e in all_expiring if e.get("employee_id", "") not in already_notified
        ]
        if not new_expiring:
            logger.info("合同到期提醒：今日已通知过所有到期人员，跳过")
            return []

        return [
            {
                "type": "expiry_summary",
                "employees": new_expiring,
                "recipient_open_ids": recipient_open_ids,
                "today": today.isoformat(),
            }
        ]

    async def execute_one(self, session: Any, item: Any) -> None:
        """发送 HR 到期人员汇总卡片并记录今日已通知。"""
        import json

        from app.core.redis import cache_get, cache_set

        new_expiring = item["employees"]
        recipient_open_ids = item["recipient_open_ids"]
        today = item["today"]

        lines = []
        for emp in new_expiring:
            lines.append(
                f"- **{emp.get('name', '')}**（{emp.get('department', '')}），"
                f"第{emp.get('contract_sequence', '')}次合同于 "
                f"**{emp.get('contract_end_date', '')}** 到期"
            )
        summary = "\n".join(lines[:20])
        if len(lines) > 20:
            summary += f"\n... 共 {len(lines)} 人"

        title = f"合同到期提醒（{today}）"
        content = f"以下人员合同即将到期，请及时处理续签：\n\n{summary}"

        sent_open_ids: set[str] = set()
        for open_id in recipient_open_ids:
            if open_id in sent_open_ids:
                continue
            sent_open_ids.add(open_id)
            try:
                await feishu_notification.send_user_card(
                    open_id=open_id,
                    title=title,
                    content=content,
                )
            except Exception:
                logger.exception(
                    "发送合同到期提醒失败",
                    extra={"open_id": open_id, "hr_module": "hr"},
                )

        # 记录今日已通知（跨天去重）
        dedup_key = f"hr:contract:notified:{today}"
        already_raw = await cache_get(dedup_key)
        already_notified: set[str] = set()
        if already_raw:
            already_notified = set(json.loads(already_raw))
        already_notified.update(e.get("employee_id", "") for e in new_expiring)
        await cache_set(dedup_key, json.dumps(list(already_notified)), ex=86400)

        logger.info(
            "合同到期提醒发送完成",
            extra={
                "total_expiring": len(new_expiring),
                "recipients": len(sent_open_ids),
                "hr_module": "hr",
            },
        )
