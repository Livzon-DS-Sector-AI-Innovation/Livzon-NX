"""Safety API — scheduled_tasks endpoints."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.response import ApiResponse
from app.modules.safety.schemas import (
    CardPreviewRequest,
    ScheduledTaskCreate,
    ScheduledTaskLogResponse,
    ScheduledTaskResponse,
    ScheduledTaskUpdate,
)
from app.modules.safety.service import (
    ScheduledTaskService,
)

scheduled_tasks_router = APIRouter()


@scheduled_tasks_router.get("/scheduled-tasks/data-source-options", response_model=ApiResponse, summary="获取可用数据来源选项")
async def get_data_source_options():
    """获取可用的数据来源列表（供前端下拉选择）"""
    options = ScheduledTaskService.get_data_source_options()
    return ApiResponse(data=options)


@scheduled_tasks_router.post("/scheduled-tasks/preview-card", response_model=ApiResponse, summary="预览消息卡片")
async def preview_card(
    data: CardPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """预览消息卡片渲染效果"""
    service = ScheduledTaskService(db)
    result = await service.preview_card(data)
    return ApiResponse(data=result)


@scheduled_tasks_router.get("/scheduled-tasks/feishu-chats", response_model=ApiResponse, summary="获取飞书群聊列表")
async def get_feishu_chats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """获取可选的飞书群聊列表（从缓存或配置中读取）"""
    from app.core.config import get_settings

    settings = get_settings()
    chats: list[dict] = []
    # Include configured chats
    if settings.FEISHU_EQUIPMENT_CHAT_ID:
        chats.append({
            "chat_id": settings.FEISHU_EQUIPMENT_CHAT_ID,
            "name": "设备管理群",
        })
    if settings.FEISHU_SAFETY_CHAT_ID:
        chats.append({
            "chat_id": settings.FEISHU_SAFETY_CHAT_ID,
            "name": "安全模块功能测试群",
        })
    return ApiResponse(data=chats)


@scheduled_tasks_router.get("/scheduled-tasks", response_model=ApiResponse, summary="获取定时任务列表")
async def get_scheduled_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    is_enabled: bool | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """获取定时任务列表（分页）"""
    service = ScheduledTaskService(db)
    skip = (page - 1) * page_size
    items, total = await service.get_tasks(skip, page_size, is_enabled, search)
    return ApiResponse(
        data=[ScheduledTaskResponse.model_validate(t) for t in items],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@scheduled_tasks_router.post("/scheduled-tasks", response_model=ApiResponse, summary="创建定时任务")
async def create_scheduled_task(
    data: ScheduledTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """创建新的定时任务"""
    service = ScheduledTaskService(db)
    task = await service.create_task(data)
    await db.commit()
    return ApiResponse(data=ScheduledTaskResponse.model_validate(task))


@scheduled_tasks_router.get("/scheduled-tasks/{task_id}", response_model=ApiResponse, summary="获取定时任务详情")
async def get_scheduled_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """获取单个定时任务详情"""
    service = ScheduledTaskService(db)
    task = await service.get_task(task_id)
    if not task:
        return ApiResponse(code=404, message="定时任务不存在")
    return ApiResponse(data=ScheduledTaskResponse.model_validate(task))


@scheduled_tasks_router.put("/scheduled-tasks/{task_id}", response_model=ApiResponse, summary="更新定时任务")
async def update_scheduled_task(
    task_id: uuid.UUID,
    data: ScheduledTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """更新定时任务配置"""
    service = ScheduledTaskService(db)
    task = await service.update_task(task_id, data)
    if not task:
        return ApiResponse(code=404, message="定时任务不存在")
    await db.commit()
    return ApiResponse(data=ScheduledTaskResponse.model_validate(task))


@scheduled_tasks_router.delete("/scheduled-tasks/{task_id}", response_model=ApiResponse, summary="删除定时任务")
async def delete_scheduled_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """删除定时任务（软删除）"""
    service = ScheduledTaskService(db)
    ok = await service.delete_task(task_id)
    if not ok:
        return ApiResponse(code=404, message="定时任务不存在")
    await db.commit()
    return ApiResponse(data=None)


@scheduled_tasks_router.post("/scheduled-tasks/{task_id}/toggle", response_model=ApiResponse, summary="启用/禁用定时任务")
async def toggle_scheduled_task(
    task_id: uuid.UUID,
    enabled: bool = Query(..., description="是否启用"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """切换定时任务的启用/禁用状态"""
    service = ScheduledTaskService(db)
    task = await service.toggle_task(task_id, enabled)
    if not task:
        return ApiResponse(code=404, message="定时任务不存在")
    await db.commit()
    return ApiResponse(data=ScheduledTaskResponse.model_validate(task))


@scheduled_tasks_router.post("/scheduled-tasks/{task_id}/run", response_model=ApiResponse, summary="手动执行定时任务")
async def run_scheduled_task_now(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """立即手动执行一次定时任务"""
    service = ScheduledTaskService(db)
    log = await service.run_task_now(task_id)
    if not log:
        return ApiResponse(code=404, message="定时任务不存在")
    await db.commit()
    return ApiResponse(data=ScheduledTaskLogResponse.model_validate(log))


@scheduled_tasks_router.get("/scheduled-tasks/{task_id}/logs", response_model=ApiResponse, summary="获取定时任务执行日志")
async def get_scheduled_task_logs(
    task_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """获取定时任务的执行日志列表"""
    service = ScheduledTaskService(db)
    skip = (page - 1) * page_size
    logs, total = await service.get_logs(task_id, skip, page_size)
    return ApiResponse(
        data=[ScheduledTaskLogResponse.model_validate(log) for log in logs],
        meta={"page": page, "page_size": page_size, "total": total},
    )


# ── 安全模块飞书 WebSocket 管理 ──


@scheduled_tasks_router.post("/feishu/ws/restart", response_model=ApiResponse, summary="手动恢复飞书 WebSocket 连接")
async def restart_feishu_ws(
    current_user: CurrentUser | None = Depends(get_current_user),
):
    """WS 因重试次数耗尽（3 次）自动停止后，手动重新建立连接。

    无需传参，调用即重置重试计数并创建新的 WS 任务。
    返回当前已注册的事件类型列表。
    """
    from app.modules.safety.feishu.event_client import restart_ws

    result = await restart_ws()
    return ApiResponse(data=result)


@scheduled_tasks_router.get("/feishu/ws/status", response_model=ApiResponse, summary="查询飞书 WebSocket 连接状态")
async def get_feishu_ws_status():
    """查询安全模块飞书 WebSocket 当前状态。

    返回是否已连接、已注册事件类型、最大重试次数。
    """
    from app.modules.safety.feishu.event_client import get_ws_status

    result = await get_ws_status()
    return ApiResponse(data=result)
