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
from app.core.jobs import submit_job
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
    DocumentEntry,
    ValidationReviewFile,
    ValidationReviewRecord,
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
    read_entry_md_contents,
)
from app.modules.quality.service.document_catalog_md import convert_word_attachment
from app.modules.quality.service.validation_basis_resolver import (
    ReferenceCheckItem,
    _compact,
    extract_document_number,
    infer_doc_kind,
    load_document_basis,
    resolve_references,
)
from app.modules.quality.service.validation_review_prompt import (
    FINDING_CATEGORIES,
    SEVERITY_LEVELS,
    build_review_prompt,
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
    review_mode: str,
    entry_id: uuid.UUID | None,
    title: str | None,
) -> ValidationReviewRecord:
    record = ValidationReviewRecord(
        title=(title or "").strip()[:255],
        review_mode=review_mode,
        status=STATUS_DRAFT,
        created_by=user_id,
    )
    db.add(record)
    await db.flush()
    if review_mode == "entry":
        if not entry_id:
            raise AppException(
                status_code=422, message="从文件管理创建审核时必须指定目录条目"
            )
        await add_entry_review_files(db, record, entry_id=entry_id, user_id=user_id)
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


async def add_entry_review_files(
    db: AsyncSession,
    record: ValidationReviewRecord,
    *,
    entry_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[ValidationReviewFile]:
    entry = await db.get(DocumentEntry, entry_id)
    if not entry or entry.is_deleted:
        raise NotFoundException(resource="文件管理条目", resource_id=str(entry_id))
    contents = read_entry_md_contents(entry)
    if not contents:
        raise AppException(
            status_code=422,
            message="该目录条目没有可解析的附件正文（需 word 或 md 附件）",
        )
    existing = await get_review_files(db, record.id)
    rows: list[ValidationReviewFile] = []
    for index, item in enumerate(contents):
        md_text = item.get("md_text") or ""
        row = ValidationReviewFile(
            review_id=record.id,
            doc_kind=infer_doc_kind(item.get("file_name") or ""),
            source=SOURCE_ENTRY,
            file_name=item.get("file_name") or "",
            file_type="text/markdown",
            file_size=len(md_text.encode("utf-8")),
            storage_key="",
            parsed_text=md_text,
            parse_status=PARSE_COMPLETED,
            sort_order=len(existing) + index,
            created_by=user_id,
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


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
) -> tuple[list[ValidationReviewRecord], int]:
    """分页列出审核会话；all_visible=True 时返回全部（QA 可见），否则仅本人创建。"""
    filters: list[Any] = [ValidationReviewRecord.is_deleted.is_(False)]
    if not all_visible:
        filters.append(ValidationReviewRecord.created_by == user_id)
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

    await submit_job(
        _run_review_job,
        task_id=job_id,
        ttl=600,
        status_extra={"owner": str(user_id)},
        record_id=record.id,
        job_id=job_id,
        user_id=user_id,
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


async def _run_review_job(
    *,
    record_id: uuid.UUID,
    job_id: str,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """后台审核任务：独立会话执行，任何失败都落库为 failed 状态。"""
    async with async_session_factory() as db:
        record = await db.get(ValidationReviewRecord, record_id)
        if record is None:
            return {"status": STATUS_FAILED, "error": "审核记录不存在"}
        try:
            await _execute_review(db, record, job_id, user_id)
            await db.commit()
            return {"status": record.status}
        except LLMRateLimitError:
            record.status = STATUS_FAILED
            record.error_message = "LLM 速率限制，重试耗尽"
            await db.commit()
            return {"status": STATUS_FAILED, "error": record.error_message}
        except (LLMConfigError, LLMOutputError, LLMProviderError) as exc:
            record.status = STATUS_FAILED
            record.error_message = _safe_error(exc)
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
) -> None:
    # 1. 解析未解析文件
    files = await get_review_files(db, record.id)
    for row in files:
        if row.parse_status != PARSE_PENDING:
            continue
        content = _read_review_file(row.storage_key)
        if content is None:
            row.parse_status = PARSE_FAILED
            row.parse_error = "原文件缺失"
        else:
            text, err = await _extract_upload_text(row.file_name, content)
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
        texts[row.doc_kind] = texts.get(row.doc_kind, "") + row.parsed_text
        ident: dict[str, Any] = {
            "file_name": row.file_name,
            "doc_number": extract_document_number(row.file_name),
        }
        content_code, content_title = extract_content_identity(row.parsed_text)
        ident["content_code"] = content_code
        ident["content_title"] = content_title
        identities.setdefault(row.doc_kind, ident)
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

    # 4. LLM 语义审核（互查/数值/规范性）
    model_name: str | None = None
    if texts:
        reference_summary = [
            item.to_dict()
            for item in reference_items
            if item.match_type != "noise"
        ]
        prompt = build_review_prompt(
            plan_text=texts.get(DOC_KIND_PLAN),
            report_text=texts.get(DOC_KIND_REPORT),
            reference_summary=reference_summary,
            plan_identity=identities.get(DOC_KIND_PLAN),
            report_identity=identities.get(DOC_KIND_REPORT),
        )
        raw, model_name = await _call_llm_with_retry(prompt)
        llm_findings = _parse_llm_findings(
            raw.get("findings") or [], list(texts.values())
        )
        findings.extend(llm_findings)

    # 5. 结论落库
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
        "truncated": any(
            len(text) > 12000 for text in texts.values()
        ),
    }
    record.output_payload = {
        "summary": _build_summary(stats),
        "stats": stats,
        "findings": findings,
        "basis_used": basis_used,
    }
    record.status = STATUS_COMPLETED
    record.model_name = model_name
    record.error_message = None
    record.last_generated_at = datetime.now(UTC)
    db.add(record)


async def _call_llm_with_retry(prompt: str) -> tuple[dict[str, Any], str | None]:
    """调用 LLM 语义审核；LLMRateLimitError 指数退避重试，耗尽后原样抛出。"""
    config = await get_config("text")
    model_name = getattr(config, "model_name", None)
    raw: dict[str, Any] = {}
    for attempt in range(_LLM_MAX_RETRIES):
        try:
            raw = await llm_client.chat_json(
                [{"role": "user", "content": prompt}],
                expected_keys=["findings"],
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


def _build_summary(stats: dict[str, Any]) -> str:
    parts = [
        f"本次 AI 审核共核对引用文件 {stats['references_checked']} 项"
        f"（目录命中 {stats['references_matched']} 项），"
        f"发现 {stats['total_findings']} 个问题"
        f"（高 {stats['high']} / 中 {stats['medium']} / 低 {stats['low']}）。"
    ]
    if stats["plan_report_checked"]:
        parts.append("已进行方案与报告一致性核对。")
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
