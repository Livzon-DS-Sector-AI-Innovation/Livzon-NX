"""验证方案/报告 AI 审核编排服务。

流程：创建会话（upload/entry）→ 挂文件 → run（预检 LLM + 后台 job）→
job 内：解析文件 → 加载目录基准 → 代码确定性核对（引用/修订号/编号一致性）
→ LLM 语义审核（互查/数值/规范性）→ 二次校验（quote_verified）→ 写回结论。

设计原则：引用存在性与修订号新旧由代码比对；LLM 输出仅辅助，逐条过
Pydantic 校验与原文包含校验，不写回任何业务台账字段。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.exceptions import AppException, NotFoundException
from app.core.jobs import is_job_running, submit_job
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.core.llm.config import get_config
from app.core.storage import delete_object, upload_object
from app.core.storage import is_enabled as minio_enabled
from app.core.upload_security import safe_upload_filename, sniff_upload_mime
from app.modules.quality.models import (
    ValidationReviewFile,
    ValidationReviewRecord,
)
from app.modules.quality.repository.quality_management import (
    get_changes,
    get_deviations,
)
from app.modules.quality.schemas.validation_review import (
    ValidationReviewFileOut,
    ValidationReviewFindingOut,
    ValidationReviewListItem,
    ValidationReviewOut,
    ValidationReviewStatsOut,
)
from app.modules.quality.service.document_catalog_attachment import (
    extract_content_identity,
)
from app.modules.quality.service.document_catalog_md import convert_word_attachment
from app.modules.quality.service.validation_basis_resolver import (
    BasisEntry,
    DocumentBasis,
    ReferenceCheckItem,
    _compact,
    extract_document_number,
    infer_doc_kind,
    load_basis_contents,
    load_document_basis,
    resolve_references,
)
from app.modules.quality.service.validation_review_prompt import (
    FINDING_CATEGORIES,
    MAX_CONTENT_COMPARE_BASES,
    SEVERITY_LEVELS,
    build_basis_selection_prompt,
    build_content_compare_prompt,
    build_review_prompt,
    split_chunks,
)
from app.platform.audit.service import record_audit_log

logger = logging.getLogger(__name__)

REVIEW_ALLOWED_EXTENSIONS = frozenset({".doc", ".docx", ".md", ".wps", ".txt"})
WORD_EXTS = frozenset({".doc", ".docx", ".wps"})
TEXT_EXTS = frozenset({".md", ".txt"})
REVIEW_MAX_SIZE = 20 * 1024 * 1024

STATUS_DRAFT = "draft"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
PARSE_PENDING = "pending"
PARSE_COMPLETED = "completed"
PARSE_FAILED = "failed"
SOURCE_UPLOAD = "upload"
SOURCE_ENTRY = "entry_attachment"
DOC_KIND_PLAN = "plan"
DOC_KIND_REPORT = "report"

# LLM 语义审核重试（限流指数退避）
_LLM_MAX_RETRIES = 3
# 解析与审核超时保护（秒）：防 soffice/转换/LLM 挂死导致永久 pending；
# 整单预算覆盖分块审核+分块正文比对（大文档 30-60 分钟级别）
_PARSE_FILE_TIMEOUT = 240
_REVIEW_TOTAL_TIMEOUT = 3600
# 单文件附件读取（同步 MinIO/local）超时，线程池内执行
_READ_FILE_TIMEOUT = 120
# P3 每份依据最多比对的验证文档分块数（超长时取开头主体+末尾结论块）
_MAX_COMPARE_CHUNKS_PER_BASIS = 4


# ─── 本地存储（MinIO/uploads 双通道，key 前缀 validation-review/） ───────


def _local_review_upload_dir() -> Path:
    upload_dir = Path(get_settings().UPLOAD_DIR) / "quality" / "validation_review"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _safe_path(storage_key: str) -> str:
    root = _local_review_upload_dir().resolve()
    path = (root / storage_key).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AppException(message="非法文件路径") from exc
    if path == root:
        raise AppException(message="非法文件路径")
    return str(path)


def _store_review_file(storage_key: str, content: bytes, content_type: str) -> str:
    if minio_enabled():
        upload_object("quality", storage_key, content, len(content), content_type)
        return storage_key
    path = _safe_path(storage_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as file_obj:
        file_obj.write(content)
    return storage_key


def _read_review_file(storage_key: str) -> bytes | None:
    if not storage_key:
        return None
    if minio_enabled():
        from app.core.storage import get_object

        stored = get_object("quality", storage_key)
        if stored is None:
            return None
        data, _ = stored
        return data
    path = _safe_path(storage_key)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as file_obj:
        return file_obj.read()


def _delete_review_file(storage_key: str) -> None:
    if not storage_key:
        return
    if minio_enabled():
        try:
            delete_object("quality", storage_key)
        except Exception:  # noqa: BLE001 —— 存储清理失败不阻塞业务，仅记录
            logger.warning(
                "validation review file delete failed",
                extra={"component": "quality", "storage_key": storage_key},
            )
        return
    path = _safe_path(storage_key)
    if os.path.exists(path):
        os.remove(path)


# ─── 文件解析 ────────────────────────────────────────────────────────


async def _extract_upload_text(
    file_name: str, content: bytes
) -> tuple[str | None, str | None]:
    """解析上传文件正文，返回 (text, error)。.doc/.docx/.wps 复用文件管理转换管线。"""
    suffix = Path(file_name).suffix.lower()
    if suffix in TEXT_EXTS:
        for encoding in ("utf-8", "gb18030"):
            try:
                return content.decode(encoding), None
            except UnicodeDecodeError:
                continue
        return None, "文本编码无法识别"
    if suffix in WORD_EXTS:
        try:
            md_text, _ = await asyncio.to_thread(
                convert_word_attachment, file_name, content
            )
            if not md_text:
                return None, "文档转换后无正文内容"
            return md_text, None
        except AppException as exc:
            return None, str(exc.message)
        except Exception as exc:  # noqa: BLE001 —— 转换库内部异常，转失败标记
            logger.warning(
                "validation review word convert failed",
                extra={
                    "component": "quality",
                    "file_name": file_name,
                    "error": str(exc),
                },
            )
            return None, "文档转换失败"
    return None, f"不支持的文件类型 {suffix}"


# ─── 记录 CRUD ───────────────────────────────────────────────────────


async def create_review_record(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str | None,
    focus_points: str | None = None,
) -> ValidationReviewRecord:
    """创建审核会话（上传模式）：VP/VR 类型与编号由 AI 管线自动识别。"""
    cleaned_focus = (focus_points or "").strip()[:2000] or None
    record = ValidationReviewRecord(
        title=(title or "").strip()[:255],
        review_mode=SOURCE_UPLOAD,
        status=STATUS_DRAFT,
        input_snapshot={"focus_points": cleaned_focus} if cleaned_focus else None,
        created_by=user_id,
    )
    db.add(record)
    await db.flush()
    return record


async def get_review_record(
    db: AsyncSession, record_id: uuid.UUID
) -> ValidationReviewRecord:
    record = await db.get(ValidationReviewRecord, record_id)
    if not record or record.is_deleted:
        raise NotFoundException(
            resource="验证 AI 审核记录", resource_id=str(record_id)
        )
    return record


async def get_review_files(
    db: AsyncSession, record_id: uuid.UUID
) -> list[ValidationReviewFile]:
    result = await db.execute(
        select(ValidationReviewFile)
        .where(
            ValidationReviewFile.review_id == record_id,
            ValidationReviewFile.is_deleted.is_(False),
        )
        .order_by(
            ValidationReviewFile.sort_order.asc(),
            ValidationReviewFile.created_at.asc(),
        )
    )
    return list(result.scalars().all())


async def add_uploaded_review_file(
    db: AsyncSession,
    record: ValidationReviewRecord,
    *,
    file: UploadFile,
    doc_kind: str | None,
    user_id: uuid.UUID,
) -> ValidationReviewFile:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in REVIEW_ALLOWED_EXTENSIONS:
        raise AppException(
            status_code=422, message="仅支持 .doc/.docx/.md/.wps/.txt 文件"
        )
    content = await file.read()
    if not content:
        raise AppException(status_code=422, message="上传文件为空")
    if len(content) > REVIEW_MAX_SIZE:
        raise AppException(status_code=413, message="文件超过 20MB 上传上限")
    content_type = file.content_type or sniff_upload_mime(file.filename or "", content)
    safe_name = (
        f"{uuid.uuid4().hex}_"
        f"{safe_upload_filename(file.filename or '', fallback='upload.bin')}"
    )
    storage_key = f"validation-review/{safe_name}"
    _store_review_file(storage_key, content, content_type)
    kind = doc_kind or infer_doc_kind(file.filename or "")
    existing = await get_review_files(db, record.id)
    row = ValidationReviewFile(
        review_id=record.id,
        doc_kind=kind,
        source=SOURCE_UPLOAD,
        file_name=file.filename or "",
        file_type=content_type,
        file_size=len(content),
        storage_key=storage_key,
        parse_status=PARSE_PENDING,
        sort_order=len(existing),
        created_by=user_id,
    )
    db.add(row)
    await db.flush()
    return row


async def delete_review_record(
    db: AsyncSession,
    record: ValidationReviewRecord,
    *,
    user_id: uuid.UUID,
) -> None:
    record.is_deleted = True
    record.updated_by = user_id
    await db.flush()
    await record_audit_log(
        db,
        action="validation_review.delete",
        user_id=user_id,
        resource_type="quality.validation_review",
        resource_id=record.id,
        extra={"title": record.title, "review_mode": record.review_mode},
    )


async def list_review_records(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    page: int,
    page_size: int,
    all_visible: bool = False,
    keyword: str | None = None,
    status: str | None = None,
    review_mode: str | None = None,
) -> tuple[list[ValidationReviewRecord], int]:
    """分页列出审核会话。

    all_visible=True 时返回全部（QA 可见），否则仅本人创建。
    keyword 按标题模糊匹配；status/review_mode 精确筛选。
    """
    filters: list[Any] = [ValidationReviewRecord.is_deleted.is_(False)]
    if not all_visible:
        filters.append(ValidationReviewRecord.created_by == user_id)
    if keyword:
        filters.append(ValidationReviewRecord.title.ilike(f"%{keyword}%"))
    if status:
        filters.append(ValidationReviewRecord.status == status)
    if review_mode:
        filters.append(ValidationReviewRecord.review_mode == review_mode)
    total_result = await db.execute(
        select(func.count())
        .select_from(ValidationReviewRecord)
        .where(*filters)
    )
    total = total_result.scalar() or 0
    result = await db.execute(
        select(ValidationReviewRecord)
        .where(*filters)
        .order_by(ValidationReviewRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


# ─── 审核执行 ────────────────────────────────────────────────────────


async def run_review(
    db: AsyncSession,
    record: ValidationReviewRecord,
    *,
    user_id: uuid.UUID,
    audit_action: str = "validation_review.run",
    focus_points: str | None = None,
) -> str:
    """发起审核：预检 LLM 配置（未配置 503 不建 job）→ 提交后台任务。"""
    try:
        await get_config("text")
    except LLMConfigError as exc:
        raise AppException(
            status_code=503, message="AI 服务尚未配置，无法发起审核"
        ) from exc
    record.status = STATUS_PROCESSING
    record.error_message = None
    record.updated_by = user_id
    await db.flush()

    job_id = f"quality:validation-review:{uuid.uuid4().hex[:12]}"
    record.job_id = job_id
    await db.flush()

    stored_focus = (record.input_snapshot or {}).get("focus_points")
    await submit_job(
        _run_review_job,
        task_id=job_id,
        ttl=600,
        status_extra={"owner": str(user_id)},
        record_id=record.id,
        job_id=job_id,
        user_id=user_id,
        focus_points=focus_points or stored_focus,
    )
    await record_audit_log(
        db,
        action=audit_action,
        user_id=user_id,
        resource_type="quality.validation_review",
        resource_id=record.id,
        extra={"title": record.title, "review_mode": record.review_mode},
    )
    return job_id


async def _report_progress(job_id: str, text: str) -> None:
    """更新后台 job 进度文案，让前端实时看到审核进行到哪一步。"""
    try:
        from app.core.jobs import update_job_progress

        await update_job_progress(job_id, text)
    except Exception:  # noqa: BLE001 —— 进度更新失败不影响审核本身
        pass


async def _run_review_job(
    *,
    record_id: uuid.UUID,
    job_id: str,
    user_id: uuid.UUID,
    focus_points: str | None = None,
) -> dict[str, Any]:
    """后台审核任务：独立会话执行，任何失败都落库为 failed 状态。"""
    async with async_session_factory() as db:
        record = await db.get(ValidationReviewRecord, record_id)
        if record is None:
            return {"status": STATUS_FAILED, "error": "审核记录不存在"}
        try:
            # 整单总超时保护：解析/转换/LLM 任一环节挂死都会强制 failed，
            # 避免记录永久停留在 processing（生产 soffice 崩溃曾导致此问题）
            await asyncio.wait_for(
                _execute_review(db, record, job_id, user_id, focus_points),
                timeout=_REVIEW_TOTAL_TIMEOUT,
            )
            await db.commit()
            return {"status": record.status}
        except TimeoutError:
            record.status = STATUS_FAILED
            record.error_message = "审核超时（整体超过预算时间），请重试"
            logger.warning(
                "validation review job %s hit total timeout",
                job_id,
                extra={"component": "quality", "record_id": str(record_id)},
            )
            await db.commit()
            return {"status": STATUS_FAILED, "error": record.error_message}
        except LLMRateLimitError:
            record.status = STATUS_FAILED
            record.error_message = "LLM 速率限制，重试耗尽"
            logger.warning(
                "validation review job %s rate limited",
                job_id,
                extra={"component": "quality", "record_id": str(record_id)},
            )
            await db.commit()
            return {"status": STATUS_FAILED, "error": record.error_message}
        except (LLMConfigError, LLMOutputError, LLMProviderError) as exc:
            record.status = STATUS_FAILED
            record.error_message = _safe_error(exc)
            # 静默落库会让排查无线索：这里必须留下失败原因
            logger.warning(
                "validation review job %s llm failed: %s",
                job_id,
                type(exc).__name__,
                extra={"component": "quality", "record_id": str(record_id)},
            )
            await db.commit()
            return {"status": STATUS_FAILED, "error": record.error_message}
        except Exception as exc:  # noqa: BLE001 —— job 边界兜底，保留异常链并落库
            logger.exception("validation review job %s failed", job_id)
            record.status = STATUS_FAILED
            record.error_message = f"审核失败：{type(exc).__name__}"
            await db.commit()
            return {"status": STATUS_FAILED, "error": record.error_message}


async def _execute_review(
    db: AsyncSession,
    record: ValidationReviewRecord,
    job_id: str,
    user_id: uuid.UUID,
    focus_points: str | None = None,
) -> None:
    # 1. 解析未解析文件
    files = await get_review_files(db, record.id)
    for row in files:
        if row.parse_status != PARSE_PENDING:
            continue
        # 读取附件在线程池+超时保护内执行：get_object 是同步 MinIO 调用，
        # 直接在事件循环上跑，socket 卡住会冻结整个循环（心跳/进度/超时
        # 保护全部失效，job 永久挂死）
        try:
            content = await asyncio.wait_for(
                asyncio.to_thread(_read_review_file, row.storage_key),
                timeout=_READ_FILE_TIMEOUT,
            )
        except TimeoutError:
            row.parse_status = PARSE_FAILED
            row.parse_error = "读取附件超时"
            db.add(row)
            continue
        if content is None:
            row.parse_status = PARSE_FAILED
            row.parse_error = "原文件缺失"
        else:
            # 单文件解析超时保护：soffice/转换挂死时强制 failed，不阻塞后续
            try:
                text, err = await asyncio.wait_for(
                    _extract_upload_text(row.file_name, content),
                    timeout=_PARSE_FILE_TIMEOUT,
                )
            except TimeoutError:
                row.parse_status = PARSE_FAILED
                row.parse_error = "解析超时"
            else:
                if text:
                    row.parsed_text = text
                    row.parse_status = PARSE_COMPLETED
                else:
                    row.parse_status = PARSE_FAILED
                    row.parse_error = err or "解析失败"
        db.add(row)
    await db.flush()

    # 2. 加载目录基准 + 逐文件核对
    basis = await load_document_basis(db)
    texts: dict[str, str] = {}
    identities: dict[str, dict[str, Any]] = {}
    reference_items: list[ReferenceCheckItem] = []
    for row in files:
        if row.parse_status != PARSE_COMPLETED or not row.parsed_text:
            continue
        # doc_kind 二次确认：文件名无 VP/VR 前缀时用正文关键词判定方案/报告
        kind = _refine_doc_kind(row.file_name, row.parsed_text)
        texts[kind] = texts.get(kind, "") + row.parsed_text
        ident: dict[str, Any] = {
            "file_name": row.file_name,
            "doc_number": extract_document_number(row.file_name),
        }
        content_code, content_title = extract_content_identity(row.parsed_text)
        ident["content_code"] = content_code
        ident["content_title"] = content_title
        identities.setdefault(kind, ident)
        # 排除文档自身编号：自己引用自己不算"引用其他文件"
        own_number = extract_document_number(row.file_name)
        resolved = resolve_references(basis, row.parsed_text)
        if own_number:
            own_compact = _compact(own_number)
            resolved = [
                item
                for item in resolved
                if _compact(item.code) != own_compact
            ]
        reference_items.extend(resolved)

    # 3. 代码确定性核对
    findings: list[dict[str, Any]] = []
    for item in reference_items:
        if item.issue == "version_mismatch":
            findings.append(
                {
                    "category": "version_mismatch",
                    "severity": "high",
                    "location": "引用文件",
                    "quote": item.code,
                    "quote_verified": _quote_verified(item.code, list(texts.values())),
                    "basis_source": (
                        f"{item.entry_code} {item.entry_name or ''}".strip()
                        if item.entry_code
                        else None
                    ),
                    "basis_match_type": item.match_type,
                    "detail": (
                        f"正文引用 {item.code}（修订 {item.revision}），"
                        f"目录现行版为 {item.entry_code}"
                        f"（修订 {item.current_revision}），版本不一致"
                    ),
                }
            )
        elif item.issue == "missing":
            findings.append(
                {
                    "category": "reference_missing",
                    "severity": "medium",
                    "location": "引用文件",
                    "quote": item.code,
                    "quote_verified": _quote_verified(item.code, list(texts.values())),
                    "basis_source": None,
                    "basis_match_type": "missing",
                    "detail": f"正文引用文件编号 {item.code} 未在文件管理目录中找到",
                }
            )

    # 编号一致性（文件名 vs 正文头部）
    for kind, ident in identities.items():
        doc_number = ident.get("doc_number")
        content_code = ident.get("content_code")
        if (
            doc_number
            and content_code
            and _compact(doc_number) != _compact(content_code)
        ):
            findings.append(
                {
                    "category": "format_issue",
                    "severity": "medium",
                    "location": (
                        f"{'方案' if kind == DOC_KIND_PLAN else '报告'}文档编号"
                    ),
                    "quote": f"{doc_number} / {content_code}",
                    "quote_verified": True,
                    "basis_source": None,
                    "basis_match_type": "document",
                    "detail": (
                        f"{'方案' if kind == DOC_KIND_PLAN else '报告'}文档："
                        f"文件名编号 {doc_number} 与正文头部编号 {content_code} 不一致"
                    ),
                }
            )

    # 4. 基准正文一致性核查：拉取依据正文 → P2 筛选 → P3 逐份比对
    # 候选来源两路：①引用编号命中目录的条目；②文档标题关键词在目录里的
    # 相关条目（正文没写编号时，如只写"按清洁规程执行"，靠标题找到
    # 《XX清洁操作规程》《XX检验方法》这类真正该比的依据）
    model_name: str | None = None
    basis_comparison: list[dict[str, Any]] = []
    hit_entries = _collect_hit_entries(reference_items)
    document_summary = _document_summary(identities)
    keyword_entries = (
        _find_title_matched_entries(basis, document_summary, hit_entries)
        if texts
        else []
    )
    basis_contents = await load_basis_contents(
        db, hit_entries + [entry.id for entry in keyword_entries]
    )
    if basis_contents and texts:
        validation_text = (
            texts.get(DOC_KIND_PLAN, "") + "\n\n" + texts.get(DOC_KIND_REPORT, "")
        ).strip()
        candidate_bases = _build_candidate_bases(reference_items, basis_contents)
        candidate_bases.extend(
            _build_keyword_candidate_bases(keyword_entries, basis_contents)
        )
        if job_id:
            await _report_progress(
                job_id, "正在筛选与验证正文实质相关的关键依据…"
            )
        key_bases, model_name = await _select_key_bases(
            document_summary, candidate_bases, focus_points
        )
        compare_findings = await _compare_basis_contents(
            validation_text,
            key_bases,
            basis_contents,
            reference_items,
            focus_points,
            job_id=job_id,
        )
        findings.extend(compare_findings)
        basis_comparison = _build_basis_comparison(
            key_bases, compare_findings, basis_contents
        )
    elif texts and reference_items:
        # 有引用但无可用基准正文：显式提示，不静默（旧项目 missing_basis 精华）
        matched_codes = [
            item.code
            for item in reference_items
            if item.matched and item.entry_id not in basis_contents
        ]
        if matched_codes:
            findings.append(
                {
                    "category": "content_consistency",
                    "severity": "low",
                    "location": "基准正文比对",
                    "quote": "、".join(matched_codes[:5]),
                    "quote_verified": True,
                    "basis_source": None,
                    "basis_match_type": "missing_basis",
                    "detail": (
                        "以下引用文件命中目录但无可用附件正文，未做正文一致性比对："
                        + "、".join(matched_codes[:5])
                    ),
                }
            )

    # 5. 质量数据联动（偏差/变更摘要）
    quality_data_summary = await _collect_quality_data_summary(db, identities, texts)

    # 6. LLM 语义审核（互查/数值/规范性 + 质量数据 + 用户关注点）
    if texts:
        reference_summary = [
            item.to_dict()
            for item in reference_items
            if item.match_type != "noise"
        ]
        # 大文档分块审核：逐块送审保证全文覆盖，findings 合并去重
        plan_chunks = split_chunks(texts.get(DOC_KIND_PLAN) or "")
        report_chunks = split_chunks(texts.get(DOC_KIND_REPORT) or "")
        model_name = None
        seen_quotes: set[tuple[str, str]] = set()

        def _merge(new_findings: list[dict[str, Any]], source_label: str) -> None:
            nonlocal model_name
            for finding in new_findings:
                dedup_key = (
                    str(finding.get("category") or ""),
                    (finding.get("quote") or "")[:100],
                )
                if dedup_key in seen_quotes:
                    continue
                seen_quotes.add(dedup_key)
                if not finding.get("location"):
                    finding["location"] = source_label
                findings.append(finding)

        total_units = len(plan_chunks) + len(report_chunks) or 1
        done_units = 0

        for idx, chunk in enumerate(plan_chunks, start=1):
            await _report_progress(
                job_id, f"正在审核方案第 {idx}/{len(plan_chunks)} 部分…"
            )
            prompt = build_review_prompt(
                plan_text=chunk["text"],
                report_text=None,
                reference_summary=reference_summary,
                plan_identity=identities.get(DOC_KIND_PLAN),
                focus_points=focus_points,
                quality_data_summary=quality_data_summary if idx == 1 else None,
            )
            raw, model_name = await _call_llm_with_retry(prompt)
            chunk_findings = _parse_llm_findings(
                raw.get("findings") or [], [chunk["text"]]
            )
            _merge(chunk_findings, f"方案第 {idx} 部分")
            done_units += 1

        for idx, chunk in enumerate(report_chunks, start=1):
            await _report_progress(
                job_id, f"正在审核报告第 {idx}/{len(report_chunks)} 部分…"
            )
            prompt = build_review_prompt(
                plan_text=None,
                report_text=chunk["text"],
                reference_summary=reference_summary,
                report_identity=identities.get(DOC_KIND_REPORT),
                focus_points=focus_points,
            )
            raw, model_name = await _call_llm_with_retry(prompt)
            chunk_findings = _parse_llm_findings(
                raw.get("findings") or [], [chunk["text"]]
            )
            _merge(chunk_findings, f"报告第 {idx} 部分")
            done_units += 1

        # 交叉互查：方案↔报告结论/摘要块（两边都有时才互查，且只取末块防重复）
        if (
            plan_chunks
            and report_chunks
            and total_units <= 8
        ):
            await _report_progress(job_id, "正在做方案↔报告交叉一致性核对…")
            prompt = build_review_prompt(
                plan_text=plan_chunks[-1]["text"],
                report_text=report_chunks[-1]["text"],
                reference_summary=[],
                focus_points=focus_points,
            )
            raw, model_name = await _call_llm_with_retry(prompt)
            cross_findings = _parse_llm_findings(
                raw.get("findings") or [],
                [plan_chunks[-1]["text"], report_chunks[-1]["text"]],
            )
            for finding in cross_findings:
                finding["category"] = (
                    "plan_report_mismatch"
                    if finding.get("category") in (
                        "content_consistency",
                        "numeric_check",
                    )
                    else finding.get("category")
                )
            _merge(cross_findings, "方案↔报告交叉核对")
        done_units += 1

        await _report_progress(job_id, "AI 审核完成，正在汇总结果…")

    # 7. 结论落库
    stats = _build_stats(findings, reference_items, texts)
    basis_used = [
        item.to_dict()
        for item in reference_items
        if item.match_type != "noise"
    ]
    record.input_snapshot = {
        "documents": [
            {"doc_kind": kind, **ident} for kind, ident in identities.items()
        ],
        "references": basis_used,
        "focus_points": focus_points,
        "basis_comparison": basis_comparison,
        "truncated": any(
            len(text) > 12000 for text in texts.values()
        ),
    }
    record.output_payload = {
        "summary": _build_summary(stats, basis_comparison),
        "stats": stats,
        "findings": findings,
        "basis_used": basis_used,
        "basis_comparison": basis_comparison,
        "focus_points": focus_points,
    }
    # 标题自动生成：未手动传标题时用文档编号+标题（plan 优先），可追溯可查询
    if not (record.title or "").strip():
        record.title = _auto_generate_title(identities)
    record.status = STATUS_COMPLETED
    record.model_name = model_name
    record.error_message = None
    record.last_generated_at = datetime.now(UTC)
    db.add(record)


def _auto_generate_title(identities: dict[str, dict[str, Any]]) -> str:
    """从文档身份生成业务标题：优先方案，其次报告。

    形如 "VP-FT3-CV1902-01 设备清洁验证方案"；无法提取时返回空由调用方保持原值。
    """
    ident = identities.get(DOC_KIND_PLAN) or identities.get(DOC_KIND_REPORT)
    if not ident:
        return ""
    number = ident.get("doc_number") or ident.get("content_code") or ""
    title_text = ident.get("content_title") or ident.get("file_name") or ""
    if not number and not title_text:
        return ""
    # 正文标题已带文档编号时不再重复拼接（如 "VP-XX-01 VP-XX-01 酸性物…"）
    if number and _compact(title_text).startswith(_compact(number)):
        return title_text.strip()[:255]
    return f"{number} {title_text}".strip()[:255]


def _refine_doc_kind(file_name: str, parsed_text: str) -> str:
    """doc_kind 二次确认：文件名带 VP/VR 前缀直接判定；否则用正文关键词。

    文件名识别不到时，正文头部出现"方案/计划"判方案，"报告/结果/结论"判报告。
    """
    name_match = re.match(r"^\s*(VP|VR)[-\s_]", file_name or "")
    if name_match:
        return DOC_KIND_REPORT if name_match.group(1).upper() == "VR" else DOC_KIND_PLAN
    head = (parsed_text or "")[:800]
    if re.search(r"(报告|结果|结论)", head):
        return DOC_KIND_REPORT
    if re.search(r"(方案|计划)", head):
        return DOC_KIND_PLAN
    return DOC_KIND_PLAN


def _collect_hit_entries(reference_items: list[ReferenceCheckItem]) -> list[uuid.UUID]:
    """引用核对命中的目录条目 ID（去重保序）。"""
    seen: set[uuid.UUID] = set()
    ids: list[uuid.UUID] = []
    for item in reference_items:
        if item.entry_id and item.entry_id not in seen:
            seen.add(item.entry_id)
            ids.append(item.entry_id)
    return ids


def _build_candidate_bases(
    reference_items: list[ReferenceCheckItem],
    basis_contents: dict[uuid.UUID, str],
) -> list[dict[str, Any]]:
    """组装 P2 筛选的候选依据列表（编号/名称/正文长度/开头摘要）。"""
    candidates: list[dict[str, Any]] = []
    seen: set[uuid.UUID] = set()
    for item in reference_items:
        if item.entry_id in seen or item.entry_id not in basis_contents:
            continue
        seen.add(item.entry_id)
        content = basis_contents[item.entry_id]
        candidates.append(
            {
                "entry_id": item.entry_id,
                "code": item.entry_code,
                "name": item.entry_name,
                "length": len(content),
                "digest": content[:300],
            }
        )
    return candidates


def _document_summary(identities: dict[str, dict[str, Any]]) -> str:
    parts = []
    for kind, ident in identities.items():
        kind_label = "方案" if kind == DOC_KIND_PLAN else "报告"
        parts.append(
            f"{kind_label}编号 {ident.get('doc_number') or ident.get('content_code')}"
            f"《{ident.get('content_title') or ident.get('file_name')}》"
        )
    return "；".join(parts) if parts else "验证文档"


# 降级排序/标题预筛的停用词：验证文档标题里的通用词，不参与相关性打分
_RELEVANCE_STOPWORDS = {"方案", "报告", "编号", "文档", "验证", "确认", "审核"}


def _extract_relevance_keywords(document_summary: str) -> set[str]:
    """从文档标题/摘要提取相关性关键词。

    中文按 2-gram 提取（整词无法匹配规程名里的子串），英文数字取 ≥3 位
    token；停用词在 gram 层剔除。
    """
    keywords: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fa5]+", document_summary or ""):
        if len(run) < 2 or run in _RELEVANCE_STOPWORDS:
            continue
        keywords.add(run)
        keywords.update(run[i : i + 2] for i in range(len(run) - 1))
    keywords.update(re.findall(r"[A-Za-z0-9]{3,}", document_summary or ""))
    return keywords - _RELEVANCE_STOPWORDS


def _rank_candidates_by_relevance(
    document_summary: str,
    candidate_bases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """P2 降级时的启发式排序：与文档标题关键词重合越多越靠前。

    例如《霉酚酸提炼生产工艺验证方案》降级时优先选工艺规程/操作规程，
    而不是按引用顺序命中一堆管理程序。
    """
    keywords = _extract_relevance_keywords(document_summary)

    def _score(item: dict[str, Any]) -> int:
        haystack = f"{item.get('name') or ''}{item.get('digest') or ''}"
        return sum(1 for word in keywords if word in haystack)

    return sorted(candidate_bases, key=_score, reverse=True)


# 标题预筛：单处命中即纳入（如"清洁"命中《清洁操作规程》），上限防 prompt 膨胀
_TITLE_MATCH_MAX_ENTRIES = 12


def _find_title_matched_entries(
    basis: DocumentBasis,
    document_summary: str,
    exclude_ids: list[uuid.UUID],
) -> list[BasisEntry]:
    """文档标题关键词在目录里的相关条目（正文未引用编号时的候选兜底）。

    例如《分析方法验证方案》即使没写检验规程编号，也能凭"分析方法"
    找到《XX检验方法/质量标准》进 P2 候选；命中的仍需过 P2 AI 筛选。
    """
    keywords = _extract_relevance_keywords(document_summary)
    if not keywords:
        return []
    excluded = set(exclude_ids)
    scored: list[tuple[int, BasisEntry]] = []
    for entry in basis.entries:
        if entry.id in excluded or not entry.name:
            continue
        score = sum(1 for word in keywords if word in entry.name)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _score, entry in scored[:_TITLE_MATCH_MAX_ENTRIES]]


def _build_keyword_candidate_bases(
    keyword_entries: list[BasisEntry],
    basis_contents: dict[uuid.UUID, str],
) -> list[dict[str, Any]]:
    """标题预筛条目转 P2 候选（无正文的跳过）。"""
    candidates: list[dict[str, Any]] = []
    for entry in keyword_entries:
        content = basis_contents.get(entry.id)
        if not content:
            continue
        candidates.append(
            {
                "entry_id": entry.id,
                "code": entry.code,
                "name": entry.name,
                "length": len(content),
                "digest": content[:300],
            }
        )
    return candidates


async def _select_key_bases(
    document_summary: str,
    candidate_bases: list[dict[str, Any]],
    focus_points: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """P2：AI 筛选实质相关的关键依据（1 次调用）。

    LLM 失败时降级：取前 MAX_CONTENT_COMPARE_BASES 份候选直接比对，
    不因筛选失败导致整单审核失败。
    """
    if not candidate_bases:
        return [], None
    try:
        prompt = build_basis_selection_prompt(
            document_summary=document_summary, candidate_bases=candidate_bases
        )
        raw, model_name = await _call_llm_with_retry(prompt, expected_keys=["selected"])
    except (LLMConfigError, LLMOutputError, LLMProviderError, LLMRateLimitError) as exc:
        logger.warning(
            "basis selection llm failed, degrade to top candidates",
            extra={"component": "quality", "error": str(exc)},
        )
        top = _rank_candidates_by_relevance(document_summary, candidate_bases)[
            :MAX_CONTENT_COMPARE_BASES
        ]
        return [
            {**item, "reason": "AI 筛选不可用，已按与文档主题相关性排序取前 N 份"}
            for item in top
        ], None
    selected = raw.get("selected") or []
    by_code = {
        _compact(item.get("code") or ""): item for item in candidate_bases
    }
    key_bases: list[dict[str, Any]] = []
    for row in selected:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "")
        matched = by_code.get(_compact(code))
        if matched is None:
            continue
        reason = str(row.get("reason") or "")[:300]
        key_bases.append({**matched, "reason": reason})
        if len(key_bases) >= MAX_CONTENT_COMPARE_BASES:
            break
    return key_bases, model_name


async def _compare_basis_contents(
    validation_text: str,
    key_bases: list[dict[str, Any]],
    basis_contents: dict[uuid.UUID, str],
    reference_items: list[ReferenceCheckItem],
    focus_points: str | None,
    job_id: str | None = None,
) -> list[dict[str, Any]]:
    """P3：逐份关键依据与验证文档正文比对（并发 2，限流重试）。

    job_id 传入时逐段上报进度：分块比对可达 10-30 分钟，且进度更新同时
    续期 Redis 任务键（TTL 600s），长时间静默会让前端轮询 404。
    """
    if not validation_text or not key_bases:
        return []
    semaphore = asyncio.Semaphore(2)

    async def _compare_one(basis: dict[str, Any]) -> list[dict[str, Any]]:
        entry_id = basis["entry_id"]
        basis_text = basis_contents.get(entry_id) or ""
        if not basis_text:
            return []
        # 超长验证文档分块逐段比对（5 万字方案不再只比前 1.2 万字）；
        # 分块超上限时取开头主体 + 末尾块（结论/判定标准常在尾部）
        chunks = split_chunks(validation_text)
        if len(chunks) > _MAX_COMPARE_CHUNKS_PER_BASIS:
            chunks = (
                chunks[: _MAX_COMPARE_CHUNKS_PER_BASIS - 1] + [chunks[-1]]
            )
        rows: list[Any] = []
        async with semaphore:
            for chunk_no, chunk in enumerate(chunks, start=1):
                if job_id:
                    await _report_progress(
                        job_id,
                        f"正在比对依据《{basis.get('name') or basis.get('code')}》"
                        f"第 {chunk_no}/{len(chunks)} 段…",
                    )
                prompt = build_content_compare_prompt(
                    validation_text=chunk["text"],
                    basis_name=basis.get("name") or "",
                    basis_code=basis.get("code") or "",
                    basis_text=basis_text,
                    focus_points=focus_points,
                )
                raw, _model = await _call_llm_with_retry(prompt)
                chunk_rows = raw.get("findings") or []
                if isinstance(chunk_rows, list):
                    rows.extend(chunk_rows)
        compact_basis = re.sub(r"\s+", "", basis_text)
        seen_quotes: set[tuple[str, str]] = set()
        results: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            validation_quote = str(item.get("validation_quote") or "")[:300]
            basis_quote = str(item.get("basis_quote") or "")[:300]
            # 相邻分块有重叠，同一条矛盾可能被重复报出
            dedup_key = (validation_quote[:100], basis_quote[:100])
            if dedup_key in seen_quotes:
                continue
            seen_quotes.add(dedup_key)
            severity = item.get("severity", "medium")
            if severity not in SEVERITY_LEVELS:
                severity = "medium"
            results.append(
                {
                    "category": "basis_content_mismatch",
                    "severity": severity,
                    "location": (
                        f"依据《{basis.get('name') or basis.get('code')}》比对"
                    ),
                    "quote": validation_quote,
                    "quote_verified": _quote_verified(
                        validation_quote, [validation_text]
                    ),
                    "basis_source": (
                        f"{basis.get('code')} {basis.get('name') or ''}".strip()
                    ),
                    "basis_match_type": "content_compare",
                    "basis_entry_id": str(entry_id),
                    "detail": str(item.get("detail") or "")[:500],
                    "validation_quote": validation_quote,
                    "basis_quote": basis_quote,
                    "basis_quote_verified": bool(
                        basis_quote
                        and re.sub(r"\s+", "", basis_quote)[:200] in compact_basis
                    ),
                }
            )
        return results

    tasks = [_compare_one(basis) for basis in key_bases]
    grouped = await asyncio.gather(*tasks, return_exceptions=True)
    findings: list[dict[str, Any]] = []
    for group in grouped:
        if isinstance(group, BaseException):
            logger.warning("basis content compare group failed: %r", group)
            continue
        findings.extend(group)
    return findings


def _build_basis_comparison(
    key_bases: list[dict[str, Any]],
    compare_findings: list[dict[str, Any]],
    basis_contents: dict[uuid.UUID, str],
) -> list[dict[str, Any]]:
    """基准比对区块：每份关键依据的筛选理由与比对结果。

    mismatch_count 用 basis_entry_id 精确关联（P3 生成时写入），避免
    编号子串误计/漏计。
    """
    rows: list[dict[str, Any]] = []
    for basis in key_bases:
        entry_id = basis["entry_id"]
        count = sum(
            1
            for finding in compare_findings
            if finding.get("basis_entry_id")
            and str(finding.get("basis_entry_id")) == str(entry_id)
        )
        rows.append(
            {
                "entry_id": str(entry_id),
                "code": basis.get("code"),
                "name": basis.get("name"),
                "reason": basis.get("reason"),
                "content_length": len(basis_contents.get(entry_id) or ""),
                "mismatch_count": count,
                "status": "completed",
            }
        )
    return rows


async def _collect_quality_data_summary(
    db: AsyncSession,
    identities: dict[str, dict[str, Any]],
    texts: dict[str, str],
) -> list[dict[str, Any]]:
    """检索与验证相关的偏差/变更摘要（本地台账，供 AI 评估影响）。"""
    keywords = _extract_quality_keywords(identities, texts)
    if not keywords:
        return []
    summary: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    try:
        for keyword in keywords[:3]:
            deviations, _total = await get_deviations(
                db, keyword=keyword, page=1, page_size=5
            )
            for deviation in deviations:
                code = deviation.deviation_code
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                summary.append(
                    {
                        "type": "deviation",
                        "code": code,
                        "title": (deviation.title or "")[:100],
                        "status": deviation.status,
                        "level": deviation.level,
                        "affected_items": (deviation.affected_items or "")[:100],
                    }
                )
            changes, _total = await get_changes(
                db, content_keyword=keyword, page=1, page_size=5
            )
            for change in changes:
                code = change.change_code
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                summary.append(
                    {
                        "type": "change",
                        "code": code,
                        "change_object": (change.change_object or "")[:100],
                        "change_content": (change.change_content or "")[:150],
                        "closed": change.closure_date is not None,
                    }
                )
        # 相关性由 LLM 结合正文判断：无关记录不产生发现即可
    except Exception as exc:  # noqa: BLE001 —— 台账检索失败降级为空，不阻塞审核
        logger.warning(
            "quality data summary failed",
            extra={"component": "quality", "error": str(exc)},
        )
        return []
    return summary[:15]


def _extract_quality_keywords(
    identities: dict[str, dict[str, Any]], texts: dict[str, str]
) -> list[str]:
    """从文档身份/正文提取质量台账检索关键词（产品代码、车间、设备前缀）。"""
    keywords: list[str] = []
    first_ident = next(iter(identities.values()), {})
    combined = " ".join(str(value) for value in first_ident.values())
    for source in (combined, " ".join(texts.values())[:4000]):
        # 编号第二段：VP-FT3-CV1902-01 → FT3；VP-MC-PV1902-01 → MC
        for match in re.findall(r"[A-Z]{2,4}-([A-Z][A-Z0-9]{1,5})-", source or ""):
            if match not in keywords and not match.isdigit():
                keywords.append(match)
        if keywords:
            break
    return keywords[:3]


async def _call_llm_with_retry(
    prompt: str, expected_keys: list[str] | None = None
) -> tuple[dict[str, Any], str | None]:
    """调用 LLM 语义审核；LLMRateLimitError 指数退避重试，耗尽后原样抛出。

    expected_keys 按调用点的输出契约传入：P1/P3 返回 findings，P2 返回 selected，
    校验错键会让该环节永远失败并静默降级。
    """
    config = await get_config("text")
    model_name = getattr(config, "model_name", None)
    raw: dict[str, Any] = {}
    for attempt in range(_LLM_MAX_RETRIES):
        try:
            raw = await llm_client.chat_json(
                [{"role": "user", "content": prompt}],
                expected_keys=expected_keys or ["findings"],
                temperature=0.2,
            )
            return raw, model_name
        except LLMRateLimitError:
            if attempt == _LLM_MAX_RETRIES - 1:
                raise
            await asyncio.sleep(2**attempt)
    return raw, model_name


def _parse_llm_findings(
    raw_findings: Any, texts: list[str]
) -> list[dict[str, Any]]:
    """LLM findings 逐条容错校验：非法分类丢弃，默认严重度 medium，quote 原文校验。"""
    if not isinstance(raw_findings, list):
        return []
    findings: list[dict[str, Any]] = []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        category = item.get("category")
        if category not in FINDING_CATEGORIES:
            continue
        severity = item.get("severity", "medium")
        if severity not in SEVERITY_LEVELS:
            severity = "medium"
        quote = str(item.get("quote", "") or "")[:300]
        findings.append(
            {
                "category": category,
                "severity": severity,
                "location": str(item.get("location", "") or "")[:200],
                "quote": quote,
                "quote_verified": _quote_verified(quote, texts),
                "basis_source": None,
                "basis_match_type": "llm",
                "detail": str(item.get("detail", "") or "")[:500],
            }
        )
    return findings


def _quote_verified(quote: str, texts: list[str]) -> bool:
    """引文是否在原文中出现（去空白比较，取前 200 字符）。"""
    compact_quote = re.sub(r"\s+", "", quote or "")[:200]
    if not compact_quote:
        return False
    for text in texts:
        if compact_quote in re.sub(r"\s+", "", text or ""):
            return True
    return False


def _build_stats(
    findings: list[dict[str, Any]],
    reference_items: list[ReferenceCheckItem],
    texts: dict[str, str],
) -> dict[str, Any]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        severity = finding.get("severity", "medium")
        if severity in counts:
            counts[severity] += 1
    checked = [item for item in reference_items if item.match_type != "noise"]
    matched = [item for item in checked if item.matched]
    return {
        "total_findings": len(findings),
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "references_checked": len(checked),
        "references_matched": len(matched),
        "plan_report_checked": (
            DOC_KIND_PLAN in texts and DOC_KIND_REPORT in texts
        ),
    }


def _build_summary(
    stats: dict[str, Any], basis_comparison: list[dict[str, Any]] | None = None
) -> str:
    parts = [
        f"本次 AI 审核共核对引用文件 {stats['references_checked']} 项"
        f"（目录命中 {stats['references_matched']} 项），"
        f"发现 {stats['total_findings']} 个问题"
        f"（高 {stats['high']} / 中 {stats['medium']} / 低 {stats['low']}）。"
    ]
    if stats["plan_report_checked"]:
        parts.append("已进行方案与报告一致性核对。")
    mismatch_bases = [
        row
        for row in (basis_comparison or [])
        if isinstance(row, dict) and row.get("mismatch_count")
    ]
    if mismatch_bases:
        names = "、".join(
            f"《{row.get('name') or row.get('code')}》" for row in mismatch_bases
        )
        parts.append(f"已与依据文件正文比对：{names}。")
    parts.append("AI 结果仅供辅助判断，需人工复核后使用，审批仍按线下流程执行。")
    return "".join(parts)


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return type(exc).__name__
    return message[:500]


# ─── 结果组装 ────────────────────────────────────────────────────────


def build_review_out(
    record: ValidationReviewRecord, files: list[ValidationReviewFile]
) -> dict[str, Any]:
    payload = record.output_payload or {}
    stats_data = payload.get("stats")
    findings = payload.get("findings") or []
    basis_used = payload.get("basis_used") or []
    basis_comparison = payload.get("basis_comparison") or []
    focus_points = payload.get("focus_points")
    out = ValidationReviewOut(
        id=record.id,
        title=record.title,
        review_mode=record.review_mode,
        status=record.status,
        error_message=record.error_message,
        model_name=record.model_name,
        input_snapshot=record.input_snapshot,
        summary=payload.get("summary"),
        stats=(
            ValidationReviewStatsOut(**stats_data)
            if isinstance(stats_data, dict)
            else None
        ),
        findings=[
            ValidationReviewFindingOut(**finding)
            for finding in findings
            if isinstance(finding, dict)
        ],
        basis_used=basis_used,
        basis_comparison=basis_comparison,
        focus_points=focus_points,
        job_id=record.job_id,
        last_generated_at=record.last_generated_at,
        files=[
            ValidationReviewFileOut(
                id=row.id,
                doc_kind=row.doc_kind,
                source=row.source,
                file_name=row.file_name,
                file_type=row.file_type,
                file_size=row.file_size,
                parse_status=row.parse_status,
                parse_error=row.parse_error,
                sort_order=row.sort_order,
            )
            for row in files
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
    return out.model_dump(mode="json")


def build_review_list_item(
    record: ValidationReviewRecord, file_count: int
) -> dict[str, Any]:
    item = ValidationReviewListItem(
        id=record.id,
        title=record.title,
        review_mode=record.review_mode,
        status=record.status,
        model_name=record.model_name,
        file_count=file_count,
        error_message=record.error_message,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
    return item.model_dump(mode="json")


async def reconcile_orphaned_reviews(db: AsyncSession) -> int:
    """启动对账：processing 但后台 job 已死的记录翻为 failed。

    服务重启/进程被杀会留下永久 processing 的孤儿记录（job 与心跳随
    进程消失，无任何收尾）；与 procurement 的 reset_interrupted_syncs
    同一模式。返回翻失败的记录数。
    """
    result = await db.execute(
        select(ValidationReviewRecord).where(
            ValidationReviewRecord.status == STATUS_PROCESSING
        )
    )
    orphans = result.scalars().all()
    flipped = 0
    for record in orphans:
        job_id = record.job_id or ""
        if job_id and await is_job_running(job_id):
            continue  # job 真的在跑（心跳存活），不动
        record.status = STATUS_FAILED
        record.error_message = "审核进程被中断（服务重启），请重新发起审核"
        flipped += 1
    if flipped:
        await db.commit()
    if flipped or orphans:
        logger.info(
            "validation review orphan reconciliation: %s flipped / %s scanned",
            flipped,
            len(orphans),
            extra={"component": "quality"},
        )
    return flipped
