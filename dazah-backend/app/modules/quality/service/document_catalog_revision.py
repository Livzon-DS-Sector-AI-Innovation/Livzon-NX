"""正文元数据校验、行锁与附件版本替换。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol, cast

from sqlalchemy import event, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.modules.quality.models.document_catalog import DocumentEntry
from app.modules.quality.service import document_catalog_attachment as storage
from app.modules.quality.service.document_catalog import parse_effective_date
from app.modules.quality.service.document_catalog_md import (
    ExtractedImage,
    convert_word_attachment,
)
from app.modules.quality.service.document_catalog_metadata import extract_field
from app.modules.quality.service.document_catalog_scope import document_entry_scope
from app.platform.identity.data_scope import DepartmentScope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AttachmentRevision:
    code: str
    prefix: str
    revision: int
    effective_date: date
    prepared: tuple[str, list[ExtractedImage]] | None


def split_code(code: str) -> tuple[str, int] | None:
    parsed = storage._parse_entry_code_revision(code)
    if parsed is None:
        return None
    prefix = code.strip()[: -len(parsed[1])].rstrip("/-_")
    return storage._normalize_identity(prefix), parsed[0]


class _PdfPage(Protocol):
    def get_text(self) -> str: ...


class _PdfDocument(Protocol):
    def __len__(self) -> int: ...
    def __getitem__(self, index: int) -> _PdfPage: ...


def _pdf_text(content: bytes) -> str:
    import pymupdf

    # PyMuPDF 未声明该入口的类型，在适配边界限定实际使用的协议。
    open_pdf = cast(Callable[..., AbstractContextManager[_PdfDocument]], pymupdf.open)
    with open_pdf(stream=content, filetype="pdf") as doc:
        return doc[0].get_text() if len(doc) else ""


async def prepare_revision(file_name: str, content: bytes) -> AttachmentRevision:
    ext = Path(file_name).suffix.lower()
    prepared = None
    if len(content) > storage.ATTACHMENT_MAX_SIZE:
        raise AppException(message="附件不能超过 20MB")
    try:
        if ext in storage.WORD_EXT:
            prepared = await asyncio.to_thread(
                convert_word_attachment, file_name, content
            )
            if prepared[0].startswith("# 文本提取模式"):
                raise AppException(
                    message="Word 格式转换失败，无法保留页眉、表格并可靠识别编号；"
                    "请检查服务端文档转换组件，目录和附件未修改"
                )
            text = prepared[0].split("\n---", 1)[0]
        elif ext == ".md":
            text = content.decode("utf-8-sig").split("\n---", 1)[0]
        elif ext == ".pdf":
            text = await asyncio.to_thread(_pdf_text, content)
        else:
            raise AppException(
                message="无法可靠读取附件正文编号和生效日期，"
                "请上传可解析的 Word、PDF 或 Markdown"
            )
    except AppException:
        raise
    except Exception as exc:
        raise AppException(
            message="附件正文解析失败，原目录和附件未修改", status_code=400
        ) from exc
    code = extract_field(text, "code")
    parsed = split_code(code)
    if parsed is None or len(code) > 255:
        raise AppException(message="附件正文缺少唯一、含版本号的文件编号，未更新")
    effective, _ = parse_effective_date(extract_field(text, "date"))
    if effective is None:
        raise AppException(message="附件正文缺少唯一、有效的生效日期，未更新")
    return AttachmentRevision(code, parsed[0], parsed[1], effective, prepared)


async def find_revision_entry(
    db: AsyncSession,
    revision: AttachmentRevision,
    scope: DepartmentScope | None,
) -> DocumentEntry | None:
    # 严格比对主体编号；禁止名称/AI 跨编号兜底，重复目录也不猜测。
    prefixes = {revision.prefix, revision.prefix.replace("(", "（").replace(")", "）")}
    conditions = []
    for prefix in prefixes:
        escaped = storage._escape_like(prefix)
        conditions.extend(
            [
                DocumentEntry.code.ilike(escaped),
                DocumentEntry.code.ilike(f"{escaped}/%"),
                DocumentEntry.code.ilike(f"{escaped}-%"),
                DocumentEntry.code.ilike(f"{escaped}\\_%"),
            ]
        )
    result = await db.execute(
        select(DocumentEntry)
        .where(
            DocumentEntry.is_deleted.is_(False),
            document_entry_scope(scope),
            or_(*conditions),
        )
        .limit(3)
    )
    matches = []
    for entry in result.scalars().all():
        parsed = split_code(entry.code or "")
        prefix = parsed[0] if parsed else storage._normalize_identity(entry.code or "")
        if prefix == revision.prefix:
            matches.append(entry)
    return matches[0] if len(matches) == 1 else None


def _object_keys(attachments: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for item in attachments:
        keys.update(
            k
            for k in [
                item.get("storage_key"),
                item.get("converted_md_key"),
                *(item.get("asset_keys") or []),
            ]
            if k
        )
    return keys


def _defer_cleanup(db: AsyncSession, old_keys: set[str], new_keys: set[str]) -> None:
    done = False

    def cleanup(session: Session, *, committed: bool) -> None:
        nonlocal done
        if done or session.in_nested_transaction():
            return
        done = True
        for key in old_keys if committed else new_keys:
            try:
                storage._delete_file(key)
            except Exception:
                logger.exception("清理替换附件对象失败: object_key=%s", key)

    event.listen(
        db.sync_session,
        "after_commit",
        lambda session: cleanup(session, committed=True),
    )
    event.listen(
        db.sync_session,
        "after_rollback",
        lambda session: cleanup(session, committed=False),
    )


async def replace_attachment(
    db: AsyncSession,
    entry: DocumentEntry,
    file_name: str,
    content: bytes,
    content_type: str,
    uploaded_by: str = "",
    *,
    revision: AttachmentRevision | None = None,
) -> tuple[dict[str, Any], storage.VersionUpdateInfo]:
    revision = revision or await prepare_revision(file_name, content)
    # 在锁内重新读取，避免两个上传都按旧版本校验后互相覆盖。
    result = await db.execute(
        select(DocumentEntry)
        .where(
            DocumentEntry.id == entry.id,
            DocumentEntry.department_id == entry.department_id,
            DocumentEntry.is_deleted.is_(False),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    locked = result.scalar_one_or_none()
    if locked is None:
        raise AppException(message="文件目录条目不存在", status_code=404)
    entry = locked
    parsed = split_code(entry.code or "")
    prefix = parsed[0] if parsed else storage._normalize_identity(entry.code or "")
    if prefix != revision.prefix:
        raise AppException(
            message="附件正文编号与目录编号不一致，未更新", status_code=409
        )
    if parsed and revision.revision <= parsed[1]:
        raise AppException(
            message="附件版本未高于当前版本，目录和附件均未更新", status_code=409
        )
    old_code = entry.code or ""
    old_date, old_text = entry.effective_date, entry.effective_date_text
    old_attachments = list(entry.attachments or [])
    try:
        # 编号、日期和附件列表在同一数据库事务内写入。
        entry.code = revision.code
        entry.effective_date = revision.effective_date
        entry.effective_date_text = None
        entry.attachments = []
        attachment = await storage.upload_attachment_to_entry(
            db,
            entry,
            file_name,
            content,
            content_type,
            uploaded_by,
            prepared=revision.prepared,
        )
    except Exception:
        entry.code = old_code
        entry.effective_date, entry.effective_date_text = old_date, old_text
        entry.attachments = old_attachments
        raise
    _defer_cleanup(db, _object_keys(old_attachments), _object_keys([attachment]))
    logger.info(
        "document attachment revision replaced",
        extra={
            "entry_id": str(entry.id),
            "old_code": old_code,
            "new_code": entry.code,
            "uploaded_by": uploaded_by,
        },
    )
    return attachment, storage.VersionUpdateInfo(old_code, entry.code)
