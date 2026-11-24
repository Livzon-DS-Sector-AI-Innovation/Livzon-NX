"""公告通知台账：AI 识别元数据、原文存档与 CRUD。

按 LLM 调用边界走「业务模块 Service → app.core.llm.llm_client」：
- PDF/DOCX 先经平台层 ``DocumentParser`` 提取文本（含扫描件 OCR 回退），
  旧版二进制 ``.doc`` 经 LibreOffice 转 PDF 后提取，再 ``chat_json`` 结构化；
- 图片公告走 ``chat_vision_json``（data URI）；
- 识别结果经校验清洗后仅作建议值/内容来源，元数据以人工确认的表单为准，
  LLM 输出不替代人工确认（平台 AI 治理约定）。

可见性口径：台账元数据对有页面权限者可见；``content`` 与原文存档仅经
operate 绑定的专用端点下发；``search_text`` 只拼元数据，不含公告内容。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.llm import llm_client
from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.administration.models import AdministrationNotice
from app.modules.administration.repository import AdministrationRepository
from app.modules.administration.schemas import (
    NoticeContentResponse,
    NoticeItem,
    NoticeListResponse,
    NoticeParsePreview,
    NoticeParseSuggestion,
    NoticeUpdateInput,
)
from app.platform.audit.service import record_audit_log

logger = logging.getLogger("dazah.administration.notice")

NOTICE_ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}
NOTICE_MAX_BYTES = 30 * 1024 * 1024

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
_TEXT_EXTS = {".pdf", ".docx", ".doc"}
_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

#: AI 识别输出的公告内容上限；编辑接口允许人工补录更长内容。
_NOTICE_CONTENT_MAX_CHARS = 8000
_EXTRACT_TEXT_MAX_CHARS = 20000

_EXPECTED_KEYS = [
    "notice_no",
    "title",
    "publisher",
    "published_at",
    "category",
    "content",
    "remark",
]

_PROMPT_TEMPLATE = """你是一名工厂行政管理专员。请从下面的公告文件内容中\
提取公告台账信息，严格输出 JSON 对象（不要输出其他文字），字段如下：

- notice_no: 公告编号（如 "2026-第03号"、"厂字〔2026〕12号"；没有则为 null）
- title: 公告标题/事由（简明概括；没有则为 null）
- publisher: 发布单位/发文部门（没有则为 null）
- published_at: 发布日期，格式 YYYY-MM-DD（没有或无法判断则为 null）
- category: 公告类别，用单个简短词概括（如 行政通知、人事公告、安全公告、\
采购公告、其他；没有则为 null）
- content: 公告正文内容，压缩为连贯的简明中文（{content_limit} 字内；\
没有则为 null）
- remark: 其他对台账有价值的补充（如附件说明、抄送范围，200 字内；没有则为 null）

公告内容：
{content}"""


class NoticeParseError(AppException):
    """公告内容识别失败（携带用户可见的安全文案与状态码）。"""


def _clean_optional_str(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.lower() == "null":
        return None
    return text[:max_length]


def _clean_notice_no(value: Any) -> str | None:
    return _clean_optional_str(value, 100)


def _clean_published_at(value: Any) -> str | None:
    text = _clean_optional_str(value, 20)
    if text is None:
        return None
    normalized = (
        text.replace("/", "-")
        .replace(".", "-")
        .replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .strip("-")
        .strip()
    )
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError:
        # 非零填充写法（如 2026-3-5）逐段解析
        parts = normalized.split("-")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            try:
                return date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
            except ValueError:
                return None
        return None


def _build_suggestion(raw: dict[str, Any]) -> NoticeParseSuggestion:
    return NoticeParseSuggestion(
        notice_no=_clean_notice_no(raw.get("notice_no")),
        title=_clean_optional_str(raw.get("title"), 255),
        publisher=_clean_optional_str(raw.get("publisher"), 255),
        published_at=_clean_published_at(raw.get("published_at")),
        category=_clean_optional_str(raw.get("category"), 50),
        remark=_clean_optional_str(raw.get("remark"), 2000),
    )


def _build_prompt(content_text: str) -> str:
    return _PROMPT_TEMPLATE.format(
        content_limit=_NOTICE_CONTENT_MAX_CHARS, content=content_text
    )


def _extract_text_via_doc_conversion(content: bytes, file_name: str) -> str:
    """旧版二进制 .doc（OLE2 复合文档）→ LibreOffice 转 PDF → 文本提取。

    平台 DocumentParser 只认 docx（zip）容器；真实 .doc 由 soffice 转换后
    再走既有 PDF 提取管线（含扫描件 OCR 回退）。转换失败返回空字符串。
    """
    from app.platform.storage.preview import convert_office_to_pdf

    pdf_bytes = convert_office_to_pdf(content, file_name)
    if not pdf_bytes:
        logger.warning("公告 .doc 转 PDF 失败: file=%s", file_name)
        return ""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = tmp.name
    try:
        return _extract_text_from_path(pdf_path)
    finally:
        try:
            os.unlink(pdf_path)
        except OSError:
            pass


def _extract_text_from_path(path: str) -> str:
    from app.platform.integrations.ai.document_parser import DocumentParser

    try:
        return DocumentParser.extract_text(path, max_chars=_EXTRACT_TEXT_MAX_CHARS)
    except Exception:
        # 解析器对损坏/旧格式文档抛出的异常类型不一，统一按"无文本"处理
        logger.warning("公告文本提取失败: path=%s", path, exc_info=True)
        return ""


def _extract_text_content(file_name: str, content: bytes) -> str:
    """PDF/DOCX/DOC → 纯文本；不支持的格式抛 NoticeParseError(422)。"""
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in _TEXT_EXTS:
        raise NoticeParseError(
            message=f"「{file_name}」格式暂不支持内容识别，请上传 PDF/Word/图片",
            status_code=422,
        )
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        text = _extract_text_from_path(tmp_path)
        if not text.strip() and ext == ".doc":
            text = _extract_text_via_doc_conversion(content, file_name)
        return text.strip()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def extract_notice_suggestion(
    *, file_name: str, content: bytes
) -> tuple[NoticeParseSuggestion | None, str | None]:
    """识别公告文件，返回（建议值, 未识别原因）。

    识别失败只返回原因，不影响上传链路；公告内容不在建议值中返回。
    """
    ext = os.path.splitext(file_name)[1].lower()
    try:
        if ext in _IMAGE_EXTS:
            data_uri = (
                f"data:{_IMAGE_MIME[ext]};base64,"
                f"{base64.b64encode(content).decode('ascii')}"
            )
            raw = await llm_client.chat_vision_json(
                _build_prompt("（见图片，公告扫描件）"),
                [data_uri],
                expected_keys=_EXPECTED_KEYS,
            )
        else:
            content_text = _extract_text_content(file_name, content)
            if not content_text:
                return None, "未能从附件中提取到文本内容，请手动填写后导入"
            raw = await llm_client.chat_json(
                [{"role": "user", "content": _build_prompt(content_text)}],
                expected_keys=_EXPECTED_KEYS,
            )
    except LLMConfigError:
        return None, "平台未配置 AI 模型，无法自动识别，请手动填写后导入"
    except LLMRateLimitError:
        return None, "AI 模型限流，请稍后重试识别"
    except LLMOutputError:
        return None, "AI 识别结果格式无效，请重试或手动填写"
    except LLMProviderError:
        return None, "AI 模型服务暂不可用，请稍后重试识别"
    except NoticeParseError as exc:
        return None, exc.message

    suggestion = _build_suggestion(raw)
    return suggestion, None


async def extract_notice_content(*, file_name: str, content: bytes) -> str:
    """识别公告正文（导入落库时使用；失败抛 NoticeParseError）。"""
    ext = os.path.splitext(file_name)[1].lower()
    try:
        if ext in _IMAGE_EXTS:
            data_uri = (
                f"data:{_IMAGE_MIME[ext]};base64,"
                f"{base64.b64encode(content).decode('ascii')}"
            )
            raw = await llm_client.chat_vision_json(
                _build_prompt("（见图片，公告扫描件）"),
                [data_uri],
                expected_keys=_EXPECTED_KEYS,
            )
        else:
            content_text = _extract_text_content(file_name, content)
            if not content_text:
                raise NoticeParseError(
                    message="未能从附件中提取到公告内容，请确认文件可读后重试",
                    status_code=422,
                )
            raw = await llm_client.chat_json(
                [{"role": "user", "content": _build_prompt(content_text)}],
                expected_keys=_EXPECTED_KEYS,
            )
    except LLMConfigError as exc:
        raise NoticeParseError(
            message="平台未配置 AI 模型，无法自动识别公告内容", status_code=502
        ) from exc
    except LLMRateLimitError as exc:
        raise NoticeParseError(
            message="AI 模型限流，请稍后重试导入", status_code=502
        ) from exc
    except LLMOutputError as exc:
        raise NoticeParseError(
            message="AI 识别结果格式无效，请重试", status_code=502
        ) from exc
    except LLMProviderError as exc:
        raise NoticeParseError(
            message="AI 模型服务暂不可用，请稍后重试导入", status_code=502
        ) from exc

    notice_content = _clean_optional_str(raw.get("content"), _NOTICE_CONTENT_MAX_CHARS)
    return notice_content or ""


# ── 原文存档：MinIO 优先、本地 uploads/administration/notices 回退 ──


def _notice_local_root() -> Path:
    root = (Path(get_settings().UPLOAD_DIR) / "administration" / "notices").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _notice_local_path(storage_key: str) -> Path:
    """把存储 key 解析为本地路径，拒绝越出存档目录。"""
    root = _notice_local_root()
    path = (root / storage_key.replace("\\", "/")).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AppException(message="非法文件路径", status_code=422) from exc
    return path


def build_notice_storage_key(file_ext: str) -> str:
    return f"{uuid.uuid4().hex}{file_ext}"


def store_notice_object(storage_key: str, content: bytes, content_type: str) -> str:
    if storage.is_enabled():
        storage.upload_object(
            "administration", storage_key, content, len(content), content_type
        )
        return storage_key
    path = _notice_local_path(storage_key)
    path.write_bytes(content)
    return storage_key


def read_notice_object(storage_key: str) -> tuple[bytes, str | None] | None:
    """返回（字节, MIME 或 None）；本地回退无法可靠判定类型时交调用方回退。"""
    if not storage_key:
        return None
    if storage.is_enabled():
        found = storage.get_object("administration", storage_key)
        if found is not None:
            return found
    path = _notice_local_path(storage_key)
    if not path.exists():
        return None
    return path.read_bytes(), None


def _build_search_text(
    notice_no: str, title: str, publisher: str, category: str, remark: str
) -> str:
    """元数据搜索文本；刻意不含公告内容，避免关键字搜索泄露内容线索。"""
    return " ".join(
        part for part in (notice_no, title, publisher, category, remark) if part
    )


def _parse_published_at(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise AppException(
            message="发布日期格式应为 YYYY-MM-DD", status_code=422
        ) from exc


def _to_notice_item(notice: AdministrationNotice) -> NoticeItem:
    return NoticeItem(
        id=notice.id,
        notice_no=notice.notice_no,
        title=notice.title,
        publisher=notice.publisher,
        published_at=(notice.published_at.isoformat() if notice.published_at else None),
        category=notice.category,
        remark=notice.remark,
        source_file_name=notice.source_file_name,
        source_size_bytes=notice.source_size_bytes,
        created_at=notice.created_at,
        updated_at=notice.updated_at,
    )


class NoticeService:
    """公告台账服务：解析预览、确认导入、台账查询与内容/原文读取。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AdministrationRepository(db)

    @staticmethod
    def to_notice_item(notice: AdministrationNotice) -> NoticeItem:
        return _to_notice_item(notice)

    async def _audit(
        self,
        action: str,
        notice_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        try:
            await record_audit_log(
                self.db,
                action=action,
                user_id=user_id,
                resource_type="administration_notice",
                resource_id=notice_id,
                extra=extra,
            )
        except Exception:  # noqa: BLE001 - 审计失败不阻断业务
            logger.exception("审计日志记录失败 (administration_notice:%s)", action)

    async def parse_preview(self, file_name: str, content: bytes) -> NoticeParsePreview:
        suggestion, error = await extract_notice_suggestion(
            file_name=file_name, content=content
        )
        if suggestion is None:
            raise NoticeParseError(message=error or "AI 识别失败", status_code=502)
        return NoticeParsePreview(file_name=file_name, suggestion=suggestion)

    async def import_notice(
        self,
        *,
        file_name: str,
        content: bytes,
        content_type: str,
        notice_no: str,
        title: str,
        publisher: str,
        published_at: str | None,
        category: str,
        remark: str,
        user_id: uuid.UUID | None,
    ) -> AdministrationNotice:
        """确认导入：AI 提取正文 → 原文存档 → 台账落库。调用方负责提交。

        元数据以人工确认的表单字段为准；公告内容由 AI 从原文提取，
        提取失败时整体报错（操作者可重试或手工补录后再导入）。
        """
        notice_content = await extract_notice_content(
            file_name=file_name, content=content
        )
        published = _parse_published_at(published_at)
        file_ext = os.path.splitext(file_name)[1].lower()
        storage_key = build_notice_storage_key(file_ext)
        await asyncio.to_thread(store_notice_object, storage_key, content, content_type)
        notice = AdministrationNotice(
            notice_no=notice_no.strip(),
            title=title.strip(),
            publisher=publisher.strip(),
            published_at=published,
            category=category.strip(),
            content=notice_content,
            remark=remark.strip() or None,
            source_file_name=file_name,
            source_storage_key=storage_key,
            source_content_type=content_type,
            source_size_bytes=len(content),
            search_text=_build_search_text(
                notice_no, title, publisher, category, remark
            ),
            created_by=user_id,
            updated_by=user_id,
        )
        self.repo.add_notice(notice)
        await self.db.flush()
        await self._audit(
            "import",
            notice_id=notice.id,
            user_id=user_id,
            extra={"notice_no": notice.notice_no, "title": notice.title},
        )
        return notice

    async def list_notices(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        category: str | None = None,
    ) -> NoticeListResponse:
        result = await self.repo.list_notices(
            page=page, page_size=page_size, keyword=keyword, category=category
        )
        categories = await self.repo.list_notice_categories()
        return NoticeListResponse(
            items=[_to_notice_item(item) for item in result.items],
            total=result.total,
            page=page,
            page_size=page_size,
            categories=categories,
        )

    async def _get_active_notice(self, notice_id: uuid.UUID) -> AdministrationNotice:
        notice = await self.repo.get_notice(notice_id)
        if notice is None:
            raise AppException(message="公告不存在或已删除", status_code=404)
        return notice

    async def get_notice_item(self, notice_id: uuid.UUID) -> NoticeItem:
        return _to_notice_item(await self._get_active_notice(notice_id))

    async def get_notice_content(self, notice_id: uuid.UUID) -> NoticeContentResponse:
        notice = await self._get_active_notice(notice_id)
        return NoticeContentResponse(
            id=notice.id,
            notice_no=notice.notice_no,
            title=notice.title,
            content=notice.content,
        )

    async def read_notice_file(self, notice_id: uuid.UUID) -> tuple[bytes, str, str]:
        """返回（原文字节, MIME, 文件名）；存档缺失按 404 处理。"""
        notice = await self._get_active_notice(notice_id)
        stored = await asyncio.to_thread(read_notice_object, notice.source_storage_key)
        if stored is None:
            raise AppException(message="公告原文存档缺失", status_code=404)
        data, content_type = stored
        return (
            data,
            content_type or notice.source_content_type or "application/octet-stream",
            notice.source_file_name,
        )

    async def update_notice(
        self,
        notice_id: uuid.UUID,
        payload: NoticeUpdateInput,
        user_id: uuid.UUID | None,
    ) -> NoticeItem:
        notice = await self._get_active_notice(notice_id)
        published = _parse_published_at(payload.published_at)
        notice.notice_no = payload.notice_no.strip()
        notice.title = payload.title.strip()
        notice.publisher = payload.publisher.strip()
        notice.published_at = published
        notice.category = payload.category.strip()
        notice.remark = payload.remark.strip() or None
        notice.content = payload.content
        notice.search_text = _build_search_text(
            notice.notice_no,
            notice.title,
            notice.publisher,
            notice.category,
            notice.remark or "",
        )
        notice.updated_by = user_id
        await self.db.flush()
        # updated_at 带 onupdate=func.now()，flush 后该列已过期；async 下
        # 必须显式刷新，禁止响应序列化触发隐式懒加载（MissingGreenlet）
        await self.db.refresh(notice)
        await self._audit("update", notice_id=notice.id, user_id=user_id)
        return _to_notice_item(notice)

    async def delete_notice(
        self, notice_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> None:
        """软删除台账记录；原文存档保留（数据可追溯，不做物理清理）。"""
        notice = await self._get_active_notice(notice_id)
        notice.is_deleted = True
        notice.updated_by = user_id
        await self.db.flush()
        await self._audit(
            "delete",
            notice_id=notice.id,
            user_id=user_id,
            extra={"notice_no": notice.notice_no},
        )
