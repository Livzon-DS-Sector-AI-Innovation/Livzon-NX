"""HR通用提醒配置 + 审批流程配置 Service"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.hr.models import (
    HrApprovalConfig,
    HrReminderConfig,
    HrReminderDeptRecipient,
)

logger = logging.getLogger(__name__)


class ContractSettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_reminder_config(self, data: dict[str, Any]) -> HrReminderConfig:
        config = HrReminderConfig(**data)
        self.session.add(config)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def ensure_default_offboarding_config(self) -> HrReminderConfig:
        """确保存在离职管理提醒默认配置，不存在则自动创建"""
        result = await self.session.execute(
            select(HrReminderConfig).where(
                HrReminderConfig.entity_code == "offboarding",
                HrReminderConfig.is_deleted.is_(False),
            )
        )
        configs = result.scalars().all()
        if configs:
            # 如果有多个，保留第一个，删除其他的
            if len(configs) > 1:
                for c in configs[1:]:
                    c.is_deleted = True
                await self.session.flush()
            return configs[0]

        return await self.create_reminder_config(
            {
                "entity_code": "offboarding",
                "entity_label": "离职管理",
                "module_group": "离职管理",
                "reminder_type": "offboarding_due",
                "reminder_label": "离职提醒",
                "reminder_days": [30, 15, 7],
                "notify_channels": ["feishu"],
                "recipient_open_ids": [],
                "dept_notify_enabled": False,
                "message_template": "",
                "auto_action": False,
                "auto_action_target": None,
                "trigger_frequency": "monthly",
                "trigger_day": 1,
                "trigger_hour": 9,
                "notify_hours": 24,
                "is_enabled": False,
                "sort_order": 0,
            }
        )

    async def list_reminder_configs(self) -> list[HrReminderConfig]:
        result = await self.session.execute(
            select(HrReminderConfig)
            .where(HrReminderConfig.is_deleted.is_(False))
            .order_by(HrReminderConfig.sort_order.asc())
        )
        return list(result.scalars().all())

    async def get_reminder_config(self, config_id: UUID) -> HrReminderConfig:
        result = await self.session.execute(
            select(HrReminderConfig).where(
                HrReminderConfig.id == config_id,
                HrReminderConfig.is_deleted.is_(False),
            )
        )
        config = result.scalar_one_or_none()
        if not config:
            raise NotFoundException("提醒配置", str(config_id))
        return config

    async def update_reminder_config(
        self, config_id: UUID, data: dict[str, Any]
    ) -> HrReminderConfig:
        config = await self.get_reminder_config(config_id)
        for key, value in data.items():
            setattr(config, key, value)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def list_dept_recipients(
        self, reminder_config_id: str
    ) -> list[HrReminderDeptRecipient]:
        result = await self.session.execute(
            select(HrReminderDeptRecipient)
            .where(
                HrReminderDeptRecipient.reminder_config_id == reminder_config_id,
                HrReminderDeptRecipient.is_deleted.is_(False),
            )
            .order_by(HrReminderDeptRecipient.department.asc())
        )
        return list(result.scalars().all())

    async def upsert_dept_recipient(
        self, data: dict[str, Any]
    ) -> HrReminderDeptRecipient:
        reminder_config_id = data["reminder_config_id"]
        department = data["department"]

        result = await self.session.execute(
            select(HrReminderDeptRecipient).where(
                HrReminderDeptRecipient.reminder_config_id == reminder_config_id,
                HrReminderDeptRecipient.department == department,
                HrReminderDeptRecipient.is_deleted.is_(False),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
            await self.session.flush()
            re_fetch = await self.session.execute(
                select(HrReminderDeptRecipient).where(
                    HrReminderDeptRecipient.id == existing.id
                )
            )
            return re_fetch.scalar_one()

        new_recipient = HrReminderDeptRecipient(**data)
        self.session.add(new_recipient)
        await self.session.flush()
        return new_recipient

    async def delete_dept_recipient(self, dept_recipient_id: UUID) -> None:
        result = await self.session.execute(
            select(HrReminderDeptRecipient).where(
                HrReminderDeptRecipient.id == dept_recipient_id,
                HrReminderDeptRecipient.is_deleted.is_(False),
            )
        )
        recipient = result.scalar_one_or_none()
        if not recipient:
            raise NotFoundException("部门接收人配置", str(dept_recipient_id))
        recipient.is_deleted = True
        await self.session.flush()

    async def list_approval_configs(self) -> list[HrApprovalConfig]:
        result = await self.session.execute(
            select(HrApprovalConfig)
            .where(HrApprovalConfig.is_deleted.is_(False))
            .order_by(HrApprovalConfig.sort_order.asc())
        )
        return list(result.scalars().all())

    async def update_approval_config(
        self, config_id: UUID, data: dict[str, Any]
    ) -> HrApprovalConfig:
        result = await self.session.execute(
            select(HrApprovalConfig).where(
                HrApprovalConfig.id == config_id,
                HrApprovalConfig.is_deleted.is_(False),
            )
        )
        config = result.scalar_one_or_none()
        if not config:
            raise NotFoundException("审批配置", str(config_id))
        for key, value in data.items():
            setattr(config, key, value)
        await self.session.flush()
        await self.session.refresh(config)
        return config
