"""历史偏差 service：台账 CRUD + 附件上传（doc/docx/wps → 标准 MD）+ AI 提取。

附件转 MD 复用文件管理同套管线（document_catalog_md.convert_word_attachment，
保留正文表格与图片），存储与图片 URL 改写约定保持一致；pdf/图片原样存储并
提取文本/OCR 供 AI 上下文。AI 提取统一走 app.core.llm.llm_client.chat_json，
结构化输出经业务校验后回填。
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import AppException, NotFoundException
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.core.llm.config import get_config
from app.core.upload_security import (
    read_upload_secure,
    safe_upload_filename,
    sniff_upload_mime,
)
from app.modules.quality.models import HistoricalDeviation
from app.modules.quality.schemas.historical_deviation import (
    CreateHistoricalDeviationRequest,
    HistoricalDeviationAttachmentOut,
    HistoricalDeviationBatchImportResult,
    HistoricalDeviationBatchImportResultItem,
    HistoricalDeviationDetail,
    HistoricalDeviationListItem,
    UpdateHistoricalDeviationRequest,
)
from app.modules.quality.service.quality_attachment import (
    MD_IMAGE_REF_RE,
    attachment_storage_keys,
    delete_file,
    generate_code,
    parse_deviation_code_from_text,
    persisted_user_id,
    read_file,
    render_word_to_md,
    store_file,
)

logger = logging.getLogger(__name__)

ALLOWED_EXT = {".md", ".doc", ".docx", ".wps", ".pdf", ".png", ".jpg", ".jpeg"}
WORD_EXT = {".doc", ".docx", ".wps"}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
TEXT_MD_MIME = "text/markdown; charset=utf-8"
ATTACHMENT_MAX_SIZE = 20 * 1024 * 1024  # 20MB
MAX_BATCH_FILES = 20
AI_CONTEXT_TEXT_LIMIT = 60000

# 本地文件存储子目录（配合 quality_attachment 共享 helper 使用）
_STORAGE_SUBDIR = "historical_deviation"

AI_EXTRACT_KEYS = [
    "deviation_event",
    "deviation_content",
    "direct_cause",
    "root_cause",
]


def _attachment_content_url(record_id: uuid.UUID, storage_key: str) -> str:
    return (
        f"/api/v1/quality/historical-deviations/{record_id}"
        f"/attachments/{quote(storage_key, safe='/')}/content"
    )


def _new_attachment(
    file_name: str,
    storage_key: str,
    content_type: str,
    file_size: int,
    *,
    converted: bool,
    converted_md_key: str | None = None,
    asset_keys: list[str] | None = None,
    uploaded_by: str = "",
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "file_name": file_name,
        "storage_key": storage_key,
        "content_type": content_type,
        "file_size": file_size,
        "converted": converted,
        "converted_md_key": converted_md_key,
        "asset_keys": list(asset_keys or []),
        "uploaded_at": datetime.now(UTC).isoformat(),
        "uploaded_by": uploaded_by or "",
    }


def _attachment_to_schema(
    record_id: uuid.UUID, attachment: dict[str, Any]
) -> HistoricalDeviationAttachmentOut:
    return HistoricalDeviationAttachmentOut(
        id=str(attachment.get("id") or ""),
        file_name=attachment.get("file_name") or "",
        url=_attachment_content_url(record_id, attachment.get("storage_key") or ""),
        content_type=attachment.get("content_type"),
        file_size=attachment.get("file_size"),
        converted=bool(attachment.get("converted")),
        uploaded_at=attachment.get("uploaded_at"),
        uploaded_by=attachment.get("uploaded_by"),
    )


async def _require_quality_ai_config() -> Any:
    try:
        return await get_config("text")
    except LLMConfigError as exc:
        raise AppException(status_code=503, message="AI 服务尚未配置") from exc


async def _get_or_raise(db: AsyncSession, record_id: uuid.UUID) -> HistoricalDeviation:
    record = await db.get(HistoricalDeviation, record_id)
    if not record or record.is_deleted:
        raise NotFoundException(resource="历史偏差")
    return record


def _list_item_to_schema(record: HistoricalDeviation) -> HistoricalDeviationListItem:
    return HistoricalDeviationListItem(
        id=record.id,
        code=record.code,
        deviation_event=record.deviation_event,
        deviation_content=record.deviation_content,
        direct_cause=record.direct_cause,
        root_cause=record.root_cause,
        investigation_conclusion=record.investigation_conclusion,
        attachment_count=len(record.attachments or []),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _detail_to_schema(record: HistoricalDeviation) -> HistoricalDeviationDetail:
    detail = _list_item_to_schema(record).model_dump()
    detail["attachments"] = [
        _attachment_to_schema(record.id, attachment).model_dump(mode="json")
        for attachment in record.attachments or []
    ]
    detail["ai_extract_payload"] = record.ai_extract_payload
    detail["remark"] = record.remark
    return HistoricalDeviationDetail.model_validate(detail)


async def get_historical_deviation_list(
    db: AsyncSession,
    *,
    keyword: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    filters: list[ColumnElement[bool]] = [HistoricalDeviation.is_deleted.is_(False)]
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(
            or_(
                HistoricalDeviation.code.ilike(pattern),
                HistoricalDeviation.deviation_event.ilike(pattern),
                HistoricalDeviation.deviation_content.ilike(pattern),
                HistoricalDeviation.direct_cause.ilike(pattern),
                HistoricalDeviation.root_cause.ilike(pattern),
                HistoricalDeviation.investigation_conclusion.ilike(pattern),
            )
        )
    query = select(HistoricalDeviation).where(*filters)
    count_query = (
        select(func.count()).select_from(HistoricalDeviation).where(*filters)
    )
    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(HistoricalDeviation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_list_item_to_schema(item) for item in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_historical_deviation_detail(
    db: AsyncSession, record_id: uuid.UUID
) -> HistoricalDeviationDetail:
    record = await _get_or_raise(db, record_id)
    return _detail_to_schema(record)


async def create_historical_deviation(
    db: AsyncSession,
    data: CreateHistoricalDeviationRequest,
    user_id: str,
) -> HistoricalDeviationDetail:
    code = await generate_code(db, HistoricalDeviation, "HD")
    record = HistoricalDeviation(
        code=code,
        deviation_event=data.deviation_event,
        deviation_content=data.deviation_content,
        direct_cause=data.direct_cause,
        root_cause=data.root_cause,
        investigation_conclusion=data.investigation_conclusion,
        remark=data.remark,
        attachments=[],
        created_by=persisted_user_id(user_id),
        updated_by=persisted_user_id(user_id),
    )
    db.add(record)
    await db.flush()
    await db.commit()
    result = await db.execute(
        select(HistoricalDeviation).where(HistoricalDeviation.id == record.id)
    )
    return _detail_to_schema(result.scalar_one())


async def update_historical_deviation(
    db: AsyncSession,
    record_id: uuid.UUID,
    data: UpdateHistoricalDeviationRequest,
    user_id: str,
) -> HistoricalDeviationDetail:
    record = await _get_or_raise(db, record_id)
    record.deviation_event = data.deviation_event
    record.deviation_content = data.deviation_content
    record.direct_cause = data.direct_cause
    record.root_cause = data.root_cause
    record.investigation_conclusion = data.investigation_conclusion
    record.remark = data.remark
    record.updated_by = persisted_user_id(user_id)
    await db.commit()
    result = await db.execute(
        select(HistoricalDeviation).where(HistoricalDeviation.id == record_id)
    )
    return _detail_to_schema(result.scalar_one())


async def _maybe_apply_pc_code(
    db: AsyncSession, record: HistoricalDeviation, file_name: str, text_sample: str
) -> None:
    """从附件文件名（回退正文）解析 PC-YYMMNNN 编号并回填 code。

    仅当当前 code 仍是 HD 占位（尚未解析出真实编号）且解析到的编号未被占用时更新；
    解析不到则保持 HD 占位，列表按「非 PC- 前缀」显示 "-"。
    """
    if record.code and record.code.startswith("PC-"):
        return
    parsed = parse_deviation_code_from_text(file_name)
    if not parsed:
        parsed = parse_deviation_code_from_text(text_sample[:300])
    if not parsed:
        return
    taken = await db.execute(
        select(HistoricalDeviation.id).where(
            HistoricalDeviation.code == parsed,
            HistoricalDeviation.is_deleted.is_(False),
            HistoricalDeviation.id != record.id,
        )
    )
    if taken.first() is not None:
        return
    record.code = parsed


async def upload_historical_deviation_attachment(
    db: AsyncSession,
    record_id: uuid.UUID,
    file: UploadFile,
    user_id: str,
) -> HistoricalDeviationAttachmentOut:
    if not file.filename:
        raise AppException(message="附件文件名不能为空")
    file_name, content = await read_upload_secure(
        file,
        max_bytes=ATTACHMENT_MAX_SIZE,
        allowed_extensions=ALLOWED_EXT,
        what="历史偏差附件",
    )
    content_type = sniff_upload_mime(file_name, content)
    record = await _get_or_raise(db, record_id)

    safe_file_name = safe_upload_filename(file_name, fallback="attachment.bin")
    safe_name = f"{uuid.uuid4().hex}_{safe_file_name}"
    original_key = f"historical-deviations/attachments/{safe_name}"
    stored_keys: list[str] = []
    try:
        store_file(_STORAGE_SUBDIR, original_key, content, content_type)
        stored_keys.append(original_key)

        converted_md_key: str | None = None
        asset_keys: list[str] = []
        text_for_code: str = file_name
        ext = Path(file_name).suffix.lower()
        if ext in WORD_EXT:
            try:
                md_text, images = await asyncio.to_thread(
                    render_word_to_md, file_name, content
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "historical deviation word convert failed, stored as-is",
                    extra={"component": "quality", "file": file_name},
                )
            else:
                text_for_code = f"{file_name}\n{md_text}"
                name_to_url: dict[str, str] = {}
                for image in images:
                    asset_key = (
                        "historical-deviations/attachments/"
                        f"{uuid.uuid4().hex}_{image.name}"
                    )
                    store_file(
                        _STORAGE_SUBDIR, asset_key, image.data, image.content_type
                    )
                    stored_keys.append(asset_key)
                    asset_keys.append(asset_key)
                    name_to_url[image.name] = _attachment_content_url(
                        record.id, asset_key
                    )
                md_text = MD_IMAGE_REF_RE.sub(
                    lambda m: f"![image]({name_to_url[m.group(1)]})", md_text
                )
                md_key = (
                    "historical-deviations/attachments/"
                    f"{uuid.uuid4().hex}_{Path(file_name).stem}.md"
                )
                store_file(
                    _STORAGE_SUBDIR, md_key, md_text.encode("utf-8"), TEXT_MD_MIME
                )
                stored_keys.append(md_key)
                converted_md_key = md_key
        elif ext == ".md":
            converted_md_key = original_key

        attachment = _new_attachment(
            file_name=file_name,
            storage_key=original_key,
            content_type=content_type,
            file_size=len(content),
            converted=converted_md_key is not None,
            converted_md_key=converted_md_key,
            asset_keys=asset_keys,
            uploaded_by=user_id,
        )
        attachments = list(record.attachments or [])
        attachments.append(attachment)
        record.attachments = attachments
        record.updated_by = persisted_user_id(user_id)
        await _maybe_apply_pc_code(db, record, file_name, text_for_code)
        await db.flush()
        await db.commit()
    except Exception:
        for stored_key in reversed(stored_keys):
            try:
                delete_file(_STORAGE_SUBDIR, stored_key)
            except Exception:  # noqa: BLE001
                logger.exception("清理历史偏差附件对象失败: object_key=%s", stored_key)
        raise
    return _attachment_to_schema(record.id, attachment)


async def delete_historical_deviation(
    db: AsyncSession,
    record_id: uuid.UUID,
    user_id: str,
) -> None:
    record = await _get_or_raise(db, record_id)
    for attachment in record.attachments or []:
        for key in attachment_storage_keys(attachment):
            try:
                delete_file(_STORAGE_SUBDIR, key)
            except Exception:  # noqa: BLE001
                logger.exception("清理历史偏差附件对象失败: object_key=%s", key)
    record.is_deleted = True
    record.deleted_by = persisted_user_id(user_id)
    record.deleted_at = datetime.now(UTC)
    await db.commit()


async def batch_import_historical_deviations(
    db: AsyncSession,
    files: list[UploadFile],
    user_id: str,
) -> HistoricalDeviationBatchImportResult:
    """批量导入历史偏差：每个附件转 MD + 建记录 + 解析 PC 编号 + AI 提取。

    单文件失败回滚会话并补偿删除半成品记录，不影响其它文件；AI 提取失败
    不算导入失败（记录与 MD 已就绪，可后续手动提取）。
    """
    if len(files) > MAX_BATCH_FILES:
        raise AppException(message=f"单次最多上传 {MAX_BATCH_FILES} 个附件")
    results: list[HistoricalDeviationBatchImportResultItem] = []
    succeeded = 0
    for file in files:
        file_name = (file.filename or "").strip()
        created_id: uuid.UUID | None = None
        try:
            created = await create_historical_deviation(
                db, CreateHistoricalDeviationRequest(), user_id
            )
            created_id = created.id
            await upload_historical_deviation_attachment(
                db, created_id, file, user_id
            )
            refreshed = await db.execute(
                select(HistoricalDeviation).where(HistoricalDeviation.id == created_id)
            )
            record = refreshed.scalar_one()
            ai_message = ""
            try:
                await ai_extract_historical_deviation(db, record.id, user_id)
            except AppException as exc:
                ai_message = f"AI 提取失败：{exc.message}"
            succeeded += 1
            results.append(
                HistoricalDeviationBatchImportResultItem(
                    file_name=file_name,
                    code=record.code,
                    status="succeeded",
                    message=ai_message,
                )
            )
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            if created_id is not None:
                # 补偿删除半成品记录，避免遗留空壳
                try:
                    await delete_historical_deviation(db, created_id, user_id)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "批量导入补偿删除失败: record_id=%s", created_id
                    )
            logger.exception("批量导入单文件失败: file=%s", file_name)
            results.append(
                HistoricalDeviationBatchImportResultItem(
                    file_name=file_name,
                    code="",
                    status="failed",
                    message=_safe_import_error(exc),
                )
            )
    return HistoricalDeviationBatchImportResult(
        total=len(files),
        succeeded=succeeded,
        failed=len(files) - succeeded,
        results=results,
    )


def _safe_import_error(exc: Exception) -> str:
    """仅回传业务异常消息，避免把 DB/内部错误细节暴露给前端。"""
    if isinstance(exc, AppException):
        return exc.message
    logger.exception("批量导入内部错误")
    return "导入失败，请检查文件格式后重试"


async def delete_historical_deviation_attachment(
    db: AsyncSession,
    record_id: uuid.UUID,
    attachment_id: str,
    user_id: str,
) -> HistoricalDeviationDetail:
    record = await _get_or_raise(db, record_id)
    attachments = list(record.attachments or [])
    target = next(
        (a for a in attachments if str(a.get("id")) == attachment_id), None
    )
    if target is None:
        raise NotFoundException(resource="附件")
    for key in attachment_storage_keys(target):
        try:
            delete_file(_STORAGE_SUBDIR, key)
        except Exception:  # noqa: BLE001
            logger.exception("清理历史偏差附件对象失败: object_key=%s", key)
    record.attachments = [
        a for a in attachments if str(a.get("id")) != attachment_id
    ]
    record.updated_by = persisted_user_id(user_id)
    await db.commit()
    result = await db.execute(
        select(HistoricalDeviation).where(HistoricalDeviation.id == record_id)
    )
    return _detail_to_schema(result.scalar_one())


async def get_historical_deviation_attachment_content(
    db: AsyncSession, record_id: uuid.UUID, storage_key: str
) -> tuple[bytes, str]:
    """读取附件预览内容（按记录校验权限后读取）。"""
    record = await _get_or_raise(db, record_id)
    return read_historical_deviation_attachment_content(record, storage_key)


def read_historical_deviation_attachment_content(
    record: HistoricalDeviation, storage_key: str
) -> tuple[bytes, str]:
    """读取附件预览内容：word 返回标准 MD；图片/PDF 返回原文件；图片资产按图返回。"""
    for attachment in record.attachments or []:
        if attachment.get("storage_key") == storage_key:
            if attachment.get("converted_md_key"):
                stored = read_file(_STORAGE_SUBDIR, attachment["converted_md_key"])
                if stored is not None:
                    data, _ = stored
                    return data, TEXT_MD_MIME
            stored = read_file(_STORAGE_SUBDIR, storage_key)
            if stored is not None:
                data, _ = stored
                return (
                    data,
                    attachment.get("content_type")
                    or "application/octet-stream",
                )
            break
        if storage_key in (attachment.get("asset_keys") or []):
            stored = read_file(_STORAGE_SUBDIR, storage_key)
            if stored is None:
                break
            data, content_type = stored
            if content_type == "application/octet-stream":
                content_type = sniff_upload_mime(storage_key, data)
            return data, content_type
    return b"", "application/octet-stream"


async def _extract_image_text(content: bytes, content_type: str) -> str:
    try:
        import pytesseract  # type: ignore[import-untyped]
        from PIL import Image

        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image, lang="chi_sim+eng").strip()
        return str(text)
    except Exception:  # noqa: BLE001
        return ""


async def _build_ai_context_text(record: HistoricalDeviation) -> str:
    """汇总附件内容供 AI 提取：正文用纯文本提取（模板化转换可能丢弃无标题正文）。

    预览仍使用转换后标准 MD（保留表格与图片）；AI 上下文以原文全文为准。
    """
    from app.platform.ai.document_text_extractor import extract_document_text

    parts: list[str] = []
    for attachment in record.attachments or []:
        file_name = attachment.get("file_name") or ""
        stored = read_file(_STORAGE_SUBDIR, attachment.get("storage_key") or "")
        if stored is None:
            continue
        content, _ = stored
        ext = Path(file_name).suffix.lower()
        try:
            if ext in IMAGE_EXT:
                content_type = attachment.get("content_type") or ""
                text = await _extract_image_text(content, content_type)
            else:
                text = extract_document_text(file_name, content)
        except Exception:  # noqa: BLE001
            logger.warning("历史偏差附件解析失败: %s", file_name)
            continue
        if text.strip():
            parts.append(f"【附件：{file_name}】\n{text.strip()}")
    joined = "\n\n".join(parts).strip()
    if len(joined) > AI_CONTEXT_TEXT_LIMIT:
        joined = joined[:AI_CONTEXT_TEXT_LIMIT]
    return joined


def _ai_extract_prompt(attachment_text: str) -> str:
    return f"""
你是原料药工厂质量管理助理。请根据以下历史偏差附件内容，提取/总结一条历史偏差记录的字段，
禁止编造附件中不存在的事实或法规条文。

附件内容：
{attachment_text}

严格输出 JSON，字段必须完整：
{{
  "deviation_event": "偏差事件：客观描述偏差发生的时间、过程与现象",
  "deviation_content": "偏差内容：按人机料法环测（5M1E）六维度总结偏差涉及内容",
  "direct_cause": "调查结论-直接原因：直接导致偏差的原因",
  "root_cause": "调查结论-根本原因：深层/系统性的根本原因"
}}
""".strip()


async def ai_extract_historical_deviation(
    db: AsyncSession,
    record_id: uuid.UUID,
    user_id: str,
) -> HistoricalDeviationDetail:
    record = await _get_or_raise(db, record_id)
    context_text = await _build_ai_context_text(record)
    if not context_text.strip():
        raise AppException(
            message="请先上传可解析的附件（Word/PDF/图片），再进行 AI 提取"
        )

    config = await _require_quality_ai_config()
    prompt = _ai_extract_prompt(context_text)
    try:
        raw: dict[str, Any] = {}
        max_retries = 3
        for attempt in range(max_retries):
            try:
                raw = await llm_client.chat_json(
                    [{"role": "user", "content": prompt}],
                    expected_keys=AI_EXTRACT_KEYS,
                    temperature=0.2,
                )
                break
            except LLMRateLimitError:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
    except LLMRateLimitError:
        raise AppException(status_code=502, message="AI 限流，请稍后重试") from None
    except LLMOutputError:
        raise AppException(status_code=502, message="AI 输出格式错误，请重试") from None
    except LLMProviderError:
        raise AppException(
            status_code=502, message="AI 服务调用失败，请稍后重试"
        ) from None

    deviation_event = str(raw.get("deviation_event") or "").strip() or None
    deviation_content = str(raw.get("deviation_content") or "").strip() or None
    direct_cause = str(raw.get("direct_cause") or "").strip() or None
    root_cause = str(raw.get("root_cause") or "").strip() or None
    if not any([deviation_event, deviation_content, direct_cause, root_cause]):
        raise AppException(status_code=502, message="AI 未提取到有效内容，请重试")

    record.deviation_event = deviation_event
    record.deviation_content = deviation_content
    record.direct_cause = direct_cause
    record.root_cause = root_cause
    record.ai_extract_payload = {
        "attachments": [
            {
                "id": a.get("id"),
                "file_name": a.get("file_name"),
                "converted": a.get("converted"),
            }
            for a in record.attachments or []
        ],
        "raw": raw,
        "model_name": config.model_name,
        "extracted_at": datetime.now(UTC).isoformat(),
    }
    record.updated_by = persisted_user_id(user_id)
    await db.commit()
    result = await db.execute(
        select(HistoricalDeviation).where(HistoricalDeviation.id == record_id)
    )
    return _detail_to_schema(result.scalar_one())
