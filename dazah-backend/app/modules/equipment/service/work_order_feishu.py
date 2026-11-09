"""Work order Feishu bot service: query, complete and report repairs via chat."""

import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.modules.equipment import repository as repo
from app.modules.equipment.feishu.notification import send_user_card
from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.models.workshop import EquipmentWorkshop
from app.modules.equipment.schemas import WorkOrderComplete, WorkOrderCreate
from app.modules.equipment.service.work_order import (
    complete_work_order,
    create_work_order,
)

logger = logging.getLogger(__name__)

_URGENT_KEYWORDS = ("紧急", "特急", "马上", "立刻", "停机", "抢险", "急")
# 分词切分：空格与常见标点
_TOKEN_SPLIT = re.compile(r"[\s,，、;；/\\]+")
# 去空格/零宽字符：整名连续比对用
_COMPACT = re.compile(r"[\s\u200b]+")


async def _find_user_by_user_id(db: AsyncSession, user_id: str) -> Any:
    """根据飞书 user_id（租户级）查找系统用户。"""
    from app.platform.identity.models import User

    if not user_id:
        return None
    result = await db.execute(
        select(User).where(
            User.feishu_user_id == user_id,
            User.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _find_user_by_open_id(db: AsyncSession, open_id: str) -> Any:
    """根据飞书 open_id 查找系统用户（飞书扫码登录时写入）。"""
    from app.platform.identity.models import User

    if not open_id:
        return None
    result = await db.execute(
        select(User).where(
            User.feishu_open_id == open_id,
            User.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _find_user_by_union_id(
    db: AsyncSession, union_id: str | None
) -> Any:
    """根据飞书 union_id 查找系统用户（跨应用唯一，卡片回调用）。"""
    from app.platform.identity.models import User

    if not union_id:
        return None
    result = await db.execute(
        select(User).where(
            User.feishu_union_id == union_id,
            User.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _find_user_by_feishu(
    db: AsyncSession,
    *,
    open_id: str,
    user_id: str | None = None,
    union_id: str | None = None,
) -> Any:
    """事件里 user_id 常为空（应用未开对应字段），union_id 跨应用最稳。"""
    user = await _find_user_by_union_id(db, union_id)
    if user is None:
        user = await _find_user_by_open_id(db, open_id)
    if user is None and user_id:
        user = await _find_user_by_user_id(db, user_id)
    return user


async def list_user_work_orders(
    user_id: str,
    open_id: str,
) -> None:
    """查询并发送用户的未关闭工单列表。"""
    async with async_session_factory() as db:
        user = await _find_user_by_feishu(db, open_id=open_id, user_id=user_id)
        if not user:
            await send_user_card(
                open_id=open_id,
                title="❌ 未找到用户",
                receive_id_type="open_id",
                content="未找到与您的飞书账号关联的系统用户。",
            )
            return

        work_orders = await repo.get_user_work_orders(db, user.id)

    if not work_orders:
        await send_user_card(
            open_id=open_id,
            title="📋 我的工单",
            receive_id_type="open_id",
            content="当前没有未关闭的工单。",
        )
        return

    lines = [f"**共 {len(work_orders)} 个未关闭工单**\n"]
    options: list[dict[str, Any]] = []
    for i, wo in enumerate(work_orders, 1):
        eq_name = wo.equipment.name if wo.equipment else "未知设备"
        status_icon = {"待处理": "⏳", "执行中": "🔄", "待验收": "✅"}.get(
            wo.status, "📋"
        )
        lines.append(
            f"**{i}.** {status_icon} {wo.work_order_no} | {wo.order_type} | "
            f"{wo.status}\n"
            f"   设备: {eq_name}"
        )
        options.append(
            {
                "index": i,
                "work_order_no": wo.work_order_no,
                "order_type": wo.order_type,
                "status": wo.status,
                "equipment_name": eq_name,
            }
        )

    lines.append(
        "\n---\n"
        "发送「完成 工单号 描述」提交完成\n"
        "或「完成 序号 描述」，例: `完成 1 更换密封圈`"
    )

    # 保存选择列表，支持后续数字索引完成
    from app.modules.equipment.service.inspection_session import save_selection

    await save_selection(open_id, select_type="work_order", options=options)

    await send_user_card(
        open_id=open_id,
        title="📋 我的工单",
        receive_id_type="open_id",
        content="\n".join(lines),
    )


async def complete_work_order_by_no(
    user_id: str,
    open_id: str,
    work_order_no: str,
    repair_detail: str | None = None,
) -> None:
    """通过工单号完成工单。"""
    async with async_session_factory() as db:
        user = await _find_user_by_feishu(db, open_id=open_id, user_id=user_id)
        if not user:
            await send_user_card(
                open_id=open_id,
                title="❌ 未找到用户",
                receive_id_type="open_id",
                content="未找到与您的飞书账号关联的系统用户。",
            )
            return

        wo = await repo.get_work_order_by_no(db, work_order_no)
        if not wo:
            await send_user_card(
                open_id=open_id,
                title="❌ 工单不存在",
                receive_id_type="open_id",
                content=f"未找到工单 **{work_order_no}**，请检查工单号。",
            )
            return

        # 校验状态：必须是执行中
        if wo.status != "执行中":
            await send_user_card(
                open_id=open_id,
                title="❌ 无法完成",
                receive_id_type="open_id",
                content=(
                    f"工单 **{work_order_no}** 当前状态为「{wo.status}」，\n"
                    "只有「执行中」的工单才能提交完成。"
                ),
            )
            return

        # 校验权限：必须是当前用户的工单
        if wo.assignee_id != user.id:
            await send_user_card(
                open_id=open_id,
                title="❌ 无权限",
                receive_id_type="open_id",
                content=(
                    f"工单 **{work_order_no}** 的执行人不是您，\n"
                    "只能完成指派给自己的工单。"
                ),
            )
            return

        detail = repair_detail or "通过飞书机器人完成"
        data = WorkOrderComplete(repair_detail=detail)

        try:
            completed_wo = await complete_work_order(db, wo.id, data)
            await db.commit()
        except Exception as e:
            logger.exception("完成工单失败: %s", e)
            await send_user_card(
                open_id=open_id,
                title="❌ 完成失败",
                receive_id_type="open_id",
                content=f"工单 **{work_order_no}** 完成失败：{e}",
            )
            return

    eq_name = completed_wo.equipment.name if completed_wo.equipment else "未知设备"
    await send_user_card(
        open_id=open_id,
        title="✅ 工单已完成",
        receive_id_type="open_id",
        content=(f"**{work_order_no}**\n设备: {eq_name}\n维修过程: {detail}"),
    )


async def _match_workshops(db: AsyncSession, text: str) -> list[Any]:
    """从报修文本中识别车间：代码（201-1）或完整名称（201一车间）命中。"""
    from app.modules.equipment.models.workshop import EquipmentWorkshop

    rows = (
        await db.execute(
            select(EquipmentWorkshop).where(
                EquipmentWorkshop.is_deleted == False,  # noqa: E712
                EquipmentWorkshop.is_enabled == True,  # noqa: E712
            )
        )
    ).scalars().all()
    return [ws for ws in rows if ws.code in text or ws.name in text]


def _split_tokens(text: str, *strip_words: str) -> list[str]:
    """按标点/空格切词，并剔除车间等已知干扰词。"""
    cleaned = text
    for word in strip_words:
        if word:
            cleaned = cleaned.replace(word, " ")
    return [t for t in _TOKEN_SPLIT.split(cleaned) if len(t) >= 2]


def _compact_hit(name: str | None, no: str | None, compact_body: str) -> bool:
    """去空格整体比对：设备全名（含序号）作为连续片段出现在报修内容里。

    处理「下卸料离心机 1」这类名称本身带空格的设备：分词会把序号
    切成单字丢弃，导致 1~5 号机全部命中；整体比对可唯一定位。
    """
    for part in (name, no):
        if part:
            compact = _COMPACT.sub("", part)
            if compact and compact in compact_body:
                return True
    return False


async def _match_equipments(
    db: AsyncSession, workshop_code: str, tokens: list[str], *, body: str = ""
) -> list[Any]:
    """车间内设备匹配：整名优先（去空格连续命中），分词兜底（双向包含）。"""

    # 不按状态过滤：维修中的设备也可能再次故障报修，
    # 可否建单由 create_work_order 的状态校验兜底
    equipments = (
        await db.execute(
            select(Equipment).where(
                Equipment.workshop_code == workshop_code,
                Equipment.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().all()
    if body:
        compact_body = _COMPACT.sub("", body)
        exact = [
            eq
            for eq in equipments
            if _compact_hit(eq.name, eq.equipment_no, compact_body)
        ]
        if exact:
            return exact
    matched: list[Any] = []
    for eq in equipments:
        for token in tokens:
            if token in eq.name or token in eq.equipment_no:
                matched.append(eq)
                break
    return matched


async def _register_mirror_equipment(db: AsyncSession, device: Any) -> Any:
    """把巡检镜像设备自动注册进台账（报修回落路径，台账随报修自动生长）。"""
    from app.modules.equipment.models.equipment import Location

    no = (device.equipment_no or "").strip() or f"MIRROR-{device.record_id[:12]}"
    existing = (
        await db.execute(
            select(Equipment).where(
                Equipment.equipment_no == no,
                Equipment.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if existing is not None:
        return existing
    location = (
        await db.execute(
            select(Location).where(
                Location.is_deleted == False,  # noqa: E712
            ).limit(1)
        )
    ).scalars().first()
    if location is None:
        location = Location(name="未分类", code="UNCATEGORIZED")
        db.add(location)
        await db.flush()
    eq = Equipment(
        equipment_no=no,
        name=(device.equipment_name or no).strip(),
        workshop_code=device.workshop_code,
        location_id=location.id,
        status="在用",
    )
    db.add(eq)
    await db.flush()
    logger.info("报修回落：巡检镜像设备自动注册台账 %s（%s）", eq.name, eq.equipment_no)
    return eq


async def _sample_ledger_names(
    db: AsyncSession, workshop_code: str
) -> list[Any]:
    """台账内该车间设备名（用于未识别提示的示例）。"""

    rows = (
        await db.execute(
            select(Equipment)
            .where(
                Equipment.workshop_code == workshop_code,
                Equipment.is_deleted == False,  # noqa: E712
            )
            .limit(10)
        )
    ).scalars()
    return list(rows)


async def create_repair_by_text(
    *, user_id: str, open_id: str, text: str, union_id: str | None = None
) -> None:
    """自然语言报修：「报修 3车间 离心泵 密封漏了 紧急」→ 建单并通知。

    命名空间说明：仅由「报修」前缀触发，不影响机器人其他指令
    （巡检、工单查询、其他模块）。
    """
    from app.platform.identity.service import get_or_create_system_admin

    body = text.removeprefix("报修").strip()
    if not body:
        await send_user_card(
            open_id=open_id,
            title="💡 报修格式",
            receive_id_type="open_id",
            content=(
                "格式：`报修 车间 设备 故障情况`\n"
                "示例：`报修 201一车间 离心泵 密封漏了 紧急`\n"
                "带「紧急」两字会生成紧急工单"
            ),
        )
        return

    priority = "紧急" if any(k in body for k in _URGENT_KEYWORDS) else "高"
    for k in _URGENT_KEYWORDS:
        body = body.replace(k, " ")
    body = body.strip()

    # LLM 意图解析：口语归一化（车间/设备/故障/紧急度），失败静默回落规则。
    # 解析结果只用于增强匹配文本与紧急度判定，业务动作仍由确定性匹配执行
    from app.modules.equipment.feishu.repair_intent import parse_repair_intent

    async with async_session_factory() as db:
        # 注册车间清单交给 LLM 做接地：口语车间名归一化为注册名
        registered = (
            (
                await db.execute(
                    select(EquipmentWorkshop).where(
                        EquipmentWorkshop.is_enabled == True,  # noqa: E712
                        EquipmentWorkshop.is_deleted == False,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        intent = await parse_repair_intent(
            text, [ws.name for ws in registered]
        )
        match_body = body
        if intent is not None:
            if intent["urgency"] == "紧急":
                priority = "紧急"
            parts = (body, intent["workshop"], intent["equipment"])
            enriched = " ".join(p for p in parts if p)
            if len(enriched) > len(body):
                match_body = enriched

        # 报修人：优先飞书绑定的平台账号（union_id 跨应用最稳）；
        # 无绑定（如外包人员）落到系统管理员
        user = await _find_user_by_feishu(
            db, open_id=open_id, user_id=user_id, union_id=union_id
        )
        if user is None:
            user = await get_or_create_system_admin(db)
        reporter_label = user.name if user.username != "system_admin" else "飞书用户"

        workshops = await _match_workshops(db, match_body)
        if len(workshops) == 0:
            all_workshops = (
                (await db.execute(
                    select(EquipmentWorkshop).where(
                        EquipmentWorkshop.is_enabled == True,  # noqa: E712
                        EquipmentWorkshop.is_deleted == False,  # noqa: E712
                    )
                )).scalars()
            )
            names = "、".join(ws.name for ws in all_workshops)
            await send_user_card(
                open_id=open_id,
                title="❌ 未识别车间",
                receive_id_type="open_id",
                content=(
                    "请在报修内容里带上车间，"
                    f"例如：`报修 201一车间 离心泵 漏了`\n可用车间：{names}"
                ),
            )
            return
        if len(workshops) > 1:
            found = "、".join(ws.name for ws in workshops)
            await send_user_card(
                open_id=open_id,
                title="❌ 匹配到多个车间",
                receive_id_type="open_id",
                content=f"同时命中：{found}\n请写完整车间名，例如「201一车间」",
            )
            return
        workshop = workshops[0]

        tokens = _split_tokens(match_body, workshop.code, workshop.name)
        equipments = await _match_equipments(
            db, workshop.code, tokens, body=match_body
        )
        if len(equipments) == 0:
            # 台账没有 → 回落到巡检镜像（飞书多维表格同步的真实设备），
            # 唯一命中时自动注册进台账后建单
            from app.modules.equipment.models.inspection_feishu_mirror import (
                EquipmentInspectionFeishuDevice,
            )

            mirror_rows = (
                await db.execute(
                    select(EquipmentInspectionFeishuDevice).where(
                        EquipmentInspectionFeishuDevice.workshop_code
                        == workshop.code,
                        EquipmentInspectionFeishuDevice.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalars().all()
            compact_body = _COMPACT.sub("", match_body)
            mirror_matched = [
                d
                for d in mirror_rows
                if _compact_hit(d.equipment_name, d.equipment_no, compact_body)
            ]
            if not mirror_matched:
                mirror_matched = [
                    d
                    for d in mirror_rows
                    if any(
                        (d.equipment_name and token in d.equipment_name)
                        or (d.equipment_no and token in d.equipment_no)
                        for token in tokens
                    )
                ]
            if len(mirror_matched) == 1:
                equipment = await _register_mirror_equipment(db, mirror_matched[0])
                await db.commit()
                equipments = [equipment]
            elif len(mirror_matched) > 1:
                lines = [f"在 {workshop.name} 匹配到多台设备，请写全名重新报修：\n"]
                for d in mirror_matched[:10]:
                    lines.append(f"- **{d.equipment_name}**（{d.equipment_no}）")
                await send_user_card(
                    open_id=open_id,
                    title="❌ 匹配到多台设备",
                    receive_id_type="open_id",
                    content="\n".join(lines),
                )
                return
            else:
                sample_names = [
                    d.equipment_name
                    for d in mirror_rows[:10]
                    if d.equipment_name
                ]
                if not sample_names:
                    ledger_rows = await _sample_ledger_names(db, workshop.code)
                    sample_names = [eq.name for eq in ledger_rows]
                sample = "、".join(sample_names) or "（该车间暂无在册设备）"
                example = sample_names[0] if sample_names else "设备名"
                await send_user_card(
                    open_id=open_id,
                    title="❌ 未识别设备",
                    receive_id_type="open_id",
                    content=(
                        f"在 {workshop.name} 没匹配到设备。\n"
                        f"请带上设备名称，如：`报修 {workshop.name} {example} 漏了`\n"
                        f"该车间设备示例：{sample}"
                    ),
                )
                return
        if len(equipments) > 1:
            lines = [f"在 {workshop.name} 匹配到多台设备，请写全名重新报修：\n"]
            for eq in equipments[:10]:
                lines.append(f"- **{eq.name}**（{eq.equipment_no}）")
            await send_user_card(
                open_id=open_id,
                title="❌ 匹配到多台设备",
                receive_id_type="open_id",
                content="\n".join(lines),
            )
            return
        equipment = equipments[0]

        name_no = f"{equipment.name} {equipment.equipment_no or ''}"
        fault = " ".join(t for t in tokens if t not in name_no) or "飞书报修"
        if reporter_label == "飞书用户":
            fault = f"[飞书报修] {fault}"

        try:
            wo = await create_work_order(
                db,
                WorkOrderCreate(
                    equipment_id=equipment.id,
                    order_type="故障维修",
                    priority=priority,
                    fault_description=fault,
                ),
                reporter_id=user.id,
            )
            # WS 会话出块即关闭，必须显式提交，否则工单随事务回滚丢失
            await db.commit()
        except Exception as exc:
            logger.exception("飞书报修建单失败")
            await send_user_card(
                open_id=open_id,
                title="❌ 报修失败",
                receive_id_type="open_id",
                content=f"工单创建失败：{exc}",
            )
            return

    # 回报修人 + 维修群派单交互卡片（可一键接单）
    await send_user_card(
        open_id=open_id,
        title=f"✅ 报修已受理 {'🔴紧急' if priority == '紧急' else ''}".strip(),
        receive_id_type="open_id",
        content=(
            f"**工单号：**{wo.work_order_no}\n"
            f"**设备：**{equipment.name}（{equipment.equipment_no}）\n"
            f"**车间：**{workshop.name}\n"
            f"**描述：**{fault}\n\n"
            "维修人员接单后您会收到通知。"
        ),
    )
    try:
        await dispatch_repair_card(
            work_order_no=wo.work_order_no,
            equipment_label=f"{equipment.name}（{equipment.equipment_no}）",
            workshop_name=workshop.name,
            fault=fault,
            priority=priority,
            reporter_name=reporter_label,
            workshop_code=workshop.code,
        )
    except Exception:
        logger.exception("报修派单群通知失败（工单已创建，不影响）")


async def resolve_repair_chat_id(workshop_code: str) -> str:
    """按车间解析维修群 chat_id：车间已配 → 用车间群；否则回落全局默认群。"""
    from app.core.config import get_settings

    if workshop_code:
        async with async_session_factory() as db:
            row = (
                (
                    await db.execute(
                        select(EquipmentWorkshop).where(
                            EquipmentWorkshop.code == workshop_code,
                            EquipmentWorkshop.is_deleted == False,  # noqa: E712
                        )
                    )
                )
                .scalars()
                .first()
            )
        if row is not None and row.feishu_chat_id:
            return str(row.feishu_chat_id)
    return get_settings().FEISHU_EQUIPMENT_CHAT_ID or ""


async def dispatch_repair_card(
    *,
    work_order_no: str,
    equipment_label: str,
    workshop_name: str,
    fault: str,
    priority: str,
    reporter_name: str,
    workshop_code: str = "",
) -> str | None:
    """向维修群发送可接单的交互卡片，message_id 存 Redis 供后续更新。

    派单群按工单所属车间路由（车间注册表的 feishu_chat_id），
    未配置的车间回落全局默认群。
    """
    from app.core.redis import redis_client
    from app.modules.equipment.feishu.repair_card import (
        build_dispatch_card,
        send_card_to_chat,
    )

    chat_id = await resolve_repair_chat_id(workshop_code)
    if not chat_id:
        logger.warning(
            "车间 %s 未配维修群且全局默认群未配置，跳过派单卡片",
            workshop_code or "-",
        )
        return None
    card = build_dispatch_card(
        work_order_no=work_order_no,
        equipment_label=equipment_label,
        workshop_name=workshop_name,
        fault=fault,
        priority=priority,
        reporter_name=reporter_name,
    )
    message_id = await send_card_to_chat(chat_id, card)
    await redis_client.set(
        f"repair:card:{work_order_no}", message_id, ex=7 * 24 * 3600
    )
    return message_id


def _card_error_payload(message: str) -> dict[str, Any]:
    """卡片回调失败时的 ACK 响应（飞书卡片回调协议）。"""
    return {"code": 0, "toast": {"type": "error", "content": message}}


def _card_ok_payload(message: str = "") -> dict[str, Any]:
    """卡片回调成功时的 ACK 响应。"""
    payload: dict[str, Any] = {"code": 0}
    if message:
        payload["toast"] = {"type": "success", "content": message}
    return payload


async def _attach_repair_photo(
    db: AsyncSession, wo_id: uuid.UUID, photo_nonce: str
) -> None:
    """把拍照识别的临时照片归档为工单附件（nonce 一次性，10 分钟内有效）。"""
    import os
    from io import BytesIO

    from fastapi import UploadFile

    from app.core.redis import redis_client
    from app.modules.equipment.service.work_order_image import upload_images

    if not photo_nonce:
        return
    photo_path = await redis_client.get(f"repair:photo:img:{photo_nonce}")
    if not photo_path or not os.path.exists(photo_path):
        return
    with open(photo_path, "rb") as f:
        content = f.read()
    upload = UploadFile(file=BytesIO(content), filename="拍照报修.jpg")
    upload.size = len(content)
    try:
        await upload_images(db, wo_id, [upload])
    except Exception:
        logger.exception("拍照报修照片归档失败（不影响工单）")


async def _handle_photo_action(
    value: dict[str, Any], *, open_id: str, union_id: str
) -> dict[str, Any]:
    """拍照报修确认卡片回调：photo_repair=确认建单，photo_cancel=取消。"""
    import uuid as uuid_mod

    from app.core.redis import redis_client
    from app.modules.equipment.service.work_order import create_work_order

    async def _fail(message: str) -> dict[str, Any]:
        if open_id:
            try:
                await send_user_card(
                    open_id=open_id,
                    title="❌ 拍照报修未完成",
                    receive_id_type="open_id",
                    content=message,
                )
            except Exception:
                logger.exception("拍照报修失败提示发送失败")
        return _card_error_payload(message)

    act = value.get("act", "")
    if act == "photo_cancel":
        return _card_ok_payload("已取消，可重拍或发送文字「报修 …」")

    eq_id = str(value.get("eq", "") or "")
    fault = str(value.get("ft", "") or "").strip()
    photo_nonce = str(value.get("ph", "") or "")
    if not eq_id:
        return await _fail("卡片数据缺失，请重新拍照报修")

    # 一次性消费照片 nonce，防连点重复建单
    if photo_nonce:
        used = await redis_client.set(
            f"repair:photo:used:{photo_nonce}", "1", ex=600, nx=True
        )
        if not used:
            return await _fail("这张照片已处理过，请勿重复点击")

    try:
        eq_uuid = uuid_mod.UUID(eq_id)
    except ValueError:
        return await _fail("设备信息无效，请重新拍照报修")

    async with async_session_factory() as db:
        user = await _find_user_by_feishu(db, open_id=open_id, union_id=union_id)
        if user is None:
            return await _fail("未绑定平台账号，请先用飞书登录一次平台后重试")
        equipment = await repo.get_equipment_by_id(db, eq_uuid)
        if equipment is None:
            return await _fail("设备不存在或已删除，请重新拍照报修")

        fault_text = f"[拍照报修] {fault}" if fault else "[拍照报修]（见附件照片）"
        try:
            wo = await create_work_order(
                db,
                WorkOrderCreate(
                    equipment_id=equipment.id,
                    order_type="故障维修",
                    priority="高",
                    fault_description=fault_text,
                ),
                reporter_id=user.id,
            )
        except Exception as exc:
            logger.exception("拍照报修建单失败")
            return await _fail(f"工单创建失败：{exc}")

        await _attach_repair_photo(db, wo.id, photo_nonce)
        await db.commit()

    workshop_name = equipment.workshop_code or ""
    await send_user_card(
        open_id=open_id,
        title="✅ 拍照报修已受理",
        receive_id_type="open_id",
        content=(
            f"**工单号：**{wo.work_order_no}\n"
            f"**设备：**{equipment.name}（{equipment.equipment_no}）\n"
            f"**描述：**{fault_text}\n\n"
            "照片已作为附件归档，维修人员接单后会更新进度。"
        ),
    )
    try:
        await dispatch_repair_card(
            work_order_no=wo.work_order_no,
            equipment_label=f"{equipment.name}（{equipment.equipment_no}）",
            workshop_name=workshop_name or "未知车间",
            fault=fault_text,
            priority="高",
            reporter_name=user.name,
            workshop_code=workshop_name,
        )
    except Exception:
        logger.exception("拍照报修派单群通知失败（工单已创建，不影响）")
    return _card_ok_payload("已建单并派发维修群")


async def _handle_knowledge_action(
    value: dict[str, Any], *, open_id: str, union_id: str
) -> dict[str, Any]:
    """维修知识案例确认卡片回调：case_verify=入库，case_dismiss=忽略。"""
    import uuid as uuid_mod

    from app.core.exceptions import AppException
    from app.modules.equipment.service import knowledge as knowledge_service

    async def _fail(message: str) -> dict[str, Any]:
        if open_id:
            try:
                await send_user_card(
                    open_id=open_id,
                    title="❌ 案例操作未生效",
                    receive_id_type="open_id",
                    content=message,
                )
            except Exception:
                logger.exception("案例操作失败提示发送失败")
        return _card_error_payload(message)

    cid = str(value.get("cid", "") or "")
    if not cid:
        return await _fail("卡片数据缺失")
    try:
        case_uuid = uuid_mod.UUID(cid)
    except ValueError:
        return await _fail("案例信息无效")

    async with async_session_factory() as db:
        user = await _find_user_by_feishu(db, open_id=open_id, union_id=union_id)
        if user is None:
            return await _fail("未绑定平台账号，请先用飞书登录一次平台后重试")
        try:
            if value.get("act") == "case_verify":
                await knowledge_service.verify_case(db, case_uuid, user.id)
                message = "维修经验已入库，感谢沉淀！"
            else:
                await knowledge_service.dismiss_case(db, case_uuid, user.id)
                message = "已忽略该案例草稿"
            await db.commit()
        except AppException as exc:
            return await _fail(exc.message)
        except Exception:
            logger.exception("案例卡片操作失败: %s", cid)
            return await _fail("操作失败，请稍后在平台「维护保养→维修知识」中处理")
    return _card_ok_payload(message)


# 后台补丁任务引用（防止被 GC 中断）
_patch_tasks: set[asyncio.Task[None]] = set()


async def _patch_card_reliably(
    message_id: str, card: dict[str, Any], *, expected_title_prefix: str
) -> None:
    """打补丁并延迟复核。

    飞书在按钮点击的交互窗口期内，对卡片的 PATCH 会返回 code=0 但被
    静默回滚（实测点击后 ~1 秒内的补丁必失效、几分钟后的补丁必生效），
    因此立即打一次后按延迟复核实际内容，未生效则重打。
    """
    from app.modules.equipment.feishu.repair_card import (
        get_card_title,
        patch_card_message,
    )

    try:
        await patch_card_message(message_id, card)
        for delay in (3, 9):
            await asyncio.sleep(delay)
            title = await get_card_title(message_id)
            if title.startswith(expected_title_prefix):
                logger.info("卡片复核通过: %s %s", message_id, title[:24])
                return
            logger.info("卡片复核未生效，重打: %s 当前=%s", message_id, title[:24])
            await patch_card_message(message_id, card)
    except Exception:
        logger.exception("卡片可靠更新失败: %s", message_id)


async def handle_card_action(payload: dict[str, Any]) -> dict[str, Any]:
    """派单卡片按钮回调：accept=接单并开始，complete=提交完成。

    由长连接 CARD 帧送达（ws_client），返回飞书卡片回调协议响应。
    """
    from app.core.redis import redis_client
    from app.modules.equipment.feishu.repair_card import (
        build_accepted_card,
        build_completed_card,
    )
    from app.modules.equipment.schemas import WorkOrderComplete
    from app.modules.equipment.service.work_order import (
        assign_work_order,
        complete_work_order,
        start_work_order,
    )

    operator = payload.get("operator") or {}
    union_id = operator.get("union_id", "") or ""
    open_id = operator.get("open_id", "") or ""
    action = payload.get("action") or {}
    value = action.get("value") or {}
    act = value.get("act", "")
    wo_no = value.get("oid", "")
    logger.info(
        "卡片按钮回调: act=%s, wo=%s, operator_open_id=%s",
        act,
        wo_no,
        open_id,
    )

    async def _fail(message: str) -> dict[str, Any]:
        """错误时私聊操作者（事件通道下 toast 不可见，私聊兜底）。"""
        if open_id:
            try:
                await send_user_card(
                    open_id=open_id,
                    title="❌ 卡片操作未生效",
                    receive_id_type="open_id",
                    content=message,
                )
            except Exception:
                logger.exception("卡片操作失败提示发送失败")
        return _card_error_payload(message)

    if act in ("photo_repair", "photo_cancel"):
        return await _handle_photo_action(value, open_id=open_id, union_id=union_id)

    if act in ("case_verify", "case_dismiss"):
        return await _handle_knowledge_action(
            value, open_id=open_id, union_id=union_id
        )

    if act in ("transfer", "transfer_pick"):
        return await _handle_transfer_action(
            payload, open_id=open_id, union_id=union_id
        )

    if act in ("parts_list", "parts_pick"):
        return await _handle_parts_action(
            payload, open_id=open_id, union_id=union_id
        )

    if act in ("repay_confirm", "repay_cancel"):
        return await _handle_repay_action(
            payload, open_id=open_id, union_id=union_id
        )

    if act not in ("accept", "complete") or not wo_no:
        return await _fail("未知操作")

    async with async_session_factory() as db:
        user = await _find_user_by_feishu(
            db, open_id=open_id, union_id=union_id
        )
        if user is None:
            return await _fail(
                "未绑定平台账号，请先用飞书登录一次平台后重试"
            )
        wo = await repo.get_work_order_by_no(db, wo_no)
        if wo is None:
            return await _fail(f"工单 {wo_no} 不存在")
        equipment_label = (
            f"{wo.equipment.name}（{wo.equipment.equipment_no}）"
            if wo.equipment
            else "未知设备"
        )

        if act == "accept":
            if wo.status != "待处理":
                return await _fail(
                    f"工单 {wo_no} 已是「{wo.status}」状态，无需接单；"
                    "请确认点的是最新一张卡片"
                )
            wo = await assign_work_order(db, wo.id, user.id)
            wo = await start_work_order(db, wo.id)
            await db.commit()
        else:  # complete
            if wo.status != "执行中":
                return await _fail(
                    f"工单 {wo_no} 当前「{wo.status}」，只有执行中可提交完成"
                )
            wo = await complete_work_order(
                db,
                wo.id,
                WorkOrderComplete(repair_detail="手机卡片一键完成"),
            )
            await db.commit()

    # 优先用回调事件自带的消息 ID（卡片就在被点击的那张上）
    card_message_id = (
        str(payload.get("open_message_id") or "")
        or await redis_client.get(f"repair:card:{wo_no}")
    )
    if card_message_id:
        card = (
            build_accepted_card(
                work_order_no=wo_no,
                equipment_label=equipment_label,
                assignee_name=user.name,
                accepted_at=datetime.now(UTC),
            )
            if act == "accept"
            else build_completed_card(
                work_order_no=wo_no,
                equipment_label=equipment_label,
                assignee_name=user.name,
            )
        )
        # 立即返回 ACK（点击后交互窗口期内的同步补丁会被飞书静默回滚），
        # 可靠更新放到后台任务里做并复核
        if act == "accept":
            expected_prefix = f"✅ 已接单 {wo_no}"
        else:
            expected_prefix = f"🛠 已完成，待验收 {wo_no}"
        task = asyncio.create_task(
            _patch_card_reliably(
                card_message_id, card, expected_title_prefix=expected_prefix
            )
        )
        _patch_tasks.add(task)
        task.add_done_callback(_patch_tasks.discard)
    logger.info("卡片按钮处理完成: act=%s, wo=%s, 操作人=%s", act, wo_no, user.name)
    return {"code": 0, "toast": {"type": "success", "content": "操作成功"}}


# ══════════════ 方案E：转派 / 申请备件 / 再报上次 ══════════════


async def _list_transfer_candidates(
    db: AsyncSession, workshop_code: str, exclude_user_id: Any
) -> list[dict[str, Any]]:
    """同车间在岗人员（排除当前维修人）作为转派候选。"""
    from sqlalchemy import select as _select

    from app.modules.equipment.models.personnel import EquipmentPersonnel
    from app.platform.identity.models import User

    rows = (
        (
            await db.execute(
                _select(EquipmentPersonnel, User)
                .join(User, User.id == EquipmentPersonnel.user_id)
                .where(
                    EquipmentPersonnel.is_deleted == False,  # noqa: E712
                    EquipmentPersonnel.is_active == True,  # noqa: E712
                    EquipmentPersonnel.workshop_code == workshop_code,
                    EquipmentPersonnel.user_id != exclude_user_id,
                )
                .order_by(EquipmentPersonnel.name)
                .limit(10)
            )
        )
        .all()
    )
    return [
        {
            "user_id": str(u.id),
            "name": p.name,
            "employee_no": p.employee_no,
        }
        for p, u in rows
    ]


async def _handle_transfer_action(
    payload: dict[str, Any], *, open_id: str, union_id: str
) -> dict[str, Any]:
    """转派入口：transfer=发候选人卡，transfer_pick=执行转派。"""
    from app.core.exceptions import AppException

    value = payload.get("action") or {}
    v = value.get("value") or {}
    act = v.get("act", "")
    wo_no = v.get("oid", "")

    async def _fail(message: str) -> dict[str, Any]:
        if open_id:
            try:
                await send_user_card(
                    open_id=open_id,
                    title="❌ 转派未完成",
                    receive_id_type="open_id",
                    content=message,
                )
            except Exception:
                logger.exception("转派失败提示发送失败")
        return _card_error_payload(message)

    async with async_session_factory() as db:
        user = await _find_user_by_feishu(db, open_id=open_id, union_id=union_id)
        if user is None:
            return await _fail("未绑定平台账号，请先用飞书登录一次平台后重试")
        wo = await repo.get_work_order_by_no(db, wo_no)
        if wo is None:
            return await _fail(f"工单 {wo_no} 不存在")
        if wo.assignee_id != user.id:
            return await _fail("只有当前维修人可以发起转派")
        if wo.status not in ("待处理", "执行中"):
            return await _fail(f"工单已是「{wo.status}」状态，无需转派")

        if act == "transfer":
            workshop = wo.equipment.workshop_code if wo.equipment else ""
            candidates = await _list_transfer_candidates(
                db, workshop, exclude_user_id=user.id
            )
            if not candidates:
                return await _fail("该车间暂无其他在岗维修人员可转派")

            await send_user_card(
                open_id=open_id,
                title=f"↗️ 转派 {wo_no}",
                receive_id_type="open_id",
                content="请选择新的维修人：",
                elements=[
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": c["name"],
                                },
                                "value": {
                                    "act": "transfer_pick",
                                    "oid": wo_no,
                                    "uid": c["user_id"],
                                },
                            }
                            for c in candidates[:10]
                        ],
                    }
                ],
            )
            return _card_ok_payload("已发送候选人选择卡片")

        # transfer_pick
        from app.modules.equipment.service.work_order import transfer_work_order
        from app.platform.identity.models import User

        try:
            wo = await transfer_work_order(
                db,
                wo.id,
                uuid.UUID(str(v.get("uid", ""))),
                operator_id=user.id,
                reason="卡片转派",
            )
            # 会话提交会过期 ORM 对象，新维修人姓名须在 commit 前取出
            to_user = await db.get(User, uuid.UUID(str(v.get("uid", ""))))
            assignee_label = to_user.name if to_user else "新维修人"
            await db.commit()
        except AppException as exc:
            return await _fail(exc.message)
        except Exception:
            logger.exception("卡片转派失败: %s", wo_no)
            return await _fail("转派失败，请稍后在平台「维修工单」中操作")
    return _card_ok_payload(f"已转派给 {assignee_label}")


async def _handle_parts_action(
    payload: dict[str, Any], *, open_id: str, union_id: str
) -> dict[str, Any]:
    """申请备件（方案E）：parts_list=备件选择卡，parts_pick=领用或生成采购建议。"""
    from sqlalchemy import select as _select

    from app.modules.equipment.models.spare_part import SparePart, SparePartStock

    value = payload.get("action") or {}
    v = value.get("value") or {}
    act = v.get("act", "")
    wo_no = v.get("oid", "")

    async def _fail(message: str) -> dict[str, Any]:
        if open_id:
            try:
                await send_user_card(
                    open_id=open_id,
                    title="❌ 备件操作未完成",
                    receive_id_type="open_id",
                    content=message,
                )
            except Exception:
                logger.exception("备件操作失败提示发送失败")
        return _card_error_payload(message)

    async with async_session_factory() as db:
        user = await _find_user_by_feishu(db, open_id=open_id, union_id=union_id)
        if user is None:
            return await _fail("未绑定平台账号，请先用飞书登录一次平台后重试")
        wo = await repo.get_work_order_by_no(db, wo_no)
        if wo is None:
            return await _fail(f"工单 {wo_no} 不存在")
        if wo.status not in ("待处理", "执行中", "待验收"):
            return await _fail(f"工单「{wo.status}」状态不可领料")

        workshop = wo.equipment.workshop_code if wo.equipment else ""

        if act == "parts_list":
            rows = (
                (
                    await db.execute(
                        _select(SparePart, SparePartStock)
                        .outerjoin(
                            SparePartStock,
                            SparePartStock.spare_part_id == SparePart.id,
                        )
                        .where(
                            SparePart.is_deleted == False,  # noqa: E712
                            SparePart.is_active == True,  # noqa: E712
                            SparePart.workshop_code == (workshop or ""),
                        )
                        .order_by(SparePart.name)
                        .limit(10)
                    )
                )
                .all()
            )
            parts = [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "current_qty": s.current_qty if s else 0,
                }
                for p, s in rows
            ]
            if not parts:
                return await _fail("该车间暂无登记备件，请到平台备件管理中维护")
            equipment_label = (
                f"{wo.equipment.name}（{wo.equipment.equipment_no}）"
                if wo.equipment
                else ""
            )
            from app.modules.equipment.feishu.plan_e_cards import (
                build_parts_select_card,
            )

            card = build_parts_select_card(
                work_order_no=wo_no,
                equipment_label=equipment_label,
                parts=parts,
            )
            await send_user_card(
                open_id=open_id,
                title=f"🔧 申请备件 {wo_no}",
                receive_id_type="open_id",
                content="请选择备件：",
                elements=card["elements"],
            )
            return _card_ok_payload("已发送备件选择卡片")

        return await _parts_pick(db, wo, v, part_name=str(v.get("nm", "")))


async def _parts_pick(
    db: AsyncSession,
    wo: Any,
    v: dict[str, Any],
    *,
    part_name: str,
) -> dict[str, Any]:
    """点选备件：库存≥1 领用 1 件；不足则生成/复用采购建议。"""
    from sqlalchemy import select as _select

    from app.core.exceptions import AppException
    from app.modules.equipment.models.purchase_suggestion import (
        SparePartPurchaseSuggestion,
    )
    from app.modules.equipment.models.spare_part import SparePartStock
    from app.modules.equipment.service.work_order import consume_materials

    try:
        part_uuid = uuid.UUID(str(v.get("sp", "")))
    except ValueError:
        return _card_error_payload("备件信息无效")

    stock = (
        (
            await db.execute(
                _select(SparePartStock).where(
                    SparePartStock.spare_part_id == part_uuid
                )
            )
        )
        .scalars()
        .first()
    )
    current = stock.current_qty if stock else 0
    if current >= 1:
        try:
            await consume_materials(
                db, wo.id, [{"spare_part_id": part_uuid, "quantity": 1}]
            )
            await db.commit()
            return _card_ok_payload(
                f"已领用 {part_name} ×1（剩余 {current - 1}），费用计入工单"
            )
        except AppException as exc:
            await db.rollback()
            return _card_error_payload(exc.message)
        except Exception:
            await db.rollback()
            logger.exception("卡片领料失败: %s", wo.work_order_no)
            return _card_error_payload("领料失败，请到平台工单详情中领料")

    existing = (
        (
            await db.execute(
                _select(SparePartPurchaseSuggestion).where(
                    SparePartPurchaseSuggestion.spare_part_id == part_uuid,
                    SparePartPurchaseSuggestion.status.in_(
                        ("suggested", "submitted", "partial")
                    ),
                    SparePartPurchaseSuggestion.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(
            SparePartPurchaseSuggestion(
                spare_part_id=part_uuid,
                current_qty=current,
                safety_qty=max(1, current + 1),
                suggest_qty=2,
                status="suggested",
                source="work_order",
                source_work_order_id=wo.id,
            )
        )
        await db.commit()
        return _card_ok_payload(
            f"{part_name} 库存不足（{current}），已生成采购建议待管理员提交采购"
        )
    status_label = existing.status
    await db.rollback()
    # 回滚会过期 ORM 属性，状态须在 rollback 前取出
    return _card_ok_payload(
        f"{part_name} 库存不足，已有进行中的采购建议（{status_label}）"
    )


async def _handle_repay_action(
    payload: dict[str, Any], *, open_id: str, union_id: str
) -> dict[str, Any]:
    """再报上次确认卡回调（方案E）：repay_confirm=建单，repay_cancel=取消。"""
    from app.core.exceptions import AppException

    value = payload.get("action") or {}
    v = value.get("value") or {}
    act = v.get("act", "")

    if act == "repay_cancel":
        return _card_ok_payload("已取消；可发文字「报修 …」随时报修")

    async def _fail(message: str) -> dict[str, Any]:
        if open_id:
            try:
                await send_user_card(
                    open_id=open_id,
                    title="❌ 再报未完成",
                    receive_id_type="open_id",
                    content=message,
                )
            except Exception:
                logger.exception("再报失败提示发送失败")
        return _card_error_payload(message)

    async with async_session_factory() as db:
        user = await _find_user_by_feishu(db, open_id=open_id, union_id=union_id)
        if user is None:
            return await _fail("未绑定平台账号，请先用飞书登录一次平台后重试")
        try:
            eq_id = uuid.UUID(str(v.get("eq", "")))
        except ValueError:
            return await _fail("设备信息无效，请重新发起")
        fault = str(v.get("ft", "")).strip() or "设备故障"
        from app.modules.equipment.schemas import WorkOrderCreate
        from app.modules.equipment.service.work_order import create_work_order

        try:
            wo = await create_work_order(
                db,
                WorkOrderCreate(
                    equipment_id=eq_id,
                    order_type="故障维修",
                    priority="高",
                    fault_description=f"[再报] {fault}",
                ),
                reporter_id=user.id,
            )
            await db.commit()
        except AppException as exc:
            await db.rollback()
            return await _fail(exc.message)
        except Exception:
            await db.rollback()
            logger.exception("再报建单失败")
            return await _fail("建单失败，请用文字「报修 …」重试")

    workshop_code = str(v.get("ws", ""))
    equipment_label = str(v.get("el", "")) or "设备"
    try:
        await dispatch_repair_card(
            work_order_no=wo.work_order_no,
            equipment_label=equipment_label,
            workshop_name=workshop_code or "未知车间",
            fault=f"[再报] {fault}",
            priority="高",
            reporter_name=user.name,
            workshop_code=workshop_code,
        )
    except Exception:
        logger.exception("再报派单群通知失败（工单已创建）")
    return _card_ok_payload(f"已建单 {wo.work_order_no} 并派发维修群")


async def send_repay_confirm_card(
    *, user_id: str, open_id: str, union_id: str
) -> None:
    """「再报上次那台」（方案E）：查该用户最近报修 → 回预填确认卡。"""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select as _select

    from app.modules.equipment.feishu.plan_e_cards import (
        build_repay_confirm_card,
    )
    from app.modules.equipment.models import Equipment, WorkOrder

    async def _reply_fail(msg: str) -> None:
        await send_user_card(
            open_id=open_id,
            title="🔁 再报上次",
            receive_id_type="open_id",
            content=msg,
        )

    try:
        async with async_session_factory() as db:
            user = await _find_user_by_feishu(
                db, open_id=open_id, union_id=union_id
            )
            if user is None:
                await _reply_fail(
                    "未绑定平台账号，请先用飞书登录一次平台后重试；"
                    "或直接发文字「报修 车间 设备 故障」。"
                )
                return
            since = datetime.now(UTC) - timedelta(days=30)
            row = (
                (
                    await db.execute(
                        _select(WorkOrder, Equipment)
                        .join(Equipment, Equipment.id == WorkOrder.equipment_id)
                        .where(
                            WorkOrder.reporter_id == user.id,
                            WorkOrder.reported_at >= since,
                            WorkOrder.is_deleted == False,  # noqa: E712
                        )
                        .order_by(WorkOrder.reported_at.desc())
                        .limit(1)
                    )
                )
                .first()
            )
            if row is None:
                await _reply_fail(
                    "近 30 天没有你的报修记录。\\n\\n"
                    "发文字报修：`报修 201一车间 离心泵 密封漏了 紧急`"
                )
                return
            wo, eq = row
            equipment_label = f"{eq.name}（{eq.equipment_no}）"
            card = build_repay_confirm_card(
                equipment_label=equipment_label,
                equipment_id=str(eq.id),
                workshop_code=eq.workshop_code or "",
                last_fault=wo.fault_description or "",
                work_order_no=wo.work_order_no,
            )
            # 把设备标签塞进按钮 value 供建单后派卡展示
            for el in card["elements"]:
                if el.get("tag") == "action":
                    for btn in el["actions"]:
                        if btn["value"].get("act") == "repay_confirm":
                            btn["value"]["el"] = equipment_label
            await send_user_card(
                open_id=open_id,
                title="🔁 再报上次那台",
                receive_id_type="open_id",
                content="请确认：",
                elements=card["elements"],
            )
    except Exception:
        logger.exception("再报确认卡发送失败: %s", open_id)
        await _reply_fail("查询上次报修失败，请直接发文字「报修 …」。")
