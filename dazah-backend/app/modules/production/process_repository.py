"""生产工序执行记录查询。"""

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.models import Batch, ProcessExecutionRecord


class ProcessExecutionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_batch_by_id(self, batch_id: uuid.UUID) -> Batch | None:
        result = await self.session.execute(
            select(Batch).where(Batch.id == batch_id, Batch.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_batch_by_no(self, batch_no: str) -> Batch | None:
        result = await self.session.execute(
            select(Batch).where(Batch.batch_no == batch_no, Batch.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

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
        filters: list[Any] = [ProcessExecutionRecord.is_deleted.is_(False)]
        if batch_no:
            filters.append(ProcessExecutionRecord.batch_no.ilike(f"%{batch_no}%"))
        if workshop_code:
            filters.append(ProcessExecutionRecord.workshop_code == workshop_code)
        if process_code:
            filters.append(ProcessExecutionRecord.process_code == process_code)
        if status:
            filters.append(ProcessExecutionRecord.status == status)
        total = await self.session.scalar(
            select(func.count(ProcessExecutionRecord.id)).where(*filters)
        )
        result = await self.session.execute(
            select(ProcessExecutionRecord)
            .where(*filters)
            .order_by(
                ProcessExecutionRecord.batch_no.desc(),
                ProcessExecutionRecord.step_sequence,
                ProcessExecutionRecord.recorded_at.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total or 0

    async def get_record(self, record_id: uuid.UUID) -> ProcessExecutionRecord | None:
        result = await self.session.execute(
            select(ProcessExecutionRecord).where(
                ProcessExecutionRecord.id == record_id,
                ProcessExecutionRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_record_by_source(
        self, process_code: str, source: str, source_record_id: str
    ) -> ProcessExecutionRecord | None:
        result = await self.session.execute(
            select(ProcessExecutionRecord).where(
                ProcessExecutionRecord.process_code == process_code,
                ProcessExecutionRecord.source == source,
                ProcessExecutionRecord.source_record_id == source_record_id,
                ProcessExecutionRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_record(self, data: dict[str, Any]) -> ProcessExecutionRecord:
        record = ProcessExecutionRecord(**data)
        self.session.add(record)
        await self.session.flush()
        return record

    async def update_record(
        self, record_id: uuid.UUID, data: dict[str, Any]
    ) -> ProcessExecutionRecord | None:
        result = await self.session.execute(
            update(ProcessExecutionRecord)
            .where(
                ProcessExecutionRecord.id == record_id,
                ProcessExecutionRecord.is_deleted.is_(False),
            )
            .values(**data)
            .returning(ProcessExecutionRecord.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get_record(record_id)

    async def delete_record(self, record_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            update(ProcessExecutionRecord)
            .where(
                ProcessExecutionRecord.id == record_id,
                ProcessExecutionRecord.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        return bool(getattr(result, "rowcount", 0))

    async def records_for_progress(
        self, workshop_code: str, batch_no: str | None = None
    ) -> list[ProcessExecutionRecord]:
        filters: list[Any] = [
            ProcessExecutionRecord.is_deleted.is_(False),
            ProcessExecutionRecord.workshop_code == workshop_code,
        ]
        if batch_no:
            filters.append(ProcessExecutionRecord.batch_no.ilike(f"%{batch_no}%"))
        result = await self.session.execute(
            select(ProcessExecutionRecord)
            .where(*filters)
            .order_by(ProcessExecutionRecord.batch_no.desc())
        )
        return list(result.scalars().all())

    async def records_for_batch(
        self, workshop_code: str, batch_no: str
    ) -> list[ProcessExecutionRecord]:
        result = await self.session.execute(
            select(ProcessExecutionRecord).where(
                ProcessExecutionRecord.is_deleted.is_(False),
                ProcessExecutionRecord.workshop_code == workshop_code,
                ProcessExecutionRecord.batch_no == batch_no,
            )
        )
        return list(result.scalars().all())
