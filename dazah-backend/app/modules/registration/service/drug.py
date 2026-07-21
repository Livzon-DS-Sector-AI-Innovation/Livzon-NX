"""Drug service: business logic."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.registration import repository as repo
from app.modules.registration.models.drug import Drug
from app.modules.registration.schemas.drug import DrugCreate, DrugUpdate


async def create_drug(db: AsyncSession, data: DrugCreate) -> Drug:
    """创建药品"""
    return await repo.create_drug(db, data.model_dump())


async def get_drugs(db: AsyncSession) -> list[Drug]:
    """获取所有药品"""
    return await repo.get_drugs(db)


async def get_drug(db: AsyncSession, drug_id: uuid.UUID) -> Drug:
    """获取单个药品"""
    drug = await repo.get_drug_by_id(db, drug_id)
    if not drug:
        raise NotFoundException("药品", str(drug_id))
    return drug


async def update_drug(
    db: AsyncSession,
    drug_id: uuid.UUID,
    data: DrugUpdate,
) -> Drug:
    """更新药品"""
    # 检查药品是否存在
    drug = await get_drug(db, drug_id)

    # 更新药品基本信息
    update_data = data.model_dump(exclude_unset=True, exclude={"nodes"})
    if update_data:
        await repo.update_drug(db, drug_id, update_data)

    # 更新节点信息
    if data.nodes:
        for node_update in data.nodes:
            existing_nodes = await repo.get_drug_nodes(db, drug_id)
            existing = any(
                n.node_index == node_update.node_index for n in existing_nodes
            )
            if existing:
                await repo.update_drug_node(
                    db,
                    drug_id,
                    node_update.node_index,
                    node_update.model_dump(exclude_unset=True),
                )
            else:
                await repo.create_drug_node(
                    db,
                    {
                        "drug_id": drug_id,
                        "node_index": node_update.node_index,
                        "actual_date": node_update.actual_date,
                    },
                )

    # 返回更新后的药品
    return await get_drug(db, drug_id)


async def delete_drug(db: AsyncSession, drug_id: uuid.UUID) -> None:
    """删除药品"""
    await get_drug(db, drug_id)  # 确保存在
    await repo.delete_drug(db, drug_id)
