import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_factory, get_db
from app.core.redis import acquire_lock, release_lock, renew_lock
from app.core.response import paginated_response, success_response
from app.modules.procurement.contract_generator import (
    get_contract_template_metadata,
)
from app.modules.procurement.material_source import (
    MaterialSourceConflictError,
    MaterialSourceError,
    MaterialSourceNotConfiguredError,
    ensure_material_source_sync_enabled,
    get_material_source_config,
    list_material_catalog,
    list_material_options,
    mark_sync_failed,
    save_material_source_config,
    sync_material_source,
    test_material_source_config,
)
from app.modules.procurement.schemas import (
    ContractCategory,
    ContractGenerateRequest,
    ContractRecordApiResponse,
    ContractRecordListResponse,
    ContractRecordResponse,
    ContractTemplateMetadata,
    InvoiceRecognitionRecordDeleteRequest,
    InvoiceRecognitionRecordDeleteResponse,
    InvoiceRecognitionRecordDeleteResult,
    InvoiceRecognitionRecordListResponse,
    InvoiceRecognitionRecordResponse,
    InvoiceRecognitionResponse,
    MaterialCatalogListMeta,
    MaterialCatalogListResponse,
    MaterialCatalogRecordResponse,
    MaterialOptionListResponse,
    MaterialSourceConfigApiResponse,
    MaterialSourceConfigResponse,
    MaterialSourceConfigUpsert,
    MaterialSourceProbeApiResponse,
    MaterialSourceProbeResponse,
    MaterialSourceSyncApiResponse,
    MaterialSourceSyncResult,
    PurchaseApprovalRequest,
    PurchaseApprovalRole,
    PurchaseApprovalView,
    PurchaseOrderListResponse,
    PurchaseRequestApiResponse,
    PurchaseRequestCategory,
    PurchaseRequestCreate,
    PurchaseRequestDeleteResponse,
    PurchaseRequestDeleteResult,
    PurchaseRequestImportResponse,
    PurchaseRequestListResponse,
    PurchaseRequestStatus,
    PurchaseRequestUpdate,
    SupplierImportResponse,
    SupplierListResponse,
)
from app.modules.procurement.service import (
    PURCHASE_CATEGORY_LABELS,
    DuplicateInvoiceError,
    approve_purchase_request,
    batch_delete_invoice_recognition_records,
    create_purchase_request,
    delete_invoice_recognition_record,
    delete_purchase_request,
    export_purchase_order_lines_xlsx,
    generate_and_store_contract,
    get_contract_record,
    get_contract_record_file,
    get_purchase_request,
    import_purchase_request_table_file,
    import_supplier_table_file,
    list_contract_records,
    list_invoice_recognition_records,
    list_purchase_order_lines,
    list_purchase_requests,
    list_suppliers,
    recognize_and_store_invoice_pdf,
    reject_purchase_request,
    submit_purchase_request,
    update_purchase_request,
)
from app.platform.audit.service import record_audit_log
from app.platform.identity.deps import AdminUser
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["procurement"])

logger = logging.getLogger(__name__)

settings = get_settings()
MAX_INVOICE_PDF_UPLOAD_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
INVOICE_UPLOAD_CHUNK_SIZE = 1024 * 1024


def _material_source_error(exc: MaterialSourceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.public_message)


def _masked_identifier(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


@router.get(
    "/material-source-config",
    summary="获取采购物料数据源配置",
    description="仅系统管理员可查看采购物料联想使用的飞书多维表格配置。",
    response_model=MaterialSourceConfigApiResponse,
)
async def get_material_source_config_record(
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    config = await get_material_source_config(db)
    data = (
        MaterialSourceConfigResponse.model_validate(config).model_dump(mode="json")
        if config is not None
        else None
    )
    return success_response(data=data)


@router.post(
    "/material-source-config/test",
    summary="测试采购物料数据源",
    description="测试飞书多维表格链接、访问权限和物料字段映射。",
    response_model=MaterialSourceProbeApiResponse,
)
async def test_material_source_config_record(
    _admin: AdminUser,
    payload: MaterialSourceConfigUpsert | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        ensure_material_source_sync_enabled()
        probe = await test_material_source_config(db, payload)
    except MaterialSourceError as exc:
        raise _material_source_error(exc) from exc
    return success_response(
        data=MaterialSourceProbeResponse.model_validate(probe.as_dict()).model_dump(
            mode="json"
        )
    )


@router.put(
    "/material-source-config",
    summary="保存采购物料数据源配置",
    description="仅系统管理员可保存配置；保存前会测试飞书访问和必需字段。",
    response_model=MaterialSourceConfigApiResponse,
)
async def save_material_source_config_record(
    payload: MaterialSourceConfigUpsert,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        ensure_material_source_sync_enabled()
        config = await save_material_source_config(
            db,
            payload,
            user_id=admin.id,
        )
    except MaterialSourceError as exc:
        raise _material_source_error(exc) from exc

    await record_audit_log(
        db,
        action="procurement_material_source_config_updated",
        user_id=admin.id,
        resource_type="procurement_material_source_config",
        resource_id=config.id,
        new_value={
            "table_id": _masked_identifier(config.table_id),
            "view_id": _masked_identifier(config.view_id),
            "field_mapping": {
                "material_code": config.material_code_field,
                "material_description": config.material_description_field,
                "rule_model": config.rule_model_field,
            },
            "last_test_status": config.last_test_status,
        },
    )
    # save 内部 flush 后 updated_at 等 onupdate 列已过期，直接序列化会触发
    # 异步 session 的同步懒加载（MissingGreenlet）；重新查询以获取完整属性。
    refreshed_config = await get_material_source_config(db)
    if refreshed_config is None:
        raise HTTPException(status_code=404, detail="采购物料数据源配置不存在")
    config = refreshed_config
    return success_response(
        data=MaterialSourceConfigResponse.model_validate(config).model_dump(
            mode="json"
        ),
        message="采购物料数据源配置已保存",
    )


MATERIAL_SYNC_LOCK_TTL_SECONDS = 1800
MATERIAL_SYNC_LOCK_RENEW_INTERVAL_SECONDS = 60.0


def _material_sync_lock_key(config_id: UUID) -> str:
    return f"procurement:material-source-sync:{config_id}"


async def _lock_heartbeat(lock_key: str) -> None:
    """后台同步期间定期续期 Redis 锁，防止慢同步超过锁 TTL 后被并发触发。"""
    try:
        while True:
            await asyncio.sleep(MATERIAL_SYNC_LOCK_RENEW_INTERVAL_SECONDS)
            await renew_lock(lock_key, MATERIAL_SYNC_LOCK_TTL_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Material sync lock renewal failed: %s",
            type(exc).__name__,
        )


async def clear_stale_material_sync_lock() -> None:
    """应用启动时释放残留的物料同步锁。

    后台任务随进程被杀后，Redis 锁会残留至 TTL 过期；数据库状态由
    reset_interrupted_syncs 重置，这里一并清掉锁，避免误报“正在进行中”。
    """
    try:
        async with async_session_factory() as session:
            config = await get_material_source_config(session)
        if config is None:
            return
        await release_lock(_material_sync_lock_key(config.id))
    except Exception as exc:
        logger.warning(
            "Failed to clear stale material sync lock: %s",
            type(exc).__name__,
        )


async def _run_material_source_sync(config_id: UUID, user_id: UUID) -> None:
    """后台执行物料同步：独立会话、记录审计、失败落库、释放同步锁。

    同步状态由 sync_material_source 写入，后台任务的生命周期与请求解耦，
    请求侧不会因同步耗时超时。
    """
    lock_key = _material_sync_lock_key(config_id)
    heartbeat_task = asyncio.create_task(_lock_heartbeat(lock_key))
    try:
        async with async_session_factory() as session:
            try:
                result = await sync_material_source(session, user_id=user_id)
            except MaterialSourceError as exc:
                logger.error(
                    "Material source sync failed: %s (%s)",
                    exc.public_message,
                    type(exc).__name__,
                )
                return
            except Exception:
                logger.exception("Material source sync crashed")
                await mark_sync_failed(
                    session,
                    config_id,
                    "物料数据同步过程中发生内部错误，请稍后重试",
                )
                return
            try:
                await record_audit_log(
                    session,
                    action="procurement_material_source_synced",
                    user_id=user_id,
                    resource_type="procurement_material_source_config",
                    resource_id=config_id,
                    new_value={
                        "synced_count": result.synced_count,
                        "deactivated_count": result.deactivated_count,
                        "sync_status": result.config.sync_status,
                    },
                )
                await session.commit()
            except Exception:
                logger.exception("Material source sync audit failed")
                await session.rollback()
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        try:
            await release_lock(lock_key)
        except Exception as exc:
            logger.warning(
                "Material source sync lock release failed: %s",
                type(exc).__name__,
            )


@router.post(
    "/material-source-config/sync",
    summary="同步采购物料数据源",
    description=(
        "仅系统管理员可将已保存的飞书多维表格数据同步到物料编码库本地镜像。"
        "同步在后台执行，接口立即返回当前配置状态，前端轮询同步结果。"
    ),
    response_model=MaterialSourceSyncApiResponse,
)
async def sync_material_source_record(
    admin: AdminUser,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        ensure_material_source_sync_enabled()
    except MaterialSourceError as exc:
        raise _material_source_error(exc) from exc
    config = await get_material_source_config(db)
    if config is None:
        raise _material_source_error(
            MaterialSourceNotConfiguredError("物料数据源尚未配置")
        )

    lock_key = _material_sync_lock_key(config.id)
    lock_acquired: bool | None
    try:
        lock_acquired = await acquire_lock(
            lock_key,
            timeout=MATERIAL_SYNC_LOCK_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "Redis unavailable for material sync lock: %s",
            type(exc).__name__,
        )
        lock_acquired = None
    if lock_acquired is False and config.sync_status != "syncing":
        # 进程被杀/容器重启后 Redis 锁可能残留至 TTL 过期，而数据库状态
        # 已由启动清理重置；此时锁是陈旧的，释放后重试一次再判定冲突。
        logger.warning("Material sync lock appears stale, releasing and retrying")
        try:
            await release_lock(lock_key)
        except Exception as exc:
            logger.warning(
                "Material sync stale lock release failed: %s",
                type(exc).__name__,
            )
        try:
            lock_acquired = await acquire_lock(
                lock_key,
                timeout=MATERIAL_SYNC_LOCK_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "Redis unavailable for material sync lock: %s",
                type(exc).__name__,
            )
            lock_acquired = None
    if lock_acquired is False:
        raise _material_source_error(
            MaterialSourceConflictError("物料数据同步正在进行中，请稍后重试")
        )
    if lock_acquired is None:
        raise _material_source_error(
            MaterialSourceConflictError("同步依赖的 Redis 当前不可用，请稍后重试")
        )

    config.sync_status = "syncing"
    config.sync_phase = "fetching"
    config.sync_error = None
    config.sync_total_records = None
    config.sync_fetched_count = 0
    config.sync_persisted_count = 0
    config.sync_heartbeat_at = datetime.now(UTC)
    await db.commit()
    background_tasks.add_task(
        _run_material_source_sync,
        config_id=config.id,
        user_id=admin.id,
    )
    # commit 后 updated_at 等 onupdate 列被标记过期，直接序列化会触发异步
    # session 的同步懒加载（MissingGreenlet）；重新查询以获取完整属性。
    config = await get_material_source_config(db)
    data = MaterialSourceSyncResult(
        config=MaterialSourceConfigResponse.model_validate(config),
        synced_count=0,
        deactivated_count=0,
    )
    return success_response(
        data=data.model_dump(mode="json"),
        message="采购物料数据同步已启动",
    )


@router.get(
    "/material-catalog",
    summary="查询物料编码库",
    description="查询采购设置同步到本地的物料编码库，支持关键词和字段筛选。",
    response_model=MaterialCatalogListResponse,
)
async def list_material_catalog_records(
    keyword: str | None = Query(None, max_length=100, description="搜索关键词"),
    material_code: str | None = Query(None, max_length=255, description="物料编码"),
    material_description: str | None = Query(
        None,
        max_length=255,
        description="物料说明",
    ),
    rule_model: str | None = Query(None, max_length=255, description="规格型号"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        records, total, config = await list_material_catalog(
            db,
            keyword=keyword,
            material_code=material_code,
            material_description=material_description,
            rule_model=rule_model,
            page=page,
            page_size=page_size,
        )
    except MaterialSourceError as exc:
        raise _material_source_error(exc) from exc

    meta = MaterialCatalogListMeta(
        page=page,
        page_size=page_size,
        total=total,
        sync_status=config.sync_status,
        sync_error=config.sync_error,
        last_synced_at=config.last_synced_at,
        last_sync_record_count=config.last_sync_record_count,
        sync_total_records=config.sync_total_records,
        sync_fetched_count=config.sync_fetched_count,
    )
    return success_response(
        data=[
            MaterialCatalogRecordResponse.model_validate(record).model_dump(mode="json")
            for record in records
        ],
        meta=meta.model_dump(mode="json"),
    )


@router.get(
    "/material-options",
    summary="联想采购物料编码",
    description="按物料编码关键词实时查询飞书多维表格，最多返回 20 条且保留重复记录。",
    response_model=MaterialOptionListResponse,
)
async def list_material_option_records(
    keyword: str = Query(
        ...,
        min_length=1,
        max_length=64,
        description="物料编码关键词",
    ),
    limit: int = Query(default=20, ge=1, le=20, description="返回数量上限"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        options = await list_material_options(db, keyword=keyword, limit=limit)
    except MaterialSourceError as exc:
        raise _material_source_error(exc) from exc
    return success_response(data=options)


@router.post(
    "/invoices/recognize",
    summary="识别采购发票 PDF",
    description=(
        "从电子发票 PDF 中识别发票号码、开票日期、销售方名称、"
        "税额合计和价税合计（小写）。开启明细识别时额外识别项目名称、单位和数量。"
    ),
    response_model=InvoiceRecognitionResponse,
)
async def recognize_invoice(
    include_details: bool = Form(False, description="是否识别发票明细"),
    file: UploadFile = File(..., description="电子发票 PDF 文件"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    filename = file.filename or ""
    allowed_content_types = {"application/pdf", "application/octet-stream"}
    if file.content_type not in allowed_content_types and not filename.lower().endswith(
        ".pdf"
    ):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件")

    pdf_bytes = await _read_upload_file_with_limit(file)
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        result = await recognize_and_store_invoice_pdf(
            db,
            pdf_bytes,
            file_name=filename,
            include_details=include_details,
        )
    except DuplicateInvoiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"发票识别失败：{exc}") from exc

    return success_response(
        data=InvoiceRecognitionRecordResponse.model_validate(result).model_dump(
            mode="json"
        )
    )


async def _read_upload_file_with_limit(
    file: UploadFile,
    *,
    file_label: str = "PDF 文件",
) -> bytes:
    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await file.read(INVOICE_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_INVOICE_PDF_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{file_label}不能超过 {settings.MAX_UPLOAD_SIZE_MB}MB",
            )
        chunks.append(chunk)

    return b"".join(chunks)


@router.get(
    "/suppliers",
    summary="查询供应商清单",
    description="查询导入的供应商清单，支持按供应商、物料、厂家、品类和原始字段关键词检索。",
    response_model=SupplierListResponse,
)
async def list_supplier_records(
    keyword: str | None = Query(None, description="跨字段关键词"),
    supplier_name: str | None = Query(None, description="供应商名称"),
    material_name: str | None = Query(None, description="物料名称"),
    purchase_category: str | None = Query(None, description="采购品类名称"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    suppliers, total, columns = await list_suppliers(
        db,
        keyword=keyword,
        supplier_name=supplier_name,
        material_name=material_name,
        purchase_category=purchase_category,
        page=page,
        page_size=page_size,
    )
    data = [supplier.model_dump(mode="json") for supplier in suppliers]
    return success_response(
        data=data,
        meta={
            "page": page,
            "page_size": page_size,
            "total": total,
            "columns": columns,
        },
    )


@router.post(
    "/suppliers/import",
    summary="导入供应商清单表格",
    description=(
        "上传 xlsx、xlsm、csv 或 tsv 表格文件，按文件表头读取字段并替换当前供应商清单。"
    ),
    response_model=SupplierImportResponse,
)
async def import_supplier_records(
    file: UploadFile = File(..., description="供应商清单表格文件"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    filename = file.filename or ""
    allowed_extensions = (".xlsx", ".xlsm", ".csv", ".tsv")
    if not filename.lower().endswith(allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail="请上传 xlsx、xlsm、csv 或 tsv 文件",
        )

    file_bytes = await _read_upload_file_with_limit(file, file_label="表格文件")
    try:
        result = await import_supplier_table_file(
            db,
            file_bytes,
            file_name=filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return success_response(
        data=result.model_dump(mode="json"),
        message="供应商清单导入成功",
    )


@router.get(
    "/invoices/recognition-records",
    summary="查询采购发票识别记录",
    description="查询已经保存到数据库的采购发票识别结果，支持按关键字、销售方和发票号码筛选。",
    response_model=InvoiceRecognitionRecordListResponse,
)
async def list_invoice_records(
    keyword: str | None = Query(None, description="文件名、发票号码或销售方关键词"),
    seller_name: str | None = Query(None, description="销售方名称"),
    invoice_number: str | None = Query(None, description="发票号码"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    records, total = await list_invoice_recognition_records(
        db,
        keyword=keyword,
        seller_name=seller_name,
        invoice_number=invoice_number,
        page=page,
        page_size=page_size,
    )
    data = [
        InvoiceRecognitionRecordResponse.model_validate(record).model_dump(mode="json")
        for record in records
    ]
    return paginated_response(data, page, page_size, total)


@router.delete(
    "/invoices/recognition-records/{record_id}",
    summary="删除采购发票识别记录",
    description="软删除单条采购发票识别历史记录。",
    response_model=InvoiceRecognitionRecordDeleteResponse,
)
async def delete_invoice_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    deleted = await delete_invoice_recognition_record(db, record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="识别记录不存在或已删除")

    return success_response(
        data=InvoiceRecognitionRecordDeleteResult(
            success_count=1,
            fail_count=0,
        ).model_dump(mode="json"),
        message="识别记录删除成功",
    )


@router.post(
    "/invoices/recognition-records/batch-delete",
    summary="批量删除采购发票识别记录",
    description="软删除多条采购发票识别历史记录。",
    response_model=InvoiceRecognitionRecordDeleteResponse,
)
async def batch_delete_invoice_records(
    payload: InvoiceRecognitionRecordDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    deleted_count = await batch_delete_invoice_recognition_records(db, payload.ids)
    return success_response(
        data=InvoiceRecognitionRecordDeleteResult(
            success_count=deleted_count,
            fail_count=max(0, len(payload.ids) - deleted_count),
        ).model_dump(mode="json"),
        message="识别记录删除成功",
    )


@router.get(
    "/purchase-orders",
    summary="查询采购订单月度汇总",
    description="按采购分类、年份和月份汇总整月已审批通过的采购申请明细。",
    response_model=PurchaseOrderListResponse,
)
async def list_purchase_order_records(
    category: PurchaseRequestCategory | None = Query(None, description="采购分类"),
    year: int = Query(..., ge=2000, le=2100, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    lines, total = await list_purchase_order_lines(
        db,
        category=category.value if category else None,
        year=year,
        month=month,
        page=page,
        page_size=page_size,
    )
    data = [line.model_dump(mode="json") for line in lines]
    return paginated_response(data, page, page_size, total)


@router.get(
    "/purchase-orders/export",
    summary="导出采购订单月度汇总 Excel",
    description="按采购分类、年份和月份导出整月已审批通过的采购申请明细 Excel。",
)
async def export_purchase_order_records(
    category: PurchaseRequestCategory | None = Query(None, description="采购分类"),
    year: int = Query(..., ge=2000, le=2100, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    xlsx_bytes = await export_purchase_order_lines_xlsx(
        db,
        category=category.value if category else None,
        year=year,
        month=month,
    )
    category_label = (
        PURCHASE_CATEGORY_LABELS.get(category.value, category.value)
        if category
        else "全部类别"
    )
    filename = f"采购订单_{category_label}_{year}-{month:02d}.xlsx"
    encoded_filename = quote(filename, safe="")
    return Response(
        content=xlsx_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"
        },
    )


@router.get(
    "/purchase-requests",
    summary="查询采购申请",
    description="按采购分类、流程状态、审批角色或申购部门关键词查询采购申请。",
    response_model=PurchaseRequestListResponse,
)
async def list_purchase_request_records(
    category: PurchaseRequestCategory | None = Query(None, description="采购分类"),
    status: PurchaseRequestStatus | None = Query(None, description="流程状态"),
    approval_role: PurchaseApprovalRole | None = Query(
        None,
        description="审批角色。与 approval_view 一起筛选该角色的审批列表。",
    ),
    approval_view: PurchaseApprovalView = Query(
        PurchaseApprovalView.pending,
        description="审批视图：待审批、审批完成或审批驳回。",
    ),
    keyword: str | None = Query(None, description="申购部门关键词"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    requests, total = await list_purchase_requests(
        db,
        category=category.value if category else None,
        status=status.value if status else None,
        approval_role=approval_role,
        approval_view=approval_view,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    data = [request.model_dump(mode="json") for request in requests]
    return paginated_response(data, page, page_size, total)


@router.post(
    "/purchase-requests",
    summary="创建采购申请",
    description="保存采购申请草稿，并按数量和单价自动计算明细总额与合计。",
    response_model=PurchaseRequestApiResponse,
)
async def create_purchase_request_record(
    payload: PurchaseRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        request = await create_purchase_request(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=request.model_dump(mode="json"),
        message="采购申请已保存",
    )


@router.post(
    "/purchase-requests/import",
    summary="导入采购申请表格",
    description=(
        "上传 xlsx、xls 或 csv 表格文件：每个工作表生成一份采购申请草稿，"
        "按表头别名识别明细字段与采购类型，逐行校验，"
        "返回成功导入的申请与失败的行/工作表明细。"
    ),
    response_model=PurchaseRequestImportResponse,
)
async def import_purchase_request_records(
    file: UploadFile = File(..., description="采购申请表格文件"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(
            status_code=400,
            detail="请上传 xlsx、xls 或 csv 文件",
        )

    file_bytes = await _read_upload_file_with_limit(file, file_label="表格文件")
    try:
        result = await import_purchase_request_table_file(
            db,
            file_bytes,
            file_name=filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return success_response(
        data=result.model_dump(mode="json"),
        message="采购申请表格导入完成",
    )


@router.get(
    "/purchase-requests/{request_id}",
    summary="获取采购申请详情",
    response_model=PurchaseRequestApiResponse,
)
async def get_purchase_request_record(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        request = await get_purchase_request(db, request_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(data=request.model_dump(mode="json"))


@router.put(
    "/purchase-requests/{request_id}",
    summary="更新采购申请",
    description="仅草稿或已驳回的采购申请允许编辑。",
    response_model=PurchaseRequestApiResponse,
)
async def update_purchase_request_record(
    request_id: UUID,
    payload: PurchaseRequestUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        request = await update_purchase_request(db, request_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=request.model_dump(mode="json"),
        message="采购申请已更新",
    )


@router.delete(
    "/purchase-requests/{request_id}",
    summary="删除采购申请",
    description="仅草稿状态的采购申请允许删除；软删除申请及其明细、审批记录。",
    response_model=PurchaseRequestDeleteResponse,
)
async def delete_purchase_request_record(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        deleted = await delete_purchase_request(db, request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=PurchaseRequestDeleteResult(
            success_count=1 if deleted else 0,
            fail_count=0 if deleted else 1,
        ).model_dump(mode="json"),
        message="采购申请已删除",
    )


@router.post(
    "/purchase-requests/{request_id}/submit",
    summary="提交采购申请",
    description="将采购申请提交到该采购类型配置的首个审批节点。",
    response_model=PurchaseRequestApiResponse,
)
async def submit_purchase_request_record(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        request = await submit_purchase_request(db, request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(
        data=request.model_dump(mode="json"),
        message="采购申请已提交",
    )


@router.post(
    "/purchase-requests/{request_id}/approve",
    summary="通过采购申请审批",
    response_model=PurchaseRequestApiResponse,
)
async def approve_purchase_request_record(
    request_id: UUID,
    payload: PurchaseApprovalRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        request = await approve_purchase_request(db, request_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=request.model_dump(mode="json"), message="审批已通过")


@router.post(
    "/purchase-requests/{request_id}/reject",
    summary="驳回采购申请审批",
    response_model=PurchaseRequestApiResponse,
)
async def reject_purchase_request_record(
    request_id: UUID,
    payload: PurchaseApprovalRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        request = await reject_purchase_request(db, request_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=request.model_dump(mode="json"), message="审批已驳回")


@router.get(
    "/contracts",
    summary="查询采购合同生成记录",
    description="查询合同生成产生的合同记录，支持按标题、合同编号和卖方名称检索。",
    response_model=ContractRecordListResponse,
)
async def list_contract_generation_records(
    keyword: str | None = Query(None, description="合同标题、编号或卖方关键词"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    records, total = await list_contract_records(
        db,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    data = [
        ContractRecordResponse.model_validate(record).model_dump(mode="json")
        for record in records
    ]
    return paginated_response(data, page, page_size, total)


@router.get(
    "/contracts/templates/{category}",
    summary="获取采购合同模板字段",
    description="返回指定合同分类的可填写字段，用于前端动态展示合同生成表单。",
    response_model=ContractTemplateMetadata,
)
async def get_contract_template(category: ContractCategory) -> Any:
    metadata = get_contract_template_metadata(category)
    return success_response(data=metadata.model_dump(mode="json"))


@router.post(
    "/contracts/generate",
    summary="生成采购合同",
    description="根据合同分类、基础信息、供应商信息和明细行生成 Word 合同。",
)
async def create_contract(
    payload: ContractGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        buffer, filename, media_type, record = await generate_and_store_contract(
            db,
            payload,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    encoded_filename = quote(filename, safe="")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}",
            "X-Contract-Record-Id": str(record.id),
        },
    )


@router.get(
    "/contracts/{contract_id}",
    summary="获取采购合同详情",
    response_model=ContractRecordApiResponse,
)
async def get_contract_generation_record(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        record = await get_contract_record(db, contract_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(
        data=ContractRecordResponse.model_validate(record).model_dump(mode="json")
    )


@router.get(
    "/contracts/{contract_id}/file",
    summary="查看采购合同文件",
)
async def get_contract_file(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        data, content_type, filename = await get_contract_record_file(db, contract_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    encoded_filename = quote(filename, safe="")
    return StreamingResponse(
        iter([data]),
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"
        },
    )
