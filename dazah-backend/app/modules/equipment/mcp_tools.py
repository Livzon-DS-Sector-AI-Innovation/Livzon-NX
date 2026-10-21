"""Equipment 模块暴露给 AI Agent 的 MCP Tools。

工具函数通过 @mcp.tool() 装饰器注册到全局 FastMCP 实例。
每个 tool 的 docstring 即为 Agent 可读的中文使用说明。

设计原则：
- tool 函数只做参数校验和 user 解析，业务逻辑通过 service 层完成
- 所有写操作必须提供 operator_id，声明替谁操作
- 不直接操作 ORM model 或 repository
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.repository.work_order import get_user_work_orders
from app.modules.equipment.service import (
    complete_work_order,
    get_work_order_by_id,
    start_work_order,
)
from app.platform.identity.models import User
from app.platform.identity.repository import UserRepository
from app.platform.mcp.deps import get_db
from app.platform.mcp.server import mcp


async def resolve_user(db: AsyncSession, operator_id: str) -> User:
    """将 operator_id 解析为 User 对象。"""
    try:
        uid = uuid.UUID(operator_id)
        user = await db.get(User, uid)
        if user and not user.is_deleted:
            return user
    except ValueError:
        pass

    repo = UserRepository()
    user = await repo.get_by_feishu_user_id(db, operator_id)
    if user:
        return user

    users, total = await repo.list_all(db, keyword=operator_id, limit=10)
    if total == 1:
        return users[0]
    if total > 1:
        raise ValueError(f"找到多个匹配用户（{total}人），请提供更精确的 user_id")

    raise ValueError(f"未找到用户：{operator_id}")


def _wo_to_dict(wo: Any) -> dict[str, Any]:
    """WorkOrder ORM → 字典"""
    return {
        "id": str(wo.id),
        "work_order_no": wo.work_order_no,
        "order_type": wo.order_type,
        "status": wo.status,
        "priority": wo.priority,
        "equipment_name": wo.equipment.name if wo.equipment else "",
        "fault_description": wo.fault_description or "",
        "assignee_name": wo.assignee.name if wo.assignee else "",
        "reporter_name": wo.reporter.name if wo.reporter else "",
        "created_at": wo.created_at.isoformat() if wo.created_at else "",
        "started_at": wo.started_at.isoformat() if wo.started_at else "",
    }



# ─────────────────────────────────────────────────────────────
# Tool 1: 查询用户身份
# ─────────────────────────────────────────────────────────────


@mcp.tool()
async def query_user(keyword: str) -> list[dict[str, Any]]:
    """
    根据姓名或工号模糊查询系统用户信息。
    适用于 Agent 在替用户操作前，需要先确认用户身份和 user_id 的场景。
    返回匹配的用户列表，包含 id、姓名、部门、职位、工号等信息。

    Args:
        keyword: 用户姓名（支持模糊匹配）或工号
    """
    db = get_db()
    repo = UserRepository()
    users, _total = await repo.list_all(db, keyword=keyword, limit=20)

    return [
        {
            "id": str(u.id),
            "name": u.name,
            "employee_no": u.employee_no or "",
            "department": u.department or "",
            "position": u.position or "",
            "email": u.email or "",
            "mobile": u.mobile or "",
            "feishu_user_id": u.feishu_user_id or "",
        }
        for u in users
    ]


# ─────────────────────────────────────────────────────────────
# Tool 2: 查询用户维护工单
# ─────────────────────────────────────────────────────────────


@mcp.tool()
async def list_work_orders(
    operator_id: str,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询指定用户的维护工单列表。
    适用的业务场景：设备部人员想知道自己当前有哪些工单需要处理，
    Agent 替其查看工单列表，可按工单状态过滤。

    Args:
        operator_id: 实际操作人的 user_id 或姓名（替谁查）
        status: 工单状态过滤，可选值：待处理 / 执行中 / 待验收 / 已完成 / 已关闭。
                 不传则返回所有未关闭的工单。
    """
    db = get_db()
    user = await resolve_user(db, operator_id)

    work_orders = await get_user_work_orders(db, user.id)

    if status:
        valid_statuses = {"待处理", "执行中", "待验收", "已完成", "已关闭"}
        if status not in valid_statuses:
            raise ValueError(
                f"无效的工单状态 '{status}'，可选值：{' / '.join(valid_statuses)}"
            )
        work_orders = [wo for wo in work_orders if wo.status == status]

    return [_wo_to_dict(wo) for wo in work_orders]


# ─────────────────────────────────────────────────────────────
# Tool 3: 开始/完成工单
# ─────────────────────────────────────────────────────────────


@mcp.tool()
async def operate_work_order(
    work_order_id: str,
    action: str,
    operator_id: str,
    repair_detail: str | None = None,
) -> dict[str, Any]:
    """
    对维护工单执行状态流转操作：开始维修 或 完成维修。

    Args:
        work_order_id: 工单编号（如 WO-20260616-0001）或工单 UUID
        action: 操作类型，可选值 start / complete
        operator_id: 实际操作人的 user_id 或姓名
        repair_detail: 维修过程描述，action=complete 时必需
    """
    db = get_db()
    await resolve_user(db, operator_id)

    if action not in ("start", "complete"):
        raise ValueError(f"无效的操作类型 '{action}'，可选值：start / complete")

    wo_uuid = uuid.UUID(work_order_id)
    wo = await get_work_order_by_id(db, wo_uuid)

    if action == "start":
        result = await start_work_order(db, wo.id)
        return {
            "success": True,
            "work_order_no": result.work_order_no,
            "old_status": "待处理",
            "new_status": result.status,
        }

    if not repair_detail or not repair_detail.strip():
        raise ValueError("完成工单时需要提供 repair_detail")

    from app.modules.equipment.schemas.work_order import WorkOrderComplete

    data = WorkOrderComplete(repair_detail=repair_detail.strip())
    result = await complete_work_order(db, wo.id, data)
    return {
        "success": True,
        "work_order_no": result.work_order_no,
        "old_status": "执行中",
        "new_status": result.status,
    }
