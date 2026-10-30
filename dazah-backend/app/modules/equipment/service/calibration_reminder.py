"""校准到期提醒：扫描即将到期/已逾期的校准计划，飞书通知负责人与维修群。

- 负责人走 identity.users 的 feishu_union_id 寻址（跨应用同企业通用）；
- 未绑定飞书或单聊失败时，回落维修群卡片兜底；
- Redis 按天防重：同一计划每天至多提醒一次，避免循环扫描重复轰炸。
"""

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.modules.equipment.models.calibration import CalibrationPlan
from app.platform.identity.models import User

logger = logging.getLogger(__name__)

# 提前提醒窗口（天）：到期前 N 天开始提醒
REMIND_AHEAD_DAYS = 7


def _build_reminder_card(
    *,
    equipment_label: str,
    calibration_type: str,
    next_date: date,
    days_left: int,
) -> dict[str, Any]:
    if days_left < 0:
        status_text, template = f"⚠️ 已逾期 {-days_left} 天", "red"
    elif days_left == 0:
        status_text, template = "🔴 今天到期", "red"
    else:
        status_text, template = f"🟡 {days_left} 天后到期", "yellow"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": f"校准到期提醒 {status_text}"},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**设备**\n{equipment_label}",
                        },
                    },
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**校准类型**\n{calibration_type}",
                        },
                    },
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**下次校准日期**\n{next_date.isoformat()}",
                        },
                    },
                ],
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "请安排校准并在「校准管理」录入校准记录，录入后提醒自动停止",
                    },
                ],
            },
        ],
    }


async def _resolve_responsible_union_id(
    db: AsyncSession, responsible_person_id: str | None
) -> str:
    if responsible_person_id is None:
        return ""
    row = (
        (
            await db.execute(
                select(User).where(User.id == responsible_person_id)
            )
        )
        .scalars()
        .first()
    )
    return (row.feishu_union_id if row else "") or ""


async def remind_due_calibration_plans(db: AsyncSession) -> tuple[int, int]:
    """提醒所有已逾期及 REMIND_AHEAD_DAYS 天内到期的启用计划。

    Returns:
        (reminded, skipped)：提醒数 / 因当日已提醒而跳过数。
    """
    from app.modules.equipment.feishu.notification import send_user_card
    from app.modules.equipment.feishu.repair_card import send_card_to_chat
    from app.modules.equipment.service.work_order_feishu import (
        resolve_repair_chat_id,
    )

    today = date.today()
    horizon = today + timedelta(days=REMIND_AHEAD_DAYS)
    plans = (
        (
            await db.execute(
                select(CalibrationPlan).where(
                    CalibrationPlan.status == "启用",
                    CalibrationPlan.is_deleted == False,  # noqa: E712
                    CalibrationPlan.next_calibration_date.isnot(None),
                    CalibrationPlan.next_calibration_date <= horizon,
                )
            )
        )
        .scalars()
        .all()
    )

    reminded = 0
    skipped = 0
    for plan in plans:
        dedup_key = f"calibration:remind:{plan.id}:{today.isoformat()}"
        is_new = await redis_client.set(dedup_key, "1", ex=48 * 3600, nx=True)
        if not is_new:
            skipped += 1
            continue

        equipment = plan.equipment
        equipment_label = f"{equipment.name}（{equipment.equipment_no}）" if equipment else str(plan.equipment_id)
        days_left = (plan.next_calibration_date - today).days
        card = _build_reminder_card(
            equipment_label=equipment_label,
            calibration_type=plan.calibration_type,
            next_date=plan.next_calibration_date,
            days_left=days_left,
        )

        # 负责人单聊优先；未绑定或发送失败时群兜底
        union_id = await _resolve_responsible_union_id(db, plan.responsible_person_id)
        dm_sent = False
        if union_id:
            try:
                dm_sent = await send_user_card(
                    open_id=union_id,
                    title="校准到期提醒",
                    content=f"{equipment_label} 下次校准 {plan.next_calibration_date.isoformat()}",
                    receive_id_type="union_id",
                )
            except Exception:
                logger.exception("校准提醒单聊发送失败: plan=%s", plan.id)

        if not dm_sent:
            chat_id = await resolve_repair_chat_id(
                equipment.workshop_code if equipment else ""
            )
            if chat_id:
                try:
                    await send_card_to_chat(chat_id, card)
                except Exception:
                    logger.exception("校准提醒群兜底发送失败: plan=%s", plan.id)
        reminded += 1

    if plans:
        logger.info(
            "校准到期提醒完成: 提醒 %d 个计划, 跳过(当日已提醒) %d 个",
            reminded,
            skipped,
        )
    return reminded, skipped
