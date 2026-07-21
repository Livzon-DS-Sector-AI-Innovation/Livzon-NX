"""Drug database queries."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.registration.models.drug import Drug, DrugNode


async def create_drug(db: AsyncSession, data: dict[str, Any]) -> Drug:
    """创建药品"""
    drug = Drug(**data)
    db.add(drug)
    await db.flush()
    return drug


async def get_drugs(db: AsyncSession) -> list[Drug]:
    """获取所有药品（含节点）"""
    query = (
        select(Drug)
        .where(Drug.is_deleted == False)  # noqa: E712
        .options(selectinload(Drug.nodes.and_(DrugNode.is_deleted == False)))
        .order_by(Drug.created_at)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_drug_by_id(db: AsyncSession, drug_id: uuid.UUID) -> Drug | None:
    """根据ID获取药品"""
    query = (
        select(Drug)
        .where(Drug.id == drug_id, Drug.is_deleted == False)  # noqa: E712
        .options(selectinload(Drug.nodes.and_(DrugNode.is_deleted == False)))
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_drug(
    db: AsyncSession,
    drug_id: uuid.UUID,
    data: dict[str, Any],
) -> Drug | None:
    """更新药品"""
    drug = await get_drug_by_id(db, drug_id)
    if not drug:
        return None
    for key, value in data.items():
        if hasattr(drug, key):
            setattr(drug, key, value)
    await db.flush()
    return drug


async def delete_drug(db: AsyncSession, drug_id: uuid.UUID) -> bool:
    """删除药品"""
    drug = await get_drug_by_id(db, drug_id)
    if not drug:
        return False
    drug.is_deleted = True
    await db.flush()
    return True


async def get_drug_nodes(db: AsyncSession, drug_id: uuid.UUID) -> list[DrugNode]:
    """获取药品的所有节点"""
    query = (
        select(DrugNode)
        .where(DrugNode.drug_id == drug_id, DrugNode.is_deleted == False)  # noqa: E712
        .order_by(DrugNode.node_index)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_drug_node(db: AsyncSession, data: dict[str, Any]) -> DrugNode:
    """创建药品节点"""
    node = DrugNode(**data)
    db.add(node)
    await db.flush()
    return node


async def update_drug_node(
    db: AsyncSession,
    drug_id: uuid.UUID,
    node_index: int,
    data: dict[str, Any],
) -> DrugNode | None:
    """更新药品节点"""
    query = (
        select(DrugNode)
        .where(
            DrugNode.drug_id == drug_id,
            DrugNode.node_index == node_index,
            DrugNode.is_deleted == False,  # noqa: E712
        )
    )
    result = await db.execute(query)
    node = result.scalar_one_or_none()
    if not node:
        return None
    for key, value in data.items():
        if hasattr(node, key):
            setattr(node, key, value)
    await db.flush()
    return node
