"""安全承诺飞书推送：车间填报卡、汇总通知（群）与签署卡。

流程：推送时间到 → 各车间负责人收「企业状态填报卡」→ 全部填齐自动
汇总 → 汇总卡推到配置群（提醒安全员网页整理）→ 安全员发布 → 签署人
收签署卡手写签名。飞书未配置或推送失败只记日志，不影响业务事务；
推送目标与开关来自 safety.feishu_app_settings（commitment_* 字段）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import SafetyFeishuAppSettings
from app.modules.safety.service.commitment_card_forms import (
    build_reminder_card,
    build_signature_card,
)
from app.modules.safety.service.commitment_signatures import (
    build_sign_url,
    create_sign_token,
    latest_signature,
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


def public_base_url() -> str:
    """网页端链接的对外基础地址（与作业票免登链接同一口径）。"""
    from app.core.config import get_settings

    settings = get_settings()
    return (settings.FRONTEND_URL or settings.BACKEND_PUBLIC_URL).rstrip("/")


def _page_url() -> str:
    return f"{public_base_url()}{COMMITMENT_PAGE_PATH}"


async def push_workshop_cards(
    db: AsyncSession, report_date: str
) -> tuple[int, int, list[str]]:
    """向全部已配置负责人的启用车间推送当日填报卡。

    返回（成功数, 失败数, 未配置负责人的车间名单）。
    """
    from app.modules.safety.service.commitment_card_forms import (
        MODULE_WORKSHOP,
    )
    from app.modules.safety.service.commitment_workshops import list_configs

    configs = await list_configs(db, ensure=True, enabled_only=True)
    targets = [c for c in configs if c.reporter_open_id]
    missing = [c.workshop_name for c in configs if not c.reporter_open_id]
    if not targets:
        logger.info("安全承诺车间填报无可用负责人配置，跳过推送")
        return 0, 0, missing

    sent = failed = 0
    for cfg in targets:
        card = build_reminder_card(
            report_date,
            "请点击「开始填报」提交本车间今日企业状态；已填数据可覆盖重填。",
            _page_url(),
            module=MODULE_WORKSHOP,
            ws_name=cfg.workshop_name,
            ws_reporter=cfg.reporter_name or "",
        )
        message_id = await send_raw_card(str(cfg.reporter_open_id), card)
        if message_id:
            sent += 1
        else:
            failed += 1
    logger.info(
        "车间填报卡推送完成: date=%s 成功=%s 失败=%s 未配置负责人=%s",
        report_date, sent, failed, len(missing),
    )
    return sent, failed, missing


async def push_remind_cards(
    db: AsyncSession, report_date: str
) -> tuple[int, int]:
    """给未填报车间的负责人推催办卡，返回（成功数, 失败数）。"""
    from app.modules.safety.service.commitment_card_forms import (
        MODULE_WORKSHOP,
    )
    from app.modules.safety.service.commitment_workshops import (
        missing_workshops,
    )

    missing = await missing_workshops(db, report_date)
    targets = [c for c in missing if c.reporter_open_id]
    sent = failed = 0
    for cfg in targets:
        card = build_reminder_card(
            report_date,
            "本车间今日企业状态尚未填报，请尽快完成（点击「开始填报」续填）。",
            _page_url(),
            module=MODULE_WORKSHOP,
            ws_name=cfg.workshop_name,
            ws_reporter=cfg.reporter_name or "",
            kind="remind",
        )
        message_id = await send_raw_card(str(cfg.reporter_open_id), card)
        if message_id:
            sent += 1
        else:
            failed += 1
    logger.info(
        "车间填报催办推送完成: date=%s 未填=%s 成功=%s 失败=%s",
        report_date, len(missing), sent, failed,
    )
    return sent, failed


def _summary_markdown(item: dict[str, Any]) -> str:
    es = item.get("enterprise_status") or {}
    workshops = item.get("workshop_summary") or []
    lines = [f"**承诺日期**：{item.get('report_date', '')}"]
    lines.append(
        f"**生产车间**：共 {es.get('workshop_total', 0)} 个，运行 "
        f"{es.get('workshop_running', 0)} 个，停产 {es.get('workshop_stopped', 0)} 个，"
        f"检修 {es.get('workshop_maintenance', 0)} 个"
    )
    sw = es.get("special_work") or {}
    lines.append(
        f"**当日特殊危险作业**：{es.get('special_work_total', 0)} 处"
        f"（一级动火 {sw.get('hot_work_level1', 0)}、登高 {sw.get('height_work', 0)}、"
        f"受限空间 {sw.get('confined_space', 0)}）"
    )
    lines.append(f"**一般安全生产隐患**：{es.get('hazard_count', 0)} 条")
    lines.append(f"**车间填报**：{len(workshops)} 个车间已完成填报")
    lines.append("请安全员登录平台，在「安全承诺」页面参考各车间明细整理并发布。")
    return "\n".join(lines)


async def push_summary_to_group(
    db: AsyncSession, item: dict[str, Any]
) -> tuple[int, int]:
    """12 车间填齐汇总后，推汇总卡到配置群提醒安全员整理（可配群）。"""
    from app.modules.safety.feishu.notification import send_group_card
    from app.modules.safety.service.commitment_card_forms import (
        build_announcement_markdown,
    )

    settings = await get_commitment_settings(db)
    if settings is None:
        return 0, 0
    chat_ids = [cid for cid in (settings.commitment_chat_ids or []) if cid]
    if not chat_ids:
        logger.info("安全承诺汇总推送群未配置（commitment_chat_ids 为空），跳过")
        return 0, 0
    content = build_announcement_markdown(item)
    extra = _summary_markdown(item)
    title = f"企业状态已汇总 · {item.get('report_date', '')}"
    sent = failed = 0
    for chat_id in chat_ids:
        message_id = await send_group_card(
            str(chat_id), title, f"{content}\n\n---\n\n{extra}",
            header_template="green",
        )
        if message_id:
            sent += 1
        else:
            failed += 1
    logger.info(
        "企业状态汇总推送完成: date=%s 成功=%s 失败=%s",
        item.get("report_date"), sent, failed,
    )
    return sent, failed


async def push_signature_card(
    db: AsyncSession, item: dict[str, Any]
) -> tuple[int, int]:
    """发布后向设置的签署人推签署卡（手写签名/用上次签名）。"""
    settings = await get_commitment_settings(db)
    signer_open_id = str(
        (settings.commitment_signer_open_id if settings else "") or ""
    )
    if not signer_open_id:
        logger.info(
            "安全承诺签署人未配置（commitment_signer_open_id 为空），跳过签署推送"
        )
        return 0, 0
    from app.platform.identity.models import User

    signer_name = ""
    result = await db.execute(
        select(User).where(User.feishu_open_id == signer_open_id)
    )
    user = result.scalar_one_or_none()
    signer_name = str(getattr(user, "name", "") or "") or "主要负责人"

    report_date = str(item.get("report_date") or "")
    token = create_sign_token(
        report_id=str(item.get("id") or ""),
        report_date=report_date,
        open_id=signer_open_id,
        signer_name=signer_name,
    )
    sign_url = build_sign_url(token)
    from app.modules.safety.service.commitment_signatures import (
        get_by_date,
    )

    existing = await get_by_date(db, report_date)
    reuse_available = existing is not None or bool(
        await latest_signature(db, signer_open_id=signer_open_id)
    )
    from app.modules.safety.service.commitment_card_forms import (
        build_announcement_markdown,
    )

    card = build_signature_card(
        report_date,
        signer_name,
        build_announcement_markdown(item),
        sign_url,
        reuse_available,
    )
    message_id = await send_raw_card(signer_open_id, card)
    ok = bool(message_id)
    logger.info(
        "安全承诺签署卡推送: date=%s 结果=%s", report_date, "成功" if ok else "失败"
    )
    return (1, 0) if ok else (0, 1)


async def send_test_workshop_card(db: AsyncSession, open_id: str, ws_name: str) -> bool:
    """设置页「测试发送」：向指定飞书账号推一张车间填报提醒卡样例。"""
    report_date = datetime.now(UTC).astimezone(CN_TZ).date().isoformat()
    from app.modules.safety.service.commitment_card_forms import (
        MODULE_WORKSHOP,
    )

    card = build_reminder_card(
        report_date,
        "这是一条测试消息：用于验证车间填报推送通道是否可用。",
        _page_url(),
        module=MODULE_WORKSHOP,
        ws_name=ws_name,
    )
    message_id = await send_raw_card(open_id, card)
    return bool(message_id)
