"""Production database queries live here."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.production.models import (
    Batch,
    BatchMaterial,
    MaterialBalance,
    PlanTask,
    ProcessParameter,
    ProcessSpec,
    ProcessStep,
    ProductionExecutionPlan,
    ProductionFeishuConfig,
    ProductionFeishuSyncBinding,
    ProductionFeishuSyncRun,
    ProductionPlan,
    ProductionRecord,
    SalesPlanDetail,
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
        product_name: str | None = None,
        batch_no: str | None = None,
        production_line: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        exclude_cancelled: bool = False,
    ) -> tuple[list[Batch], int]:
        """获取批次列表

        Args:
            exclude_cancelled: 是否排除已取消的批次，用于生产记录下拉框等场景
        """
        query = select(Batch).where(Batch.is_deleted.is_(False))

        if exclude_cancelled:
            query = query.where(Batch.status != "cancelled")
        if status:
            query = query.where(Batch.status == status)
        if product_code:
            query = query.where(Batch.product_code == product_code)
        if product_name:
            query = query.where(Batch.product_name.contains(product_name))
        if batch_no:
            query = query.where(Batch.batch_no.contains(batch_no))
        if production_line:
            query = query.where(Batch.production_line == production_line)
        if start_date:
            query = query.where(Batch.start_time >= start_date)
        if end_date:
            query = query.where(Batch.end_time <= end_date)

        count_query = select(func.count(Batch.id)).where(Batch.is_deleted.is_(False))
        if exclude_cancelled:
            count_query = count_query.where(Batch.status != "cancelled")
        if status:
            count_query = count_query.where(Batch.status == status)
        if product_code:
            count_query = count_query.where(Batch.product_code == product_code)
        if product_name:
            count_query = count_query.where(Batch.product_name.contains(product_name))
        if batch_no:
            count_query = count_query.where(Batch.batch_no.contains(batch_no))
        if production_line:
            count_query = count_query.where(Batch.production_line == production_line)

        total = await self.session.scalar(count_query)
        query = query.offset(skip).limit(limit).order_by(Batch.created_at.desc())
        result = await self.session.execute(query)
        batches = list(result.scalars().all())
        return batches, total or 0

    async def get_batch_by_id(self, batch_id: uuid.UUID) -> Batch | None:
        """获取批次详情"""
        query = select(Batch).where(Batch.id == batch_id, Batch.is_deleted.is_(False))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_batch(self, data: dict[str, Any]) -> Batch:
        """创建批次"""
        batch = Batch(**data)
        self.session.add(batch)
        await self.session.flush()
        await self.session.refresh(batch)
        return batch

    async def update_batch(
        self, batch_id: uuid.UUID, data: dict[str, Any]
    ) -> Batch | None:
        """更新批次"""
        query = (
            update(Batch)
            .where(Batch.id == batch_id, Batch.is_deleted.is_(False))
            .values(**data)
            .returning(Batch)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_batch(self, batch_id: uuid.UUID) -> bool:
        """删除批次(软删除)"""
        query = (
            update(Batch)
            .where(Batch.id == batch_id, Batch.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return bool(getattr(result, "rowcount", 0))

    # ============ BatchMaterial Operations ============

    async def get_batch_materials(self, batch_id: uuid.UUID) -> list[BatchMaterial]:
        """获取批次物料列表"""
        query = select(BatchMaterial).where(
            BatchMaterial.batch_id == batch_id, BatchMaterial.is_deleted.is_(False)
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
            .where(BatchMaterial.id == material_id, BatchMaterial.is_deleted.is_(False))
            .values(**data)
            .returning(BatchMaterial)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_batch_material(self, material_id: uuid.UUID) -> bool:
        """删除批次物料"""
        query = (
            update(BatchMaterial)
            .where(BatchMaterial.id == material_id, BatchMaterial.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return bool(getattr(result, "rowcount", 0))

    # ============ ProductionPlan Operations ============

    async def get_plans(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        plan_month: str | None = None,
    ) -> tuple[list[ProductionPlan], int]:
        """获取生产计划列表"""
        query = select(ProductionPlan).where(ProductionPlan.is_deleted.is_(False))

        if status:
            query = query.where(ProductionPlan.status == status)
        if plan_month:
            query = query.where(ProductionPlan.plan_month == plan_month)

        count_query = select(func.count(ProductionPlan.id)).where(
            ProductionPlan.is_deleted.is_(False)
        )
        if status:
            count_query = count_query.where(ProductionPlan.status == status)
        if plan_month:
            count_query = count_query.where(ProductionPlan.plan_month == plan_month)

        total = await self.session.scalar(count_query)
        query = (
            query.offset(skip).limit(limit).order_by(ProductionPlan.created_at.desc())
        )
        result = await self.session.execute(query)
        plans = list(result.scalars().all())
        return plans, total or 0

    async def get_plan_by_id(self, plan_id: uuid.UUID) -> ProductionPlan | None:
        """获取生产计划详情"""
        query = (
            select(ProductionPlan)
            .options(selectinload(ProductionPlan.tasks))
            .where(ProductionPlan.id == plan_id, ProductionPlan.is_deleted.is_(False))
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

    async def update_plan(
        self, plan_id: uuid.UUID, data: dict[str, Any]
    ) -> ProductionPlan | None:
        """更新生产计划"""
        query = (
            update(ProductionPlan)
            .where(ProductionPlan.id == plan_id, ProductionPlan.is_deleted.is_(False))
            .values(**data)
            .returning(ProductionPlan)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_plan(self, plan_id: uuid.UUID) -> bool:
        """删除生产计划"""
        query = (
            update(ProductionPlan)
            .where(ProductionPlan.id == plan_id, ProductionPlan.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return bool(getattr(result, "rowcount", 0))

    # ============ PlanTask Operations ============

    async def get_tasks_by_plan(self, plan_id: uuid.UUID) -> list[PlanTask]:
        """获取计划任务列表"""
        query = select(PlanTask).where(
            PlanTask.plan_id == plan_id, PlanTask.is_deleted.is_(False)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_task(self, data: dict[str, Any]) -> PlanTask:
        """创建计划任务"""
        task = PlanTask(**data)
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def update_task(
        self, task_id: uuid.UUID, data: dict[str, Any]
    ) -> PlanTask | None:
        """更新计划任务"""
        query = (
            update(PlanTask)
            .where(PlanTask.id == task_id, PlanTask.is_deleted.is_(False))
            .values(**data)
            .returning(PlanTask)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_task(self, task_id: uuid.UUID) -> bool:
        """删除计划任务"""
        query = (
            update(PlanTask)
            .where(PlanTask.id == task_id, PlanTask.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return bool(getattr(result, "rowcount", 0))

    # ============ ProductionExecutionPlan Operations ============

    async def get_execution_plans(
        self,
        skip: int = 0,
        limit: int = 20,
        workshop: str | None = None,
        product_name: str | None = None,
    ) -> tuple[list[ProductionExecutionPlan], int]:
        filters: list[Any] = [ProductionExecutionPlan.is_deleted.is_(False)]
        if workshop:
            filters.append(ProductionExecutionPlan.workshop == workshop.strip())
        if product_name:
            filters.append(
                ProductionExecutionPlan.product_name.ilike(f"%{product_name.strip()}%")
            )
        total = await self.session.scalar(
            select(func.count(ProductionExecutionPlan.id)).where(*filters)
        )
        result = await self.session.execute(
            select(ProductionExecutionPlan)
            .where(*filters)
            .order_by(
                ProductionExecutionPlan.plan_date.desc().nullslast(),
                ProductionExecutionPlan.updated_at.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total or 0

    async def get_execution_plan_by_id(
        self, plan_id: uuid.UUID
    ) -> ProductionExecutionPlan | None:
        result = await self.session.execute(
            select(ProductionExecutionPlan).where(
                ProductionExecutionPlan.id == plan_id,
                ProductionExecutionPlan.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_batch_by_no(self, batch_no: str) -> Batch | None:
        """按唯一批次号获取未删除批次。"""
        result = await self.session.execute(
            select(Batch).where(
                Batch.batch_no == batch_no,
                Batch.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_execution_plan_by_source_record(
        self, source: str, source_record_id: str
    ) -> ProductionExecutionPlan | None:
        result = await self.session.execute(
            select(ProductionExecutionPlan).where(
                ProductionExecutionPlan.source == source,
                ProductionExecutionPlan.source_record_id == source_record_id,
                ProductionExecutionPlan.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_execution_plan(
        self, data: dict[str, Any]
    ) -> ProductionExecutionPlan:
        plan = ProductionExecutionPlan(**data)
        self.session.add(plan)
        await self.session.flush()
        return plan

    async def update_execution_plan(
        self, plan_id: uuid.UUID, data: dict[str, Any]
    ) -> ProductionExecutionPlan | None:
        result = await self.session.execute(
            update(ProductionExecutionPlan)
            .where(
                ProductionExecutionPlan.id == plan_id,
                ProductionExecutionPlan.is_deleted.is_(False),
            )
            .values(**data)
            .returning(ProductionExecutionPlan.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get_execution_plan_by_id(plan_id)

    async def delete_execution_plan(self, plan_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            update(ProductionExecutionPlan)
            .where(
                ProductionExecutionPlan.id == plan_id,
                ProductionExecutionPlan.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        return bool(getattr(result, "rowcount", 0))

    # ============ SalesPlanDetail Operations ============

    async def get_sales_plan_details(
        self, skip: int = 0, limit: int = 20, product_name: str | None = None
    ) -> tuple[list[SalesPlanDetail], int]:
        """获取销售执行明细列表。"""
        query = select(SalesPlanDetail).where(SalesPlanDetail.is_deleted.is_(False))
        count_query = select(func.count(SalesPlanDetail.id)).where(
            SalesPlanDetail.is_deleted.is_(False)
        )
        if product_name:
            pattern = f"%{product_name.strip()}%"
            query = query.where(SalesPlanDetail.product_name.ilike(pattern))
            count_query = count_query.where(SalesPlanDetail.product_name.ilike(pattern))

        total = await self.session.scalar(count_query)
        result = await self.session.execute(
            query.order_by(SalesPlanDetail.updated_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total or 0

    async def get_sales_plan_detail_by_id(
        self, detail_id: uuid.UUID
    ) -> SalesPlanDetail | None:
        """获取单条销售执行明细。"""
        result = await self.session.execute(
            select(SalesPlanDetail).where(
                SalesPlanDetail.id == detail_id, SalesPlanDetail.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def create_sales_plan_detail(self, data: dict[str, Any]) -> SalesPlanDetail:
        """创建销售执行明细。"""
        detail = SalesPlanDetail(**data)
        self.session.add(detail)
        await self.session.flush()
        return detail

    async def update_sales_plan_detail(
        self, detail_id: uuid.UUID, data: dict[str, Any]
    ) -> SalesPlanDetail | None:
        """更新销售执行明细，并重新查询以获取异步安全的最新实体。"""
        result = await self.session.execute(
            update(SalesPlanDetail)
            .where(
                SalesPlanDetail.id == detail_id,
                SalesPlanDetail.is_deleted.is_(False),
            )
            .values(**data)
            .returning(SalesPlanDetail.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get_sales_plan_detail_by_id(detail_id)

    async def delete_sales_plan_detail(self, detail_id: uuid.UUID) -> bool:
        """软删除销售执行明细。"""
        result = await self.session.execute(
            update(SalesPlanDetail)
            .where(
                SalesPlanDetail.id == detail_id,
                SalesPlanDetail.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        return bool(getattr(result, "rowcount", 0))

    # ============ ProcessSpec Operations ============

    async def get_process_specs(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        product_code: str | None = None,
    ) -> tuple[list[ProcessSpec], int]:
        """获取工艺规程列表"""
        query = select(ProcessSpec).where(ProcessSpec.is_deleted.is_(False))

        if status:
            query = query.where(ProcessSpec.status == status)
        if product_code:
            query = query.where(ProcessSpec.product_code == product_code)

        count_query = select(func.count(ProcessSpec.id)).where(
            ProcessSpec.is_deleted.is_(False)
        )
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
            .options(
                selectinload(ProcessSpec.steps).selectinload(ProcessStep.parameters)
            )
            .where(ProcessSpec.id == spec_id, ProcessSpec.is_deleted.is_(False))
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
            .where(ProcessSpec.id == spec_id, ProcessSpec.is_deleted.is_(False))
            .values(**data)
            .returning(ProcessSpec)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_process_spec(self, spec_id: uuid.UUID) -> bool:
        """删除工艺规程"""
        query = (
            update(ProcessSpec)
            .where(ProcessSpec.id == spec_id, ProcessSpec.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return bool(getattr(result, "rowcount", 0))

    # ============ ProcessStep Operations ============

    async def get_steps_by_spec(self, spec_id: uuid.UUID) -> list[ProcessStep]:
        """获取工艺步骤列表"""
        query = (
            select(ProcessStep)
            .options(selectinload(ProcessStep.parameters))
            .where(ProcessStep.spec_id == spec_id, ProcessStep.is_deleted.is_(False))
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
            .where(ProcessStep.id == step_id, ProcessStep.is_deleted.is_(False))
            .values(**data)
            .returning(ProcessStep)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_process_step(self, step_id: uuid.UUID) -> bool:
        """删除工艺步骤"""
        query = (
            update(ProcessStep)
            .where(ProcessStep.id == step_id, ProcessStep.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return bool(getattr(result, "rowcount", 0))

    # ============ ProcessParameter Operations ============

    async def get_parameters_by_step(
        self, step_id: uuid.UUID
    ) -> list[ProcessParameter]:
        """获取工艺参数列表"""
        query = select(ProcessParameter).where(
            ProcessParameter.step_id == step_id, ProcessParameter.is_deleted.is_(False)
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
            .where(
                ProcessParameter.id == param_id, ProcessParameter.is_deleted.is_(False)
            )
            .values(**data)
            .returning(ProcessParameter)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_process_parameter(self, param_id: uuid.UUID) -> bool:
        """删除工艺参数"""
        query = (
            update(ProcessParameter)
            .where(
                ProcessParameter.id == param_id, ProcessParameter.is_deleted.is_(False)
            )
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return bool(getattr(result, "rowcount", 0))

    # ============ ProductionRecord Operations ============

    async def get_records_by_batch(
        self, batch_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[ProductionRecord]:
        """获取生产记录列表"""
        query = (
            select(ProductionRecord)
            .where(
                ProductionRecord.batch_id == batch_id,
                ProductionRecord.is_deleted.is_(False),
            )
            .offset(skip)
            .limit(limit)
            .order_by(ProductionRecord.operation_time.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_record_by_id(self, record_id: uuid.UUID) -> ProductionRecord | None:
        """通过ID获取单条生产记录"""
        query = select(ProductionRecord).where(
            ProductionRecord.id == record_id, ProductionRecord.is_deleted.is_(False)
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
            .where(
                ProductionRecord.id == record_id, ProductionRecord.is_deleted.is_(False)
            )
            .values(**data)
            .returning(ProductionRecord)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_production_record(self, record_id: uuid.UUID) -> bool:
        """删除生产记录"""
        query = (
            update(ProductionRecord)
            .where(
                ProductionRecord.id == record_id, ProductionRecord.is_deleted.is_(False)
            )
            .values(is_deleted=True)
        )
        result = await self.session.execute(query)
        return bool(getattr(result, "rowcount", 0))

    # ============ MaterialBalance Operations ============

    async def get_material_balance(self, batch_id: uuid.UUID) -> MaterialBalance | None:
        """获取物料平衡"""
        query = select(MaterialBalance).where(
            MaterialBalance.batch_id == batch_id, MaterialBalance.is_deleted.is_(False)
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
            .where(
                MaterialBalance.batch_id == batch_id,
                MaterialBalance.is_deleted.is_(False),
            )
            .values(**data)
            .returning(MaterialBalance)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    # ============ Feishu Config Operations ============

    async def get_active_feishu_config(self) -> ProductionFeishuConfig | None:
        """获取启用的生产飞书配置"""
        query = (
            select(ProductionFeishuConfig)
            .where(
                ProductionFeishuConfig.is_deleted.is_(False),
                ProductionFeishuConfig.is_active.is_(True),
            )
            .order_by(ProductionFeishuConfig.updated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_feishu_config_by_id(
        self, config_id: uuid.UUID
    ) -> ProductionFeishuConfig | None:
        """通过 ID 获取生产飞书配置"""
        query = select(ProductionFeishuConfig).where(
            ProductionFeishuConfig.id == config_id,
            ProductionFeishuConfig.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_any_feishu_config(self) -> ProductionFeishuConfig | None:
        """获取最近一条生产飞书配置"""
        query = (
            select(ProductionFeishuConfig)
            .where(ProductionFeishuConfig.is_deleted.is_(False))
            .order_by(ProductionFeishuConfig.updated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_feishu_configs(self) -> list[ProductionFeishuConfig]:
        """获取生产飞书配置列表"""
        query = (
            select(ProductionFeishuConfig)
            .where(ProductionFeishuConfig.is_deleted.is_(False))
            .order_by(ProductionFeishuConfig.updated_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def save_feishu_config(
        self, config: ProductionFeishuConfig
    ) -> ProductionFeishuConfig:
        """保存生产飞书配置"""
        self.session.add(config)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    # ============ Feishu Sync Binding Operations ============

    async def list_feishu_sync_bindings(
        self, config_id: uuid.UUID | None = None
    ) -> list[ProductionFeishuSyncBinding]:
        """获取未删除的飞书同步绑定。"""
        query = select(ProductionFeishuSyncBinding).where(
            ProductionFeishuSyncBinding.is_deleted.is_(False)
        )
        if config_id:
            query = query.where(ProductionFeishuSyncBinding.config_id == config_id)
        result = await self.session.execute(
            query.order_by(ProductionFeishuSyncBinding.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_feishu_sync_binding_by_id(
        self, binding_id: uuid.UUID
    ) -> ProductionFeishuSyncBinding | None:
        """获取单个飞书同步绑定。"""
        result = await self.session.execute(
            select(ProductionFeishuSyncBinding).where(
                ProductionFeishuSyncBinding.id == binding_id,
                ProductionFeishuSyncBinding.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_feishu_sync_binding(
        self, data: dict[str, Any]
    ) -> ProductionFeishuSyncBinding:
        """创建飞书同步绑定。"""
        binding = ProductionFeishuSyncBinding(**data)
        self.session.add(binding)
        await self.session.flush()
        return binding

    async def update_feishu_sync_binding(
        self, binding_id: uuid.UUID, data: dict[str, Any]
    ) -> ProductionFeishuSyncBinding | None:
        """更新飞书同步绑定，并重新查询最新实体。"""
        result = await self.session.execute(
            update(ProductionFeishuSyncBinding)
            .where(
                ProductionFeishuSyncBinding.id == binding_id,
                ProductionFeishuSyncBinding.is_deleted.is_(False),
            )
            .values(**data)
            .returning(ProductionFeishuSyncBinding.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get_feishu_sync_binding_by_id(binding_id)

    async def delete_feishu_sync_binding(self, binding_id: uuid.UUID) -> bool:
        """软删除飞书同步绑定。"""
        result = await self.session.execute(
            update(ProductionFeishuSyncBinding)
            .where(
                ProductionFeishuSyncBinding.id == binding_id,
                ProductionFeishuSyncBinding.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        return bool(getattr(result, "rowcount", 0))

    async def get_sales_plan_detail_by_source_record(
        self, source: str, source_record_id: str
    ) -> SalesPlanDetail | None:
        """按外部来源记录标识读取销售执行明细，用于幂等同步。"""
        result = await self.session.execute(
            select(SalesPlanDetail).where(
                SalesPlanDetail.source == source,
                SalesPlanDetail.source_record_id == source_record_id,
                SalesPlanDetail.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    # ============ Feishu Sync Run Operations ============

    async def create_feishu_sync_run(
        self, data: dict[str, Any]
    ) -> ProductionFeishuSyncRun:
        """创建同步运行记录。"""
        sync_run = ProductionFeishuSyncRun(**data)
        self.session.add(sync_run)
        await self.session.flush()
        return sync_run

    async def get_feishu_sync_run_by_idempotency_key(
        self, binding_id: uuid.UUID, idempotency_key: str
    ) -> ProductionFeishuSyncRun | None:
        """读取同一绑定下已完成的同幂等请求。"""
        result = await self.session.execute(
            select(ProductionFeishuSyncRun).where(
                ProductionFeishuSyncRun.binding_id == binding_id,
                ProductionFeishuSyncRun.idempotency_key == idempotency_key,
                ProductionFeishuSyncRun.status.in_(("success", "failed")),
                ProductionFeishuSyncRun.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_feishu_sync_runs(
        self, binding_id: uuid.UUID, limit: int = 20
    ) -> list[ProductionFeishuSyncRun]:
        """获取绑定的最近同步运行记录。"""
        result = await self.session.execute(
            select(ProductionFeishuSyncRun)
            .where(
                ProductionFeishuSyncRun.binding_id == binding_id,
                ProductionFeishuSyncRun.is_deleted.is_(False),
            )
            .order_by(ProductionFeishuSyncRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
