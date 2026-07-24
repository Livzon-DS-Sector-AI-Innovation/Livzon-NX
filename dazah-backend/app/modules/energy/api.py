"""HTTP API for the read-only Energy Wiki ingestion module."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.modules.energy.models import EnergyFeishuPageBinding
from app.modules.energy.schemas import (
    EnergyApiResponse,
    EnergyFeishuConfigResponse,
    EnergyFeishuConfigUpsert,
    EnergyFeishuConnectivityResult,
    EnergyFeishuSourceRootInput,
    EnergyFeishuSourceRootResponse,
    EnergyFeishuSourceRootUpdate,
    EnergyMappingPreviewResponse,
    EnergyOverviewResponse,
    EnergySheetMappingResponse,
    EnergySheetMappingUpsert,
    EnergySnapshotResponse,
    EnergySnapshotRowResponse,
    EnergySnapshotRowsData,
    EnergySourceBatchRequest,
    EnergySourceDeleteResult,
    EnergySourceDocumentResponse,
    EnergySourceSheetResponse,
    EnergySyncRunResponse,
    EnergySyncTriggerRequest,
    OverviewScope,
)
from app.modules.energy.wiki_service import EnergyWikiService
from app.platform.identity.deps import AdminUser
from app.platform.integrations.feishu.page_keys import validate_module_page_key
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["energy"])


def _validate_page_key(page_key: str) -> None:
    validate_module_page_key(page_key, "energy")


class EnergyPageBindingInput(BaseModel):
    resource_id: UUID
    tab_name: str = Field(min_length=1, max_length=255)
    sort_order: int = 0
    is_default: bool = False
    is_enabled: bool = True
    visible_field_ids: list[str] = Field(default_factory=list)


class EnergyPageBindingReplace(BaseModel):
    bindings: list[EnergyPageBindingInput]


def _energy_field_id(index: int, name: str) -> str:
    digest = hashlib.sha256(f"{index}:{name}".encode()).hexdigest()[:16]
    return f"energy_col_{digest}"


def _render_energy_cell(header: str, value: object) -> object:
    """Render spreadsheet date serials without changing the stored raw snapshot."""
    normalized_header = header.strip()
    is_date_field = "日期" in normalized_header or normalized_header in {
        "时间",
        "日期时间",
        "时间日期",
    }
    if (
        not is_date_field
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        return value
    if not 1 <= float(value) <= 2_958_465:
        return value
    rendered = datetime(1899, 12, 30) + timedelta(days=float(value))
    if rendered.time() == datetime.min.time():
        return rendered.date().isoformat()
    return rendered.isoformat(sep=" ", timespec="seconds")


def _service(db: AsyncSession) -> EnergyWikiService:
    return EnergyWikiService(db)


@router.get(
    "/feishu-config",
    summary="获取能源 Wiki 飞书配置",
    response_model=EnergyApiResponse[EnergyFeishuConfigResponse],
)
async def get_feishu_config(
    _admin: AdminUser, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    data = await _service(db).get_config()
    return success_response(data.model_dump(mode="json"))


@router.put(
    "/feishu-config",
    summary="保存能源 Wiki 飞书配置",
    response_model=EnergyApiResponse[EnergyFeishuConfigResponse],
)
async def save_feishu_config(
    payload: EnergyFeishuConfigUpsert,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    data = await _service(db).save_config(payload)
    return success_response(data.model_dump(mode="json"))


@router.get(
    "/feishu/roots",
    summary="查询能源飞书 Wiki/Base 入口",
    response_model=EnergyApiResponse[list[EnergyFeishuSourceRootResponse]],
)
async def list_energy_feishu_roots(
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    roots = await _service(db).list_source_roots()
    return success_response([item.model_dump(mode="json") for item in roots])


@router.post(
    "/feishu/roots",
    summary="新增能源飞书 Wiki/Base 入口",
    response_model=EnergyApiResponse[EnergyFeishuSourceRootResponse],
)
async def create_energy_feishu_root(
    payload: EnergyFeishuSourceRootInput,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    root = await _service(db).create_source_root(payload)
    return success_response(root.model_dump(mode="json"))


@router.delete("/feishu/roots/{root_id}", summary="停用能源飞书入口")
async def delete_energy_feishu_root(
    root_id: UUID,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await _service(db).delete_source_root(root_id)
    return success_response({"id": str(root_id)})


@router.put(
    "/feishu/roots/{root_id}",
    summary="修改能源飞书 Wiki/Base 入口",
    response_model=EnergyApiResponse[EnergyFeishuSourceRootResponse],
)
async def update_energy_feishu_root(
    root_id: UUID,
    payload: EnergyFeishuSourceRootUpdate,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    root = await _service(db).update_source_root(root_id, payload)
    return success_response(root.model_dump(mode="json"))


@router.post(
    "/feishu-config/test",
    summary="测试能源 Wiki 飞书连通性",
    response_model=EnergyApiResponse[EnergyFeishuConnectivityResult],
)
async def test_feishu_config(
    _admin: AdminUser, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    data = await _service(db).test_connectivity()
    return success_response(data.model_dump(mode="json"))


@router.post(
    "/sync-runs",
    summary="手动触发能源 Wiki 同步",
    response_model=EnergyApiResponse[EnergySyncRunResponse],
)
async def trigger_sync(
    payload: EnergySyncTriggerRequest,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    run = await _service(db).trigger_sync(force=payload.force)
    return success_response(
        EnergySyncRunResponse.model_validate(run).model_dump(mode="json"),
        message="同步任务已完成",
    )


@router.get(
    "/sync-runs",
    summary="查询能源 Wiki 同步运行记录",
    response_model=EnergyApiResponse[list[EnergySyncRunResponse]],
)
async def list_sync_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    runs, total = await _service(db).list_sync_runs(page=page, page_size=page_size)
    return paginated_response(
        [
            EnergySyncRunResponse.model_validate(run).model_dump(mode="json")
            for run in runs
        ],
        page,
        page_size,
        total,
    )


@router.get(
    "/sources/documents",
    summary="查询已发现的 Wiki 月度文档",
    response_model=EnergyApiResponse[list[EnergySourceDocumentResponse]],
)
async def list_source_documents(
    period_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    documents = await _service(db).list_documents(period_month=period_month)
    return success_response(
        [
            EnergySourceDocumentResponse.model_validate(document).model_dump(
                mode="json"
            )
            for document in documents
        ]
    )


@router.get(
    "/sources",
    summary="查询能源来源工作表",
    response_model=EnergyApiResponse[list[EnergySourceSheetResponse]],
)
async def list_source_sheets(
    period_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    mapping_status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    rows = await _service(db).list_sources(
        period_month=period_month, mapping_status=mapping_status
    )
    data = []
    service = _service(db)
    for sheet, document in rows:
        mapping = await service.get_mapping(sheet.id)
        data.append(
            EnergySourceSheetResponse(
                **EnergySourceSheetResponse.model_validate(sheet).model_dump(
                    exclude={"source_role", "document_title", "period_month"}
                ),
                source_role=mapping.source_role if mapping else None,
                document_title=document.title,
                period_month=document.period_month,
            ).model_dump(mode="json")
        )
    return success_response(data)


@router.post(
    "/sources/batch-sync",
    summary="批量同步能源资源",
    response_model=EnergyApiResponse[EnergySyncRunResponse],
)
async def batch_sync_source_sheets(
    payload: EnergySourceBatchRequest,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    run = await _service(db).sync_sources(payload.sheet_ids)
    return success_response(
        EnergySyncRunResponse.model_validate(run).model_dump(mode="json"),
        message="批量同步已完成",
    )


@router.delete(
    "/sources/batch",
    summary="批量删除能源资源及本地数据",
    response_model=EnergyApiResponse[EnergySourceDeleteResult],
)
async def batch_delete_source_sheets(
    payload: EnergySourceBatchRequest,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await _service(db).delete_sources(payload.sheet_ids)
    return success_response(result, message="资源及本地数据已删除")


@router.delete(
    "/sources/{sheet_id}",
    summary="删除能源资源及本地数据",
    response_model=EnergyApiResponse[EnergySourceDeleteResult],
)
async def delete_source_sheet(
    sheet_id: UUID,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await _service(db).delete_sources([sheet_id])
    return success_response(result, message="资源及本地数据已删除")


@router.get(
    "/sources/{sheet_id}/snapshots",
    summary="查询工作表快照",
    response_model=EnergyApiResponse[list[EnergySnapshotResponse]],
)
async def list_sheet_snapshots(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    snapshots = await _service(db).list_snapshots(sheet_id)
    return success_response(
        [
            EnergySnapshotResponse.model_validate(item).model_dump(mode="json")
            for item in snapshots
        ]
    )


@router.get(
    "/sources/{sheet_id}/mapping",
    summary="获取工作表字段映射",
    response_model=EnergyApiResponse[EnergySheetMappingResponse | None],
)
async def get_sheet_mapping(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    mapping = await _service(db).get_mapping(sheet_id)
    return success_response(
        EnergySheetMappingResponse.model_validate(mapping).model_dump(mode="json")
        if mapping
        else None
    )


@router.post(
    "/sources/{sheet_id}/mapping/preview",
    summary="预览字段映射",
    response_model=EnergyApiResponse[EnergyMappingPreviewResponse],
)
async def preview_sheet_mapping(
    sheet_id: UUID,
    payload: EnergySheetMappingUpsert,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    data = await _service(db).preview_mapping(sheet_id, payload)
    return success_response(data.model_dump(mode="json"))


@router.put(
    "/sources/{sheet_id}/mapping",
    summary="保存工作表字段映射",
    response_model=EnergyApiResponse[EnergySheetMappingResponse],
)
async def save_sheet_mapping(
    sheet_id: UUID,
    payload: EnergySheetMappingUpsert,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    mapping = await _service(db).save_mapping(sheet_id, payload)
    return success_response(
        EnergySheetMappingResponse.model_validate(mapping).model_dump(mode="json")
    )


@router.get(
    "/snapshots/{snapshot_id}/rows",
    summary="分页读取原始快照行",
    response_model=EnergyApiResponse[EnergySnapshotRowsData],
)
async def list_snapshot_rows(
    snapshot_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    snapshot, rows, total = await _service(db).list_snapshot_rows(
        snapshot_id=snapshot_id, page=page, page_size=page_size
    )
    return success_response(
        data={
            "snapshot": EnergySnapshotResponse.model_validate(snapshot).model_dump(
                mode="json"
            ),
            "rows": [
                EnergySnapshotRowResponse.model_validate(row).model_dump(mode="json")
                for row in rows
            ],
        },
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/page-data/{page_key}", summary="读取能源统一数据页绑定")
async def get_energy_page_data(
    page_key: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _validate_page_key(page_key)
    service = _service(db)
    sources = await service.list_sources(period_month=None, mapping_status=None)
    source_by_id = {sheet.id: (sheet, document) for sheet, document in sources}
    published = await service.repo.list_page_bindings(page_key)
    selected = [
        (binding, source_by_id[binding.sheet_id])
        for binding in published
        if binding.sheet_id in source_by_id
    ]
    bindings = []
    for binding, (sheet, document) in selected:
        snapshot = await service.repo.get_latest_snapshot(sheet.id)
        bindings.append(
            {
                "id": str(binding.id),
                "page_key": page_key,
                "table_pk": str(sheet.id),
                "resource_id": str(sheet.id),
                "tab_label": binding.tab_name,
                "tab_name": binding.tab_name,
                "display_order": binding.sort_order,
                "sort_order": binding.sort_order,
                "is_default": binding.is_default,
                "visible_field_ids": binding.visible_field_ids,
                "default_sort": [],
                "history_mode": "daily_snapshot",
                "is_enabled": binding.is_enabled,
                "status": "published",
                "table": {
                    "id": str(sheet.id),
                    "business_domain": "energy",
                    "app_token": document.document_token or "",
                    "table_id": sheet.external_sheet_id,
                    "name": sheet.title,
                    "source_path": document.node_path,
                    "field_count": len(sheet.headers),
                    "record_count": snapshot.row_count if snapshot else 0,
                    "active_mirror_version": str(snapshot.id) if snapshot else None,
                    "last_synced_at": sheet.last_synced_at,
                    "sync_status": "success" if snapshot else "pending",
                    "sync_error": None,
                    "is_enabled": True,
                },
            }
        )
    return success_response({"page_key": page_key, "bindings": bindings})


@router.put("/page-data/{page_key}", summary="发布能源菜单页面的数据表绑定")
async def replace_energy_page_data(
    page_key: str,
    payload: EnergyPageBindingReplace,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _validate_page_key(page_key)
    service = _service(db)
    seen: set[UUID] = set()
    rows: list[EnergyFeishuPageBinding] = []
    default_seen = False
    for index, item in enumerate(payload.bindings):
        if item.resource_id in seen:
            raise AppException(
                message="同一页面不能重复绑定同一数据表", status_code=400
            )
        seen.add(item.resource_id)
        await service.get_sheet_or_raise(item.resource_id)
        is_default = item.is_default and not default_seen
        default_seen = default_seen or is_default
        rows.append(
            EnergyFeishuPageBinding(
                page_key=page_key,
                sheet_id=item.resource_id,
                tab_name=item.tab_name.strip(),
                sort_order=item.sort_order if item.sort_order else index,
                is_default=is_default,
                is_enabled=item.is_enabled,
                visible_field_ids=item.visible_field_ids,
            )
        )
    if rows and not default_seen:
        rows[0].is_default = True
    await service.repo.replace_page_bindings(page_key, rows)
    await db.commit()
    return await get_energy_page_data(page_key=page_key, db=db)


@router.get(
    "/page-data/{page_key}/{binding_id}/records",
    summary="分页读取能源工作表本地快照",
)
async def get_energy_page_records(
    page_key: str,
    binding_id: UUID,
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _validate_page_key(page_key)
    service = _service(db)
    binding = await service.repo.get_page_binding(page_key, binding_id)
    if binding is None:
        raise AppException(message="页面数据表绑定不存在", status_code=404)
    sheet = await service.get_sheet_or_raise(binding.sheet_id)
    snapshot = await service.repo.get_latest_snapshot(sheet.id)
    if snapshot is None:
        return success_response(
            {
                "dataset": None,
                "fields": [],
                "records": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0},
            }
        )
    headers = snapshot.header_values or sheet.headers
    fields = [
        {
            "field_id": _energy_field_id(index, name),
            "field_name": name or f"第 {index + 1} 列",
            "type": None,
            "property": None,
            "display_order": index,
        }
        for index, name in enumerate(headers)
    ]
    if keyword:
        all_rows = await service.repo.list_all_snapshot_rows(snapshot.id)
        matched_rows = [
            row
            for row in all_rows
            if keyword.casefold() in " ".join(map(str, row.values)).casefold()
        ]
        total = len(matched_rows)
        rows = matched_rows[(page - 1) * page_size : page * page_size]
    else:
        rows, total = await service.repo.list_snapshot_rows(
            snapshot_id=snapshot.id, page=page, page_size=page_size
        )
    records = []
    for row in rows:
        display_values = getattr(row, "display_values", None) or row.values
        values = {
            (headers[index] or f"第 {index + 1} 列"): _render_energy_cell(
                headers[index] or f"第 {index + 1} 列", value
            )
            for index, value in enumerate(display_values)
            if index < len(headers)
        }
        normalized_values = {
            (headers[index] or f"第 {index + 1} 列"): value
            for index, value in enumerate(row.values)
            if index < len(headers)
        }
        records.append(
            {
                "record_id": str(row.row_index),
                "fields": values,
                "normalized_fields": normalized_values,
                "created_time": None,
                "last_modified_time": None,
            }
        )
    document = await service.repo.get_document_by_id(sheet.document_id)
    dataset = {
        "id": str(sheet.id),
        "page_key": page_key,
        "table_pk": str(sheet.id),
        "tab_label": sheet.title,
        "display_order": sheet.sheet_index,
        "is_default": False,
        "visible_field_ids": [],
        "default_sort": [],
        "history_mode": "daily_snapshot",
        "is_enabled": True,
        "status": "published",
        "table": {
            "id": str(sheet.id),
            "business_domain": "energy",
            "app_token": document.document_token if document else "",
            "table_id": sheet.external_sheet_id,
            "name": sheet.title,
            "source_path": document.node_path if document else [],
            "field_count": len(fields),
            "record_count": total,
            "active_mirror_version": str(snapshot.id),
            "last_synced_at": sheet.last_synced_at,
            "sync_status": "success",
            "sync_error": None,
            "is_enabled": True,
        },
    }
    return success_response(
        {
            "dataset": dataset,
            "fields": fields,
            "records": records,
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }
    )


@router.get(
    "/overview",
    summary="能源 Wiki 数据分析总览",
    response_model=EnergyApiResponse[EnergyOverviewResponse],
)
async def get_overview(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    energy_type: str | None = Query(default=None),
    group_by: str | None = Query(default=None),
    source_scope: OverviewScope = Query(default="detail"),
    workshop: str | None = Query(default=None, max_length=128),
    source_sheet_title: str | None = Query(default=None, max_length=256),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    data = await _service(db).get_overview(
        start=start_time,
        end=end_time,
        energy_type=energy_type,
        group_by=group_by,
        source_scope=source_scope,
        workshop=workshop,
        source_sheet_title=source_sheet_title,
    )
    return success_response(data.model_dump(mode="json"))
