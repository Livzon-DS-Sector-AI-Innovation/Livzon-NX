"""生产工序执行、批次进度与批次全貌业务服务。"""

import re
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.production.models import ProcessExecutionRecord
from app.modules.production.process_catalog import (
    PROCESS_STEPS,
    process_step,
    validate_process_data,
)
from app.modules.production.process_repository import ProcessExecutionRepository
from app.modules.production.process_schemas import (
    BatchProfileResponse,
    BatchProgressItem,
    BatchProgressResponse,
    BatchProgressSummary,
    ProcessBottleneck,
    ProcessExecutionRecordCreate,
    ProcessExecutionRecordResponse,
    ProcessExecutionRecordUpdate,
    ProcessStepProgress,
)


class ProcessExecutionService:
    def __init__(self, session: AsyncSession):
        self.repo = ProcessExecutionRepository(session)

    async def list_records(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        batch_no: str | None = None,
        workshop_code: str | None = None,
        process_code: str | None = None,
        status: str | None = None,
    ) -> tuple[list[ProcessExecutionRecord], int]:
        return await self.repo.list_records(
            skip=skip,
            limit=limit,
            batch_no=batch_no,
            workshop_code=workshop_code,
            process_code=process_code,
            status=status,
        )

    async def create_record(
        self, data: ProcessExecutionRecordCreate, actor_id: uuid.UUID | None = None
    ) -> ProcessExecutionRecord:
        payload = data.model_dump()
        batch = None
        if data.batch_id:
            batch = await self.repo.get_batch_by_id(data.batch_id)
            if not batch:
                raise AppException(message="关联批次不存在")
            if batch.batch_no != data.batch_no:
                raise AppException(message="批次 ID 与批次号不一致")
        else:
            batch = await self.repo.get_batch_by_no(data.batch_no)
            if batch:
                payload["batch_id"] = batch.id
        definition = process_step(data.process_code)
        if not definition:
            raise AppException(message="不支持的工序编码")
        payload["step_sequence"] = definition["sequence"]
        payload["data"] = validate_process_data(data.process_code, data.data)
        await self._ensure_step_available(
            data.workshop_code,
            data.batch_no,
            data.process_code,
        )
        payload["created_by"] = actor_id
        payload["updated_by"] = actor_id
        if data.status == "completed":
            payload["completed_at"] = datetime.now(UTC)
        return await self.repo.create_record(payload)

    async def update_record(
        self,
        record_id: uuid.UUID,
        data: ProcessExecutionRecordUpdate,
        actor_id: uuid.UUID | None = None,
    ) -> ProcessExecutionRecord | None:
        current = await self.repo.get_record(record_id)
        if not current:
            return None
        if current.status == "completed":
            raise AppException(message="已完成工序已锁定，不能直接修改")
        payload = data.model_dump(exclude_unset=True)
        if data.data is not None:
            payload["data"] = validate_process_data(current.process_code, data.data)
        if data.status == "completed":
            await self._ensure_previous_completed(current)
        payload["updated_by"] = actor_id
        if data.status == "completed":
            payload["completed_at"] = datetime.now(UTC)
        elif data.status in {"draft", "in_progress"}:
            payload["completed_at"] = None
        return await self.repo.update_record(record_id, payload)

    async def complete_record(
        self, record_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> ProcessExecutionRecord | None:
        current = await self.repo.get_record(record_id)
        if not current:
            return None
        if current.status == "completed":
            return current
        await self._ensure_previous_completed(current)
        return await self.repo.update_record(
            record_id,
            {
                "status": "completed",
                "completed_at": datetime.now(UTC),
                "updated_by": actor_id,
            },
        )

    async def delete_record(self, record_id: uuid.UUID) -> bool:
        current = await self.repo.get_record(record_id)
        if current and current.status == "completed":
            raise AppException(message="已完成工序不能删除，如需修订请走受控修订流程")
        return await self.repo.delete_record(record_id)

    async def _ensure_step_available(
        self, workshop_code: str, batch_no: str, process_code: str
    ) -> None:
        definition = process_step(process_code)
        if not definition:
            raise AppException(message="不支持的工序编码")
        records = await self.repo.records_for_batch(workshop_code, batch_no)
        if any(
            record.process_code == process_code and record.status == "completed"
            for record in records
        ):
            raise AppException(message="该批次的当前工序已经完成，不能重复创建")
        if definition["sequence"] == 1:
            return
        previous_code = PROCESS_STEPS[definition["sequence"] - 2]["code"]
        if not any(
            record.process_code == previous_code and record.status == "completed"
            for record in records
        ):
            previous_label = PROCESS_STEPS[definition["sequence"] - 2]["label"]
            raise AppException(message=f"请先完成前序工序：{previous_label}")

    async def _ensure_previous_completed(
        self, record: ProcessExecutionRecord
    ) -> None:
        if record.step_sequence == 1:
            return
        records = await self.repo.records_for_batch(
            record.workshop_code, record.batch_no
        )
        previous = PROCESS_STEPS[record.step_sequence - 2]
        if not any(
            item.process_code == previous["code"] and item.status == "completed"
            for item in records
        ):
            raise AppException(message=f"请先完成前序工序：{previous['label']}")

    async def get_progress(
        self, workshop_code: str = "203", batch_no: str | None = None
    ) -> BatchProgressResponse:
        records = await self.repo.records_for_progress(workshop_code, batch_no)
        grouped: dict[str, list[ProcessExecutionRecord]] = defaultdict(list)
        for record in records:
            grouped[record.batch_no].append(record)

        batch_items = [
            self._build_batch_progress(number, workshop_code, batch_records)
            for number, batch_records in grouped.items()
        ]
        completed_batches = sum(
            1
            for item in batch_items
            if next(step for step in item.steps if step.code == "pack").completed
        )
        today = date.today()
        monthly_output = 0.0
        today_pack_count = 0
        for record in records:
            if record.process_code != "pack" or record.status != "completed":
                continue
            local_date = record.recorded_at.date()
            if local_date == today:
                today_pack_count += 1
            if local_date.year == today.year and local_date.month == today.month:
                monthly_output += self._number_from_data(
                    record.data.get("total_net_weight")
                )

        bottlenecks: list[ProcessBottleneck] = []
        for index, definition in enumerate(PROCESS_STEPS[1:], start=1):
            previous_code = PROCESS_STEPS[index - 1]["code"]
            stuck = [
                item.batch_no
                for item in batch_items
                if self._step_completed(item, previous_code)
                and not self._step_completed(item, definition["code"])
            ]
            if stuck:
                bottlenecks.append(
                    ProcessBottleneck(
                        process_code=definition["code"],
                        process_label=definition["label"],
                        stuck_count=len(stuck),
                        stuck_batches=stuck[:10],
                        has_more=len(stuck) > 10,
                    )
                )

        return BatchProgressResponse(
            batches=batch_items,
            steps=[dict(step) for step in PROCESS_STEPS],
            summary=BatchProgressSummary(
                total_batches=len(batch_items),
                in_progress=len(batch_items) - completed_batches,
                completed=completed_batches,
                today_pack_count=today_pack_count,
                monthly_output_kg=round(monthly_output, 2),
                bottlenecks=bottlenecks,
            ),
        )

    async def get_batch_profile(self, batch_no: str) -> BatchProfileResponse:
        batch = await self.repo.get_batch_by_no(batch_no)
        records, _ = await self.repo.list_records(batch_no=batch_no, limit=1000)
        exact_records = [record for record in records if record.batch_no == batch_no]
        if not batch and not exact_records:
            raise AppException(status_code=404, message="批次不存在")
        progress = (
            self._build_batch_progress(
                batch_no,
                batch.production_line or "203" if batch else "203",
                exact_records,
            )
            if exact_records
            else None
        )
        grouped: dict[str, list[ProcessExecutionRecordResponse]] = defaultdict(list)
        for record in exact_records:
            grouped[record.process_code].append(
                ProcessExecutionRecordResponse.model_validate(record)
            )
        batch_data = None
        if batch:
            batch_data = {
                "id": str(batch.id),
                "batch_no": batch.batch_no,
                "product_code": batch.product_code,
                "product_name": batch.product_name,
                "status": (
                    batch.status.value
                    if hasattr(batch.status, "value")
                    else batch.status
                ),
                "production_line": batch.production_line,
                "planned_qty": batch.planned_qty,
                "actual_qty": batch.actual_qty,
            }
        return BatchProfileResponse(
            batch_no=batch_no,
            batch=batch_data,
            progress=progress,
            records=dict(grouped),
        )

    @staticmethod
    def _build_batch_progress(
        batch_no: str,
        workshop_code: str,
        records: list[ProcessExecutionRecord],
    ) -> BatchProgressItem:
        records_by_step: dict[str, list[ProcessExecutionRecord]] = defaultdict(list)
        for record in records:
            records_by_step[record.process_code].append(record)
        steps = []
        for definition in PROCESS_STEPS:
            step_records = records_by_step.get(definition["code"], [])
            steps.append(
                ProcessStepProgress(
                    code=definition["code"],
                    label=definition["label"],
                    short=definition["short"],
                    sequence=definition["sequence"],
                    has_record=bool(step_records),
                    completed=any(
                        record.status == "completed" for record in step_records
                    ),
                    record_count=len(step_records),
                )
            )
        completed = sum(1 for step in steps if step.completed)
        return BatchProgressItem(
            batch_no=batch_no,
            workshop_code=workshop_code,
            completed=completed,
            total=len(PROCESS_STEPS),
            progress_percent=round(completed / len(PROCESS_STEPS) * 100, 1),
            steps=steps,
        )

    @staticmethod
    def _step_completed(item: BatchProgressItem, process_code: str) -> bool:
        return any(step.code == process_code and step.completed for step in item.steps)

    @staticmethod
    def _number_from_data(value: Any) -> float:
        if isinstance(value, int | float):
            return float(value)
        if value is None:
            return 0.0
        match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
        return float(match.group(0)) if match else 0.0
