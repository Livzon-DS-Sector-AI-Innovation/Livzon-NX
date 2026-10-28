"""设备台账 API 路由."""

import io
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import paginated_response, success_response
from app.core.upload_security import validate_upload_metadata
from app.modules.equipment import repository as repo
from app.modules.equipment import service
from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.schemas import (
    EquipmentCategoryCreate,
    EquipmentCategoryResponse,
    EquipmentCategoryTree,
    EquipmentCategoryUpdate,
    EquipmentCreate,
    EquipmentResponse,
    EquipmentStatistics,
    EquipmentUpdate,
    LocationCreate,
    LocationResponse,
    LocationTree,
    LocationUpdate,
)
from app.modules.equipment.service import (
    equipment_import,
    equipment_ledger_archive,
    equipment_qrcode,
)

router = APIRouter()

# 车间代码形如 101 / 101-1 / dlz；列表缺省 = 跨车间查询
WORKSHOP_QUERY = Query(
    None,
    pattern=r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$",
    description="车间代码（如 101-1 / dlz）",
)


async def _equipment_to_response(
    equipment: Equipment, db: AsyncSession | None = None
) -> EquipmentResponse:
    """将 ORM Equipment 转为响应对象，填充多分类信息及部门信息"""
    resp = EquipmentResponse.model_validate(equipment)
    links = getattr(equipment, "category_links", []) or []
    resp.category_ids = [link.category_id for link in links if not link.is_deleted]
    names = [
        link.category.name for link in links if not link.is_deleted and link.category
    ]
    resp.category_names = "、".join(names) if names else None
    resp.location_name = equipment.location.name if equipment.location else None
    # 填充部门信息
    if equipment.department_id and db:
        dept_info = await repo.get_department_info(db, equipment.department_id)
        if dept_info:
            resp.department_name = dept_info["name"]
            # 负责人：优先用设备独立设置的 responsible_person_id；否则由部门负责人推导
            if not equipment.responsible_person_id:
                resp.responsible_person_name = dept_info["leader_name"]
                resp.responsible_person_id = dept_info.get("leader_id")
    # 负责人名称：如果独立设置了 responsible_person_id，从用户表查找
    if equipment.responsible_person_id and db:
        resp.responsible_person_name = await repo.get_user_name_by_id(
            db, equipment.responsible_person_id
        )
    return resp


# ==================== 设备分类 ====================
@router.post("/categories", summary="创建设备分类")
async def create_equipment_category(
    data: EquipmentCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """创建设备分类"""
    category = await service.create_equipment_category(db, data)
    return success_response(data=EquipmentCategoryResponse.model_validate(category))


@router.get("/categories", summary="获取设备分类列表")
async def get_equipment_categories(
    parent_id: uuid.UUID | None = Query(None, description="父分类ID"),
    tree: bool = Query(False, description="是否返回树形结构"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取设备分类列表"""
    if tree:
        categories = await service.get_equipment_category_tree(db)
        return success_response(
            data=[EquipmentCategoryTree.model_validate(c) for c in categories]
        )
    categories = await service.get_equipment_categories(db, parent_id)
    return success_response(
        data=[EquipmentCategoryResponse.model_validate(c) for c in categories]
    )


@router.get("/categories/{category_id}", summary="获取设备分类详情")
async def get_equipment_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取设备分类详情"""
    category = await service.get_equipment_category_by_id(db, category_id)
    return success_response(data=EquipmentCategoryResponse.model_validate(category))


@router.put("/categories/{category_id}", summary="更新设备分类")
async def update_equipment_category(
    category_id: uuid.UUID,
    data: EquipmentCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """更新设备分类"""
    category = await service.update_equipment_category(db, category_id, data)
    return success_response(data=EquipmentCategoryResponse.model_validate(category))


@router.delete("/categories/{category_id}", summary="删除设备分类")
async def delete_equipment_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """删除设备分类"""
    await service.delete_equipment_category(db, category_id)
    return success_response(message="删除成功")


# ==================== 位置管理 ====================
@router.post("/locations", summary="创建位置")
async def create_location(
    data: LocationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """创建位置"""
    location = await service.create_location(db, data)
    return success_response(data=LocationResponse.model_validate(location))


@router.get("/locations", summary="获取位置列表")
async def get_locations(
    parent_id: uuid.UUID | None = Query(None, description="父位置ID"),
    tree: bool = Query(False, description="是否返回树形结构"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取位置列表"""
    if tree:
        locations = await service.get_location_tree(db)
        return success_response(
            data=[LocationTree.model_validate(loc) for loc in locations]
        )
    locations = await service.get_locations(db, parent_id)
    return success_response(
        data=[LocationResponse.model_validate(loc) for loc in locations]
    )


@router.get("/locations/{location_id}", summary="获取位置详情")
async def get_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取位置详情"""
    location = await service.get_location_by_id(db, location_id)
    return success_response(data=LocationResponse.model_validate(location))


@router.put("/locations/{location_id}", summary="更新位置")
async def update_location(
    location_id: uuid.UUID,
    data: LocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """更新位置"""
    location = await service.update_location(db, location_id, data)
    return success_response(data=LocationResponse.model_validate(location))


@router.delete("/locations/{location_id}", summary="删除位置")
async def delete_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """删除位置"""
    await service.delete_location(db, location_id)
    return success_response(message="删除成功")


# ==================== 部门列表（供设备表单下拉使用） ====================
@router.get("/departments", summary="获取部门列表（供设备表单下拉使用）")
async def get_departments_list(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取可选部门列表，含部门名称和负责人姓名"""
    departments = await service.get_departments_for_select(db)
    return success_response(data=departments)


# ==================== 设备管理 ====================
@router.post("/equipments", summary="创建设备")
async def create_equipment(
    data: EquipmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """创建设备"""
    equipment = await service.create_equipment(db, data)
    return success_response(data=await _equipment_to_response(equipment, db))


@router.get("/equipments", summary="获取设备列表")
async def get_equipments(
    category_id: uuid.UUID | None = Query(None, description="设备分类ID"),
    location_id: uuid.UUID | None = Query(None, description="设备位置ID"),
    department_id: uuid.UUID | None = Query(None, description="归属部门ID"),
    status: str | None = Query(None, description="设备状态"),
    keyword: str | None = Query(None, description="关键词搜索"),
    workshop: str | None = WORKSHOP_QUERY,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取设备列表"""
    equipments, total = await service.get_equipments(
        db,
        category_id,
        location_id,
        department_id,
        status,
        keyword,
        workshop,
        page,
        page_size,
    )
    equipment_responses = []
    for e in equipments:
        equipment_responses.append(await _equipment_to_response(e, db))
    return paginated_response(
        data=equipment_responses,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/equipments/statistics", summary="获取设备统计")
async def get_equipment_statistics(
    workshop: str | None = WORKSHOP_QUERY,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取设备统计"""
    stats = await service.get_equipment_statistics(db, workshop)
    return success_response(data=EquipmentStatistics(**stats))


@router.get("/equipments/qrcode-pdf", summary="导出车间设备报修二维码 PDF")
async def export_equipment_qrcode_pdf(
    workshop: str = Query(
        ...,
        pattern=r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$",
        description="车间代码（必填，如 101-1 / dlz）",
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """按车间导出设备报修二维码 PDF（A4 一页 12 枚，打印覆膜张贴）。

    码内容为纯文本「报修 {车间全名} {设备名} {设备编号}」，扫码后复制
    发到维修群即可建单，不编码任何平台地址。
    """
    try:
        pdf_bytes, _workshop_name = (
            await equipment_qrcode.generate_workshop_qrcode_pdf(db, workshop)
        )
    except LookupError:
        raise HTTPException(
            status_code=404, detail=f"车间不存在: {workshop}"
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    filename = quote(f"设备报修码_{workshop}.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
        },
    )


_ALLOWED_IMPORT_EXTENSIONS = {".xlsx"}
_ALLOWED_IMPORT_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_MAX_IMPORT_UPLOAD_BYTES = 2 * 1024 * 1024  # 台账 .xlsx 通常几十 KB
_ARCHIVE_UPLOAD_SUB_DIR = "equipment-ledger-archive"


def _archive_upload_dir() -> Path:
    directory = Path(get_settings().UPLOAD_DIR) / _ARCHIVE_UPLOAD_SUB_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _ensure_archive_file(original_path: str) -> Path:
    """original_path 相对 uploads 根目录，返回真实文件路径并校验存在。"""
    base = Path(get_settings().UPLOAD_DIR).resolve()
    path = (base / original_path).resolve()
    if base not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="原始文件不存在")
    return path


@router.get("/equipments/import-template", summary="下载设备台账导入模板")
async def download_equipment_import_template() -> StreamingResponse:
    """下载标准台账 .xlsx 模板（含表头与示例行）"""
    content = equipment_import.build_ledger_template()
    return StreamingResponse(
        io.BytesIO(content),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                'attachment; filename="equipment-ledger-template.xlsx"'
            )
        },
    )


@router.post("/equipments/import", summary="Excel 批量导入设备台账")
async def import_equipments(
    file: UploadFile = File(..., description="按模板填写的台账 .xlsx 文件"),
    default_category_id: uuid.UUID | None = Form(
        None, description="默认设备分类（可选，传入则导入设备统一挂该分类）"
    ),
    default_location_id: uuid.UUID | None = Form(
        None, description="默认安装地点（台账安装地点无法匹配时使用）"
    ),
    workshop: str | None = Form(
        "201-1", pattern=r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$", description="归属车间代码"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """按设备编号增量导入：已存在则更新台账字段，不存在则新建；成功后留上传存档"""
    filename = validate_upload_metadata(
        file,
        allowed_extensions=_ALLOWED_IMPORT_EXTENSIONS,
        allowed_mimes=_ALLOWED_IMPORT_MIMES,
    )
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_IMPORT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="台账文件不能超过 2MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")

    # 导入前解析回看快照并保存原件；导入失败时清理原件且不留存档
    snapshot = equipment_ledger_archive.parse_ledger_snapshot(data)
    object_name = f"{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
    relative_path = f"{_ARCHIVE_UPLOAD_SUB_DIR}/{object_name}"
    (_archive_upload_dir() / object_name).write_bytes(data)
    try:
        summary = await equipment_import.import_equipment_ledger(
            db,
            data,
            default_category_id=default_category_id,
            default_location_id=default_location_id,
            workshop_code=workshop or "201-1",
        )
    except Exception:
        (_archive_upload_dir() / object_name).unlink(missing_ok=True)
        raise
    archive = await equipment_ledger_archive.create_archive(
        db,
        workshop_code=workshop or "201-1",
        file_name=filename,
        sheet_name=snapshot["sheet_name"],
        original_path=relative_path,
        rows=snapshot["rows"],
        merges=snapshot["merges"],
        col_widths=snapshot["col_widths"],
        row_count=snapshot["row_count"],
        col_count=snapshot["col_count"],
        import_summary={
            key: summary[key] for key in summary if key != "failures"
        },
        created_by=current_user.id if current_user else None,
    )
    return success_response(
        data={**summary, "archive_id": str(archive.id)},
        message="台账导入完成，已留存档",
    )


@router.get(
    "/equipments/import-archives", summary="设备台账上传存档列表"
)
async def list_equipment_import_archives(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    workshop: str | None = WORKSHOP_QUERY,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """历次台账上传存档（新在前）；列表项不含大字段，点详情回看完整表格"""
    items, total = await equipment_ledger_archive.list_archives(
        db, page=page, page_size=page_size, workshop_code=workshop
    )
    return paginated_response(
        [
            equipment_ledger_archive.serialize_archive_summary(
                archive, created_by_name=name
            )
            for archive, name in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/equipments/import-archives/{archive_id}",
    summary="设备台账上传存档详情（含完整表格）",
)
async def get_equipment_import_archive(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    archive = await equipment_ledger_archive.get_archive(db, archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="存档记录不存在")
    created_by_name = await equipment_ledger_archive.get_user_name(
        db, archive.created_by
    )
    return success_response(
        data=equipment_ledger_archive.serialize_archive(
            archive, created_by_name=created_by_name
        )
    )


@router.get(
    "/equipments/import-archives/{archive_id}/file",
    summary="下载台账上传原件",
)
async def download_equipment_import_archive_file(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    archive = await equipment_ledger_archive.get_archive(db, archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="存档记录不存在")
    path = _ensure_archive_file(archive.original_path)
    return FileResponse(
        path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename=archive.file_name,
    )


@router.delete(
    "/equipments/import-archives/{archive_id}", summary="删除台账上传存档"
)
async def delete_equipment_import_archive(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """软删存档：只删快照记录，不影响已导入的台账数据"""
    archive = await equipment_ledger_archive.get_archive(db, archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="存档记录不存在")
    await equipment_ledger_archive.delete_archive(
        db, archive, deleted_by=current_user.id if current_user else None
    )
    return success_response(data=None, message="存档已删除")


@router.get("/equipments/{equipment_id}", summary="获取设备详情")
async def get_equipment(
    equipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取设备详情"""
    equipment = await service.get_equipment_by_id(db, equipment_id)
    return success_response(data=await _equipment_to_response(equipment, db))


@router.put("/equipments/{equipment_id}", summary="更新设备")
async def update_equipment(
    equipment_id: uuid.UUID,
    data: EquipmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """更新设备"""
    equipment = await service.update_equipment(db, equipment_id, data)
    return success_response(data=await _equipment_to_response(equipment, db))


@router.delete("/equipments/{equipment_id}", summary="删除设备")
async def delete_equipment(
    equipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    """删除设备"""
    await service.delete_equipment(db, equipment_id)
    return success_response(message="删除成功")
