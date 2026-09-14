"""Notification service for regulatory tracker daily updates."""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.public_api import get_module_feishu_app_credentials
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
from app.platform.identity.public_api import resolve_feishu_notification_recipient
from app.platform.integrations.feishu.notification import send_user_card

logger = logging.getLogger(__name__)


def _normalize_department(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


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


_DEFAULT_NOTIFICATION_HEADER = "以下为今日法规跟踪自动抓取到的更新内容，请及时查看："
_PREVIEW_LIMIT = 10


def _render_template(
    template: str | None,
    default: str,
    replacements: dict[str, str],
) -> str:
    """渲染消息模板：空白回退默认文案，支持 {key} 占位符，未知占位符原样保留。"""
    text = (template or "").strip() or default
    for key, value in replacements.items():
        text = text.replace("{" + key + "}", value)
    return text


def _build_notification_content(
    documents: list[RegulatoryDocument],
    *,
    header_template: str | None = None,
    footer_template: str | None = None,
) -> str:
    count = len(documents)
    template_vars = {
        "date": date.today().isoformat(),
        "count": str(count),
        "overflow_count": str(max(count - _PREVIEW_LIMIT, 0)),
    }
    header = _render_template(
        header_template, _DEFAULT_NOTIFICATION_HEADER, template_vars
    )
    lines = [header, ""]

    preview_documents = documents[:_PREVIEW_LIMIT]
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

    footer = (footer_template or "").strip()
    if footer:
        lines.extend(["", _render_template(footer, "", template_vars)])
    elif count > len(preview_documents):
        lines.extend(
            [
                "",
                (
                    f"其余还有 **{count - len(preview_documents)}** 条，"
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
        from app.modules.quality.public_api import get_qa_reminder_recipients

        try:
            recipients = await get_qa_reminder_recipients(self.session)
        except Exception:
            return []

        options = [
            RegulatoryTrackerNotificationRecipientOption(
                open_id=str(item.get("open_id") or ""),
                name=str(item.get("name") or "未命名联系人"),
                department=_normalize_department(item.get("department")) or None,
                enterprise_email=str(item.get("enterprise_email") or "") or None,
            )
            for item in recipients
            if str(item.get("open_id") or "").strip()
        ]
        return sorted(
            options,
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
                header_template=None,
                footer_template=None,
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
            header_template=setting.header_template,
            footer_template=setting.footer_template,
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
            header_template=(data.header_template or "").strip() or None,
            footer_template=(data.footer_template or "").strip() or None,
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

        # 发送借用质量模块飞书应用；接收人 open_id 属登录应用命名空间，
        # 须经平台标识解析换出跨应用可用的 user_id/邮箱后再发送。
        app_id, app_secret = await get_module_feishu_app_credentials(self.session)
        if not app_id or not app_secret:
            logger.warning("质量模块飞书应用未配置或已停用，法规跟踪推送失败")
            return {"sent": 0, "skipped": 0, "failed": len(documents_to_send)}

        resolved = await resolve_feishu_notification_recipient(
            self.session, recipient_open_id, "open_id"
        )
        if resolved is None:
            logger.warning(
                "法规跟踪推送接收人缺少可用飞书标识（open_id=%s…）",
                recipient_open_id[:16],
            )
            return {"sent": 0, "skipped": 0, "failed": len(documents_to_send)}

        receive_id, receive_id_type = resolved
        # 无平台用户账号时 open_id 无法跨应用发送：回退人员目录企业邮箱
        if receive_id_type == "open_id":
            option = await self._get_recipient_by_open_id(recipient_open_id)
            if option and option.enterprise_email:
                receive_id, receive_id_type = option.enterprise_email, "email"
            else:
                logger.warning(
                    "法规跟踪推送接收人缺少跨应用可用的飞书标识（open_id=%s…）",
                    recipient_open_id[:16],
                )
                return {"sent": 0, "skipped": 0, "failed": len(documents_to_send)}

        success = await send_user_card(
            open_id=receive_id,
            title="法规跟踪更新提醒",
            content=_build_notification_content(
                documents_to_send,
                header_template=setting.header_template,
                footer_template=setting.footer_template,
            ),
            receive_id_type=receive_id_type,
            app_id=app_id,
            app_secret=app_secret,
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

    async def _list_sample_documents(self) -> list[RegulatoryDocument]:
        """测试消息样例：最近 3 条 accepted 法规，无数据时用合成样例。"""
        result = await self.session.execute(
            select(RegulatoryDocument)
            .where(
                and_(
                    RegulatoryDocument.is_deleted == False,  # noqa: E712
                    RegulatoryDocument.filter_status == "accepted",
                )
            )
            .order_by(
                RegulatoryDocument.capture_date.desc(),
                RegulatoryDocument.created_at.desc(),
            )
            .limit(3)
        )
        documents = list(result.scalars().all())
        if documents:
            return documents

        today = date.today()
        return [
            RegulatoryDocument(
                title=f"【测试样例】原料药相关法规更新示例 {index}",
                source_site_name="样例站点",
                publish_date=today,
                summary_text="这是一条测试发送的样例内容，用于验证推送模板与送达链路。",
                source_url="https://example.com/sample",
            )
            for index in range(1, 4)
        ]

    async def send_test_notification(
        self,
        *,
        recipient_open_id: str,
        header_template: str | None = None,
        footer_template: str | None = None,
    ) -> dict[str, Any]:
        """向指定接收人发送测试推送消息；不写推送记录，不影响真实推送幂等。"""
        normalized_open_id = (recipient_open_id or "").strip()
        if not normalized_open_id:
            raise AppException(message="测试发送前请先选择接收人")

        recipient = await self._get_recipient_by_open_id(normalized_open_id)
        if recipient is None:
            # 与真实发送一致：已保存的接收人即使之后调离 QA 名单也允许测试验证
            setting = await repo.get_notification_setting(self.session)
            if setting and (
                str(setting.recipient_open_id or "").strip() == normalized_open_id
            ):
                recipient = SimpleNamespace(
                    open_id=normalized_open_id,
                    name=str(setting.recipient_name or "已配置接收人"),
                    department=str(setting.recipient_department or "") or None,
                    enterprise_email=None,
                )
        if recipient is None:
            raise AppException(message="所选接收人不在 QA 联系人范围内")

        app_id, app_secret = await get_module_feishu_app_credentials(self.session)
        if not app_id or not app_secret:
            return {
                "sent": False,
                "recipient_name": recipient.name,
                "detail": "质量模块飞书应用未配置或已停用，无法发送测试消息",
            }

        resolved = await resolve_feishu_notification_recipient(
            self.session, normalized_open_id, "open_id"
        )
        if resolved is None:
            return {
                "sent": False,
                "recipient_name": recipient.name,
                "detail": "接收人缺少可用飞书标识（平台账号未绑定飞书且无企业邮箱）",
            }

        receive_id, receive_id_type = resolved
        # 无平台用户账号时 open_id 无法跨应用发送：回退人员目录企业邮箱
        if receive_id_type == "open_id":
            option = await self._get_recipient_by_open_id(normalized_open_id)
            enterprise_email = (
                option.enterprise_email
                if option
                else getattr(recipient, "enterprise_email", None)
            )
            if enterprise_email:
                receive_id, receive_id_type = enterprise_email, "email"
            else:
                return {
                    "sent": False,
                    "recipient_name": recipient.name,
                    "detail": "接收人缺少跨应用可用的飞书标识（无企业邮箱）",
                }

        success = await send_user_card(
            open_id=receive_id,
            title="法规跟踪更新提醒（测试）",
            content=_build_notification_content(
                await self._list_sample_documents(),
                header_template=header_template,
                footer_template=footer_template,
            ),
            receive_id_type=receive_id_type,
            app_id=app_id,
            app_secret=app_secret,
        )
        if not success:
            return {
                "sent": False,
                "recipient_name": recipient.name,
                "detail": "飞书消息发送失败，请检查质量模块飞书应用配置",
            }
        return {
            "sent": True,
            "recipient_name": recipient.name,
            "detail": f"测试消息已发送至 {recipient.name}",
        }
