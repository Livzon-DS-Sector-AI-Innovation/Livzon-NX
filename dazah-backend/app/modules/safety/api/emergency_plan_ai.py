"""Safety API — 应急预案 AI 工作台端点。

生成/审核走后台任务（202 + job_id），对话为 SSE 流式；正文读写带修订
快照与乐观锁；导出按公司模板版式生成 Word。所有端点登记在
``safety:emergency-accident:emergency-mgmt`` 页面权限下。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException
from app.core.jobs import get_job_status, is_job_running
from app.core.upload_security import read_upload_secure
from app.modules.safety.schemas.emergency_plan_ai import (
    EmergencyPlanAiOptions,
    EmergencyPlanChatMessage,
    EmergencyPlanChatMessageListResponse,
    EmergencyPlanChatRequest,
    EmergencyPlanChecksResponse,
    EmergencyPlanContentResponse,
    EmergencyPlanContentUpdate,
    EmergencyPlanGenerateRequest,
    EmergencyPlanJobStatus,
    EmergencyPlanJobSubmitted,
    EmergencyPlanRevisionDetail,
    EmergencyPlanRevisionListResponse,
    EmergencyPlanRevisionSummary,
)
from app.modules.safety.service.emergency_plan_context import load_options
from app.modules.safety.service.emergency_plan_docx import (
    build_plan_docx,
    export_filename,
)
from app.modules.safety.service.emergency_plan_import import (
    MIN_TEMPLATE_HEADINGS,
    parse_plan_docx,
)
from app.modules.safety.service.emergency_plan_workbench import (
    ContentMutation,
    apply_chat_edits_with_revision,
    apply_mutation,
    build_content_response,
    chat_turn,
    get_content_row,
    get_plan_or_404,
    get_revision_detail,
    job_id_for,
    list_chat_messages,
    list_revisions,
    parse_document,
    record_chat_message,
    restore_revision,
    run_checks_only,
    save_content,
    submit_plan_job,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger("safety.emergency_plan")

emergency_plan_ai_router = APIRouter()

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _require_user_id(current_user: CurrentUser | None) -> UUID:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    return current_user.id


def _sse(data: dict[str, object]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------- 向导选项与任务 ----------


@emergency_plan_ai_router.get(
    "/emergency-plans/ai/options",
    response_model=ApiResponseEnvelope[EmergencyPlanAiOptions],
    summary="AI 工作台向导选项（危化品/厂区建筑/事故类型/组织机构预填）",
)
async def get_emergency_plan_ai_options(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanAiOptions]:
    _require_user_id(current_user)
    return ApiResponseEnvelope(data=await load_options(db))


@emergency_plan_ai_router.post(
    "/emergency-plans/{plan_id}/ai/generate",
    response_model=ApiResponseEnvelope[EmergencyPlanJobSubmitted],
    summary="提交应急预案 AI 生成任务（后台执行）",
)
async def submit_emergency_plan_generate(
    plan_id: UUID,
    data: EmergencyPlanGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanJobSubmitted]:
    user_id = _require_user_id(current_user)
    plan = await get_plan_or_404(db, plan_id)
    job_id = await submit_plan_job(
        db,
        plan_id,
        kind="generate",
        user_id=user_id,
        params=data,
        plan_name=plan.name,
    )
    await db.commit()
    return ApiResponseEnvelope(
        data=EmergencyPlanJobSubmitted(job_id=job_id, kind="generate")
    )


@emergency_plan_ai_router.post(
    "/emergency-plans/{plan_id}/ai/review",
    response_model=ApiResponseEnvelope[EmergencyPlanJobSubmitted],
    summary="提交应急预案 AI 审核修正任务（后台执行）",
)
async def submit_emergency_plan_review(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanJobSubmitted]:
    user_id = _require_user_id(current_user)
    job_id = await submit_plan_job(db, plan_id, kind="review", user_id=user_id)
    await db.commit()
    return ApiResponseEnvelope(
        data=EmergencyPlanJobSubmitted(job_id=job_id, kind="review")
    )


@emergency_plan_ai_router.get(
    "/emergency-plans/{plan_id}/ai/job",
    response_model=ApiResponseEnvelope[EmergencyPlanJobStatus],
    summary="查询应急预案 AI 任务状态",
)
async def get_emergency_plan_job_status(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanJobStatus]:
    _require_user_id(current_user)
    await get_plan_or_404(db, plan_id)
    job_id = job_id_for(plan_id)
    if await is_job_running(job_id):
        running_status = await get_job_status(job_id) or {}
        return ApiResponseEnvelope(
            data=EmergencyPlanJobStatus(
                job_id=job_id,
                kind=running_status.get("kind"),
                state="running",
                progress=running_status.get("progress", ""),
            )
        )
    status = await get_job_status(job_id)
    if status is None:
        return ApiResponseEnvelope(
            data=EmergencyPlanJobStatus(
                job_id=job_id, kind=None, state="completed", progress=""
            )
        )
    if status.get("state") == "running":
        # 心跳已过期（服务重启/网络中断导致任务孤儿化）：如实报告中断
        return ApiResponseEnvelope(
            data=EmergencyPlanJobStatus(
                job_id=job_id,
                kind=status.get("kind"),
                state="interrupted",
                progress="任务已中断（服务重启或网络中断），请重新提交",
            )
        )
    return ApiResponseEnvelope(
        data=EmergencyPlanJobStatus(
            job_id=job_id,
            kind=status.get("kind"),
            state=status.get("state", "completed"),
            progress=status.get("progress", ""),
        )
    )


# ---------- 导入 ----------


@emergency_plan_ai_router.post(
    "/emergency-plans/{plan_id}/ai/import",
    response_model=ApiResponseEnvelope[EmergencyPlanContentResponse],
    summary="导入预案 docx（模板结构确定性解析，非模板自动走 AI 整理任务）",
)
async def import_emergency_plan_docx(
    plan_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanContentResponse]:
    user_id = _require_user_id(current_user)
    plan = await get_plan_or_404(db, plan_id)
    _, content = await read_upload_secure(
        file,
        max_bytes=20 * 1024 * 1024,
        allowed_extensions={".docx"},
        what="预案文档",
    )
    imported = await asyncio.to_thread(parse_plan_docx, content)

    upload_dir = os.path.join("uploads", "safety", "emergency")
    os.makedirs(upload_dir, exist_ok=True)
    saved_path = os.path.join(
        upload_dir, f"import_{plan_id}_{int(datetime.now().timestamp())}.docx"
    )

    def _write_file() -> None:
        with open(saved_path, "wb") as file_obj:
            file_obj.write(content)

    await asyncio.to_thread(_write_file)

    mutation = ContentMutation(
        document=imported.document,
        source="import",
        summary=f"导入文档（识别模板章节 {imported.template_headings} 个）",
        status="draft",
    )
    response = await apply_mutation(db, plan_id, mutation, user_id)
    from app.modules.safety.service.emergency_mgmt import EmergencyMgmtService

    await EmergencyMgmtService(db).set_plan_file(
        plan_id, saved_path, file.filename or "plan.docx", user_id=user_id
    )
    if imported.template_headings < MIN_TEMPLATE_HEADINGS:
        await submit_plan_job(db, plan_id, kind="import_structure", user_id=user_id)
    await db.commit()
    await db.refresh(plan)
    response = await build_content_response(db, plan_id)
    logger.info(
        "应急预案导入完成",
        extra={
            "module_name": "safety",
            "plan_id": str(plan_id),
            "template_headings": imported.template_headings,
        },
    )
    return ApiResponseEnvelope(data=response)


# ---------- 正文读写 / 校验 / 定稿 ----------


@emergency_plan_ai_router.get(
    "/emergency-plans/{plan_id}/content",
    response_model=ApiResponseEnvelope[EmergencyPlanContentResponse],
    summary="读取应急预案结构化正文",
)
async def get_emergency_plan_content(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanContentResponse]:
    _require_user_id(current_user)
    return ApiResponseEnvelope(data=await build_content_response(db, plan_id))


@emergency_plan_ai_router.put(
    "/emergency-plans/{plan_id}/content",
    response_model=ApiResponseEnvelope[EmergencyPlanContentResponse],
    summary="保存应急预案结构化正文（乐观锁，生成修订快照）",
)
async def put_emergency_plan_content(
    plan_id: UUID,
    data: EmergencyPlanContentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanContentResponse]:
    user_id = _require_user_id(current_user)
    response = await save_content(db, plan_id, data, user_id)
    await db.commit()
    return ApiResponseEnvelope(data=response)


@emergency_plan_ai_router.get(
    "/emergency-plans/{plan_id}/content/checks",
    response_model=ApiResponseEnvelope[EmergencyPlanChecksResponse],
    summary="应急预案确定性校验（不调 AI）",
)
async def check_emergency_plan_content(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanChecksResponse]:
    _require_user_id(current_user)
    _, issues, _ = await run_checks_only(db, plan_id)
    return ApiResponseEnvelope(data=EmergencyPlanChecksResponse(issues=issues))


@emergency_plan_ai_router.post(
    "/emergency-plans/{plan_id}/finalize",
    response_model=ApiResponseEnvelope[EmergencyPlanContentResponse],
    summary="应急预案定稿（人工确认后归档状态）",
)
async def finalize_emergency_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanContentResponse]:
    user_id = _require_user_id(current_user)
    await get_plan_or_404(db, plan_id)
    row = await get_content_row(db, plan_id)
    if row is None or not row.content:
        raise AppException(status_code=422, message="该预案尚无正文内容")
    row.content_status = "finalized"
    row.updated_by = user_id
    await db.flush()
    response = await build_content_response(db, plan_id)
    await db.commit()
    return ApiResponseEnvelope(data=response)


# ---------- 修订 ----------


@emergency_plan_ai_router.get(
    "/emergency-plans/{plan_id}/revisions",
    response_model=ApiResponseEnvelope[EmergencyPlanRevisionListResponse],
    summary="应急预案修订记录列表",
)
async def list_emergency_plan_revisions(
    plan_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanRevisionListResponse]:
    _require_user_id(current_user)
    await get_plan_or_404(db, plan_id)
    rows, _total = await list_revisions(db, plan_id, page=page, page_size=page_size)
    return ApiResponseEnvelope(
        data=EmergencyPlanRevisionListResponse(
            items=[
                EmergencyPlanRevisionSummary(
                    id=row.id,
                    revision_no=row.revision_no,
                    source=row.source,
                    summary=row.summary,
                    changed_sections=row.changed_sections or [],
                    created_at=row.created_at,
                )
                for row in rows
            ]
        )
    )


@emergency_plan_ai_router.get(
    "/emergency-plans/{plan_id}/revisions/{revision_no}",
    response_model=ApiResponseEnvelope[EmergencyPlanRevisionDetail],
    summary="应急预案修订详情（含完整正文与修正日志）",
)
async def get_emergency_plan_revision(
    plan_id: UUID,
    revision_no: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanRevisionDetail]:
    _require_user_id(current_user)
    return ApiResponseEnvelope(data=await get_revision_detail(db, plan_id, revision_no))


@emergency_plan_ai_router.post(
    "/emergency-plans/{plan_id}/revisions/{revision_no}/restore",
    response_model=ApiResponseEnvelope[EmergencyPlanContentResponse],
    summary="恢复应急预案到指定修订（生成新修订，可再次撤销）",
)
async def restore_emergency_plan_revision(
    plan_id: UUID,
    revision_no: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanContentResponse]:
    user_id = _require_user_id(current_user)
    if await is_job_running(job_id_for(plan_id)):
        raise AppException(status_code=409, message="AI 任务运行中，暂不能恢复")
    response = await restore_revision(db, plan_id, revision_no, user_id)
    await db.commit()
    return ApiResponseEnvelope(data=response)


# ---------- 导出 ----------


@emergency_plan_ai_router.get(
    "/emergency-plans/{plan_id}/export-docx",
    response_model=None,
    summary="导出应急预案 Word（公司模板版式）",
)
async def export_emergency_plan_docx(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> StreamingResponse:
    _require_user_id(current_user)
    plan = await get_plan_or_404(db, plan_id)
    row = await get_content_row(db, plan_id)
    document = parse_document(row.content) if row is not None else None
    if document is None:
        raise AppException(status_code=422, message="该预案尚无正文内容")
    data = await asyncio.to_thread(build_plan_docx, document)
    filename = export_filename(document, plan.name)
    return StreamingResponse(
        iter([data]),
        media_type=_DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


# ---------- 对话 ----------


@emergency_plan_ai_router.get(
    "/emergency-plans/{plan_id}/ai/messages",
    response_model=ApiResponseEnvelope[EmergencyPlanChatMessageListResponse],
    summary="应急预案 AI 对话历史",
)
async def list_emergency_plan_chat_messages(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[EmergencyPlanChatMessageListResponse]:
    _require_user_id(current_user)
    await get_plan_or_404(db, plan_id)
    rows = await list_chat_messages(db, plan_id)
    return ApiResponseEnvelope(
        data=EmergencyPlanChatMessageListResponse(
            items=[EmergencyPlanChatMessage.model_validate(row) for row in rows]
        )
    )


@emergency_plan_ai_router.post(
    "/emergency-plans/{plan_id}/ai/chat",
    summary="应急预案 AI 对话（SSE；返回回复，修改补丁直接应用并生成修订）",
)
async def chat_emergency_plan_stream(
    plan_id: UUID,
    data: EmergencyPlanChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> StreamingResponse:
    user_id = _require_user_id(current_user)
    await get_plan_or_404(db, plan_id)
    message = data.message.strip()
    if not message:
        raise AppException(status_code=400, message="消息不能为空")
    from app.core.llm.exceptions import (
        LLMConfigError,
        LLMOutputError,
        LLMProviderError,
        LLMRateLimitError,
    )

    history_rows = await list_chat_messages(db, plan_id)
    history = [
        {"role": row.role, "content": row.content}
        for row in history_rows[-10:]
        if row.role in ("user", "assistant")
    ]

    async def event_stream() -> AsyncIterator[str]:
        try:
            yield _sse({"status": "已连接，AI 正在处理…"})
            reply, edits = await chat_turn(
                db,
                plan_id,
                message=message,
                section=data.section,
                history=history,
            )
            if edits:
                row = await get_content_row(db, plan_id)
                base_revision = row.revision_no if row else 0
                response, warnings, sections = await apply_chat_edits_with_revision(
                    db,
                    plan_id,
                    message=message,
                    reply=reply,
                    edits=edits,
                    base_revision_no=base_revision,
                    user_id=user_id,
                )
                await db.commit()
                yield _sse({"reply": reply})
                yield _sse({"revision": response.revision_no, "sections": sections})
                yield _sse({"warnings": [issue.model_dump() for issue in warnings]})
                yield _sse({"content": json.loads(response.model_dump_json())})
            else:
                await record_chat_message(db, plan_id, "user", message, user_id)
                await record_chat_message(db, plan_id, "assistant", reply, user_id)
                await db.commit()
                yield _sse({"reply": reply})
            yield _sse({"done": True})
        except LLMRateLimitError:
            yield _sse({"content": "AI 服务请求过于频繁，请稍后再试。"})
            yield _sse({"done": True})
        except LLMConfigError:
            yield _sse({"content": "AI 服务尚未配置，请先在系统管理中配置 AI 模型。"})
            yield _sse({"done": True})
        except LLMOutputError:
            yield _sse({"content": "AI 返回格式异常，请重试或换一种问法。"})
            yield _sse({"done": True})
        except LLMProviderError:
            logger.exception("应急预案 AI 对话供应商错误")
            yield _sse({"content": "AI 服务暂时不可用，请稍后重试。"})
            yield _sse({"done": True})
        except AppException as exc:
            yield _sse({"content": exc.message or "处理失败，请稍后重试。"})
            yield _sse({"done": True})
        except Exception:
            logger.exception("应急预案 AI 对话未知错误")
            yield _sse({"content": "AI 服务出现未知错误，请联系管理员。"})
            yield _sse({"done": True})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
