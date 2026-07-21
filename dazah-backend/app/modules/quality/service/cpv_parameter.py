"""CPV Parameter service layer."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality import repository as repo
from app.modules.quality.models.cpv_parameter import CpvParameter
from app.modules.quality.schemas import CpvParameterCreate, CpvParameterUpdate


async def create_parameter(
    db: AsyncSession,
    product_id: uuid.UUID,
    data: CpvParameterCreate,
) -> CpvParameter:
    """创建参数"""
    param_data = data.model_dump()
    param_data["product_id"] = product_id
    return await repo.create_parameter(db, param_data)


async def get_parameter_by_id(
    db: AsyncSession,
    parameter_id: uuid.UUID,
) -> CpvParameter:
    """获取参数"""
    parameter = await repo.get_parameter_by_id(db, parameter_id)
    if not parameter:
        raise NotFoundException("参数", str(parameter_id))
    return parameter


async def get_parameters(
    db: AsyncSession,
    product_id: uuid.UUID,
    parameter_type: str | None = None,
    is_enabled: bool | None = None,
) -> list[CpvParameter]:
    """获取参数列表"""
    return await repo.get_parameters(db, product_id, parameter_type, is_enabled)


async def update_parameter(
    db: AsyncSession,
    parameter_id: uuid.UUID,
    data: CpvParameterUpdate,
) -> CpvParameter:
    """更新参数"""
    parameter = await repo.update_parameter(
        db, parameter_id, data.model_dump(exclude_unset=True)
    )
    if not parameter:
        raise NotFoundException("参数", str(parameter_id))
    return parameter


async def delete_parameter(
    db: AsyncSession,
    parameter_id: uuid.UUID,
) -> None:
    """删除参数"""
    success = await repo.delete_parameter(db, parameter_id)
    if not success:
        raise NotFoundException("参数", str(parameter_id))
