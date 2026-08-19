"""Production database queries live here."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.production.models import (
    Batch,
    BatchMaterial,
    MaterialBalance,
    ProcessParameter,
    ProcessSpec,
    ProcessStep,
    ProductionPlan,
    ProductionRecord,
)


class ProductionRepository:
    """Production module repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============ Batch Operations ============

    async def get_batches(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        product_code: str | None = None,
        batch_no: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        exclude_cancelled: bool = False,
    ) -> tuple[list[Batch], int]:
        """获取批次列表

        Args:
            exclude_cancelled: 是否排除已取消的批次，用于生产记录下拉框等场景
        """
        query = select(Batch).where(Batch.is_deleted == False)

        if exclude_cancelled:
            query = query.where(Batch.status != 'cancelled')
        if status:
            query = query.where(Batch.status == status)
        if product_code:
            query = query.where(Batch.product_code == product_code)
        if batch_no:
            query = query.where(Batch.batch_no.contains(batch_no))
        if start_date:
            query = query.where(Batch.start_time >= start_date)
        if end_date:
            query = query.where(Batch.end_time <= end_date)

        count_query = select(func.count(Batch.id)).where(Batch.is_deleted == False)
        if exclude_cancelled:
            count_query = count_query.where(Batch.status != 'cancelled')
        if status:
            count_query = count_query.where(Batch.status == status)
        if product_code:
            count_query = count_query.where(Batch.product_code == product_code)
        if batch_no:
            count_query = count_query.where(Batch.batch_no.contains(batch_no))

        total = await self.session.scalar(count_query)
        query = query.offset(skip).limit(limit).order_by(Batch.created_at.desc())
        result = await self.session.execute(query)
        batches = list(result.scalars().all())
        return batches, total or 0

    async def get_batch_by_id(self, batch_id: uuid.UUID) -> Batch | None:
        """获取批次详情"""
        query = select(Batch).where(Batch.id == batch_id, Batch.is_deleted == False)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_batch(self, data: dict[str, Any]) -> Batch:
        """创建批次"""
        batch = Batch(**data)
        self.session.add(batch)
        await self.session.flush()
        await self.session.refresh(batch)
        return batch

    async def update_batch(self, batch_id: uuid.UUID, data: dict[str, Any]) -> Batch | None:
        """更新批次"""
        query = (
            update(Batch)
            .where(Batch.id == batch_id, Batch.is_deleted == False)
            .values(**data)
            .returning(Batch)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_batch(self, batch_id: uuid.UUID) -> bool:
        """删除批次(软删除)"""
        query = (
            update(Batch)
            .where(Batch.id == batch_id, Batch.is_deleted == False)
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return result.rowcount > 0

    # ============ BatchMaterial Operations ============

    async def get_batch_materials(self, batch_id: uuid.UUID) -> list[BatchMaterial]:
        """获取批次物料列表"""
        query = select(BatchMaterial).where(
            BatchMaterial.batch_id == batch_id, BatchMaterial.is_deleted == False
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_batch_material(self, data: dict[str, Any]) -> BatchMaterial:
        """创建批次物料"""
        material = BatchMaterial(**data)
        self.session.add(material)
        await self.session.flush()
        await self.session.refresh(material)
        return material

    async def update_batch_material(
        self, material_id: uuid.UUID, data: dict[str, Any]
    ) -> BatchMaterial | None:
        """更新批次物料"""
        query = (
            update(BatchMaterial)
            .where(BatchMaterial.id == material_id, BatchMaterial.is_deleted == False)
            .values(**data)
            .returning(BatchMaterial)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_batch_material(self, material_id: uuid.UUID) -> bool:
        """删除批次物料"""
        query = (
            update(BatchMaterial)
            .where(BatchMaterial.id == material_id, BatchMaterial.is_deleted == False)
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return result.rowcount > 0

    # ============ ProductionPlan Operations ============

    async def get_plans(
        self,
        skip: int = 0,
        limit: int = 20,
        product_name: str | None = None,
        workshop: str | None = None,
    ) -> tuple[list[ProductionPlan], int]:
        """获取生产计划列表"""
        query = select(ProductionPlan).where(ProductionPlan.is_deleted == False)

        if product_name:
            query = query.where(ProductionPlan.product_name == product_name)
        if workshop:
            query = query.where(ProductionPlan.workshop == workshop)

        count_query = select(func.count(ProductionPlan.id)).where(ProductionPlan.is_deleted == False)
        if product_name:
            count_query = count_query.where(ProductionPlan.product_name == product_name)
        if workshop:
            count_query = count_query.where(ProductionPlan.workshop == workshop)

        total = await self.session.scalar(count_query)
        query = query.offset(skip).limit(limit).order_by(ProductionPlan.plan_date.desc().nullslast(), ProductionPlan.created_at.desc())
        result = await self.session.execute(query)
        plans = list(result.scalars().all())
        return plans, total or 0

    async def get_plan_by_id(self, plan_id: uuid.UUID) -> ProductionPlan | None:
        """获取生产计划详情"""
        query = (
            select(ProductionPlan)
            .where(ProductionPlan.id == plan_id, ProductionPlan.is_deleted == False)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_plan(self, data: dict[str, Any]) -> ProductionPlan:
        """创建生产计划"""
        plan = ProductionPlan(**data)
        self.session.add(plan)
        await self.session.flush()
        await self.session.refresh(plan)
        return plan

    async def update_plan(self, plan_id: uuid.UUID, data: dict[str, Any]) -> ProductionPlan | None:
        """更新生产计划"""
        query = (
            update(ProductionPlan)
            .where(ProductionPlan.id == plan_id, ProductionPlan.is_deleted == False)
            .values(**data)
            .returning(ProductionPlan)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_plan(self, plan_id: uuid.UUID) -> bool:
        """删除生产计划"""
        query = (
            update(ProductionPlan)
            .where(ProductionPlan.id == plan_id, ProductionPlan.is_deleted == False)
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return result.rowcount > 0

    # ============ ProcessSpec Operations ============

    async def get_process_specs(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        product_code: str | None = None,
    ) -> tuple[list[ProcessSpec], int]:
        """获取工艺规程列表"""
        query = select(ProcessSpec).where(ProcessSpec.is_deleted == False)

        if status:
            query = query.where(ProcessSpec.status == status)
        if product_code:
            query = query.where(ProcessSpec.product_code == product_code)

        count_query = select(func.count(ProcessSpec.id)).where(ProcessSpec.is_deleted == False)
        if status:
            count_query = count_query.where(ProcessSpec.status == status)
        if product_code:
            count_query = count_query.where(ProcessSpec.product_code == product_code)

        total = await self.session.scalar(count_query)
        query = query.offset(skip).limit(limit).order_by(ProcessSpec.created_at.desc())
        result = await self.session.execute(query)
        specs = list(result.scalars().all())
        return specs, total or 0

    async def get_process_spec_by_id(self, spec_id: uuid.UUID) -> ProcessSpec | None:
        """获取工艺规程详情"""
        query = (
            select(ProcessSpec)
            .options(selectinload(ProcessSpec.steps).selectinload(ProcessStep.parameters))
            .where(ProcessSpec.id == spec_id, ProcessSpec.is_deleted == False)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_process_spec(self, data: dict[str, Any]) -> ProcessSpec:
        """创建工艺规程"""
        spec = ProcessSpec(**data)
        self.session.add(spec)
        await self.session.flush()
        await self.session.refresh(spec)
        return spec

    async def update_process_spec(
        self, spec_id: uuid.UUID, data: dict[str, Any]
    ) -> ProcessSpec | None:
        """更新工艺规程"""
        query = (
            update(ProcessSpec)
            .where(ProcessSpec.id == spec_id, ProcessSpec.is_deleted == False)
            .values(**data)
            .returning(ProcessSpec)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_process_spec(self, spec_id: uuid.UUID) -> bool:
        """删除工艺规程"""
        query = (
            update(ProcessSpec)
            .where(ProcessSpec.id == spec_id, ProcessSpec.is_deleted == False)
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return result.rowcount > 0

    # ============ ProcessStep Operations ============

    async def get_steps_by_spec(self, spec_id: uuid.UUID) -> list[ProcessStep]:
        """获取工艺步骤列表"""
        query = (
            select(ProcessStep)
            .options(selectinload(ProcessStep.parameters))
            .where(ProcessStep.spec_id == spec_id, ProcessStep.is_deleted == False)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_process_step(self, data: dict[str, Any]) -> ProcessStep:
        """创建工艺步骤"""
        step = ProcessStep(**data)
        self.session.add(step)
        await self.session.flush()
        await self.session.refresh(step)
        return step

    async def update_process_step(
        self, step_id: uuid.UUID, data: dict[str, Any]
    ) -> ProcessStep | None:
        """更新工艺步骤"""
        query = (
            update(ProcessStep)
            .where(ProcessStep.id == step_id, ProcessStep.is_deleted == False)
            .values(**data)
            .returning(ProcessStep)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_process_step(self, step_id: uuid.UUID) -> bool:
        """删除工艺步骤"""
        query = (
            update(ProcessStep)
            .where(ProcessStep.id == step_id, ProcessStep.is_deleted == False)
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return result.rowcount > 0

    # ============ ProcessParameter Operations ============

    async def get_parameters_by_step(self, step_id: uuid.UUID) -> list[ProcessParameter]:
        """获取工艺参数列表"""
        query = select(ProcessParameter).where(
            ProcessParameter.step_id == step_id, ProcessParameter.is_deleted == False
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_process_parameter(self, data: dict[str, Any]) -> ProcessParameter:
        """创建工艺参数"""
        param = ProcessParameter(**data)
        self.session.add(param)
        await self.session.flush()
        await self.session.refresh(param)
        return param

    async def update_process_parameter(
        self, param_id: uuid.UUID, data: dict[str, Any]
    ) -> ProcessParameter | None:
        """更新工艺参数"""
        query = (
            update(ProcessParameter)
            .where(ProcessParameter.id == param_id, ProcessParameter.is_deleted == False)
            .values(**data)
            .returning(ProcessParameter)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_process_parameter(self, param_id: uuid.UUID) -> bool:
        """删除工艺参数"""
        query = (
            update(ProcessParameter)
            .where(ProcessParameter.id == param_id, ProcessParameter.is_deleted == False)
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return result.rowcount > 0

    # ============ ProductionRecord Operations ============

    async def get_records_by_batch(
        self, batch_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[ProductionRecord]:
        """获取生产记录列表"""
        query = (
            select(ProductionRecord)
            .where(ProductionRecord.batch_id == batch_id, ProductionRecord.is_deleted == False)
            .offset(skip)
            .limit(limit)
            .order_by(ProductionRecord.operation_time.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_record_by_id(self, record_id: uuid.UUID) -> ProductionRecord | None:
        """通过ID获取单条生产记录"""
        query = select(ProductionRecord).where(
            ProductionRecord.id == record_id, ProductionRecord.is_deleted == False
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_production_record(self, data: dict[str, Any]) -> ProductionRecord:
        """创建生产记录"""
        record = ProductionRecord(**data)
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def update_production_record(
        self, record_id: uuid.UUID, data: dict[str, Any]
    ) -> ProductionRecord | None:
        """更新生产记录"""
        query = (
            update(ProductionRecord)
            .where(ProductionRecord.id == record_id, ProductionRecord.is_deleted == False)
            .values(**data)
            .returning(ProductionRecord)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_production_record(self, record_id: uuid.UUID) -> bool:
        """删除生产记录"""
        query = (
            update(ProductionRecord)
            .where(ProductionRecord.id == record_id, ProductionRecord.is_deleted == False)
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return result.rowcount > 0

    # ============ MaterialBalance Operations ============

    async def get_material_balance(self, batch_id: uuid.UUID) -> MaterialBalance | None:
        """获取物料平衡"""
        query = select(MaterialBalance).where(
            MaterialBalance.batch_id == batch_id, MaterialBalance.is_deleted == False
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_material_balance(self, data: dict[str, Any]) -> MaterialBalance:
        """创建物料平衡"""
        balance = MaterialBalance(**data)
        self.session.add(balance)
        await self.session.flush()
        await self.session.refresh(balance)
        return balance

    async def update_material_balance(
        self, batch_id: uuid.UUID, data: dict[str, Any]
    ) -> MaterialBalance | None:
        """更新物料平衡"""
        query = (
            update(MaterialBalance)
            .where(MaterialBalance.batch_id == batch_id, MaterialBalance.is_deleted == False)
            .values(**data)
            .returning(MaterialBalance)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_material_balance(self, batch_id: uuid.UUID) -> bool:
        """软删除物料平衡"""
        query = (
            update(MaterialBalance)
            .where(MaterialBalance.batch_id == batch_id, MaterialBalance.is_deleted == False)
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return result.rowcount > 0