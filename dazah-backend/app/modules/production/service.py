"""Production business workflows live here."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.models import (
    Batch,
    BatchMaterial,
    BatchStatus,
    MaterialBalance,
    ProcessParameter,
    ProcessSpec,
    ProcessSpecStatus,
    ProcessStep,
    ProductionPlan,
    ProductionRecord,
)
from app.modules.production.repository import ProductionRepository
from app.modules.production.schemas import (
    BatchCreate,
    BatchStatusUpdate,
    BatchUpdate,
    ProcessParameterCreate,
    ProcessParameterUpdate,
    ProcessSpecCreate,
    ProcessSpecUpdate,
    ProcessStepCreate,
    ProcessStepUpdate,
    ProductionPlanCreate,
    ProductionPlanUpdate,
    ProductionRecordCreate,
    ProductionRecordUpdate,
)


class ProductionService:
    """Production module service"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ProductionRepository(session)

    # ============ Batch Operations ============

    async def get_batches(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        product_code: str | None = None,
        batch_no: str | None = None,
        exclude_cancelled: bool = False,
    ) -> tuple[list[Batch], int]:
        """获取批次列表"""
        return await self.repo.get_batches(
            skip,
            limit,
            status,
            product_code,
            batch_no,
            exclude_cancelled=exclude_cancelled,
        )

    async def get_batch(self, batch_id: uuid.UUID) -> Batch | None:
        """获取批次详情"""
        return await self.repo.get_batch_by_id(batch_id)

    async def create_batch(self, data: BatchCreate) -> Batch:
        """创建批次"""
        batch_data = data.model_dump()
        return await self.repo.create_batch(batch_data)

    async def update_batch(
        self, batch_id: uuid.UUID, data: BatchUpdate
    ) -> Batch | None:
        """更新批次"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        return await self.repo.update_batch(batch_id, update_data)

    async def update_batch_status(
        self, batch_id: uuid.UUID, data: BatchStatusUpdate
    ) -> Batch | None:
        """更新批次状态"""
        batch = await self.repo.get_batch_by_id(batch_id)
        if not batch:
            return None

        # 状态流转校验
        valid_transitions: dict[str, list[str]] = {
            BatchStatus.DRAFT.value: [
                BatchStatus.RELEASED.value,
                BatchStatus.CANCELLED.value,
            ],
            BatchStatus.RELEASED.value: [
                BatchStatus.IN_PROGRESS.value,
                BatchStatus.CANCELLED.value,
            ],
            BatchStatus.IN_PROGRESS.value: [
                BatchStatus.COMPLETED.value,
                BatchStatus.CANCELLED.value,
            ],
            BatchStatus.COMPLETED.value: [],
            BatchStatus.CANCELLED.value: [],
        }

        current_status = str(getattr(batch.status, "value", batch.status))
        target_status = data.status.value
        if target_status not in valid_transitions.get(current_status, []):
            raise ValueError(
                f"无效的状态转换: {current_status} -> {target_status}"
            )

        # 处理状态变更的副作用
        next_status = BatchStatus(target_status)
        update_data: dict[str, Any] = {"status": next_status.value}

        if next_status == BatchStatus.IN_PROGRESS and not batch.start_time:
            update_data["start_time"] = datetime.now()
        elif next_status == BatchStatus.COMPLETED:
            update_data["end_time"] = datetime.now()

        return await self.repo.update_batch(batch_id, update_data)

    async def delete_batch(self, batch_id: uuid.UUID) -> bool:
        """删除批次"""
        return await self.repo.delete_batch(batch_id)

    # ============ BatchMaterial Operations ============

    async def get_batch_materials(self, batch_id: uuid.UUID) -> list[BatchMaterial]:
        """获取批次物料列表"""
        return await self.repo.get_batch_materials(batch_id)

    async def add_batch_material(
        self, batch_id: uuid.UUID, data: dict[str, Any]
    ) -> BatchMaterial:
        """添加批次物料"""
        data["batch_id"] = batch_id
        return await self.repo.create_batch_material(data)

    async def update_batch_material(
        self, material_id: uuid.UUID, data: dict[str, Any]
    ) -> BatchMaterial | None:
        """更新批次物料"""
        return await self.repo.update_batch_material(material_id, data)

    async def delete_batch_material(self, material_id: uuid.UUID) -> bool:
        """删除批次物料"""
        return await self.repo.delete_batch_material(material_id)

    # ============ ProductionPlan Operations ============

    async def get_plans(
        self,
        skip: int = 0,
        limit: int = 20,
        product_name: str | None = None,
        workshop: str | None = None,
    ) -> tuple[list[ProductionPlan], int]:
        """获取生产计划列表"""
        return await self.repo.get_plans(skip, limit, product_name, workshop)

    async def get_plan(self, plan_id: uuid.UUID) -> ProductionPlan | None:
        """获取生产计划详情"""
        return await self.repo.get_plan_by_id(plan_id)

    async def create_plan(self, data: ProductionPlanCreate) -> ProductionPlan:
        """创建生产计划"""
        plan_data = data.model_dump()
        plan_data.setdefault("source", "manual")
        return await self.repo.create_plan(plan_data)

    async def update_plan(
        self, plan_id: uuid.UUID, data: ProductionPlanUpdate
    ) -> ProductionPlan | None:
        """更新生产计划"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        return await self.repo.update_plan(plan_id, update_data)

    async def delete_plan(self, plan_id: uuid.UUID) -> bool:
        """删除生产计划"""
        return await self.repo.delete_plan(plan_id)

    # ============ ProcessSpec Operations ============

    async def get_process_specs(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        product_code: str | None = None,
    ) -> tuple[list[ProcessSpec], int]:
        """获取工艺规程列表"""
        return await self.repo.get_process_specs(skip, limit, status, product_code)

    async def get_process_spec(self, spec_id: uuid.UUID) -> ProcessSpec | None:
        """获取工艺规程详情"""
        return await self.repo.get_process_spec_by_id(spec_id)

    async def create_process_spec(self, data: ProcessSpecCreate) -> ProcessSpec:
        """创建工艺规程"""
        spec_data = data.model_dump()
        return await self.repo.create_process_spec(spec_data)

    async def update_process_spec(
        self, spec_id: uuid.UUID, data: ProcessSpecUpdate
    ) -> ProcessSpec | None:
        """更新工艺规程"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        return await self.repo.update_process_spec(spec_id, update_data)

    async def approve_process_spec(
        self, spec_id: uuid.UUID, approved_by: uuid.UUID, approved_by_name: str
    ) -> ProcessSpec | None:
        """批准工艺规程"""
        spec = await self.repo.get_process_spec_by_id(spec_id)
        if not spec or spec.status != ProcessSpecStatus.DRAFT:
            return None
        return await self.repo.update_process_spec(
            spec_id,
            {
                "status": ProcessSpecStatus.APPROVED,
                "approved_by": approved_by,
                "approved_by_name": approved_by_name,
                "approved_at": datetime.now(),
            },
        )

    async def effectivate_process_spec(self, spec_id: uuid.UUID) -> ProcessSpec | None:
        """使工艺规程生效"""
        spec = await self.repo.get_process_spec_by_id(spec_id)
        if not spec or spec.status != ProcessSpecStatus.APPROVED:
            return None
        return await self.repo.update_process_spec(
            spec_id,
            {
                "status": ProcessSpecStatus.EFFECTIVE,
                "effective_date": datetime.now(),
            },
        )

    async def archive_process_spec(self, spec_id: uuid.UUID) -> ProcessSpec | None:
        """归档工艺规程"""
        spec = await self.repo.get_process_spec_by_id(spec_id)
        if not spec or spec.status != ProcessSpecStatus.EFFECTIVE:
            return None
        return await self.repo.update_process_spec(
            spec_id,
            {"status": ProcessSpecStatus.ARCHIVED},
        )

    async def delete_process_spec(self, spec_id: uuid.UUID) -> bool:
        """删除工艺规程"""
        return await self.repo.delete_process_spec(spec_id)

    # ============ ProcessStep Operations ============

    async def get_steps(self, spec_id: uuid.UUID) -> list[ProcessStep]:
        """获取工艺步骤列表"""
        return await self.repo.get_steps_by_spec(spec_id)

    async def create_process_step(self, data: ProcessStepCreate) -> ProcessStep:
        """创建工艺步骤"""
        step_data = data.model_dump()
        return await self.repo.create_process_step(step_data)

    async def update_process_step(
        self, step_id: uuid.UUID, data: ProcessStepUpdate
    ) -> ProcessStep | None:
        """更新工艺步骤"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        return await self.repo.update_process_step(step_id, update_data)

    async def delete_process_step(self, step_id: uuid.UUID) -> bool:
        """删除工艺步骤"""
        return await self.repo.delete_process_step(step_id)

    # ============ ProcessParameter Operations ============

    async def get_parameters(self, step_id: uuid.UUID) -> list[ProcessParameter]:
        """获取工艺参数列表"""
        return await self.repo.get_parameters_by_step(step_id)

    async def create_process_parameter(
        self, data: ProcessParameterCreate
    ) -> ProcessParameter:
        """创建工艺参数"""
        param_data = data.model_dump()
        return await self.repo.create_process_parameter(param_data)

    async def update_process_parameter(
        self, param_id: uuid.UUID, data: ProcessParameterUpdate
    ) -> ProcessParameter | None:
        """更新工艺参数"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        return await self.repo.update_process_parameter(param_id, update_data)

    async def delete_process_parameter(self, param_id: uuid.UUID) -> bool:
        """删除工艺参数"""
        return await self.repo.delete_process_parameter(param_id)

    # ============ ProductionRecord Operations ============

    async def get_records(
        self, batch_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[ProductionRecord]:
        """获取生产记录列表"""
        return await self.repo.get_records_by_batch(batch_id, skip, limit)

    async def create_production_record(
        self, data: ProductionRecordCreate
    ) -> ProductionRecord:
        """创建生产记录"""
        record_data = data.model_dump()
        record = await self.repo.create_production_record(record_data)

        # 自动同步批次投入产出数据
        if record.batch_id:
            await self._sync_batch_input_output(record.batch_id)

        return record

    async def update_production_record(
        self, record_id: uuid.UUID, data: ProductionRecordUpdate
    ) -> ProductionRecord | None:
        """更新生产记录"""
        # 获取原记录以获取 batch_id
        await self.repo.get_record_by_id(record_id)

        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        record = await self.repo.update_production_record(record_id, update_data)

        # 自动同步批次投入产出数据
        if record and record.batch_id:
            await self._sync_batch_input_output(record.batch_id)

        return record

    async def _sync_batch_input_output(self, batch_id: uuid.UUID) -> None:
        """同步批次的投入产出数据（基于生产记录）"""
        # 获取该批次所有生产记录
        records = await self.repo.get_records_by_batch(batch_id, skip=0, limit=1000)

        # 汇总投料记录（累计所有投料量）
        total_input = 0.0
        for r in records:
            if r.operation_type == "material_add" and r.parameters:
                try:
                    import json

                    params = json.loads(r.parameters)
                    if "quantity" in params:
                        total_input += params["quantity"]
                except Exception:
                    pass

        # 汇总包装记录（累计所有包装产出量）
        total_output = 0.0
        for r in records:
            if r.operation_type == "packaging" and r.parameters:
                try:
                    import json

                    params = json.loads(r.parameters)
                    if "quantity" in params:
                        total_output += params["quantity"]
                except Exception:
                    pass

        # 更新批次数据
        update_data = {}
        if total_input > 0:
            update_data["input_qty"] = total_input  # 投入量
        if total_output > 0:
            update_data["actual_qty"] = total_output  # 产出量

        if update_data:
            await self.repo.update_batch(batch_id, update_data)

    async def delete_production_record(self, record_id: uuid.UUID) -> bool:
        """删除生产记录"""
        return await self.repo.delete_production_record(record_id)

    # ============ MaterialBalance Operations ============

    async def get_material_balance(self, batch_id: uuid.UUID) -> MaterialBalance | None:
        """获取物料平衡"""
        return await self.repo.get_material_balance(batch_id)

    async def calculate_material_balance(
        self, batch_id: uuid.UUID, min_balance_rate: float = 95.0
    ) -> MaterialBalance | None:
        """计算物料平衡"""
        # 获取批次
        batch = await self.repo.get_batch_by_id(batch_id)
        if not batch:
            return None

        # 获取批次物料（从物料表获取投入）
        materials = await self.repo.get_batch_materials(batch_id)
        material_input = sum(m.actual_qty or 0 for m in materials)

        # 获取生产记录中的投料和包装数据
        records = await self.repo.get_records_by_batch(batch_id, skip=0, limit=1000)

        record_input = 0.0
        record_output = 0.0
        for r in records:
            if r.operation_type == "material_add" and r.parameters:
                try:
                    import json

                    params = json.loads(r.parameters)
                    if "quantity" in params:
                        record_input += params["quantity"]
                except Exception:
                    pass
            elif r.operation_type == "packaging" and r.parameters:
                try:
                    import json

                    params = json.loads(r.parameters)
                    if "quantity" in params:
                        record_output += params["quantity"]
                except Exception:
                    pass

        # 投入量优先使用生产记录，如果没有则使用物料表
        total_input = record_input if record_input > 0 else material_input
        if batch.input_qty and batch.input_qty > 0:
            total_input = batch.input_qty

        # 产出量优先使用生产记录，如果没有则使用批次 actual_qty
        total_output = record_output if record_output > 0 else (batch.actual_qty or 0)

        # 计算平衡率
        loss_qty = total_input - total_output
        balance_rate = (total_output / total_input * 100) if total_input > 0 else 0
        is_balanced = balance_rate >= min_balance_rate
        deviation_rate = abs(balance_rate - 100) if balance_rate > 0 else 0

        balance_data = {
            "batch_id": batch_id,
            "input_qty": total_input,
            "output_qty": total_output,
            "loss_qty": loss_qty,
            "balance_rate": round(balance_rate, 2),
            "min_balance_rate": min_balance_rate,
            "is_balanced": is_balanced,
            "deviation_rate": round(deviation_rate, 2),
            "calculated_at": datetime.now(),
        }

        # 检查是否已存在
        existing = await self.repo.get_material_balance(batch_id)
        if existing:
            return await self.repo.update_material_balance(batch_id, balance_data)
        else:
            return await self.repo.create_material_balance(balance_data)

    async def update_material_balance(
        self, batch_id: uuid.UUID, data: dict[str, Any]
    ) -> MaterialBalance | None:
        """更新物料平衡"""
        # 重新计算平衡
        if "input_qty" in data or "output_qty" in data:
            return await self.calculate_material_balance(
                batch_id, data.get("min_balance_rate", 95.0)
            )
        return await self.repo.update_material_balance(batch_id, data)

    async def delete_material_balance(self, batch_id: uuid.UUID) -> bool:
        """软删除物料平衡"""
        return await self.repo.delete_material_balance(batch_id)
