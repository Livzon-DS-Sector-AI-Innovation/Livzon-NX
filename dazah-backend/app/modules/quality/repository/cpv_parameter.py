"""CPV Parameter database queries."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.cpv_parameter import CpvParameter


async def create_parameter(db: AsyncSession, data: dict[str, Any]) -> CpvParameter:
    """创建参数"""
    parameter = CpvParameter(**data)
    db.add(parameter)
    await db.flush()
    return parameter


async def get_parameter_by_id(
    db: AsyncSession, parameter_id: uuid.UUID
) -> CpvParameter | None:
    """根据ID获取参数"""
    result = await db.execute(
        select(CpvParameter).where(
            CpvParameter.id == parameter_id,
            CpvParameter.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_parameters(
    db: AsyncSession,
    product_id: uuid.UUID,
    parameter_type: str | None = None,
    is_enabled: bool | None = None,
) -> list[CpvParameter]:
    """获取参数列表"""
    query = select(CpvParameter).where(
        CpvParameter.product_id == product_id,
        CpvParameter.is_deleted == False,  # noqa: E712
    )

    if parameter_type:
        query = query.where(CpvParameter.parameter_type == parameter_type)
    if is_enabled is not None:
        query = query.where(CpvParameter.is_enabled == is_enabled)

    query = query.order_by(CpvParameter.sort_order, CpvParameter.created_at)

    result = await db.execute(query)
    return list(result.scalars().all())


async def update_parameter(
    db: AsyncSession,
    parameter_id: uuid.UUID,
    data: dict[str, Any],
) -> CpvParameter | None:
    """更新参数"""
    parameter = await get_parameter_by_id(db, parameter_id)
    if not parameter:
        return None

    for key, value in data.items():
        setattr(parameter, key, value)

    await db.flush()
    await db.flush()
    return parameter


async def delete_parameter(db: AsyncSession, parameter_id: uuid.UUID) -> bool:
    """删除参数（软删除）"""
    parameter = await get_parameter_by_id(db, parameter_id)
    if not parameter:
        return False

    parameter.is_deleted = True
    await db.flush()
    return True


async def count_parameters(
    db: AsyncSession,
    product_id: uuid.UUID,
    parameter_type: str | None = None,
) -> int:
    """统计参数数量"""
    from sqlalchemy import func

    query = (
        select(func.count())
        .select_from(CpvParameter)
        .where(
            CpvParameter.product_id == product_id,
            CpvParameter.is_deleted == False,  # noqa: E712
        )
    )

    if parameter_type:
        query = query.where(CpvParameter.parameter_type == parameter_type)

    result = await db.execute(query)
    return result.scalar_one()
