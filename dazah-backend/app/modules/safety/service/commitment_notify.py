"""安全承诺飞书推送：每日填报卡（个人）与承诺公告卡（群）。

飞书未配置或推送失败只记日志，不影响日报业务事务；
推送目标与开关来自 safety.feishu_app_settings（commitment_* 字段）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.feishu.notification import send_group_card
from app.modules.safety.models import SafetyFeishuAppSettings
from app.modules.safety.service.commitment_card_forms import (
    build_announcement_markdown,
    build_reminder_card,
)
from app.modules.safety.service.work_permit_notify import send_raw_card

CN_TZ = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)

# 与前端页面路由保持一致（74号文：每天上午10时前更新公告）
COMMITMENT_PAGE_PATH = "/safety/safety-commitment"


async def get_commitment_settings(
    db: AsyncSession,
) -> SafetyFeishuAppSettings | None:
    result = await db.execute(
        select(SafetyFeishuAppSettings)
        .where(SafetyFeishuAppSettings.is_deleted.is_(False))
        .order_by(SafetyFeishuAppSettings.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _status_line(report: Any) -> str:
    if report is None:
        return "今日日报尚未创建，点击「开始填报」完成当日安全承诺填报。"
    if getattr(report, "status", "draft") == "published":
        return (
            f"今日承诺公告已发布（承诺人：{report.publisher_name or '—'}），"
            "仍可点击「开始填报」补充或修改企业状态。"
        )
    return "今日日报待填报，请点击「开始填报」完成当日安全承诺（含承诺确认）。"


def public_base_url() -> str:
    """网页端链接的对外基础地址（与作业票免登链接同一口径）。"""
    from app.core.config import get_settings

    settings = get_settings()
    return (settings.FRONTEND_URL or settings.BACKEND_PUBLIC_URL).rstrip("/")


async def push_fill_cards(db: AsyncSession, report_date: str, report: Any) -> tuple[int, int]:
    """向配置的填报人员逐一推送填报提醒卡，返回（成功数, 失败数）。"""
    settings = await get_commitment_settings(db)
    if settings is None or not settings.commitment_notify_enabled:
        logger.info("安全承诺填报推送未启用（commitment_notify_enabled=false），跳过")
        return 0, 0
    user_ids = [uid for uid in (settings.commitment_user_ids or []) if uid]
    if not user_ids:
        logger.info("安全承诺填报人员未配置（commitment_user_ids 为空），跳过")
        return 0, 0

    detail_url = f"{public_base_url()}{COMMITMENT_PAGE_PATH}"
    card = build_reminder_card(report_date, _status_line(report), detail_url)
    sent = failed = 0
    for open_id in user_ids:
        message_id = await send_raw_card(str(open_id), card)
        if message_id:
            sent += 1
        else:
            failed += 1
    logger.info(
        "安全承诺填报提醒推送完成: date=%s 成功=%s 失败=%s",
        report_date,
        sent,
        failed,
    )
    return sent, failed


async def push_announcement_cards(db: AsyncSession, item: dict[str, Any]) -> tuple[int, int]:
    """发布后推送承诺公告卡到配置群，返回（成功数, 失败数）。"""
    settings = await get_commitment_settings(db)
    if settings is None:
        return 0, 0
    chat_ids = [cid for cid in (settings.commitment_chat_ids or []) if cid]
    if not chat_ids:
        logger.info("安全承诺公告群未配置（commitment_chat_ids 为空），跳过公告推送")
        return 0, 0
    content = build_announcement_markdown(item)
    title = f"安全承诺公告 · {item.get('report_date', '')}"
    sent = failed = 0
    for chat_id in chat_ids:
        message_id = await send_group_card(
            str(chat_id), title, content, header_template="green"
        )
        if message_id:
            sent += 1
        else:
            failed += 1
    logger.info(
        "安全承诺公告推送完成: date=%s 成功=%s 失败=%s",
        item.get("report_date"),
        sent,
        failed,
    )
    return sent, failed


async def send_test_fill_card(db: AsyncSession, open_id: str) -> bool:
    """设置页「测试发送」：向指定飞书账号推一张填报提醒卡样例。"""
    report_date = (
        datetime.now(UTC).astimezone(CN_TZ).date().isoformat()
    )
    detail_url = f"{public_base_url()}{COMMITMENT_PAGE_PATH}"
    card = build_reminder_card(
        report_date,
        "这是一条测试消息：用于验证安全承诺填报推送通道是否可用。",
        detail_url,
    )
    message_id = await send_raw_card(open_id, card)
    return bool(message_id)
