"""Notification service for regulatory tracker daily updates."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.models import (
    RegulatoryDocument,
    RegulatoryTrackerNotificationRecord,
)
from app.modules.regulatory_tracker.schemas.notification import (
    RegulatoryTrackerNotificationRecipientOption,
    RegulatoryTrackerNotificationSettingRead,
    RegulatoryTrackerNotificationSettingUpdate,
)
from app.platform.integrations.feishu.notification import send_user_card


def _normalize_department(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _normalize_department_text(value: str | None) -> str:
    if not value:
        return ""
    return "".join((value or "").split()).upper()


def _is_qa_department(value: str | None) -> bool:
    normalized = _normalize_department_text(value)
    return "QA" in normalized or "质量保证" in normalized


def _truncate_summary(value: str | None, *, max_length: int = 100) -> str:
    text = " ".join((value or "").split()).strip()
    if not text:
        return "暂无内容总结"
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}…"


def _resolve_display_summary(document: RegulatoryDocument) -> str:
    ai_summary = (document.ai_summary or "").strip()
    if ai_summary:
        return _truncate_summary(ai_summary)
    return _truncate_summary(document.summary_text)


def _build_notification_content(documents: list[RegulatoryDocument]) -> str:
    lines = [
        "以下为今日法规跟踪自动抓取到的更新内容，请及时查看：",
        "",
    ]

    preview_documents = documents[:10]
    for index, document in enumerate(preview_documents, start=1):
        lines.extend(
            [
                f"{index}. **{document.title}**",
                f"   - 来源网站：{document.source_site_name or '—'}",
                (
                    f"   - 发布日期："
                    f"{document.publish_date.isoformat() if document.publish_date else '—'}"  # noqa: E501
                ),
                f"   - 内容总结："
                f"{_resolve_display_summary(document)}",
                f"   - 链接：{document.source_url or document.original_url or '—'}",
            ]
        )

    if len(documents) > len(preview_documents):
        lines.extend(
            [
                "",
                (
                    f"其余还有 **{len(documents) - len(preview_documents)}** 条，"
                    "请到系统 `注册管理 -> 法规跟踪` 查看。"
                ),

            ]
        )

    return "\n".join(lines)


class RegulatoryTrackerNotificationService:
    """法规跟踪推送配置与发送服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _list_reminder_recipient_options(
        self,
    ) -> list[RegulatoryTrackerNotificationRecipientOption]:
        from app.modules.quality.service.department_contacts import (
            get_department_contact_list_from_feishu,
        )

        try:
            result = await get_department_contact_list_from_feishu(
                self.session,
                page=1,
                page_size=1000,
            )
        except Exception:
            return []

        options_by_open_id: dict[str, RegulatoryTrackerNotificationRecipientOption] = {}
        for item in result.get("items", []):
            open_id = str(item.get("open_id") or "").strip()
            if not open_id:
                continue

            name = str(item.get("name") or "").strip() or "未命名联系人"
            department = _normalize_department(item.get("department"))
            if not _is_qa_department(department):
                continue
            enterprise_email = str(item.get("enterprise_email") or "").strip() or None
            options_by_open_id[open_id] = RegulatoryTrackerNotificationRecipientOption(
                open_id=open_id,
                name=name,
                department=department or None,
                enterprise_email=enterprise_email,
            )

        return sorted(
            options_by_open_id.values(),
            key=lambda item: ((item.department or ""), item.name, item.open_id),
        )

    async def _get_recipient_by_open_id(
        self,
        open_id: str,
    ) -> RegulatoryTrackerNotificationRecipientOption | None:
        for option in await self._list_reminder_recipient_options():
            if option.open_id == open_id:
                return option
        return None

    async def _count_pending_documents(
        self,
        *,
        recipient_open_id: str | None,
        recent_days: int,
    ) -> int:
        normalized_open_id = (recipient_open_id or "").strip()
        if not normalized_open_id:
            return 0

        threshold = date.today() - timedelta(days=max(recent_days - 1, 0))
        result = await self.session.execute(
            select(RegulatoryDocument).where(
                and_(
                    RegulatoryDocument.is_deleted == False,  # noqa: E712
                    RegulatoryDocument.filter_status == "accepted",
                    RegulatoryDocument.capture_date >= threshold,
                )
            )
        )
        documents = list(result.scalars().all())
        pending = 0
        for document in documents:
            if await repo.notification_record_exists(
                self.session,
                document_id=document.id,
                recipient_open_id=normalized_open_id,
                content_hash=document.content_hash,
            ):
                continue
            pending += 1
        return pending

    async def get_notification_settings(
        self,
    ) -> RegulatoryTrackerNotificationSettingRead:
        setting = await repo.get_notification_setting(self.session)
        if setting is None:
            return RegulatoryTrackerNotificationSettingRead(
                is_enabled=False,
                recent_days=7,
                recipient_open_id=None,
                recipient_name=None,
                recipient_department=None,
                schedule_time="10:00",
                pending_count=0,
            )

        pending_count = await self._count_pending_documents(
            recipient_open_id=setting.recipient_open_id,
            recent_days=setting.recent_days,
        )
        return RegulatoryTrackerNotificationSettingRead(
            is_enabled=setting.is_enabled,
            recent_days=setting.recent_days,
            recipient_open_id=setting.recipient_open_id,
            recipient_name=setting.recipient_name,
            recipient_department=setting.recipient_department,
            schedule_time=setting.schedule_time,
            pending_count=pending_count,
        )

    async def list_notification_recipient_options(
        self,
    ) -> list[RegulatoryTrackerNotificationRecipientOption]:
        return await self._list_reminder_recipient_options()

    async def update_notification_settings(
        self,
        data: RegulatoryTrackerNotificationSettingUpdate,
    ) -> RegulatoryTrackerNotificationSettingRead:
        recipient_open_id = (data.recipient_open_id or "").strip() or None
        recipient_name: str | None = None
        recipient_department: str | None = None

        if data.is_enabled:
            if not recipient_open_id:
                raise AppException(message="启用自动推送时必须选择接收人")
            recipient = await self._get_recipient_by_open_id(recipient_open_id)
            if recipient is None:
                raise AppException(message="所选接收人不在 QA 联系人范围内")
            recipient_name = recipient.name
            recipient_department = recipient.department
        else:
            recipient_open_id = None

        setting = await repo.get_notification_setting(self.session)
        await repo.save_notification_setting(
            self.session,
            setting=setting,
            is_enabled=data.is_enabled,
            recent_days=data.recent_days,
            recipient_open_id=recipient_open_id,
            recipient_name=recipient_name,
            recipient_department=recipient_department,
            schedule_time="10:00",
        )
        await self.session.commit()
        return await self.get_notification_settings()

    async def send_update_notifications(
        self,
        *,
        document_ids: list[str],
        trigger_type: str = "daily_auto_sync",
    ) -> dict[str, Any]:
        setting = await repo.get_notification_setting(self.session)
        if (
            setting is None
            or not setting.is_enabled
            or not (setting.recipient_open_id or "").strip()
        ):
            return {"sent": 0, "skipped": len(document_ids), "failed": 0}

        recipient_open_id = str(setting.recipient_open_id).strip()
        recipient = await self._get_recipient_by_open_id(recipient_open_id)
        if recipient is None:
            return {"sent": 0, "skipped": len(document_ids), "failed": 0}

        resolved_document_ids = [
            document_id for document_id in document_ids if document_id
        ]
        if not resolved_document_ids:
            return {"sent": 0, "skipped": 0, "failed": 0}

        documents = await repo.list_documents_by_ids(
            self.session,
            [uuid.UUID(document_id) for document_id in resolved_document_ids],
        )

        documents_to_send: list[RegulatoryDocument] = []
        for document in documents:
            if await repo.notification_record_exists(
                self.session,
                document_id=document.id,
                recipient_open_id=recipient_open_id,
                content_hash=document.content_hash,
            ):
                continue
            documents_to_send.append(document)

        if not documents_to_send:
            return {"sent": 0, "skipped": len(documents), "failed": 0}

        recipient_receive_id = recipient.enterprise_email or recipient.open_id
        recipient_receive_id_type = "email" if recipient.enterprise_email else "open_id"
        success = await send_user_card(
            open_id=recipient_receive_id,
            title="法规跟踪更新提醒",
            content=_build_notification_content(documents_to_send),
            receive_id_type=recipient_receive_id_type,
        )
        if not success:
            return {"sent": 0, "skipped": 0, "failed": len(documents_to_send)}

        await repo.create_notification_records(
            self.session,
            [
                RegulatoryTrackerNotificationRecord(
                    document_id=document.id,
                    recipient_open_id=recipient_open_id,
                    recipient_name=setting.recipient_name,
                    content_hash=document.content_hash or "",
                    document_title=document.title,
                    source_site_name=document.source_site_name,
                    publish_date=document.publish_date,
                    source_url=document.source_url or document.original_url,
                    summary_text=_resolve_display_summary(document),
                    trigger_type=trigger_type,
                )
                for document in documents_to_send
            ],
        )
        await self.session.commit()
        return {"sent": len(documents_to_send), "skipped": 0, "failed": 0}
