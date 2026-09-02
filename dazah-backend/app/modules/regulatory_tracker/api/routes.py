"""Regulatory Tracker API routes."""

import asyncio
import logging
import time
import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_db
from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.schemas import (
    RegulatoryTrackerNotificationSettingUpdate,
    TrackerLedgerDetailRead,
    TrackerLedgerDetailResponse,
    TrackerLedgerItemRead,
    TrackerLedgerListResponse,
    TrackerLedgerPageRead,
)
from app.modules.regulatory_tracker.services.ai_analysis_service import (
    analyze_and_update,
    analyze_new_documents,
)
from app.modules.regulatory_tracker.services.notification_service import (
    RegulatoryTrackerNotificationService,
)
from app.modules.regulatory_tracker.services.summary_backfill_service import (
    backfill_document_summaries,
)
from app.modules.regulatory_tracker.services.sync_service import run_all_sites

logger = logging.getLogger(__name__)

router = APIRouter()

# 模块级任务状态：用于后台异步抓取任务的状态查询
_SYNC_TASK_TIMEOUT_SECONDS = 600  # 超过10分钟自动标记为超时
_sync_task_state: dict[str, Any] = {
    "status": "idle",  # idle / running / completed / failed
    "started_at": None,
    "completed_at": None,
    "result": None,
    "error": None,
}


def _check_sync_timeout() -> None:
    """如果任务运行超过超时阈值，自动标记为失败。"""
    if _sync_task_state["status"] != "running":
        return
    if _sync_task_state["started_at"] is None:
        return
    elapsed = time.time() - (_sync_task_state["started_at"] or 0)
    if elapsed > _SYNC_TASK_TIMEOUT_SECONDS:
        _sync_task_state["status"] = "failed"
        _sync_task_state["error"] = f"任务执行超时（{int(elapsed)}秒）"
        _sync_task_state["completed_at"] = time.time()


async def _run_sync_background(recent_days: int) -> None:
    """后台执行法规抓取，更新模块级任务状态。"""
    _sync_task_state["status"] = "running"
    _sync_task_state["started_at"] = time.time()
    _sync_task_state["completed_at"] = None
    _sync_task_state["error"] = None
    _sync_task_state["result"] = None
    try:
        async with async_session_factory() as db:
            result = await run_all_sites(db, recent_days=recent_days)
        _sync_task_state["result"] = result
        _sync_task_state["status"] = "completed"
    except Exception as exc:
        logger.exception("❌ 后台法规抓取任务异常")
        _sync_task_state["error"] = str(exc)
        _sync_task_state["status"] = "failed"
    finally:
        _sync_task_state["completed_at"] = time.time()


def _default_recent_week_start() -> date:
    return date.today() - timedelta(days=6)


def _default_recent_week_end() -> date:
    return date.today()


def _contains_cjk(text: str | None) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _resolve_display_summary(document: object) -> str | None:
    ai_summary: Any = getattr(document, "ai_summary", None)
    summary_text: Any = getattr(document, "summary_text", None)
    for candidate in (ai_summary, summary_text):
        if isinstance(candidate, str) and _contains_cjk(candidate):
            return candidate.strip()
    for candidate in (summary_text, ai_summary):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _build_tracker_ledger_item(document: object) -> TrackerLedgerItemRead:
    payload = TrackerLedgerItemRead.model_validate(document).model_dump()
    payload["summary_text"] = _resolve_display_summary(document)
    return TrackerLedgerItemRead.model_validate(payload)


def _normalize_ai_key_points(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, dict):
        normalized: list[str] = []
        for item in value.values():
            if isinstance(item, list):
                normalized.extend(str(entry) for entry in item if entry is not None)
            elif item is not None:
                normalized.append(str(item))
        return normalized or None
    return [str(value)]


def _build_tracker_ledger_detail(document: object) -> TrackerLedgerDetailRead:
    detail_payload = TrackerLedgerDetailRead.model_validate(document).model_dump()
    detail_payload["ai_key_points"] = _normalize_ai_key_points(
        getattr(document, "ai_key_points", None)
    )
    detail_payload["summary_text"] = _resolve_display_summary(document)
    return TrackerLedgerDetailRead.model_validate(detail_payload)


# ============ 统计摘要 ============


@router.get("/regulatory-tracker/summary", summary="法规追踪统计摘要")
async def get_summary(db: AsyncSession = Depends(get_db)) -> Any:
    """
    返回法规追踪统计信息：
    - totalCount: 文档总数
    - todayNewCount: 今日新增数
    - unreadNewCount: 未读新增数
    - lastSyncTime: 最近同步时间
    - lastSyncStatus: 最近同步状态
    """
    stats = await repo.get_summary_stats(db)
    return {
        "code": 200,
        "message": "success",
        "data": stats,
    }


@router.post(
    "/regulatory-documents/sync",
    summary="手动触发法规站点同步",
)
async def trigger_manual_sync(
    recent_days: int = Query(
        2,
        ge=1,
        le=366,
        alias="recentDays",
        description="最近抓取天数窗口",
    ),
) -> Any:
    """手动触发法规跟踪同步，后台异步执行，立即返回任务启动状态。

    通过 ``GET /regulatory-documents/sync/status`` 轮询任务进度。
    """
    _check_sync_timeout()
    if _sync_task_state["status"] == "running":
        return {
            "code": 409,
            "message": "已有抓取任务正在执行",
            "data": _sync_task_state,
        }

    asyncio.create_task(_run_sync_background(recent_days))
    return {
        "code": 200,
        "message": "success",
        "data": {
            "status": "started",
            "message": "法规抓取任务已启动",
        },
    }


@router.get("/regulatory-documents/sync/status", summary="查询法规抓取任务状态")
async def get_sync_status() -> Any:
    """返回后台法规抓取任务的当前状态。

    状态取值：``idle`` / ``running`` / ``completed`` / ``failed``。
    ``completed`` 时 ``result`` 字段包含上次执行结果。
    """
    return {"code": 200, "message": "success", "data": _sync_task_state}


@router.get(
    "/regulatory-documents/notification-settings", summary="获取法规更新推送配置"
)
async def get_notification_settings(
    db: AsyncSession = Depends(get_db),
) -> Any:
    settings = await RegulatoryTrackerNotificationService(
        db
    ).get_notification_settings()
    return {
        "code": 200,
        "message": "success",
        "data": settings.model_dump(mode="json"),
    }


@router.get(
    "/regulatory-documents/notification-recipients", summary="获取法规更新推送接收人"
)
async def list_notification_recipients(
    db: AsyncSession = Depends(get_db),
) -> Any:
    items = await RegulatoryTrackerNotificationService(
        db
    ).list_notification_recipient_options()
    return {
        "code": 200,
        "message": "success",
        "data": [item.model_dump(mode="json") for item in items],
    }


@router.put(
    "/regulatory-documents/notification-settings", summary="更新法规更新推送配置"
)
async def update_notification_settings(
    data: RegulatoryTrackerNotificationSettingUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    settings = await RegulatoryTrackerNotificationService(
        db
    ).update_notification_settings(data)
    return {
        "code": 200,
        "message": "推送配置已保存",
        "data": settings.model_dump(mode="json"),
    }


# ============ 法规文档列表 ============


@router.get(
    "/regulatory-documents",
    summary="法规文档列表",
    response_model=TrackerLedgerListResponse,
)
async def list_documents(
    keyword: str | None = Query(None, description="关键词搜索"),
    source_site: str | None = Query(None, alias="sourceSite", description="来源网站"),
    publish_date_from: date | None = Query(
        alias="publishDateFrom",
        default_factory=_default_recent_week_start,
        description="发布日期起始",
    ),
    publish_date_to: date | None = Query(
        alias="publishDateTo",
        default_factory=_default_recent_week_end,
        description="发布日期结束",
    ),
    capture_date_from: date | None = Query(
        None, alias="captureDateFrom", description="抓取日期起始"
    ),
    capture_date_to: date | None = Query(
        None, alias="captureDateTo", description="抓取日期结束"
    ),
    status_text: str | None = Query(None, alias="statusText", description="状态筛选"),
    classification: str | None = Query(None, description="分类筛选"),
    is_new: bool | None = Query(None, alias="isNew", description="是否新增"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize", description="每页条数"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    获取法规文档列表，支持多种筛选条件和分页。
    """
    documents, total = await repo.get_documents_with_filters(
        db=db,
        keyword=keyword,
        source_site=source_site,
        publish_date_from=publish_date_from,
        publish_date_to=publish_date_to,
        capture_date_from=capture_date_from,
        capture_date_to=capture_date_to,
        status_text=status_text,
        classification=classification,
        is_new=is_new,
        page=page,
        page_size=page_size,
    )

    items = [_build_tracker_ledger_item(doc) for doc in documents]

    return TrackerLedgerListResponse(
        code=200,
        message="success",
        data=TrackerLedgerPageRead(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if page_size > 0 else 0,
        ),
    )


# ============ 标记已读 ============


@router.patch("/regulatory-documents/{doc_id}/read", summary="标记文档已读")
async def mark_document_read(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    将指定文档标记为已读（is_new=false）。
    """
    doc = await repo.get_document_by_id(db, doc_id)
    if not doc:
        return {
            "code": 404,
            "message": "文档不存在",
            "data": None,
        }

    await repo.update_document(
        db,
        doc_id,
        {
            "is_new": False,
            "is_read": True,
        },
    )
    await db.commit()

    return {
        "code": 200,
        "message": "success",
        "data": {"id": str(doc_id)},
    }


# ============ 同步任务列表 ============


@router.get("/sync-jobs", summary="同步任务列表")
async def list_sync_jobs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(
        20, ge=1, le=100, alias="pageSize", description="每页条数"
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    获取同步任务日志列表。
    """
    jobs, total = await repo.get_sync_jobs_list(
        db=db,
        page=page,
        page_size=page_size,
    )

    # 转换为响应格式
    items = []
    for job in jobs:
        items.append(
            {
                "id": str(job.id),
                "sourceId": str(job.source_id),
                "channelId": str(job.channel_id),
                "jobType": job.job_type,
                "startedAt": job.started_at.isoformat() if job.started_at else None,
                "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
                "status": job.status,
                "totalPages": job.total_pages,
                "checkedCount": job.checked_count,
                "newCount": job.new_count,
                "updatedCount": job.updated_count,
                "errorMessage": job.error_message,
                "createdAt": job.created_at.isoformat() if job.created_at else None,
            }
        )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        },
    }


# ============ AI 分析 ============


@router.post("/regulatory-documents/analyze", summary="触发 AI 分析")
async def trigger_ai_analysis(
    limit: int = Query(10, ge=1, le=50, description="最多分析文档数量"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    触发 AI 分析未处理的文档。
    """
    stats = await analyze_new_documents(db, limit=limit)
    return {
        "code": 200,
        "message": "success",
        "data": stats,
    }


@router.post("/regulatory-documents/backfill-summaries", summary="回填中文内容总结")
async def trigger_summary_backfill(
    limit: int = Query(200, ge=1, le=1000, description="最多回填文档数量"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """回填国际站点历史文档的中文内容总结。"""
    stats = await backfill_document_summaries(db, limit=limit)
    return {
        "code": 200,
        "message": "success",
        "data": stats,
    }


@router.post("/regulatory-documents/{doc_id}/analyze", summary="分析单个文档")
async def analyze_single_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    对单个文档执行 AI 分析。
    """
    doc = await repo.get_document_by_id(db, doc_id)
    if not doc:
        return {
            "code": 404,
            "message": "文档不存在",
            "data": None,
        }

    success = await analyze_and_update(db, doc)
    return {
        "code": 200,
        "message": "success" if success else "failed",
        "data": {"id": str(doc_id), "analyzed": success},
    }


@router.get(
    "/regulatory-documents/{doc_id}",
    summary="法规文档详情",
    response_model=TrackerLedgerDetailResponse,
)
async def get_document_detail(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    获取法规台账详情。
    """
    doc = await repo.get_document_by_id(db, doc_id)
    if not doc:
        return {
            "code": 404,
            "message": "文档不存在",
            "data": None,
        }

    return TrackerLedgerDetailResponse(
        code=200,
        message="success",
        data=_build_tracker_ledger_detail(doc),
    )
