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
            await _execute_review(db, record, job_id, user_id, focus_points)
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
    focus_points: str | None = None,
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

    # 4. 基准正文一致性核查：拉取命中依据正文 → P2 筛选 → P3 逐份比对
    model_name: str | None = None
    basis_comparison: list[dict[str, Any]] = []
    hit_entries = _collect_hit_entries(reference_items)
    basis_contents = await load_basis_contents(db, hit_entries)
    if basis_contents and texts:
        validation_text = (
            texts.get(DOC_KIND_PLAN, "") + "\n\n" + texts.get(DOC_KIND_REPORT, "")
        ).strip()
        candidate_bases = _build_candidate_bases(reference_items, basis_contents)
        document_summary = _document_summary(identities)
        key_bases, model_name = await _select_key_bases(
            document_summary, candidate_bases, focus_points
        )
        compare_findings = await _compare_basis_contents(
            validation_text,
            key_bases,
            basis_contents,
            reference_items,
            focus_points,
        )
        findings.extend(compare_findings)
        basis_comparison = _build_basis_comparison(
            key_bases, compare_findings, basis_contents
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
        prompt = build_review_prompt(
            plan_text=texts.get(DOC_KIND_PLAN),
            report_text=texts.get(DOC_KIND_REPORT),
            reference_summary=reference_summary,
            plan_identity=identities.get(DOC_KIND_PLAN),
            report_identity=identities.get(DOC_KIND_REPORT),
            focus_points=focus_points,
            quality_data_summary=quality_data_summary,
        )
        raw, model_name = await _call_llm_with_retry(prompt)
        llm_findings = _parse_llm_findings(
            raw.get("findings") or [], list(texts.values())
        )
        findings.extend(llm_findings)

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
    record.status = STATUS_COMPLETED
    record.model_name = model_name
    record.error_message = None
    record.last_generated_at = datetime.now(UTC)
    db.add(record)


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


async def _select_key_bases(
    document_summary: str,
    candidate_bases: list[dict[str, Any]],
    focus_points: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """P2：AI 筛选实质相关的关键依据（1 次调用）。"""
    if not candidate_bases:
        return [], None
    prompt = build_basis_selection_prompt(
        document_summary=document_summary, candidate_bases=candidate_bases
    )
    raw, model_name = await _call_llm_with_retry(prompt)
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
) -> list[dict[str, Any]]:
    """P3：逐份关键依据与验证文档正文比对（并发 2，限流重试）。"""
    if not validation_text or not key_bases:
        return []
    semaphore = asyncio.Semaphore(2)

    async def _compare_one(basis: dict[str, Any]) -> list[dict[str, Any]]:
        entry_id = basis["entry_id"]
        basis_text = basis_contents.get(entry_id) or ""
        if not basis_text:
            return []
        prompt = build_content_compare_prompt(
            validation_text=validation_text,
            basis_name=basis.get("name") or "",
            basis_code=basis.get("code") or "",
            basis_text=basis_text,
            focus_points=focus_points,
        )
        async with semaphore:
            raw, _model = await _call_llm_with_retry(prompt)
        rows = raw.get("findings") or []
        if not isinstance(rows, list):
            return []
        compact_basis = re.sub(r"\s+", "", basis_text)
        results: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            validation_quote = str(item.get("validation_quote") or "")[:300]
            basis_quote = str(item.get("basis_quote") or "")[:300]
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
    """基准比对区块：每份关键依据的筛选理由与比对结果。"""
    rows: list[dict[str, Any]] = []
    for basis in key_bases:
        entry_id = basis["entry_id"]
        count = sum(
            1
            for finding in compare_findings
            if finding.get("basis_source")
            and basis.get("code")
            and str(basis.get("code")) in str(finding.get("basis_source"))
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
