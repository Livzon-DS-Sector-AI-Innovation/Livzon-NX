"""Regulatory Tracker API routes."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.services.ai_analysis_service import analyze_new_documents, analyze_and_update
from app.modules.regulatory_tracker.schemas import (
    RegulatoryDocumentRead,
    SyncJobRead,
)

router = APIRouter()


# ============ 统计摘要 ============

@router.get("/regulatory-tracker/summary", summary="法规追踪统计摘要")
async def get_summary(db: AsyncSession = Depends(get_db)):
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


# ============ 法规文档列表 ============

@router.get("/regulatory-documents", summary="法规文档列表")
async def list_documents(
    keyword: str | None = Query(None, description="关键词搜索"),
    publishDateFrom: date | None = Query(None, description="发布日期起始"),
    publishDateTo: date | None = Query(None, description="发布日期结束"),
    statusText: str | None = Query(None, description="状态筛选"),
    classification: str | None = Query(None, description="分类筛选"),
    isNew: bool | None = Query(None, description="是否新增"),
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取法规文档列表，支持多种筛选条件和分页。
    """
    documents, total = await repo.get_documents_with_filters(
        db=db,
        keyword=keyword,
        publish_date_from=publishDateFrom,
        publish_date_to=publishDateTo,
        status_text=statusText,
        classification=classification,
        is_new=isNew,
        page=page,
        page_size=pageSize,
    )
    
    # 转换为响应格式
    items = []
    for doc in documents:
        items.append({
            "id": str(doc.id),
            "sourceId": str(doc.source_id),
            "channelId": str(doc.channel_id),
            "documentId": doc.document_id,
            "title": doc.title,
            "publishDate": doc.publish_date.isoformat() if doc.publish_date else None,
            "statusText": doc.status_text,
            "classification": doc.classification,
            "originalUrl": doc.original_url,
            "isNew": doc.is_new,
            "isRead": doc.is_read,
            "firstFoundAt": doc.first_found_at.isoformat() if doc.first_found_at else None,
            "lastCheckedAt": doc.last_checked_at.isoformat() if doc.last_checked_at else None,
            "createdAt": doc.created_at.isoformat() if doc.created_at else None,
            "aiSummary": doc.ai_summary,
            "aiKeyPoints": doc.ai_key_points,
            "aiRelevanceScore": doc.ai_relevance_score,
            "aiAnalyzedAt": doc.ai_analyzed_at.isoformat() if doc.ai_analyzed_at else None,
            "aiAnalysisStatus": doc.ai_analysis_status,
        })
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": pageSize,
            "totalPages": (total + pageSize - 1) // pageSize if pageSize > 0 else 0,
        },
    }


# ============ 标记已读 ============

@router.patch("/regulatory-documents/{doc_id}/read", summary="标记文档已读")
async def mark_document_read(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
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
    
    await repo.update_document(db, doc_id, {
        "is_new": False,
        "is_read": True,
    })
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
    pageSize: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取同步任务日志列表。
    """
    jobs, total = await repo.get_sync_jobs_list(
        db=db,
        page=page,
        page_size=pageSize,
    )
    
    # 转换为响应格式
    items = []
    for job in jobs:
        items.append({
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
        })
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": pageSize,
            "totalPages": (total + pageSize - 1) // pageSize if pageSize > 0 else 0,
        },
    }

# ============ AI 分析 ============

@router.post("/regulatory-documents/analyze", summary="触发 AI 分析")
async def trigger_ai_analysis(
    limit: int = Query(10, ge=1, le=50, description="最多分析文档数量"),
    db: AsyncSession = Depends(get_db),
):
    """
    触发 AI 分析未处理的文档。
    """
    stats = await analyze_new_documents(db, limit=limit)
    return {
        "code": 200,
        "message": "success",
        "data": stats,
    }


@router.post("/regulatory-documents/{doc_id}/analyze", summary="分析单个文档")
async def analyze_single_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
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
