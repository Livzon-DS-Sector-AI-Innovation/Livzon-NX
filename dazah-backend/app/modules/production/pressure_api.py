"""Pressure differential inspection API routes."""

import uuid
from datetime import date, datetime
from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.pressure_schemas import (
    AuditRequest,
    BatchAuditRequest,
    BatchCreateDataMasterRequest,
    BatchDeleteMergedRowsRequest,
    BatchManualEntryRequest,
    CreateManualRecordRequest,
    CreateOcrRecordRequest,
    CreateOcrTaskRequest,
    DataMasterCreate,
    DataMasterUpdate,
    DeleteMergedRowRequest,
    DeleteRecordsRequest,
    PointMappingCreate,
    PointMappingUpdate,
    SubmitOcrTaskResultRequest,
    UpdateMergedRowRequest,
)
from app.modules.production.pressure_service import PressureService
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE
from app.shared.schemas import PageParams

router = create_module_router(MODULES_BY_CODE["production"])


def get_pressure_service(
    session: AsyncSession = Depends(get_db),
) -> PressureService:
    return PressureService(session)


# ═══════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════


@router.get("/pressure/dashboard", summary="压差统计仪表盘")
async def get_dashboard(
    service: PressureService = Depends(get_pressure_service),
):
    stats = await service.get_dashboard_stats()
    return success_response(data=stats.model_dump(mode="json"))


# ═══════════════════════════════════════════════════════
# PointMapping — 位点管理
# ═══════════════════════════════════════════════════════


@router.get("/pressure/point-mappings", summary="位点映射列表")
async def list_point_mappings(
    area: str | None = Query(None, description="区域筛选"),
    keyword: str | None = Query(None, description="位点编号搜索"),
    page_params: PageParams = Depends(),
    service: PressureService = Depends(get_pressure_service),
):
    mappings, total = await service.list_point_mappings(
        area=area, keyword=keyword, page=page_params.page, page_size=page_params.page_size
    )
    data = [m.model_dump(mode="json") for m in mappings]
    return paginated_response(data=data, page=page_params.page, page_size=page_params.page_size, total=total)


@router.get("/pressure/point-mappings/check-unique", summary="检查位点编号唯一性")
async def check_point_id_unique(
    point_id: str = Query(..., description="位点编号"),
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.check_unique(point_id)
    return success_response(data=result.model_dump(mode="json"))


@router.post("/pressure/point-mappings", summary="创建位点映射")
async def create_point_mapping(
    payload: PointMappingCreate,
    service: PressureService = Depends(get_pressure_service),
):
    mapping = await service.create_point_mapping(payload)
    return success_response(data=mapping.model_dump(mode="json"), message="位点创建成功", status_code=201)


@router.get("/pressure/point-mappings/{mapping_id}", summary="位点映射详情")
async def get_point_mapping(
    mapping_id: UUID,
    service: PressureService = Depends(get_pressure_service),
):
    mapping = await service.get_point_mapping(mapping_id)
    return success_response(data=mapping.model_dump(mode="json"))


@router.put("/pressure/point-mappings/{mapping_id}", summary="更新位点映射")
async def update_point_mapping(
    mapping_id: UUID,
    payload: PointMappingUpdate,
    service: PressureService = Depends(get_pressure_service),
):
    mapping = await service.update_point_mapping(mapping_id, payload)
    return success_response(data=mapping.model_dump(mode="json"), message="位点更新成功")


@router.delete("/pressure/point-mappings/{mapping_id}", summary="删除位点映射")
async def delete_point_mapping(
    mapping_id: UUID,
    service: PressureService = Depends(get_pressure_service),
):
    await service.delete_point_mapping(mapping_id)
    return success_response(message="位点删除成功")


# ═══════════════════════════════════════════════════════
# PressureRecord — 压差记录
# ═══════════════════════════════════════════════════════


@router.get("/pressure/records", summary="压差记录列表")
async def list_records(
    area: str | None = Query(None),
    point_id: str | None = Query(None),
    input_type: str | None = Query(None),
    status: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    page_params: PageParams = Depends(),
    service: PressureService = Depends(get_pressure_service),
):
    records, total = await service.list_records(
        area=area,
        point_id=point_id,
        input_type=input_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    data = [r.model_dump(mode="json") for r in records]
    return paginated_response(data=data, page=page_params.page, page_size=page_params.page_size, total=total)


@router.get("/pressure/records/merged", summary="合并压差记录列表")
async def list_merged_records(
    area: str | None = Query(None),
    point_id: str | None = Query(None),
    input_type: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    page_params: PageParams = Depends(),
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.list_merged(
        area=area,
        point_id=point_id,
        input_type=input_type,
        start_date=start_date,
        end_date=end_date,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return paginated_response(
        data=[item.model_dump(mode="json") for item in result.items],
        page=page_params.page,
        page_size=page_params.page_size,
        total=result.total,
    )


@router.get("/pressure/records/export/by-area", summary="按区域导出压差记录")
async def export_by_area(
    area: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    point_id: str | None = Query(None),
    service: PressureService = Depends(get_pressure_service),
):
    data = await service.get_export_by_area(
        area=area, start_date=start_date, end_date=end_date, point_id=point_id
    )
    return success_response(data=[d.model_dump(mode="json") for d in data])


@router.post("/pressure/records/manual", summary="手动录入单条压差记录")
async def create_manual_record(
    payload: CreateManualRecordRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.create_manual_record(payload)
    return success_response(data=result, message="记录创建成功", status_code=201)


@router.post("/pressure/records/manual/batch", summary="批量手动录入压差记录")
async def create_batch_manual(
    payload: BatchManualEntryRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.create_batch_manual(payload)
    return success_response(data=result.model_dump(mode="json"), message="批量录入完成")


@router.post("/pressure/records/ocr", summary="提交 OCR 识别后的压差记录")
async def create_ocr_records(
    payload: CreateOcrRecordRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.create_ocr_records(payload)
    return success_response(data=result.model_dump(mode="json"), message="OCR 记录提交成功")


@router.post("/pressure/records/merged/delete", summary="删除合并行")
async def delete_merged_row(
    payload: DeleteMergedRowRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.delete_merged_row(payload)
    return success_response(data=result)


@router.post("/pressure/records/merged/batch-delete", summary="批量删除合并行")
async def batch_delete_merged_rows(
    payload: BatchDeleteMergedRowsRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.batch_delete_merged_rows(payload)
    return success_response(data=result)


@router.post("/pressure/records/merged/update", summary="更新合并行")
async def update_merged_row(
    payload: UpdateMergedRowRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.update_merged_row(payload)
    return success_response(data=result.model_dump(mode="json"))


@router.get("/pressure/records/{record_id}", summary="压差记录详情")
async def get_record(
    record_id: UUID,
    service: PressureService = Depends(get_pressure_service),
):
    record = await service.get_record(record_id)
    return success_response(data=record.model_dump(mode="json"))


@router.patch("/pressure/records/{record_id}/audit", summary="审核压差记录")
async def audit_record(
    record_id: UUID,
    payload: AuditRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.audit_record(record_id, payload)
    return success_response(data=result, message="审核完成")


@router.patch("/pressure/records/batch-audit", summary="批量审核压差记录")
async def batch_audit(
    payload: BatchAuditRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.batch_audit(payload)
    return success_response(data=result.model_dump(mode="json"), message="批量审核完成")


@router.delete("/pressure/records/{record_id}", summary="删除压差记录")
async def delete_record(
    record_id: UUID,
    service: PressureService = Depends(get_pressure_service),
):
    await service.delete_record(record_id)
    return success_response(message="记录删除成功")


@router.post("/pressure/records/batch-delete", summary="批量删除压差记录")
async def batch_delete_records(
    payload: DeleteRecordsRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.batch_delete_records(payload.ids)
    return success_response(data=result.model_dump(mode="json"))


# ═══════════════════════════════════════════════════════
# Audit Stats
# ═══════════════════════════════════════════════════════


@router.get("/pressure/audit/stats", summary="审核统计")
async def get_audit_stats(
    service: PressureService = Depends(get_pressure_service),
):
    stats = await service.get_audit_stats()
    return success_response(data=stats.model_dump(mode="json"))


# ═══════════════════════════════════════════════════════
# OcrTask — OCR 任务
# ═══════════════════════════════════════════════════════


@router.get("/pressure/ocr-tasks", summary="OCR 任务列表")
async def list_ocr_tasks(
    status: str | None = Query(None),
    page_params: PageParams = Depends(),
    service: PressureService = Depends(get_pressure_service),
):
    tasks, total = await service.list_ocr_tasks(
        status=status, page=page_params.page, page_size=page_params.page_size
    )
    data = [t.model_dump(mode="json") for t in tasks]
    return paginated_response(data=data, page=page_params.page, page_size=page_params.page_size, total=total)


@router.post("/pressure/ocr-tasks", summary="创建 OCR 任务")
async def create_ocr_task(
    payload: CreateOcrTaskRequest,
    service: PressureService = Depends(get_pressure_service),
):
    task = await service.create_ocr_task(payload)
    return success_response(data=task.model_dump(mode="json"), message="OCR 任务创建成功", status_code=201)


@router.get("/pressure/ocr-tasks/{task_id}", summary="OCR 任务详情")
async def get_ocr_task(
    task_id: UUID,
    service: PressureService = Depends(get_pressure_service),
):
    task = await service.get_ocr_task(task_id)
    return success_response(data=task.model_dump(mode="json"))


@router.post("/pressure/ocr-tasks/{task_id}/submit", summary="提交 OCR 任务识别结果")
async def submit_ocr_task_result(
    task_id: UUID,
    payload: SubmitOcrTaskResultRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.submit_ocr_task_result(task_id, payload)
    return success_response(data=result.model_dump(mode="json"), message="OCR 结果提交成功")


# ═══════════════════════════════════════════════════════
# DataMaster — 数据总表
# ═══════════════════════════════════════════════════════


@router.get("/pressure/data-master", summary="数据总表列表")
async def list_data_master(
    material_name: str | None = Query(None),
    supplier: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    source: str | None = Query(None),
    page_params: PageParams = Depends(),
    service: PressureService = Depends(get_pressure_service),
):
    items, total = await service.list_data_master(
        material_name=material_name,
        supplier=supplier,
        start_date=start_date,
        end_date=end_date,
        source=source,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    data = [i.model_dump(mode="json") for i in items]
    return paginated_response(data=data, page=page_params.page, page_size=page_params.page_size, total=total)


@router.post("/pressure/data-master", summary="创建数据总表记录")
async def create_data_master(
    payload: DataMasterCreate,
    service: PressureService = Depends(get_pressure_service),
):
    item = await service.create_data_master(payload)
    return success_response(data=item.model_dump(mode="json"), message="记录创建成功", status_code=201)


@router.post("/pressure/data-master/batch", summary="批量创建数据总表记录")
async def batch_create_data_master(
    payload: BatchCreateDataMasterRequest,
    service: PressureService = Depends(get_pressure_service),
):
    items = await service.batch_create_data_master(payload)
    data = [i.model_dump(mode="json") for i in items]
    return success_response(data=data, message="批量创建成功")


@router.get("/pressure/data-master/{item_id}", summary="数据总表记录详情")
async def get_data_master(
    item_id: UUID,
    service: PressureService = Depends(get_pressure_service),
):
    item = await service.get_data_master(item_id)
    return success_response(data=item.model_dump(mode="json"))


@router.put("/pressure/data-master/{item_id}", summary="更新数据总表记录")
async def update_data_master(
    item_id: UUID,
    payload: DataMasterUpdate,
    service: PressureService = Depends(get_pressure_service),
):
    item = await service.update_data_master(item_id, payload.model_dump(exclude_unset=True))
    return success_response(data=item.model_dump(mode="json"), message="记录更新成功")


@router.delete("/pressure/data-master/{item_id}", summary="删除数据总表记录")
async def delete_data_master(
    item_id: UUID,
    service: PressureService = Depends(get_pressure_service),
):
    await service.delete_data_master(item_id)
    return success_response(message="记录删除成功")


@router.post("/pressure/data-master/batch-delete", summary="批量删除数据总表记录")
async def batch_delete_data_master(
    payload: DeleteRecordsRequest,
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.batch_delete_data_master(payload.ids)
    return success_response(data=result.model_dump(mode="json"))


# ═══════════════════════════════════════════════════════
# Notification — 通知
# ═══════════════════════════════════════════════════════


@router.get("/pressure/notifications", summary="通知列表")
async def list_notifications(
    user_id: str | None = Query(None),
    page_params: PageParams = Depends(),
    service: PressureService = Depends(get_pressure_service),
):
    result = await service.list_notifications(
        user_id=user_id, page=page_params.page, page_size=page_params.page_size
    )
    return success_response(data=result.model_dump(mode="json"))


@router.patch("/pressure/notifications/{notification_id}/read", summary="标记通知已读")
async def mark_notification_read(
    notification_id: UUID,
    service: PressureService = Depends(get_pressure_service),
):
    await service.mark_notification_read(notification_id)
    return success_response(message="已标记为已读")


@router.patch("/pressure/notifications/read-all", summary="全部标记已读")
async def mark_all_read(
    user_id: str | None = Query(None),
    service: PressureService = Depends(get_pressure_service),
):
    await service.mark_all_notifications_read(user_id)
    return success_response(message="全部标记已读")
