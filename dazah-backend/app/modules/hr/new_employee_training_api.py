"""新员工培训 API."""

import logging
from datetime import date, timedelta
from io import BytesIO
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException, NotFoundException
from app.core.response import paginated_response, success_response
from app.modules.hr.new_employee_training_service import NewEmployeeTrainingService
from app.modules.hr.schemas import (
    NewEmployeeTrainingItemAdd,
    NewEmployeeTrainingManualAdd,
    NewEmployeeTrainingPlanGenerate,
    NewEmployeeTrainingPlanUpdate,
    NewEmployeeTrainingStartRequest,
    NewEmployeeTrainingStartResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/new-employee-training", tags=["人事-新员工培训"])

# 列表默认展示入职3个月内员工
PENDING_HIRE_DAYS = 90


def _require_user(current_user: CurrentUser) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")


def _get_service(db: AsyncSession = Depends(get_db)) -> NewEmployeeTrainingService:
    return NewEmployeeTrainingService(db)


@router.get("/stats", summary="新员工培训统计")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    from app.modules.hr.api import _resolve_visible_scope

    alias_set = await _resolve_visible_scope(db, current_user)
    stats = await service.get_stats(dept_alias_set=alias_set)
    return success_response(data=stats.model_dump(mode="json"))


@router.get("/plans", summary="新员工培训计划列表")
async def list_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    department: str | None = Query(None, description="部门筛选"),
    status: str | None = Query(None, description="状态: 待安排/培训中/已完成/逾期"),
    keyword: str | None = Query(None, description="姓名关键词"),
    include_pending: bool = Query(
        True, description="是否包含未生成计划的近3个月新员工"
    ),
    db: AsyncSession = Depends(get_db),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    from app.modules.hr.api import _assert_dept_in_scope, _resolve_visible_norms

    alias_set = await _assert_dept_in_scope(db, current_user, department)
    visible_norms = await _resolve_visible_norms(db, current_user)
    plans, total = await service.list_plans(
        page=page,
        page_size=page_size,
        department=department,
        status=status,
        keyword=keyword,
        dept_alias_set=alias_set,
    )
    data = list(plans)

    # 合并：入职3个月内、尚未生成计划的新员工（仅第一页展示）
    if include_pending and page == 1:
        hire_date_from = date.today() - timedelta(days=PENDING_HIRE_DAYS)
        pending = await service.list_pending_employees(
            hire_date_from=hire_date_from,
            department=department,
            visible_norms=visible_norms,
        )
        existing_ids = {p["employee_id"] for p in data if p.get("plan_id")}
        rows = [p for p in pending if p["employee_id"] not in existing_ids]
        if rows:
            data = rows + data
    return paginated_response(data=data, page=page, page_size=page_size, total=total)


@router.post("/plans/generate", summary="生成新员工培训计划")
async def generate_plan(
    body: NewEmployeeTrainingPlanGenerate,
    db: AsyncSession = Depends(get_db),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _require_user(current_user)
    plan = await service.generate_plan(
        body.employee_id, user_id, body.training_position
    )
    resp = await service.get_plan(plan.id)
    return success_response(
        data=resp,
        message="培训计划已生成"
        if resp and resp["items"]
        else "已生成培训计划（该岗位暂无岗位培训清单，可手动添加教材）",
    )


@router.post("/plans/manual-add", summary="手动新增新员工培训计划（离岗复训）")
async def manual_add_plan(
    body: NewEmployeeTrainingManualAdd,
    db: AsyncSession = Depends(get_db),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    """手动新增新员工培训计划：用于离岗超过 3 个月的员工回岗重新培训。

    员工在档案中时自动带出档案信息（入职日期以档案为准）；
    不在档案时按前端传入值创建。
    """
    user_id = _require_user(current_user)
    plan = await service.create_manual_plan(
        name=body.name,
        department=body.department,
        position=body.position,
        hire_date=body.hire_date,
        user_id=user_id,
        sub_department=body.sub_department,
        training_position=body.training_position,
        employee_id=body.employee_id,
    )
    resp = await service.get_plan(plan.id)
    return success_response(
        data=resp,
        message="培训计划已生成"
        if resp and resp["items"]
        else "已生成培训计划（该岗位暂无岗位培训清单，可手动添加教材）",
    )


@router.get("/plans/{plan_id}", summary="新员工培训计划详情")
async def get_plan(
    plan_id: UUID,
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    resp = await service.get_plan(plan_id)
    if not resp:
        raise NotFoundException(resource="新员工培训计划", resource_id=str(plan_id))
    return success_response(data=resp)


@router.put("/plans/{plan_id}", summary="更新新员工培训计划")
async def update_plan(
    plan_id: UUID,
    body: NewEmployeeTrainingPlanUpdate,
    db: AsyncSession = Depends(get_db),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _require_user(current_user)
    resp = await service.update_plan(plan_id, body, user_id)
    if not resp:
        raise NotFoundException(resource="新员工培训计划", resource_id=str(plan_id))
    return success_response(data=resp, message="更新成功")


@router.post("/plans/{plan_id}/items", summary="手动添加培训教材")
async def add_item(
    plan_id: UUID,
    body: NewEmployeeTrainingItemAdd,
    db: AsyncSession = Depends(get_db),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _require_user(current_user)
    resp = await service.add_item(plan_id, body.model_dump(exclude_unset=True), user_id)
    if not resp:
        raise NotFoundException(resource="新员工培训计划", resource_id=str(plan_id))
    return success_response(data=resp, message="已添加培训教材")


@router.get("/available-trainees", summary="可一起培训的新员工列表")
async def list_available_trainees(
    department: str | None = Query(None, description="按部门筛选（可选）"),
    exclude_plan_id: UUID | None = Query(None, description="排除当前计划（避免重复）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    """获取可一起培训的新员工列表（未完成的计划，排除当前计划）"""
    _require_user(current_user)
    trainees = await service.list_available_trainees(
        department=department,
        exclude_plan_id=exclude_plan_id,
        page=page,
        page_size=page_size,
    )
    return success_response(data=trainees)


@router.post("/plans/{plan_id}/start-training", summary="开始培训（创建培训会话）")
async def start_training(
    plan_id: UUID,
    body: NewEmployeeTrainingStartRequest,
    db: AsyncSession = Depends(get_db),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _require_user(current_user)
    additional = None
    if body.additional_trainees:
        additional = [t.model_dump() for t in body.additional_trainees]
    result = await service.start_training(plan_id, body.item_ids, user_id, additional)
    return success_response(
        data=NewEmployeeTrainingStartResponse.model_validate(result).model_dump(
            mode="json"
        ),
        message="请前往培训资料页面完善培训信息",
    )


@router.delete("/plans/{plan_id}", summary="删除新员工培训计划")
async def delete_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _require_user(current_user)
    deleted = await service.delete_plan(plan_id, user_id)
    if not deleted:
        raise NotFoundException(resource="新员工培训计划", resource_id=str(plan_id))
    return success_response(message="已删除")


@router.get("/plans/{plan_id}/export-confirmation", summary="导出岗位培训确认表")
async def export_confirmation(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: NewEmployeeTrainingService = Depends(_get_service),
    current_user: CurrentUser = None,
) -> Any:
    """导出岗位培训确认表（APP14），包含员工基本信息和所有培训记录。"""
    _require_user(current_user)
    plan_data = await service.get_plan(plan_id)
    if not plan_data:
        raise NotFoundException(resource="新员工培训计划", resource_id=str(plan_id))

    from app.modules.hr.position_training_confirmation_generator import (
        generate_position_training_confirmation,
    )

    # 构建培训记录列表
    training_items = []
    for item in plan_data.get("items", []):
        training_items.append(
            {
                "textbook_name": item.get("textbook_name", ""),
                "textbook_code": item.get("textbook_code", ""),
                "training_date": item.get("completed_date", ""),
                "assessment_result": item.get("assessment_method", ""),
            }
        )

    try:
        buffer: BytesIO = generate_position_training_confirmation(
            employee_name=plan_data["employee_name"],
            employee_number=plan_data.get("employee_number"),
            department=plan_data["department"],
            position=plan_data["position"],
            hire_date=plan_data["hire_date"],
            employee_category="入职",
            training_items=training_items,
        )
    except FileNotFoundError as e:
        raise AppException(status_code=400, message=str(e))

    def _iterfile() -> Any:
        buffer.seek(0)
        yield buffer.read()

    filename = (
        f"岗位培训确认表_{plan_data['employee_name']}_"
        f"{plan_data['employee_number'] or 'nonumber'}.xlsx"
    )
    return StreamingResponse(
        _iterfile(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
