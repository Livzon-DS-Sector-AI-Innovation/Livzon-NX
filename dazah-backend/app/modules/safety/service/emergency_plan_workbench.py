"""应急预案 AI 工作台：正文读写、修订快照与后台任务编排。

- 正文与修订各自独立成表；每次内容变化生成递增修订号，AI 生成/修正、
  对话修改、人工保存、导入与恢复都留痕可撤销。
- 生成/审核/非模板导入属于长耗时任务，走 ``app/core/jobs.py``（HTTP 请求
  禁止超过 5 秒），每个预案同时只允许一个任务，任务运行期间拒绝保存。
- 后台任务函数自带独立数据库会话；LLM 异常映射为可读的业务错误文案。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import AppException, NotFoundException
from app.core.jobs import (
    get_job_status,
    is_job_running,
    submit_job,
    update_job_progress,
)
from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.safety.models import (
    EmergencyPlan,
    EmergencyPlanAiMessage,
    EmergencyPlanContent,
    EmergencyPlanRevision,
)
from app.modules.safety.schemas.emergency_plan_ai import (
    ChatEdit,
    CheckIssue,
    ContentStatus,
    EmergencyPlanContentResponse,
    EmergencyPlanContentUpdate,
    EmergencyPlanDocument,
    EmergencyPlanGenerateRequest,
    EmergencyPlanJobStatus,
    EmergencyPlanReviewReport,
    EmergencyPlanRevisionDetail,
    RevisionSource,
)
from app.modules.safety.service.emergency_plan_ai import (
    apply_chat_edits,
    chat_reply,
    generate_document,
    review_document,
)
from app.modules.safety.service.emergency_plan_checks import run_checks
from app.modules.safety.service.emergency_plan_context import (
    PlanGenerationContext,
    context_for_document,
    context_for_params,
)

logger = logging.getLogger(__name__)

JOB_TTL_SECONDS = 3600
_CHANGE_LOG_LIMIT = 200

JobKindHint = str  # generate / review / import_structure


@dataclass
class ContentMutation:
    """一次正文变化（统一创建修订快照与更新主表）。"""

    document: EmergencyPlanDocument
    source: RevisionSource
    summary: str
    changes: list[dict[str, str]] | None = None
    ai_generated: bool | None = None
    review_report: dict[str, Any] | None = None
    status: ContentStatus | None = None
    generation_params: dict[str, Any] | None = None


def _llm_error_message(exc: Exception) -> str:
    if isinstance(exc, LLMConfigError):
        return "尚未配置分析模型，请先在系统管理中启用 AI 模型配置"
    if isinstance(exc, LLMRateLimitError):
        return "模型调用触发限流，请稍后重试"
    if isinstance(exc, LLMOutputError):
        return "AI 返回内容无法解析，请重试"
    if isinstance(exc, LLMProviderError):
        return "模型服务暂不可用，请稍后重试"
    return "AI 处理失败，请稍后重试"


# ---------- 查询 ----------


async def get_content_row(
    db: AsyncSession, plan_id: UUID
) -> EmergencyPlanContent | None:
    result = await db.execute(
        select(EmergencyPlanContent).where(
            EmergencyPlanContent.plan_id == plan_id,
            EmergencyPlanContent.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def get_plan_or_404(db: AsyncSession, plan_id: UUID) -> EmergencyPlan:
    plan = await db.get(EmergencyPlan, plan_id)
    if plan is None or plan.is_deleted:
        raise NotFoundException("应急预案")
    return plan


def parse_document(raw: Any) -> EmergencyPlanDocument | None:
    if not raw:
        return None
    try:
        return EmergencyPlanDocument.model_validate(raw)
    except Exception:  # noqa: BLE001 — 历史数据损坏时不阻塞读取
        logger.warning("预案正文解析失败", exc_info=True)
        return None


async def build_content_response(
    db: AsyncSession, plan_id: UUID, *, include_document: bool = True
) -> EmergencyPlanContentResponse:
    plan = await get_plan_or_404(db, plan_id)
    row = await get_content_row(db, plan_id)
    job: EmergencyPlanJobStatus | None = None
    if await is_job_running(job_id_for(plan_id)):
        status = await get_job_status(job_id_for(plan_id)) or {}
        job = EmergencyPlanJobStatus(
            job_id=job_id_for(plan_id),
            kind=status.get("kind"),
            state="running",
            progress=status.get("progress", ""),
        )
    document = parse_document(row.content) if row else None
    last_review: EmergencyPlanReviewReport | None = None
    if row is not None and row.last_review:
        try:
            last_review = EmergencyPlanReviewReport.model_validate(row.last_review)
        except Exception:  # noqa: BLE001
            logger.warning("预案审核报告解析失败: plan=%s", plan_id, exc_info=True)
    return EmergencyPlanContentResponse(
        plan_id=plan.id,
        plan_name=plan.name,
        content_status=row.content_status if row else "empty",
        revision_no=row.revision_no if row else 0,
        ai_generated=row.ai_generated if row else False,
        content=document if include_document else None,
        last_review=last_review,
        last_reviewed_at=row.last_reviewed_at if row else None,
        content_updated_at=row.content_updated_at if row else None,
        job=job,
    )


async def load_document(db: AsyncSession, plan_id: UUID) -> EmergencyPlanDocument:
    row = await get_content_row(db, plan_id)
    document = parse_document(row.content) if row else None
    if document is None:
        raise AppException(status_code=422, message="该预案尚无正文内容")
    return document


# ---------- 修订 ----------


def _changed_sections(
    before: EmergencyPlanDocument | None, after: EmergencyPlanDocument
) -> list[str]:
    if before is None:
        return ["*"]
    changed: list[str] = []
    if before.preface != after.preface:
        changed.append("preface")
    if before.organization != after.organization:
        changed.append("organization")
    if before.workshop_organization != after.workshop_organization:
        changed.append("workshop_organization")
    before_chapters = {chapter.key: chapter for chapter in before.chapters}
    for chapter in after.chapters:
        old = before_chapters.get(chapter.key)
        if old is None or old.title != chapter.title or old.content != chapter.content:
            changed.append(chapter.key)
    return changed


async def apply_mutation(
    db: AsyncSession, plan_id: UUID, mutation: ContentMutation, user_id: UUID
) -> EmergencyPlanContentResponse:
    """写入正文与修订快照（调用方负责 commit）。"""
    plan = await get_plan_or_404(db, plan_id)
    row = await get_content_row(db, plan_id)
    if row is None:
        row = EmergencyPlanContent(plan_id=plan_id, created_by=user_id)
        db.add(row)
    before = parse_document(row.content)
    row.content = mutation.document.model_dump(mode="json")
    row.content_status = mutation.status or (
        "reviewed" if mutation.source == "ai_fix" else "draft"
    )
    row.revision_no = (row.revision_no or 0) + 1
    if mutation.ai_generated is not None:
        row.ai_generated = mutation.ai_generated
    if mutation.generation_params is not None:
        row.generation_params = mutation.generation_params
    if mutation.review_report is not None:
        row.last_review = mutation.review_report
    row.updated_by = user_id
    row.content_updated_at = datetime.now(UTC)
    await db.flush()
    db.add(
        EmergencyPlanRevision(
            plan_id=plan_id,
            revision_no=row.revision_no,
            source=mutation.source,
            summary=mutation.summary[:500],
            content=mutation.document.model_dump(mode="json"),
            changed_sections=_changed_sections(before, mutation.document),
            changes=(mutation.changes or [])[:_CHANGE_LOG_LIMIT],
            created_by=user_id,
        )
    )
    plan.updated_by = user_id
    await db.flush()
    return await build_content_response(db, plan_id)


async def list_revisions(
    db: AsyncSession, plan_id: UUID, page: int = 1, page_size: int = 50
) -> tuple[list[EmergencyPlanRevision], int]:
    conditions = (
        EmergencyPlanRevision.plan_id == plan_id,
        EmergencyPlanRevision.is_deleted.is_(False),
    )
    total = (
        await db.execute(
            select(func.count()).select_from(EmergencyPlanRevision).where(*conditions)
        )
    ).scalar() or 0
    rows = await db.execute(
        select(EmergencyPlanRevision)
        .where(*conditions)
        .order_by(EmergencyPlanRevision.revision_no.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows.scalars().all()), total


async def get_revision_detail(
    db: AsyncSession, plan_id: UUID, revision_no: int
) -> EmergencyPlanRevisionDetail:
    result = await db.execute(
        select(EmergencyPlanRevision).where(
            EmergencyPlanRevision.plan_id == plan_id,
            EmergencyPlanRevision.revision_no == revision_no,
            EmergencyPlanRevision.is_deleted.is_(False),
        )
    )
    revision = result.scalar_one_or_none()
    if revision is None:
        raise NotFoundException("修订记录")
    document = parse_document(revision.content)
    if document is None:
        raise AppException(status_code=422, message="修订正文数据损坏")
    return EmergencyPlanRevisionDetail(
        id=revision.id,
        revision_no=revision.revision_no,
        source=revision.source,
        summary=revision.summary,
        changed_sections=revision.changed_sections or [],
        created_at=revision.created_at,
        content=document,
        changes=revision.changes or [],
    )


async def restore_revision(
    db: AsyncSession, plan_id: UUID, revision_no: int, user_id: UUID
) -> EmergencyPlanContentResponse:
    detail = await get_revision_detail(db, plan_id, revision_no)
    mutation = ContentMutation(
        document=detail.content,
        source="restore",
        summary=f"恢复到修订 {revision_no}",
    )
    return await apply_mutation(db, plan_id, mutation, user_id)


# ---------- 内容保存 / 校验 / 对话应用 ----------


def _check_log(issues: list[CheckIssue]) -> list[dict[str, str]]:
    return [
        {
            "section": issue.section,
            "reason": issue.message,
            "before": issue.quote,
            "after": issue.replacement or "",
        }
        for issue in issues[:_CHANGE_LOG_LIMIT]
    ]


async def save_content(
    db: AsyncSession,
    plan_id: UUID,
    data: EmergencyPlanContentUpdate,
    user_id: UUID,
) -> EmergencyPlanContentResponse:
    await get_plan_or_404(db, plan_id)
    row = await get_content_row(db, plan_id)
    if row is not None and row.revision_no != data.base_revision_no:
        raise AppException(
            status_code=409,
            message="正文已被其他修改更新，请刷新后重试",
        )
    if await is_job_running(job_id_for(plan_id)):
        raise AppException(status_code=409, message="AI 任务运行中，暂不能保存")
    issues = run_checks(data.content)
    was_finalized = row is not None and row.content_status == "finalized"
    mutation = ContentMutation(
        document=data.content,
        source="user_edit",
        summary=data.summary[:200] or "人工编辑",
        changes=_check_log(issues),
        status="draft" if was_finalized else None,
    )
    return await apply_mutation(db, plan_id, mutation, user_id)


async def run_checks_only(
    db: AsyncSession, plan_id: UUID
) -> tuple[EmergencyPlanDocument, list[CheckIssue], PlanGenerationContext | None]:
    document = await load_document(db, plan_id)
    row = await get_content_row(db, plan_id)
    context = await context_for_document(
        db, document, row.generation_params if row else None
    )
    issues = run_checks(
        document, substances=context.substance_names, msds_text=context.msds_text
    )
    return document, issues, context


async def chat_turn(
    db: AsyncSession,
    plan_id: UUID,
    *,
    message: str,
    section: str | None,
    history: list[dict[str, str]],
) -> tuple[str, list[ChatEdit]]:
    """对话一轮（不落库）：返回回复与校验后的补丁。"""
    document = await load_document(db, plan_id)
    return await chat_reply(
        db, document=document, history=history, message=message, section=section
    )


async def apply_chat_edits_with_revision(
    db: AsyncSession,
    plan_id: UUID,
    *,
    message: str,
    reply: str,
    edits: list[ChatEdit],
    base_revision_no: int,
    user_id: UUID,
) -> tuple[EmergencyPlanContentResponse, list[CheckIssue], list[str]]:
    """应用对话补丁：乐观锁校验 → 修订 → 记录对话 → 重新校验。"""
    row = await get_content_row(db, plan_id)
    if row is not None and row.revision_no != base_revision_no:
        raise AppException(status_code=409, message="正文已被其他修改更新，请重试")
    if await is_job_running(job_id_for(plan_id)):
        raise AppException(status_code=409, message="AI 任务运行中，暂不能修改")
    document = await load_document(db, plan_id)
    new_document, sections = apply_chat_edits(document, edits)
    mutation = ContentMutation(
        document=new_document,
        source="ai_chat",
        summary=reply[:200] or "AI 对话修改",
        ai_generated=True,
    )
    response = await apply_mutation(db, plan_id, mutation, user_id)
    db.add(
        EmergencyPlanAiMessage(
            plan_id=plan_id, role="user", content=message[:8000], created_by=user_id
        )
    )
    db.add(
        EmergencyPlanAiMessage(
            plan_id=plan_id,
            role="assistant",
            content=reply[:8000],
            revision_no=response.revision_no,
            created_by=user_id,
        )
    )
    await db.flush()
    warnings = run_checks(new_document)
    return response, warnings, sections


async def record_chat_message(
    db: AsyncSession, plan_id: UUID, role: str, content: str, user_id: UUID
) -> None:
    db.add(
        EmergencyPlanAiMessage(
            plan_id=plan_id, role=role, content=content[:8000], created_by=user_id
        )
    )
    await db.flush()


async def list_chat_messages(
    db: AsyncSession, plan_id: UUID, limit: int = 100
) -> list[EmergencyPlanAiMessage]:
    result = await db.execute(
        select(EmergencyPlanAiMessage)
        .where(
            EmergencyPlanAiMessage.plan_id == plan_id,
            EmergencyPlanAiMessage.is_deleted.is_(False),
        )
        .order_by(EmergencyPlanAiMessage.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ---------- 后台任务 ----------


def job_id_for(plan_id: UUID) -> str:
    return f"job:safety-emergency-plan:{plan_id}"


def serialize_review_report(report: EmergencyPlanReviewReport) -> dict[str, Any]:
    return report.model_dump(mode="json")


def _job_error(exc: Exception, plan_id: UUID, action: str) -> AppException:
    if not isinstance(
        exc, (LLMConfigError, LLMRateLimitError, LLMOutputError, LLMProviderError)
    ):
        logger.exception("应急预案 AI %s失败: plan=%s", action, plan_id)
    return AppException(status_code=502, message=_llm_error_message(exc))


async def run_generate_job(
    plan_id: UUID,
    params: EmergencyPlanGenerateRequest,
    plan_name: str,
    user_id: UUID,
    job_id: str,
) -> dict[str, Any]:
    async with async_session_factory() as db:
        try:
            await update_job_progress(
                job_id, "正在汇总危化品与厂区资料…", ttl=JOB_TTL_SECONDS
            )
            context = await context_for_params(db, params)
            document = await generate_document(
                db,
                params=params,
                plan_name=plan_name,
                context=context,
                on_progress=lambda text: update_job_progress(
                    job_id, text, ttl=JOB_TTL_SECONDS
                ),
            )
            await update_job_progress(job_id, "AI 正在自检修正…", ttl=JOB_TTL_SECONDS)
            new_document, report = await review_document(
                db,
                document=document,
                context=context,
                on_progress=lambda text: update_job_progress(
                    job_id, text, ttl=JOB_TTL_SECONDS
                ),
            )
        except Exception as exc:
            await db.rollback()
            raise _job_error(exc, plan_id, "生成") from exc
        mutation = ContentMutation(
            document=new_document,
            source="ai_generate",
            summary="AI 生成预案初稿并通过自检修正",
            ai_generated=True,
            review_report=serialize_review_report(report),
            generation_params=params.model_dump(mode="json"),
        )
        response = await apply_mutation(db, plan_id, mutation, user_id)
        await db.commit()
        return response.model_dump(mode="json")


async def run_review_job(plan_id: UUID, user_id: UUID, job_id: str) -> dict[str, Any]:
    async with async_session_factory() as db:
        try:
            document = await load_document(db, plan_id)
            row = await get_content_row(db, plan_id)
            await update_job_progress(
                job_id, "正在汇总危化品与厂区资料…", ttl=JOB_TTL_SECONDS
            )
            context = await context_for_document(
                db, document, row.generation_params if row else None
            )
            new_document, report = await review_document(
                db,
                document=document,
                context=context,
                on_progress=lambda text: update_job_progress(
                    job_id, text, ttl=JOB_TTL_SECONDS
                ),
            )
        except Exception as exc:
            await db.rollback()
            raise _job_error(exc, plan_id, "审核") from exc
        mutation = ContentMutation(
            document=new_document,
            source="ai_fix",
            summary=f"AI 审核修正（{report.fixed_count} 处自动修正）",
            ai_generated=True,
            review_report=serialize_review_report(report),
            status="reviewed",
        )
        response = await apply_mutation(db, plan_id, mutation, user_id)
        await db.commit()
        return response.model_dump(mode="json")


async def run_import_structure_job(
    plan_id: UUID, user_id: UUID, job_id: str
) -> dict[str, Any]:
    async with async_session_factory() as db:
        try:
            document = await load_document(db, plan_id)
            row = await get_content_row(db, plan_id)
            await update_job_progress(
                job_id, "AI 正在整理章节结构…", ttl=JOB_TTL_SECONDS
            )
            from app.modules.safety.service.emergency_plan_ai import (
                structure_document,
            )

            structured = await structure_document(db, document=document)
            if structured is None:
                structured = document
            await update_job_progress(job_id, "AI 正在审阅修正…", ttl=JOB_TTL_SECONDS)
            context = await context_for_document(
                db, structured, row.generation_params if row else None
            )
            new_document, report = await review_document(
                db,
                document=structured,
                context=context,
                on_progress=lambda text: update_job_progress(
                    job_id, text, ttl=JOB_TTL_SECONDS
                ),
            )
        except Exception as exc:
            await db.rollback()
            raise _job_error(exc, plan_id, "导入整理") from exc
        mutation = ContentMutation(
            document=new_document,
            source="ai_fix",
            summary=f"AI 整理导入文档并审核修正（{report.fixed_count} 处修正）",
            ai_generated=True,
            review_report=serialize_review_report(report),
            status="reviewed",
        )
        response = await apply_mutation(db, plan_id, mutation, user_id)
        await db.commit()
        return response.model_dump(mode="json")


async def submit_plan_job(
    db: AsyncSession,
    plan_id: UUID,
    *,
    kind: JobKindHint,
    user_id: UUID,
    params: EmergencyPlanGenerateRequest | None = None,
    plan_name: str | None = None,
) -> str:
    await get_plan_or_404(db, plan_id)
    job_id = job_id_for(plan_id)
    if await is_job_running(job_id):
        raise AppException(status_code=409, message="该预案已有 AI 任务在运行，请稍候")
    if kind == "generate":
        if params is None or plan_name is None:
            raise AppException(status_code=422, message="缺少生成参数")
        return await submit_job(
            run_generate_job,
            task_id=job_id,
            ttl=JOB_TTL_SECONDS,
            status_extra={"kind": "generate", "owner": str(user_id)},
            plan_id=plan_id,
            params=params,
            plan_name=plan_name,
            user_id=user_id,
            job_id=job_id,
        )
    if kind == "review":
        row = await get_content_row(db, plan_id)
        if row is None or not row.content:
            raise AppException(status_code=422, message="该预案尚无正文内容")
        return await submit_job(
            run_review_job,
            task_id=job_id,
            ttl=JOB_TTL_SECONDS,
            status_extra={"kind": "review", "owner": str(user_id)},
            plan_id=plan_id,
            user_id=user_id,
            job_id=job_id,
        )
    if kind == "import_structure":
        row = await get_content_row(db, plan_id)
        if row is None or not row.content:
            raise AppException(status_code=422, message="该预案尚无导入内容")
        return await submit_job(
            run_import_structure_job,
            task_id=job_id,
            ttl=JOB_TTL_SECONDS,
            status_extra={"kind": "import", "owner": str(user_id)},
            plan_id=plan_id,
            user_id=user_id,
            job_id=job_id,
        )
    raise AppException(status_code=422, message="未知任务类型")
