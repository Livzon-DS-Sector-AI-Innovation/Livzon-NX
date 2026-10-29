"""设备车间注册表服务。

车间清单数据源：统一工作台车间块、各功能视图车间切换与飞书配置页
清单均读取启用车间。新增/改名/启停在「车间管理」页操作；代码创建后
不可改（业务数据按 workshop_code 关联），删除一律走停用保留数据。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models.workshop import EquipmentWorkshop
from app.modules.equipment.schemas.workshop import (
    WorkshopAdminSummary,
    WorkshopCreateRequest,
    WorkshopSummary,
    WorkshopUpdateRequest,
)

_ORDER = (EquipmentWorkshop.code, EquipmentWorkshop.id)


async def _get_row(db: AsyncSession, code: str) -> EquipmentWorkshop | None:
    result = await db.execute(
        select(EquipmentWorkshop).where(
            EquipmentWorkshop.code == code,
            EquipmentWorkshop.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalars().first()


async def list_enabled(db: AsyncSession) -> list[WorkshopSummary]:
    """启用车间清单（按代码排序），工作台与飞书配置页数据源。"""
    rows = (
        await db.execute(
            select(EquipmentWorkshop)
            .where(
                EquipmentWorkshop.is_deleted == False,  # noqa: E712
                EquipmentWorkshop.is_enabled == True,  # noqa: E712
            )
            .order_by(*_ORDER)
        )
    ).scalars().all()
    return [
        WorkshopSummary(code=row.code, name=row.name, is_enabled=True)
        for row in rows
    ]


async def list_all(db: AsyncSession) -> list[WorkshopAdminSummary]:
    """全部车间清单（含停用），车间管理页数据源。"""
    rows = (
        await db.execute(
            select(EquipmentWorkshop)
            .where(EquipmentWorkshop.is_deleted == False)  # noqa: E712
            .order_by(EquipmentWorkshop.is_enabled.desc(), *_ORDER)
        )
    ).scalars().all()
    return [
        WorkshopAdminSummary(
            code=row.code,
            name=row.name,
            is_enabled=row.is_enabled,
            feishu_chat_id=row.feishu_chat_id,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def create_workshop(
    db: AsyncSession, data: WorkshopCreateRequest
) -> WorkshopAdminSummary:
    code = data.code.strip()
    name = data.name.strip()
    if not name:
        raise AppException(message="车间名称不能为空")
    existing = await _get_row(db, code)
    if existing is not None:
        raise AppException(
            message=f"车间代码 {code} 已存在（{existing.name}），请换一个代码"
        )
    row = EquipmentWorkshop(
        code=code,
        name=name,
        is_enabled=True,
        feishu_chat_id=(data.feishu_chat_id or "").strip() or None,
    )
    db.add(row)
    await db.commit()
    return WorkshopAdminSummary(
        code=row.code,
        name=row.name,
        is_enabled=row.is_enabled,
        feishu_chat_id=row.feishu_chat_id,
        created_at=row.created_at,
    )


async def update_workshop(
    db: AsyncSession, code: str, data: WorkshopUpdateRequest
) -> WorkshopAdminSummary:
    row = await _get_row(db, code)
    if row is None:
        raise AppException(message=f"车间 {code} 不存在", status_code=404)
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise AppException(message="车间名称不能为空")
        row.name = name
    if data.is_enabled is not None:
        row.is_enabled = data.is_enabled
    if data.feishu_chat_id is not None:
        row.feishu_chat_id = data.feishu_chat_id.strip() or None
    await db.commit()
    return WorkshopAdminSummary(
        code=row.code,
        name=row.name,
        is_enabled=row.is_enabled,
        feishu_chat_id=row.feishu_chat_id,
        created_at=row.created_at,
    )
