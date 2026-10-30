"""Work order service: state machine, business logic."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.equipment import repository as repo
from app.modules.equipment.models import WorkOrder
from app.modules.equipment.schemas import (
    WorkOrderComplete,
    WorkOrderCreate,
    WorkOrderUpdate,
    WorkOrderVerify,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3

_VALID_TRANSITIONS: dict[str, list[str]] = {
    "待处理": ["执行中", "已关闭"],
    "执行中": ["待验收", "已完成", "已关闭"],
    "待验收": ["已完成", "执行中", "已关闭"],
    "已完成": ["已关闭"],
    "已关闭": [],
}


async def generate_work_order_no(db: AsyncSession) -> str:
    """生成工单号：WO-{yyyyMMdd}-{seq:04d}"""
    max_no = await repo.get_max_work_order_no(db)
    today = datetime.now().strftime("%Y%m%d")
    if max_no:
        seq_str = max_no.split("-")[-1]
        seq = int(seq_str) + 1
    else:
        seq = 1
    return f"WO-{today}-{seq:04d}"


def _validate_transition(current: str, target: str) -> None:
    """校验状态转换是否合法"""
    allowed = _VALID_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise AppException(message=f"状态不允许从 '{current}' 转换到 '{target}'")


async def _get_work_order(db: AsyncSession, work_order_id: uuid.UUID) -> WorkOrder:
    """获取工单，不存在则抛异常"""
    wo = await repo.get_work_order_by_id(db, work_order_id)
    if not wo:
        raise NotFoundException("工单", str(work_order_id))
    return wo


async def _update_equipment_status(
    db: AsyncSession,
    equipment_id: uuid.UUID,
    status: str,
) -> None:
    """直接更新设备状态（模块内使用）"""
    equipment = await repo.get_equipment_by_id(db, equipment_id)
    if equipment:
        equipment.status = status
        await db.flush()


async def auto_finish_pending_verify(
    db: AsyncSession, prior: WorkOrder, *, reason: str
) -> None:
    """待验收工单自动结单：系统管理员验收合格并关闭，恢复设备状态。

    用于两类场景：重复报修时解锁设备、完成超时无人验收兜底。
    验收人记系统管理员，备注写明自动原因，保留完整轨迹。
    """
    from app.platform.identity.service import get_or_create_system_admin

    admin = await get_or_create_system_admin(db)
    await verify_work_order(
        db,
        prior.id,
        admin.id,
        WorkOrderVerify(result="合格", remark=reason),
    )
    await close_work_order(db, prior.id)
    logger.info("待验收工单自动结单: %s（%s）", prior.work_order_no, reason)


async def create_work_order(
    db: AsyncSession,
    data: WorkOrderCreate,
    reporter_id: uuid.UUID,
) -> WorkOrder:
    """创建维修工单"""
    equipment = await repo.get_equipment_by_id(db, data.equipment_id)
    if not equipment:
        raise NotFoundException("设备", str(data.equipment_id))

    # 校验设备状态。「维修中」且旧单已提交完成待验收 → 自动结旧单解锁：
    # 刚修好又坏、旧单无人验收的重复故障场景，师傅无需找人验收即可再报修
    if equipment.status not in ("在用", "备用"):
        hold: WorkOrder | None = None
        if equipment.status == "维修中":
            hold = (
                (
                    await db.execute(
                        select(WorkOrder)
                        .where(
                            WorkOrder.equipment_id == data.equipment_id,
                            WorkOrder.status.in_(
                                ["待处理", "执行中", "待验收"]
                            ),
                            WorkOrder.is_deleted == False,  # noqa: E712
                        )
                        .order_by(WorkOrder.created_at.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
        if hold is not None and hold.status == "待验收":
            await auto_finish_pending_verify(
                db, hold, reason="重复报修自动验收"
            )
            # 重复故障标注：第 N 次报修 + 关联前单，供报表与追溯
            prior_count = (

                    await db.execute(
                        select(func.count())
                        .select_from(WorkOrder)
                        .where(
                            WorkOrder.equipment_id == data.equipment_id,
                            WorkOrder.is_deleted == False,  # noqa: E712
                        )
                    )

            ).scalar() or 0
            prefix = f"[第{prior_count + 1}次报修·前单{hold.work_order_no}] "
            data = data.model_copy(
                update={
                    "fault_description": prefix + (data.fault_description or "")
                }
            )
        elif hold is not None:
            raise AppException(
                message=(
                    f"设备维修中（工单 {hold.work_order_no} 尚未完成），"
                    "不能重复报修"
                )
            )
        else:
            raise AppException(
                message=f"设备当前状态为 '{equipment.status}'，不能创建工单"
            )

    original_status = equipment.status

    for attempt in range(_MAX_RETRIES):
        wo_no = await generate_work_order_no(db)

        wo_data = data.model_dump()
        wo_data["work_order_no"] = wo_no
        wo_data["reporter_id"] = reporter_id
        wo_data["status"] = "待处理"
        wo_data["original_equipment_status"] = original_status

        try:
            work_order = await repo.create_work_order(db, wo_data)
            # 非"异常处理"类型的工单才自动改设备状态为维修中
            if data.order_type != "异常处理":
                await _update_equipment_status(db, data.equipment_id, "维修中")
            # eager re-fetch，避免返回对象触发懒加载 MissingGreenlet
            saved_work_order = await repo.get_work_order_by_id(db, work_order.id)
            if saved_work_order is None:
                raise AppException(message="工单创建后读取失败")
            return saved_work_order
        except IntegrityError:
            if attempt < _MAX_RETRIES - 1:
                await db.rollback()
                continue
            raise AppException(message="工单号生成失败，请重试")

    raise AppException(message="工单号生成失败，请重试")


async def update_work_order(
    db: AsyncSession,
    work_order_id: uuid.UUID,
    data: WorkOrderUpdate,
) -> WorkOrder:
    """更新工单信息"""
    wo = await _get_work_order(db, work_order_id)

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise AppException(message="没有需要更新的字段")

    for field, value in update_data.items():
        setattr(wo, field, value)

    await db.flush()
    await db.refresh(wo)
    # 飞书台账镜像（延迟后台任务，失败不影响主流程）
    from app.modules.equipment.feishu.repair_ledger import schedule_ledger_sync

    schedule_ledger_sync(wo.work_order_no)

    return wo


async def assign_work_order(
    db: AsyncSession,
    work_order_id: uuid.UUID,
    assignee_id: uuid.UUID,
) -> WorkOrder:
    """指派维修人（不改变工单状态，仅记录指派人）"""
    wo = await _get_work_order(db, work_order_id)

    wo.assignee_id = assignee_id
    wo.assigned_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(wo)
    # 飞书台账镜像（延迟后台任务，失败不影响主流程）
    from app.modules.equipment.feishu.repair_ledger import schedule_ledger_sync

    schedule_ledger_sync(wo.work_order_no)

    return wo


async def start_work_order(
    db: AsyncSession,
    work_order_id: uuid.UUID,
) -> WorkOrder:
    """开始执行"""
    wo = await _get_work_order(db, work_order_id)
    _validate_transition(wo.status, "执行中")

    wo.status = "执行中"
    wo.started_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(wo)
    # 飞书台账镜像（延迟后台任务，失败不影响主流程）
    from app.modules.equipment.feishu.repair_ledger import schedule_ledger_sync

    schedule_ledger_sync(wo.work_order_no)

    return wo


async def complete_work_order(
    db: AsyncSession,
    work_order_id: uuid.UUID,
    data: WorkOrderComplete,
) -> WorkOrder:
    """提交完成"""
    wo = await _get_work_order(db, work_order_id)

    is_repair = wo.order_type in ("故障维修", "校准", "异常处理")
    target = "待验收" if is_repair else "已完成"
    _validate_transition(wo.status, target)

    now = datetime.now(UTC)
    wo.status = target
    wo.completed_at = now
    wo.repair_detail = data.repair_detail

    # 计算耗时
    if wo.started_at:
        delta = now - wo.started_at
        wo.actual_duration = int(delta.total_seconds() / 60)

    await db.flush()

    # 计划维护工单完成时，联动更新维护计划日期
    if wo.order_type == "计划维护" and wo.maintenance_plan_id:
        await _update_maintenance_plan_on_completion(db, wo.maintenance_plan_id)

    # 待验收时，飞书通知责任人确认验收
    if target == "待验收":
        responsible = wo.responsible_person
        equipment = wo.equipment
        feishu_uid = (
            getattr(responsible, "feishu_union_id", None) if responsible else None
        )
        if feishu_uid:
            asyncio.ensure_future(
                _notify_verification(
                    feishu_union_id=feishu_uid,
                    work_order_no=wo.work_order_no,
                    equipment_name=equipment.name if equipment else "",
                    assignee_name=wo.assignee.name if wo.assignee else "",
                    priority=wo.priority,
                )
            )

    saved_work_order = await repo.get_work_order_by_id(db, wo.id)
    if saved_work_order is None:
        raise AppException(message="工单更新后读取失败")
    return saved_work_order


async def _update_maintenance_plan_on_completion(
    db: AsyncSession,
    maintenance_plan_id: uuid.UUID,
) -> None:
    """计划维护工单完成时，自动推进维护计划的日期。"""
    from datetime import date as date_type

    from app.modules.equipment.service.maintenance_plan import (
        _calculate_next_maintenance_date,
    )

    plan = await repo.get_maintenance_plan_by_id(db, maintenance_plan_id)
    if not plan:
        return

    today = date_type.today()
    plan.last_maintenance_date = today
    plan.next_maintenance_date = _calculate_next_maintenance_date(
        today, plan.frequency, plan.frequency_unit
    )
    # last_generated_date 保持旧值，让 scheduler 下个周期自然触发
    await db.flush()


async def _notify_rework(
    *,
    feishu_union_id: str,
    work_order_no: str,
    equipment_name: str,
    remark: str,
) -> None:
    """工单验收不合格被打回时，飞书通知维修人返修。非关键路径。"""
    try:
        from app.modules.equipment.feishu.notification import send_user_card

        lines = [
            f"**工单编号：**{work_order_no}",
            f"**关联设备：**{equipment_name or '-'}",
        ]
        if remark:
            lines.append(f"**验收备注：**{remark}")
        lines.extend(
            [
                "",
                "工单已退回「执行中」。返修完成后任选一种方式提交：",
                "① 点下方按钮一键提交",
                f"② 回复我：`完成 {work_order_no} 更换情况`",
                "③ 平台「设备管理 → 维修」页提交",
            ]
        )
        elements = [
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "✅ 返修完成，提交验收",
                        },
                        "type": "primary",
                        "value": {"act": "complete", "oid": work_order_no},
                    }
                ],
            }
        ]
        ok = await send_user_card(
            open_id=feishu_union_id,
            title=f"⚠️ 验收不合格已打回 - {work_order_no}",
            content="\n".join(lines),
            elements=elements,
            receive_id_type="union_id",
        )
        if not ok:
            logger.warning(
                "打回重修通知发送失败: %s -> %s", work_order_no, feishu_union_id
            )
    except Exception:
        logger.exception("打回重修通知异常: %s", work_order_no)


async def _notify_verification(
    feishu_union_id: str,
    work_order_no: str,
    equipment_name: str,
    assignee_name: str,
    priority: str,
) -> None:
    """工单进入待验收时，飞书通知责任人确认验收。

    非关键路径：发送失败只记日志，不影响主流程。
    """
    try:
        from app.modules.equipment.feishu.notification import send_user_card

        title = f"🔔 工单待验收 - {work_order_no}"
        lines = [
            f"**工单编号：**{work_order_no}",
            f"**关联设备：**{equipment_name}",
            f"**优先级：**{priority}",
        ]
        if assignee_name:
            lines.append(f"**维修人员：**{assignee_name}")
        lines.extend(
            [
                "",
                "维修已完成，请及时确认验收。",
            ]
        )
        content = "\n".join(lines)

        ok = await send_user_card(
            open_id=feishu_union_id,
            title=title,
            content=content,
            receive_id_type="union_id",
        )
        if ok:
            logger.info(
                "验收通知已发送: %s -> %s",
                work_order_no,
                feishu_union_id,
            )
        else:
            logger.warning(
                "验收通知发送失败: %s -> %s",
                work_order_no,
                feishu_union_id,
            )
    except Exception:
        logger.exception(
            "验收通知异常: %s -> %s",
            work_order_no,
            feishu_union_id,
        )


async def verify_work_order(
    db: AsyncSession,
    work_order_id: uuid.UUID,
    verifier_id: uuid.UUID,
    data: WorkOrderVerify,
) -> WorkOrder:
    """验收工单"""
    wo = await _get_work_order(db, work_order_id)
    if wo.order_type not in ("故障维修", "校准", "异常处理"):
        raise AppException(message=f"工单类型 '{wo.order_type}' 不支持验收")

    wo.verified_by = verifier_id
    wo.verified_at = datetime.now(UTC)
    wo.verification_result = data.result
    wo.verification_remark = data.remark

    if data.result == "合格":
        _validate_transition(wo.status, "已完成")
        wo.status = "已完成"
    else:
        # 打回重修
        _validate_transition(wo.status, "执行中")
        wo.status = "执行中"
        wo.started_at = None
        wo.completed_at = None
        wo.actual_duration = None
        # 飞书通知维修人返修（非关键路径，失败只记日志）
        assignee = wo.assignee
        feishu_uid = (
            getattr(assignee, "feishu_union_id", None) if assignee else None
        )
        if feishu_uid:
            asyncio.ensure_future(
                _notify_rework(
                    feishu_union_id=feishu_uid,
                    work_order_no=wo.work_order_no,
                    equipment_name=wo.equipment.name if wo.equipment else "",
                    remark=data.remark or "",
                )
            )

    await db.flush()
    await db.refresh(wo)
    # 飞书台账镜像（延迟后台任务，失败不影响主流程）
    from app.modules.equipment.feishu.repair_ledger import schedule_ledger_sync

    schedule_ledger_sync(wo.work_order_no)

    return wo


async def close_work_order(
    db: AsyncSession,
    work_order_id: uuid.UUID,
) -> WorkOrder:
    """关闭工单"""
    wo = await _get_work_order(db, work_order_id)
    _validate_transition(wo.status, "已关闭")

    wo.status = "已关闭"
    await db.flush()

    # 恢复设备到创建工单前的原始状态
    restore_status = wo.original_equipment_status or "在用"
    await _update_equipment_status(db, wo.equipment_id, restore_status)

    await db.refresh(wo)
    # 飞书台账镜像（延迟后台任务，失败不影响主流程）
    from app.modules.equipment.feishu.repair_ledger import schedule_ledger_sync

    schedule_ledger_sync(wo.work_order_no)

    return wo


async def delete_work_order(
    db: AsyncSession,
    work_order_id: uuid.UUID,
) -> WorkOrder:
    """删除工单（软删除）。

    开放状态（待处理/执行中/待验收）的工单把设备占用为「维修中」，
    删除时必须同步恢复设备到建单前的原始状态——否则设备会永久卡在
    「维修中」，无法再次报修。
    """
    wo = await _get_work_order(db, work_order_id)
    if wo.status in ("待处理", "执行中", "待验收"):
        restore_status = wo.original_equipment_status or "在用"
        await _update_equipment_status(db, wo.equipment_id, restore_status)

    wo.is_deleted = True
    await db.flush()
    return wo


async def get_work_orders(
    db: AsyncSession,
    status: str | None = None,
    equipment_id: uuid.UUID | None = None,
    priority: str | None = None,
    order_type: str | None = None,
    workshop_code: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[WorkOrder], int]:
    """获取工单列表（workshop_code 经所属设备派生，缺省跨车间）"""
    return await repo.get_work_orders(
        db,
        status=status,
        equipment_id=equipment_id,
        priority=priority,
        order_type=order_type,
        workshop_code=workshop_code,
        page=page,
        page_size=page_size,
    )


async def get_work_order_statistics(
    db: AsyncSession, workshop_code: str | None = None
) -> dict[str, object]:
    """获取工单统计"""
    return await repo.get_work_order_statistics(db, workshop_code)


async def get_work_order_by_id(
    db: AsyncSession,
    work_order_id: uuid.UUID,
) -> WorkOrder:
    """获取工单"""
    return await _get_work_order(db, work_order_id)


async def claim_work_order(
    db: AsyncSession,
    work_order_id: uuid.UUID,
    user_id: uuid.UUID,
) -> WorkOrder:
    """维修人员自主抢单（不改变工单状态，仅记录指派人）"""
    wo = await _get_work_order(db, work_order_id)

    if wo.status != "待处理":
        raise AppException(message="该工单已不可抢单")
    if wo.assignee_id is not None:
        raise AppException(message="该工单已被其他人接单")

    wo.assignee_id = user_id
    wo.assigned_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(wo)
    return wo


async def consume_materials(
    db: AsyncSession,
    work_order_id: uuid.UUID,
    items: list[dict[str, Any]],
) -> list[Any]:
    """工单领料"""
    wo = await _get_work_order(db, work_order_id)

    if wo.status in ("已完成", "已关闭"):
        raise AppException(message="工单已完成或已关闭，不能领料")

    from app.modules.equipment.service.spare_part import (
        get_spare_part_by_id,
        get_stock_by_spare_part_id,
        outbound_stock,
    )

    total_cost = 0.0
    transactions = []

    for item in items:
        spare_part = await get_spare_part_by_id(db, item["spare_part_id"])
        stock = await get_stock_by_spare_part_id(db, item["spare_part_id"])

        if not stock or stock.current_qty < item["quantity"]:
            raise AppException(message=f"备件 '{spare_part.name}' 库存不足")

        # 扣减库存
        await outbound_stock(db, item["spare_part_id"], item["quantity"])

        # 创建流水记录
        transaction = await repo.create_material_consumption(
            db,
            {
                "spare_part_id": item["spare_part_id"],
                "work_order_id": work_order_id,
                "transaction_type": "出库",
                "quantity": -item["quantity"],
                "remark": f"工单 {wo.work_order_no} 领料",
            },
        )
        transactions.append(transaction)

        # 累加费用
        if spare_part.unit_price:
            total_cost += spare_part.unit_price * item["quantity"]

    # 更新工单备件费用
    current_cost = wo.spare_parts_cost or 0.0
    wo.spare_parts_cost = current_cost + total_cost
    await db.flush()

    # 领料后检查安全线：事务内可读到刚扣减的库存值
    await _notify_low_stock(db, items)

    return transactions


async def _notify_low_stock(db: AsyncSession, items: list[dict[str, Any]]) -> None:
    """领料后检查库存：跌破安全线的备件向维修群发提醒卡片。

    群取全局默认维修群；单条提醒失败不影响领料主流程。
    """
    from app.modules.equipment.feishu.repair_card import send_card_to_chat
    from app.modules.equipment.service import spare_part as sp_service
    from app.modules.equipment.service.work_order_feishu import (
        resolve_repair_chat_id,
    )

    chat_id = ""
    for item in items:
        try:
            spare_part = await sp_service.get_spare_part_by_id(
                db, item["spare_part_id"]
            )
            stock = await sp_service.get_stock_by_spare_part_id(
                db, item["spare_part_id"]
            )
            if not stock or not spare_part:
                continue
            if stock.current_qty >= stock.safety_qty:
                continue
            if not chat_id:
                chat_id = await resolve_repair_chat_id("")
                if not chat_id:
                    return
            card = {
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": "red",
                    "title": {"tag": "plain_text", "content": "备件库存预警"},
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                f"备件 **{spare_part.name}** 库存 **{stock.current_qty:g}**，"
                                f"已低于安全线 **{stock.safety_qty}**，请及时补充"
                            ),
                        },
                    },
                ],
            }
            await send_card_to_chat(chat_id, card)
        except Exception:
            logger.exception(
                "库存安全线提醒发送失败: spare_part_id=%s", item["spare_part_id"]
            )
