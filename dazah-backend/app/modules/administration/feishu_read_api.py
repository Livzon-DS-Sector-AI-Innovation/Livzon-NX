"""Administration read-only Feishu mirror routes (烟酒礼品管理).

复用平台层 ``ModuleFeishuReadMirrorService``，模块侧只负责鉴权入参、
页面 key 校验与载荷转发；配置端点负责行政模块飞书凭证的保存与测试。
镜像页 ``page-data`` 载荷由平台服务生成，按既有镜像页契约原样转发。
"""

import uuid

import httpx
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException
from app.modules.administration.repository import AdministrationRepository
from app.modules.administration.schemas import (
    AdministrationFeishuBindingReplace,
    AdministrationFeishuConfigInput,
    AdministrationFeishuConfigResponse,
    AdministrationFeishuConnectivityResult,
    AdministrationFeishuResource,
    AdministrationFeishuSourceRoot,
    AdministrationFeishuSourceRootInput,
    AdministrationFeishuSyncResult,
    DormitoryCheckinInput,
    DormitoryCheckinResult,
    DormitoryOccupancyStats,
    DormitoryRoomRecommendation,
    TobaccoGiftAiAnalysis,
    TobaccoGiftDashboardStats,
)
from app.modules.administration.service import (
    ADMINISTRATION_READ_PAGE_KEYS,
    AdministrationDormitoryService,
    AdministrationFeishuService,
    AdministrationTobaccoGiftService,
    build_read_mirror_service,
    decorate_records_for_display,
    prune_resource_history,
    resolve_person_avatars,
)
from app.platform.identity.data_scope import current_page_key
from app.platform.identity.deps import RequireUser
from app.shared.schemas import ApiResponse, ApiResponseEnvelope

router = APIRouter()


def _validate_page_key(page_key: str) -> None:
    if page_key not in ADMINISTRATION_READ_PAGE_KEYS:
        raise AppException(message="未登记的行政管理数据页面", status_code=404)


def _require_page_context(page_key: str) -> None:
    """记录/附件读取的 URL page_key 必须等于本次请求已授权的页面。

    page_data（绑定配置）按绑定元组放行即可；记录与附件涉及业务数据，
    必须与安全模块镜像接口一致地校验页面上下文，防止持有 A 页权限读取 B 页。
    """
    authorized = current_page_key.get()
    if not authorized or authorized != page_key:
        raise AppException(
            message="请求的数据页面与当前页面上下文不一致", status_code=403
        )


def _translate_upstream_error(exc: Exception) -> AppException:
    """飞书上游调用失败 → 502，不把内部堆栈细节透给前端。"""
    detail = str(exc).replace("Bearer ", "Bearer ***").strip()[:300]
    return AppException(
        message=f"飞书接口调用失败：{detail or '未知错误'}", status_code=502
    )


async def _mirror_config_id(db: AsyncSession) -> uuid.UUID:
    """读取镜像用的配置取最近一份已配置凭证；is_active 只约束定时自动同步。"""
    config = await AdministrationRepository(db).get_latest_config()
    if config is None or not config.app_id or not config.encrypted_app_secret:
        raise AppException(
            message="行政飞书应用凭据未配置，请先在「飞书设置」完成配置",
            status_code=400,
        )
    return config.id


# ── 飞书应用配置 ────────────────────────────────────────────────


@router.get(
    "/feishu-config",
    summary="获取行政飞书配置",
    response_model=ApiResponseEnvelope[AdministrationFeishuConfigResponse],
)
async def get_feishu_config(
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[AdministrationFeishuConfigResponse]:
    config = await AdministrationFeishuService(db).get_config_response()
    return ApiResponseEnvelope(data=config)


@router.put(
    "/feishu-config",
    summary="保存行政飞书配置",
    response_model=ApiResponseEnvelope[AdministrationFeishuConfigResponse],
)
async def save_feishu_config(
    _current_user: RequireUser,
    payload: AdministrationFeishuConfigInput,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[AdministrationFeishuConfigResponse]:
    config = await AdministrationFeishuService(db).save_config(payload)
    return ApiResponseEnvelope(data=config)


@router.post(
    "/feishu-config/test",
    summary="测试行政飞书连通性",
    response_model=ApiResponseEnvelope[AdministrationFeishuConnectivityResult],
)
async def test_feishu_config(
    _current_user: RequireUser,
    payload: AdministrationFeishuConfigInput | None = None,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[AdministrationFeishuConnectivityResult]:
    result = await AdministrationFeishuService(db).test_connectivity(payload)
    return ApiResponseEnvelope(data=result)


# ── 只读镜像：入口、数据表、页面绑定 ─────────────────────────────


@router.get(
    "/feishu-read/roots",
    summary="查询行政飞书数据入口",
    response_model=ApiResponseEnvelope[list[AdministrationFeishuSourceRoot]],
)
async def list_read_roots(
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[list[AdministrationFeishuSourceRoot]]:
    service = await build_read_mirror_service(db)
    roots = await service.list_roots(await _mirror_config_id(db))
    return ApiResponseEnvelope(
        data=[AdministrationFeishuSourceRoot.model_validate(item) for item in roots]
    )


@router.post(
    "/feishu-read/roots",
    summary="新增行政飞书数据入口",
    response_model=ApiResponseEnvelope[AdministrationFeishuSourceRoot],
)
async def create_read_root(
    _current_user: RequireUser,
    payload: AdministrationFeishuSourceRootInput,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[AdministrationFeishuSourceRoot]:
    service = await build_read_mirror_service(db)
    root = await service.create_root(
        config_id=await _mirror_config_id(db),
        name=payload.name,
        source_type=payload.source_type,
        source_url=payload.source_url,
    )
    return ApiResponseEnvelope(data=AdministrationFeishuSourceRoot.model_validate(root))


@router.delete(
    "/feishu-read/roots/{root_id}",
    summary="停用行政飞书数据入口",
    response_model=ApiResponse,
)
async def delete_read_root(
    _current_user: RequireUser,
    root_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    service = await build_read_mirror_service(db)
    await service.delete_root(root_id)
    return ApiResponse(data={"deleted": True})


@router.post(
    "/feishu-read/roots/{root_id}/discover",
    summary="发现行政飞书数据入口下的数据表",
    response_model=ApiResponseEnvelope[list[AdministrationFeishuResource]],
)
async def discover_read_root(
    _current_user: RequireUser,
    root_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[list[AdministrationFeishuResource]]:
    service = await build_read_mirror_service(db)
    try:
        resources = await service.discover_root(root_id)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise _translate_upstream_error(exc) from exc
    return ApiResponseEnvelope(
        data=[AdministrationFeishuResource.model_validate(item) for item in resources]
    )


@router.get(
    "/feishu-read/resources",
    summary="查询已发现的数据表",
    response_model=ApiResponseEnvelope[list[AdministrationFeishuResource]],
)
async def list_read_resources(
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[list[AdministrationFeishuResource]]:
    service = await build_read_mirror_service(db)
    resources = await service.list_resources()
    return ApiResponseEnvelope(
        data=[AdministrationFeishuResource.model_validate(item) for item in resources]
    )


@router.get(
    "/feishu-read/person-avatars",
    summary="按企业邮箱批量解析镜像人员头像",
    response_model=ApiResponseEnvelope[dict[str, str]],
)
async def get_person_avatars(
    emails: list[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[dict[str, str]]:
    avatars = await resolve_person_avatars(db, emails)
    return ApiResponseEnvelope(data=avatars)


@router.post(
    "/feishu-read/resources/{resource_id}/sync",
    summary="同步数据表镜像",
    response_model=ApiResponseEnvelope[AdministrationFeishuSyncResult],
)
async def sync_read_resource(
    _current_user: RequireUser,
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[AdministrationFeishuSyncResult]:
    service = await build_read_mirror_service(db)
    try:
        result = await service.sync_resource(resource_id)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise _translate_upstream_error(exc) from exc
    # 平台镜像服务每轮全量插入新版本，及时清理非激活版本防止镜像表无限增长
    await prune_resource_history(db, resource_id)
    return ApiResponseEnvelope(
        data=AdministrationFeishuSyncResult.model_validate(result)
    )


@router.put(
    "/feishu-read/page-bindings/{page_key:path}",
    summary="替换页面数据表绑定",
    response_model=ApiResponse,
)
async def replace_read_bindings(
    _current_user: RequireUser,
    page_key: str,
    payload: AdministrationFeishuBindingReplace,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    _validate_page_key(page_key)
    service = await build_read_mirror_service(db)
    return ApiResponse(
        data=await service.replace_bindings(
            page_key, [item.model_dump() for item in payload.bindings]
        )
    )


# ── 页面数据（镜像读取，平台载荷原样转发） ───────────────────────


@router.get("/page-data/{page_key}", summary="页面绑定数据", response_model=ApiResponse)
async def get_read_page(
    page_key: str,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponse:
    _validate_page_key(page_key)
    service = await build_read_mirror_service(db)
    return ApiResponse(data=await service.page_data(page_key))


def _parse_filters(
    filter_field: list[str], filter_operator: list[str], filter_value: list[str]
) -> list[dict[str, str]]:
    """把三组平行查询参数拼成条件列表（前端筛选器逐行提供）。"""
    filters: list[dict[str, str]] = []
    for index, field in enumerate(filter_field):
        if not field:
            continue
        filters.append(
            {
                "field": field,
                "operator": (
                    filter_operator[index]
                    if index < len(filter_operator)
                    else "contains"
                ),
                "value": filter_value[index] if index < len(filter_value) else "",
            }
        )
    return filters


@router.get(
    "/page-data/{page_key}/{binding_id}/records",
    summary="页面数据记录",
    response_model=ApiResponse,
)
async def get_read_page_records(
    page_key: str,
    binding_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    keyword: str | None = None,
    sort_field: str | None = Query(default=None, max_length=255),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    filter_field: list[str] | None = Query(default=None),
    filter_operator: list[str] | None = Query(default=None),
    filter_value: list[str] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponse:
    _validate_page_key(page_key)
    _require_page_context(page_key)
    service = await build_read_mirror_service(db)
    data = await service.page_records(
        page_key=page_key,
        binding_id=binding_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        sort_field=sort_field,
        sort_direction=sort_direction,
        filters=_parse_filters(
            filter_field or [], filter_operator or [], filter_value or []
        ),
    )
    # 关联字段（领用物品）只回 ID，装饰成物品名称供表格与详情直接展示
    data = await decorate_records_for_display(db, data)
    return ApiResponse(data=data)


@router.get(
    "/page-data/{page_key}/{binding_id}/export",
    summary="导出页面数据（Excel/PDF，含图片与头像）",
    response_model=None,
)
async def export_read_page_records(
    page_key: str,
    binding_id: uuid.UUID,
    format: str = Query(default="xlsx", pattern="^(xlsx|pdf)$"),
    columns: str | None = Query(default=None, max_length=2000),
    sort_field: str | None = Query(default=None, max_length=255),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    filter_field: list[str] | None = Query(default=None),
    filter_operator: list[str] | None = Query(default=None),
    filter_value: list[str] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    """按当前筛选/排序导出全量记录；columns 为逗号分隔的展示列 field_id。"""
    from urllib.parse import quote

    from app.modules.administration.export_service import (
        export_binding_records,
    )

    _validate_page_key(page_key)
    _require_page_context(page_key)
    service = await build_read_mirror_service(db)
    column_ids = [item for item in columns.split(",") if item] if columns else None
    try:
        content, filename, mime = await export_binding_records(
            db,
            service,
            page_key=page_key,
            binding_id=binding_id,
            file_format=format,
            columns=column_ids,
            filters=_parse_filters(
                filter_field or [], filter_operator or [], filter_value or []
            ),
            sort_field=sort_field,
            sort_direction=sort_direction,
        )
    except (RuntimeError, httpx.HTTPError) as exc:
        raise _translate_upstream_error(exc) from exc
    quoted_name = quote(f"{page_key.split(':')[-1]}-{filename}")
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_name}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/page-data/{page_key}/{binding_id}/record/{record_id}"
    "/attachments/{field_id}/{file_token}",
    summary="下载记录附件",
)
async def download_read_attachment(
    page_key: str,
    binding_id: uuid.UUID,
    record_id: str,
    field_id: str,
    file_token: str,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    _validate_page_key(page_key)
    _require_page_context(page_key)
    service = await build_read_mirror_service(db)
    try:
        content, content_type, _disposition = await service.download_attachment(
            page_key=page_key,
            binding_id=binding_id,
            record_id=record_id,
            field_id=field_id,
            file_token=file_token,
        )
    except (RuntimeError, httpx.HTTPError) as exc:
        raise _translate_upstream_error(exc) from exc
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "attachment",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ── 烟酒礼品仪表台 ─────────────────────────────────────────────


@router.get(
    "/tobacco-gift/dashboard-stats",
    summary="烟酒礼品仪表台统计",
    response_model=ApiResponseEnvelope[TobaccoGiftDashboardStats],
)
async def get_tobacco_gift_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[TobaccoGiftDashboardStats]:
    stats = await AdministrationTobaccoGiftService(db).get_dashboard_stats()
    return ApiResponseEnvelope(data=stats)


@router.post(
    "/tobacco-gift/ai-analysis",
    summary="生成烟酒礼品仪表台 AI 分析",
    response_model=ApiResponseEnvelope[TobaccoGiftAiAnalysis],
)
async def generate_tobacco_gift_ai_analysis(
    _current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[TobaccoGiftAiAnalysis]:
    analysis = await AdministrationTobaccoGiftService(db).generate_ai_analysis()
    return ApiResponseEnvelope(data=analysis)


# ── 宿舍管理：入住率仪表盘 + AI 推荐入住 ───────────────────────


@router.get(
    "/dormitory/dashboard-stats",
    summary="宿舍入住率统计",
    response_model=ApiResponseEnvelope[DormitoryOccupancyStats],
)
async def get_dormitory_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[DormitoryOccupancyStats]:
    stats = await AdministrationDormitoryService(db).get_dashboard_stats()
    return ApiResponseEnvelope(data=stats)


@router.post(
    "/dormitory/checkin-recommend",
    summary="AI 推荐入住房间",
    response_model=ApiResponseEnvelope[DormitoryRoomRecommendation],
)
async def recommend_dormitory_rooms(
    _current_user: RequireUser,
    payload: DormitoryCheckinInput,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[DormitoryRoomRecommendation]:
    recommendation = await AdministrationDormitoryService(db).recommend_rooms(payload)
    return ApiResponseEnvelope(data=recommendation)


@router.post(
    "/dormitory/checkin",
    summary="办理新员工入住（回写飞书）",
    response_model=ApiResponseEnvelope[DormitoryCheckinResult],
)
async def create_dormitory_checkin(
    _current_user: RequireUser,
    payload: DormitoryCheckinInput,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[DormitoryCheckinResult]:
    service = AdministrationDormitoryService(db)
    try:
        result = await service.checkin(payload)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise _translate_upstream_error(exc) from exc
    return ApiResponseEnvelope(data=result)
