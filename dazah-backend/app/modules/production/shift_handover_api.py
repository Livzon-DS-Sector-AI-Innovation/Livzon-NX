"""班组交接确认 API routes."""

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.shift_handover_schemas import (
    ShiftHandoverCreate,
    ShiftHandoverResponse,
    ShiftHandoverUpdate,
)
from app.modules.production.shift_handover_service import ShiftHandoverService
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


def get_shift_handover_service(
    session: AsyncSession = Depends(get_db),
) -> ShiftHandoverService:
    return ShiftHandoverService(session)


@router.get("/shift-handovers", summary="班组交接记录列表")
async def list_shift_handovers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    position: str | None = Query(None, description="岗位"),
    workshop: str | None = Query(None, description="车间"),
    date_from: str | None = Query(None, description="开始日期"),
    date_to: str | None = Query(None, description="结束日期"),
    svc: ShiftHandoverService = Depends(get_shift_handover_service),
):
    items, total = await svc.list_records(
        page=page,
        page_size=page_size,
        position=position,
        workshop=workshop,
        date_from=date_from,
        date_to=date_to,
    )
    response_items = [ShiftHandoverResponse.model_validate(item) for item in items]
    return paginated_response(response_items, page, page_size, total)


@router.get("/shift-handovers/search-users", summary="搜索企业用户")
async def search_users(
    q: str = Query("", description="搜索关键词"),
    session: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.core.secrets import decrypt_secret
    from app.modules.production.production_feishu_client import ProductionFeishuClient
    from app.modules.production.production_feishu_models import ProductionFeishuConfig

    try:
        result = await session.execute(
            select(ProductionFeishuConfig)
            .where(
                ProductionFeishuConfig.is_active,
                not ProductionFeishuConfig.is_deleted,
            )
            .limit(1)
        )
        config = result.scalar_one_or_none()
        if not config:
            return success_response([], message="无可用飞书配置")

        secret = decrypt_secret(config.encrypted_app_secret)
        client = ProductionFeishuClient(config.app_id, secret, config.bitable_app_token)
        token = await client._get_token()

        import httpx

        from app.platform.integrations.feishu.utils import OPEN_API_BASE_URL

        async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=30) as h:
            resp = await h.get(
                "/contact/v3/users",
                headers={"Authorization": f"Bearer {token}"},
                params={"page_size": 100, "department_id_type": "open_department_id"},
            )
            data = resp.json()

        if data.get("code") != 0:
            return success_response([], message=f"通讯录访问失败: {data.get('msg')}")

        items = data.get("data", {}).get("items", [])
        q_lower = q.lower()
        result_users = [
            {
                "id": u.get("open_id", ""),
                "name": u.get("name", ""),
                "department": ",".join(u.get("department_ids", [])),
            }
            for u in items
            if q_lower in u.get("name", "").lower()
            or q_lower in (u.get("en_name") or "").lower()
        ][:20]
        return success_response(result_users)
    except Exception as e:
        return success_response([], message=f"搜索失败: {e}")


@router.get("/shift-handovers/positions", summary="获取所有岗位列表")
async def get_positions(
    svc: ShiftHandoverService = Depends(get_shift_handover_service),
):
    positions = await svc.get_distinct_positions()
    return success_response(positions)


@router.get("/shift-handovers/{record_id}", summary="班组交接记录详情")
async def get_shift_handover(
    record_id: UUID,
    svc: ShiftHandoverService = Depends(get_shift_handover_service),
):
    record = await svc.get_record(record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    return success_response(ShiftHandoverResponse.model_validate(record))


@router.post("/shift-handovers", summary="创建班组交接记录")
async def create_shift_handover(
    data: ShiftHandoverCreate,
    svc: ShiftHandoverService = Depends(get_shift_handover_service),
):
    record = await svc.create_record(data.model_dump())
    return success_response(
        ShiftHandoverResponse.model_validate(record), message="创建成功"
    )


@router.put("/shift-handovers/{record_id}", summary="更新班组交接记录")
async def update_shift_handover(
    record_id: UUID,
    data: ShiftHandoverUpdate,
    svc: ShiftHandoverService = Depends(get_shift_handover_service),
):
    record = await svc.update_record(record_id, data.model_dump(exclude_unset=True))
    return success_response(
        ShiftHandoverResponse.model_validate(record), message="更新成功"
    )


@router.post("/shift-handovers/{record_id}/confirm", summary="确认接班")
async def confirm_shift_handover(
    record_id: UUID,
    svc: ShiftHandoverService = Depends(get_shift_handover_service),
):
    record = await svc.confirm_record(record_id)
    return success_response(
        ShiftHandoverResponse.model_validate(record), message="确认成功"
    )


@router.delete("/shift-handovers/{record_id}", summary="删除班组交接记录")
async def delete_shift_handover(
    record_id: UUID,
    svc: ShiftHandoverService = Depends(get_shift_handover_service),
):
    await svc.delete_record(record_id)
    return success_response(None, message="删除成功")
