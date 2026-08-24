"""发酵、种子培养、事件和班次业务服务。"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.production.models import (
    FermentationRecord,
    NonConformingEvent,
    SeedCultureRecord,
    ShiftHandover,
    ShiftLog,
)
from app.modules.production.operations_repository import OperationsRepository
from app.modules.production.operations_schemas import (
    FermentationCreate,
    FermentationUpdate,
    NonConformingEventCreate,
    NonConformingEventUpdate,
    SeedCultureCreate,
    SeedCultureUpdate,
    ShiftHandoverCreate,
    ShiftHandoverUpdate,
    ShiftLogCreate,
    ShiftLogUpdate,
)


class OperationsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = OperationsRepository(session)

    @staticmethod
    def _audit(
        data: dict[str, Any], actor_id: uuid.UUID | None, *, create: bool
    ) -> dict[str, Any]:
        data["updated_by"] = actor_id
        if create:
            data["created_by"] = actor_id
        return data

    async def list_fermentations(
        self, *, skip: int, limit: int, batch_no: str | None, status: str | None
    ) -> Any:
        return await self.repo.list_records(
            FermentationRecord,
            skip=skip,
            limit=limit,
            filters={"status": status},
            searches={"batch_no": batch_no or ""},
            order_by="entry_date",
        )

    async def create_fermentation(
        self, payload: FermentationCreate, actor_id: uuid.UUID | None
    ) -> Any:
        self._validate_fermentation(payload.entry_date, payload.discharge_date)
        return await self.repo.create(
            FermentationRecord,
            self._audit(payload.model_dump(), actor_id, create=True),
        )

    async def update_fermentation(
        self,
        record_id: uuid.UUID,
        payload: FermentationUpdate,
        actor_id: uuid.UUID | None,
    ) -> Any:
        current = await self.repo.get(FermentationRecord, record_id)
        if not current:
            return None
        data = payload.model_dump(exclude_unset=True)
        self._validate_fermentation(
            data.get("entry_date", current.entry_date),
            data.get("discharge_date", current.discharge_date),
        )
        return await self.repo.update(
            FermentationRecord, record_id, self._audit(data, actor_id, create=False)
        )

    async def list_seed_cultures(
        self, *, skip: int, limit: int, batch_no: str | None, status: str | None
    ) -> Any:
        return await self.repo.list_records(
            SeedCultureRecord,
            skip=skip,
            limit=limit,
            filters={"status": status},
            searches={"batch_no": batch_no or ""},
            order_by="prepare_date",
        )

    async def create_seed_culture(
        self, payload: SeedCultureCreate, actor_id: uuid.UUID | None
    ) -> Any:
        return await self.repo.create(
            SeedCultureRecord,
            self._audit(payload.model_dump(), actor_id, create=True),
        )

    async def update_seed_culture(
        self,
        record_id: uuid.UUID,
        payload: SeedCultureUpdate,
        actor_id: uuid.UUID | None,
    ) -> Any:
        return await self.repo.update(
            SeedCultureRecord,
            record_id,
            self._audit(payload.model_dump(exclude_unset=True), actor_id, create=False),
        )

    async def list_events(
        self, *, skip: int, limit: int, workshop: str | None, status: str | None
    ) -> Any:
        return await self.repo.list_records(
            NonConformingEvent,
            skip=skip,
            limit=limit,
            filters={"workshop": workshop, "status": status},
            order_by="event_time",
        )

    async def create_event(
        self, payload: NonConformingEventCreate, actor_id: uuid.UUID | None
    ) -> Any:
        data = payload.model_dump()
        self._set_impact_duration(data)
        return await self.repo.create(
            NonConformingEvent, self._audit(data, actor_id, create=True)
        )

    async def update_event(
        self,
        record_id: uuid.UUID,
        payload: NonConformingEventUpdate,
        actor_id: uuid.UUID | None,
    ) -> Any:
        current = await self.repo.get(NonConformingEvent, record_id)
        if not current:
            return None
        data = payload.model_dump(exclude_unset=True)
        merged = {
            "event_time": data.get("event_time", current.event_time),
            "restore_time": data.get("restore_time", current.restore_time),
        }
        self._set_impact_duration(merged)
        if merged.get("impact_duration"):
            data["impact_duration"] = merged["impact_duration"]
        return await self.repo.update(
            NonConformingEvent, record_id, self._audit(data, actor_id, create=False)
        )

    async def close_event(
        self, record_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> Any:
        current = await self.repo.get(NonConformingEvent, record_id)
        if not current:
            return None
        restore_time = current.restore_time or datetime.now(UTC)
        data: dict[str, Any] = {"status": "closed", "restore_time": restore_time}
        duration_data = {"event_time": current.event_time, "restore_time": restore_time}
        self._set_impact_duration(duration_data)
        data["impact_duration"] = duration_data["impact_duration"]
        return await self.repo.update(
            NonConformingEvent, record_id, self._audit(data, actor_id, create=False)
        )

    async def list_shift_logs(
        self, *, skip: int, limit: int, workshop: str | None, shift: str | None
    ) -> Any:
        return await self.repo.list_records(
            ShiftLog,
            skip=skip,
            limit=limit,
            filters={"workshop": workshop, "shift": shift},
            order_by="log_date",
        )

    async def create_shift_log(
        self, payload: ShiftLogCreate, actor_id: uuid.UUID | None
    ) -> Any:
        return await self.repo.create(
            ShiftLog, self._audit(payload.model_dump(), actor_id, create=True)
        )

    async def update_shift_log(
        self, record_id: uuid.UUID, payload: ShiftLogUpdate, actor_id: uuid.UUID | None
    ) -> Any:
        return await self.repo.update(
            ShiftLog,
            record_id,
            self._audit(payload.model_dump(exclude_unset=True), actor_id, create=False),
        )

    async def list_handovers(
        self, *, skip: int, limit: int, workshop: str | None, status: str | None
    ) -> Any:
        return await self.repo.list_records(
            ShiftHandover,
            skip=skip,
            limit=limit,
            filters={"workshop": workshop, "status": status},
            order_by="handover_time",
        )

    async def create_handover(
        self, payload: ShiftHandoverCreate, actor_id: uuid.UUID | None
    ) -> Any:
        return await self.repo.create(
            ShiftHandover, self._audit(payload.model_dump(), actor_id, create=True)
        )

    async def update_handover(
        self,
        record_id: uuid.UUID,
        payload: ShiftHandoverUpdate,
        actor_id: uuid.UUID | None,
    ) -> Any:
        return await self.repo.update(
            ShiftHandover,
            record_id,
            self._audit(payload.model_dump(exclude_unset=True), actor_id, create=False),
        )

    async def confirm_handover(
        self, record_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> Any:
        current = await self.repo.get(ShiftHandover, record_id)
        if not current:
            return None
        if current.status == "confirmed":
            return current
        return await self.repo.update(
            ShiftHandover,
            record_id,
            self._audit(
                {
                    "status": "confirmed",
                    "confirmed_at": datetime.now(UTC),
                    "confirmed_by": actor_id,
                },
                actor_id,
                create=False,
            ),
        )

    async def delete(
        self,
        model: type[
            FermentationRecord
            | SeedCultureRecord
            | NonConformingEvent
            | ShiftLog
            | ShiftHandover
        ],
        record_id: uuid.UUID,
    ) -> Any:
        return await self.repo.soft_delete(model, record_id)

    @staticmethod
    def _validate_fermentation(entry_date: Any, discharge_date: Any) -> None:
        if discharge_date and discharge_date < entry_date:
            raise AppException(status_code=400, message="放罐日期不能早于进罐日期")

    @staticmethod
    def _set_impact_duration(data: dict[str, Any]) -> None:
        start = data.get("event_time")
        end = data.get("restore_time")
        if start and end:
            if end < start:
                raise AppException(status_code=400, message="恢复时间不能早于事件时间")
            minutes = int((end - start).total_seconds() // 60)
            data["impact_duration"] = f"{minutes // 60}小时{minutes % 60}分钟"
