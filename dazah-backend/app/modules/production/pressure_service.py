"""Pressure differential inspection business workflows."""

import logging
import uuid
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.production.pressure_models import (
    DataMaster,
    Notification,
    OcrTask,
    PointMapping,
    PressureRecord,
)
from app.modules.production.pressure_repository import PressureRepository
from app.modules.production.pressure_schemas import (
    AreaExportData,
    AuditRequest,
    AuditStats,
    BatchAuditRequest,
    BatchAuditResponse,
    BatchCreateDataMasterRequest,
    BatchDeleteMergedRowsRequest,
    BatchManualEntryRequest,
    BatchManualEntryResponse,
    CheckUniqueResponse,
    CreateManualRecordRequest,
    CreateOcrRecordRequest,
    CreateOcrTaskRequest,
    DashboardStats,
    DataMasterCreate,
    DataMasterResponse,
    DeleteMergedRowRequest,
    DeleteRecordsResponse,
    MergedPressureResponse,
    MergedPressureRow,
    NotificationListResponse,
    NotificationResponse,
    OcrSubmitResponse,
    OcrTaskResponse,
    PointMappingCreate,
    PointMappingResponse,
    PointMappingUpdate,
    PressureRecordResponse,
    SubmitOcrTaskResultRequest,
    TemplateExportRow,
    UpdateMergedRowRequest,
    UpdateMergedRowResponse,
)

logger = logging.getLogger(__name__)


class PressureService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PressureRepository(session)

    # ─── Dashboard ───

    async def get_dashboard_stats(self) -> DashboardStats:
        stats = await self.repo.get_dashboard_stats()
        return DashboardStats(**stats)

    # ─── PointMapping ───

    async def list_point_mappings(
        self,
        *,
        area: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PointMappingResponse], int]:
        mappings, total = await self.repo.list_point_mappings(
            area=area, keyword=keyword, page=page, page_size=page_size
        )
        return [PointMappingResponse.model_validate(m) for m in mappings], total

    async def get_point_mapping(self, mapping_id: UUID) -> PointMappingResponse:
        mapping = await self.repo.get_point_mapping_by_id(mapping_id)
        if not mapping:
            raise NotFoundException("位点映射", str(mapping_id))
        return PointMappingResponse.model_validate(mapping)

    async def check_unique(self, point_id: str) -> CheckUniqueResponse:
        exists = await self.repo.check_point_id_unique(point_id)
        return CheckUniqueResponse(exists=exists)

    async def create_point_mapping(
        self, data: PointMappingCreate
    ) -> PointMappingResponse:
        exists = await self.repo.check_point_id_unique(data.point_id)
        if exists:
            raise AppException(status_code=409, message=f"位点编号 {data.point_id} 已存在")
        mapping = await self.repo.create_point_mapping(data.model_dump())
        return PointMappingResponse.model_validate(mapping)

    async def update_point_mapping(
        self, mapping_id: UUID, data: PointMappingUpdate
    ) -> PointMappingResponse:
        mapping = await self.repo.get_point_mapping_by_id(mapping_id)
        if not mapping:
            raise NotFoundException("位点映射", str(mapping_id))
        update_data = data.model_dump(exclude_unset=True)
        updated = await self.repo.update_point_mapping(mapping_id, update_data)
        return PointMappingResponse.model_validate(updated)

    async def delete_point_mapping(self, mapping_id: UUID) -> None:
        mapping = await self.repo.get_point_mapping_by_id(mapping_id)
        if not mapping:
            raise NotFoundException("位点映射", str(mapping_id))
        await self.repo.delete_point_mapping(mapping_id)

    # ─── PressureRecord ───

    async def list_records(
        self,
        *,
        area: str | None = None,
        point_id: str | None = None,
        input_type: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PressureRecordResponse], int]:
        records, total = await self.repo.list_records(
            area=area,
            point_id=point_id,
            input_type=input_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
        return [PressureRecordResponse.model_validate(r) for r in records], total

    async def get_record(self, record_id: UUID) -> PressureRecordResponse:
        record = await self.repo.get_record_by_id(record_id)
        if not record:
            raise NotFoundException("压差记录", str(record_id))
        return PressureRecordResponse.model_validate(record)

    async def create_manual_record(
        self, data: CreateManualRecordRequest, creator: str = ""
    ) -> dict:
        # 查找位点映射获取区域和标准压差
        mapping = await self.repo.get_point_mapping_by_point_id(data.point_id)
        area = mapping.area if mapping else "其他"
        standard_pressure = mapping.standard_pressure if mapping else 0

        record = await self.repo.create_record({
            "point_id": data.point_id,
            "area": area,
            "pressure_value": data.pressure_value,
            "standard_pressure": standard_pressure,
            "record_time": data.record_time,
            "input_type": "manual",
            "creator": creator,
            "time_slot": data.time_slot,
            "remark": data.remark,
        })
        return {"id": str(record.id), "success": True}

    async def create_batch_manual(
        self, data: BatchManualEntryRequest, creator: str = ""
    ) -> BatchManualEntryResponse:
        batch_id = str(uuid.uuid4())
        success_count = 0
        fail_count = 0

        # 获取该区域所有位点
        all_points = await self.repo.get_points_by_area(data.area)
        point_map = {p.point_id: p for p in all_points}

        records_to_create = []
        for row in data.rows:
            record_date = datetime.strptime(row.date, "%Y-%m-%d")
            for raw_key, value in row.values.items():
                if value is None:
                    continue

                point_id = raw_key
                time_slot = None
                if data.time_slots:
                    sep_idx = raw_key.rfind("::")
                    if sep_idx > 0:
                        point_id = raw_key[:sep_idx]
                        time_slot = raw_key[sep_idx + 2 :]

                mapping = point_map.get(point_id)
                area = mapping.area if mapping else data.area
                standard_pressure = mapping.standard_pressure if mapping else 0

                records_to_create.append(
                    PressureRecord(
                        point_id=point_id,
                        area=area,
                        pressure_value=int(value),
                        standard_pressure=standard_pressure,
                        record_time=record_date,
                        input_type="manual",
                        creator=creator,
                        batch_id=batch_id,
                        time_slot=time_slot,
                        remark=data.remark,
                    )
                )
                success_count += 1

        if records_to_create:
            await self.repo.create_records_batch(records_to_create)

        return BatchManualEntryResponse(
            success_count=success_count,
            fail_count=fail_count,
            batch_id=batch_id,
        )

    async def create_ocr_records(
        self, data: CreateOcrRecordRequest, creator: str = ""
    ) -> OcrSubmitResponse:
        batch_id = str(uuid.uuid4())
        success_count = 0
        records_to_create = []

        for rec_data in data.records:
            point_id = rec_data.get("point_id", "")
            mapping = await self.repo.get_point_mapping_by_point_id(point_id)
            area = rec_data.get("area", mapping.area if mapping else "其他")
            standard_pressure = rec_data.get(
                "standard_pressure",
                mapping.standard_pressure if mapping else 0,
            )

            record_time = rec_data.get("record_time", datetime.now().isoformat())
            if isinstance(record_time, str):
                try:
                    record_time = datetime.fromisoformat(record_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    record_time = datetime.now()

            records_to_create.append(
                PressureRecord(
                    point_id=point_id,
                    area=area,
                    pressure_value=int(rec_data.get("pressure_value", 0)),
                    standard_pressure=standard_pressure,
                    record_time=record_time,
                    input_type="ocr",
                    creator=creator,
                    image_url=data.image_url,
                    batch_id=batch_id,
                    time_slot=rec_data.get("time_slot"),
                    remark=rec_data.get("remark"),
                )
            )
            success_count += 1

        if records_to_create:
            await self.repo.create_records_batch(records_to_create)

        # 如果关联了 OCR 任务，更新任务状态
        if data.task_id:
            try:
                await self.repo.update_ocr_task(
                    UUID(data.task_id),
                    {"status": "submitted", "batch_id": batch_id},
                )
            except Exception:
                logger.warning(f"更新 OCR 任务状态失败: task_id={data.task_id}")

        return OcrSubmitResponse(
            success_count=success_count,
            fail_count=0,
            success=True,
            batch_id=batch_id,
        )

    async def delete_record(self, record_id: UUID) -> None:
        record = await self.repo.get_record_by_id(record_id)
        if not record:
            raise NotFoundException("压差记录", str(record_id))
        await self.repo.delete_record(record_id)

    async def batch_delete_records(
        self, ids: list[UUID]
    ) -> DeleteRecordsResponse:
        deleted = await self.repo.batch_delete_records(ids)
        return DeleteRecordsResponse(
            success_count=deleted,
            fail_count=len(ids) - deleted,
            success=True,
        )

    # ─── Audit ───

    async def audit_record(
        self, record_id: UUID, data: AuditRequest
    ) -> dict:
        record = await self.repo.get_record_by_id(record_id)
        if not record:
            raise NotFoundException("压差记录", str(record_id))
        await self.repo.audit_record(record_id, data.status, data.reject_reason)
        return {"success": True}

    async def batch_audit(self, data: BatchAuditRequest) -> BatchAuditResponse:
        success = await self.repo.batch_audit_records(
            data.ids, data.status, data.reject_reason
        )
        return BatchAuditResponse(
            success_count=success,
            fail_count=len(data.ids) - success,
            success=True,
        )

    async def get_audit_stats(self) -> AuditStats:
        stats = await self.repo.get_audit_stats()
        return AuditStats(**stats)

    # ─── Merged View ───

    async def list_merged(
        self,
        *,
        area: str | None = None,
        point_id: str | None = None,
        input_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> MergedPressureResponse:
        items, total = await self.repo.list_merged_records(
            area=area,
            point_id=point_id,
            input_type=input_type,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
        return MergedPressureResponse(
            items=[MergedPressureRow(**item) for item in items],
            total=total,
        )

    async def delete_merged_row(self, data: DeleteMergedRowRequest) -> dict:
        deleted = await self.repo.delete_merged_row(data.point_id, data.date)
        return {"success_count": deleted, "success": True}

    async def batch_delete_merged_rows(
        self, data: BatchDeleteMergedRowsRequest
    ) -> dict:
        deleted = await self.repo.batch_delete_merged_rows(
            [r.model_dump() for r in data.rows]
        )
        return {"success_count": deleted, "fail_count": 0, "success": True}

    async def update_merged_row(
        self, data: UpdateMergedRowRequest
    ) -> UpdateMergedRowResponse:
        count = await self.repo.update_merged_row(
            data.point_id, data.date, data.time_slot_values
        )
        return UpdateMergedRowResponse(success_count=count, success=True)

    # ─── Export ───

    async def get_export_by_area(
        self,
        *,
        area: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        point_id: str | None = None,
    ) -> list[AreaExportData]:
        data = await self.repo.get_export_by_area(
            area=area, start_date=start_date, end_date=end_date, point_id=point_id
        )
        return [AreaExportData(**d) for d in data]

    # ─── OcrTask ───

    async def list_ocr_tasks(
        self,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[OcrTaskResponse], int]:
        tasks, total = await self.repo.list_ocr_tasks(
            status=status, page=page, page_size=page_size
        )
        return [OcrTaskResponse.model_validate(t) for t in tasks], total

    async def get_ocr_task(self, task_id: UUID) -> OcrTaskResponse:
        task = await self.repo.get_ocr_task_by_id(task_id)
        if not task:
            raise NotFoundException("OCR 任务", str(task_id))
        return OcrTaskResponse.model_validate(task)

    async def create_ocr_task(
        self, data: CreateOcrTaskRequest, creator: str = ""
    ) -> OcrTaskResponse:
        task = await self.repo.create_ocr_task({
            "image_url": data.image_url,
            "creator": creator,
        })
        # 异步执行 OCR 识别（这里简化为同步，实际可用 Celery 等）
        try:
            await self.repo.update_ocr_task(task.id, {"status": "processing"})
            # TODO: 实际 OCR 识别逻辑，需要集成 Tesseract 或其他 OCR 引擎
            # 暂时标记为完成但无结果
            await self.repo.update_ocr_task(task.id, {
                "status": "completed",
                "result": {"records": []},
            })
            # 创建通知
            await self.repo.create_notification({
                "type": "ocr_completed",
                "title": "OCR 识别完成",
                "message": f"图片识别已完成，请查看结果",
                "target_user_id": creator,
                "related_id": str(task.id),
                "related_type": "ocr_task",
            })
        except Exception as e:
            await self.repo.update_ocr_task(task.id, {
                "status": "failed",
                "error_message": str(e),
            })
            await self.repo.create_notification({
                "type": "ocr_failed",
                "title": "OCR 识别失败",
                "message": f"图片识别失败: {str(e)}",
                "target_user_id": creator,
                "related_id": str(task.id),
                "related_type": "ocr_task",
            })

        updated_task = await self.repo.get_ocr_task_by_id(task.id)
        return OcrTaskResponse.model_validate(updated_task)

    async def submit_ocr_task_result(
        self,
        task_id: UUID,
        data: SubmitOcrTaskResultRequest,
        creator: str = "",
    ) -> OcrSubmitResponse:
        task = await self.repo.get_ocr_task_by_id(task_id)
        if not task:
            raise NotFoundException("OCR 任务", str(task_id))

        ocr_data = CreateOcrRecordRequest(
            records=data.records,
            image_url=task.image_url,
            task_id=str(task_id),
        )
        return await self.create_ocr_records(ocr_data, creator)

    # ─── DataMaster ───

    async def list_data_master(
        self,
        *,
        material_name: str | None = None,
        supplier: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DataMasterResponse], int]:
        items, total = await self.repo.list_data_master(
            material_name=material_name,
            supplier=supplier,
            start_date=start_date,
            end_date=end_date,
            source=source,
            page=page,
            page_size=page_size,
        )
        return [DataMasterResponse.model_validate(i) for i in items], total

    async def get_data_master(self, item_id: UUID) -> DataMasterResponse:
        item = await self.repo.get_data_master_by_id(item_id)
        if not item:
            raise NotFoundException("数据总表记录", str(item_id))
        return DataMasterResponse.model_validate(item)

    async def create_data_master(
        self, data: DataMasterCreate
    ) -> DataMasterResponse:
        item = await self.repo.create_data_master(data.model_dump())
        return DataMasterResponse.model_validate(item)

    async def batch_create_data_master(
        self, data: BatchCreateDataMasterRequest
    ) -> list[DataMasterResponse]:
        items = [DataMaster(**item.model_dump()) for item in data.items]
        created = await self.repo.create_data_master_batch(items)
        return [DataMasterResponse.model_validate(i) for i in created]

    async def update_data_master(
        self, item_id: UUID, data: dict
    ) -> DataMasterResponse:
        item = await self.repo.get_data_master_by_id(item_id)
        if not item:
            raise NotFoundException("数据总表记录", str(item_id))
        updated = await self.repo.update_data_master(item_id, data)
        return DataMasterResponse.model_validate(updated)

    async def delete_data_master(self, item_id: UUID) -> None:
        item = await self.repo.get_data_master_by_id(item_id)
        if not item:
            raise NotFoundException("数据总表记录", str(item_id))
        await self.repo.delete_data_master(item_id)

    async def batch_delete_data_master(
        self, ids: list[UUID]
    ) -> DeleteRecordsResponse:
        deleted = await self.repo.batch_delete_data_master(ids)
        return DeleteRecordsResponse(
            success_count=deleted,
            fail_count=len(ids) - deleted,
            success=True,
        )

    # ─── Notification ───

    async def list_notifications(
        self,
        *,
        user_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> NotificationListResponse:
        items, total = await self.repo.list_notifications(
            user_id=user_id, page=page, page_size=page_size
        )
        unread = await self.repo.get_unread_count(user_id)
        return NotificationListResponse(
            items=[NotificationResponse.model_validate(i) for i in items],
            unread_count=unread,
        )

    async def mark_notification_read(self, notification_id: UUID) -> None:
        await self.repo.mark_read(notification_id)

    async def mark_all_notifications_read(
        self, user_id: str | None = None
    ) -> None:
        await self.repo.mark_all_read(user_id)
