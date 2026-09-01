"""Document catalog attachment service: 附件上传/绑定/删除/预览内容。

附件导入匹配策略（三段式）：
1. 编码匹配：文件名中的编码（含修订号，如 SMP-QA-001-02 → SMP-QA-001/02）精确/前缀匹配；
2. 名称模糊匹配：文件名中文核心词与条目名称互含，唯一则命中；
3. LLM 匹配：前两步失败时，调用全局 llm_client 在候选条目中识别最匹配条目。

word 附件转换：.doc/.docx/.wps 转标准 MD（模板化管线，保留表格与图片），
图片存为独立对象并在 attachment 记录 `asset_keys` 中登记。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.core.storage import (
    delete_object,
    get_object,
    upload_object,
)
from app.core.storage import (
    is_enabled as minio_enabled,
)
from app.core.upload_security import safe_upload_filename, sniff_upload_mime
from app.modules.quality.models.document_catalog import (
    DocumentEntry,
)
from app.modules.quality.service.document_catalog_md import (
    ExtractedImage,
    convert_word_attachment,
)

logger = logging.getLogger(__name__)

# 文件名中提取文件编码，如 SMP-QC-001 / SOP-SC(DR)-411-04 / SOP-SC（LN）-401-06
CODE_PATTERN = re.compile(r"([A-Z]{2,3}-[A-Za-z0-9（）()]+-\d{3})")
# 提取编码 + 可选修订号：SOP-SC(FA)-412-03 → ("SOP-SC(FA)-412", "03")
CODE_REV_PATTERN = re.compile(
    r"([A-Z]{2,3}-[A-Za-z0-9（）()]+-\d{3})(?:[-\/](\d{1,3}))?"
)

ALLOWED_EXT = {
    ".md",
    ".doc",
    ".docx",
    ".wps",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
}
WORD_EXT = {".doc", ".docx", ".wps"}
TEXT_MD_MIME = "text/markdown; charset=utf-8"

# 转换后 md 中图片占位引用（document_catalog_docx_md 产物），如 (img_000.png)
_MD_IMAGE_REF_RE = re.compile(r"!\[image\]\((img_\d+\.[A-Za-z0-9]+)\)")
# md 中的图片引用行（供培训出题 AI 的文本输入需剥离）
_MD_ANY_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

ATTACHMENT_MAX_SIZE = 20 * 1024 * 1024  # 20MB


def _local_upload_dir() -> Path:
    upload_dir = Path(get_settings().UPLOAD_DIR) / "quality" / "document_catalog"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _safe_path(storage_key: str) -> str:
    root = _local_upload_dir().resolve()
    path = (root / storage_key).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AppException(message="非法文件路径") from exc
    if path == root:
        raise AppException(message="非法文件路径")
    return str(path)


def _store_file(storage_key: str, content: bytes, content_type: str) -> str:
    if minio_enabled():
        upload_object("quality", storage_key, content, len(content), content_type)
        return storage_key
    path = _safe_path(storage_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as file_obj:
        file_obj.write(content)
    return storage_key


def _read_file(storage_key: str) -> tuple[bytes, str] | None:
    if minio_enabled():
        return get_object("quality", storage_key)
    path = _safe_path(storage_key)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as file_obj:
        return file_obj.read(), "application/octet-stream"


def _delete_file(storage_key: str) -> None:
    if minio_enabled():
        delete_object("quality", storage_key)
        return
    path = _safe_path(storage_key)
    if os.path.exists(path):
        os.remove(path)


def _new_attachment(
    file_name: str,
    storage_key: str,
    content_type: str,
    file_size: int,
    converted: bool,
    converted_md_key: str | None = None,
    uploaded_by: str = "",
    asset_keys: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "file_name": file_name,
        "storage_key": storage_key,
        "converted_md_key": converted_md_key,
        "content_type": content_type,
        "file_size": file_size,
        "converted": converted,
        "uploaded_at": datetime.now(UTC).isoformat(),
        "uploaded_by": uploaded_by or "",
        "asset_keys": list(asset_keys or []),
        # 转换管线标记（历史附件重转脚本据此跳过已处理附件）
        "pipeline": "v2",
    }


def _attachment_asset_url(entry_id: Any, asset_key: str) -> str:
    """图片对象的前端可加载 URL（经 Next 代理注入鉴权）。"""
    return (
        f"/api/v1/quality/document-entries/{entry_id}"
        f"/attachments/{quote(asset_key, safe='/')}/content"
    )


async def upload_attachment_to_entry(
    db: AsyncSession,
    entry: DocumentEntry,
    file_name: str,
    content: bytes,
    content_type: str,
    uploaded_by: str = "",
    prepared: tuple[str, list[ExtractedImage]] | None = None,
) -> dict[str, Any]:
    """上传附件并绑定到条目：word 附件转标准 MD（表格/图片保留），图片/PDF 原样存储。

    prepared 为外部已完成转换的结果（批量导入先转换后匹配时传入，避免重复转换）。
    """
    ext = os.path.splitext(file_name or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise AppException(
            message=f"不支持的文件类型：{ext or '未知'}，仅支持 {sorted(ALLOWED_EXT)}"
        )
    if len(content) > ATTACHMENT_MAX_SIZE:
        raise AppException(message="附件不能超过 20MB")

    safe_file_name = safe_upload_filename(file_name, fallback="attachment.bin")
    safe_name = f"{uuid.uuid4().hex}_{safe_file_name}"
    original_key = f"document-catalog/attachments/{safe_name}"
    stored_keys: list[str] = []
    try:
        _store_file(original_key, content, content_type)
        stored_keys.append(original_key)

        converted_md_key: str | None = None
        asset_keys: list[str] = []
        if ext in WORD_EXT:
            try:
                if prepared is None:
                    # soffice 子进程与 docx 解析为阻塞调用，放入线程避免阻塞事件循环
                    prepared = await asyncio.to_thread(
                        convert_word_attachment, file_name, content
                    )
                md_text, images = prepared
            except Exception:  # noqa: BLE001
                # 转换失败（伪 docx/加密/损坏文件）：降级为原样存储，仍可下载/预览原文件
                logger.warning(
                    "word attachment convert failed, stored as-is",
                    extra={"component": "quality", "file": file_name},
                )
            else:
                name_to_url: dict[str, str] = {}
                for image in images:
                    asset_key = (
                        f"document-catalog/attachments/{uuid.uuid4().hex}_{image.name}"
                    )
                    _store_file(asset_key, image.data, image.content_type)
                    stored_keys.append(asset_key)
                    asset_keys.append(asset_key)
                    name_to_url[image.name] = _attachment_asset_url(entry.id, asset_key)
                md_text = _MD_IMAGE_REF_RE.sub(
                    lambda m: f"![image]({name_to_url[m.group(1)]})", md_text
                )
                md_key = (
                    f"document-catalog/attachments/{uuid.uuid4().hex}_"
                    f"{os.path.splitext(file_name)[0]}.md"
                )
                _store_file(md_key, md_text.encode("utf-8"), TEXT_MD_MIME)
                stored_keys.append(md_key)
                converted_md_key = md_key
        elif ext == ".md":
            # 已是标准 MD（如公司文件库已转换产物），原样存储，预览直接读取自身
            converted_md_key = original_key

        attachment = _new_attachment(
            file_name=file_name,
            storage_key=original_key,
            content_type=content_type,
            file_size=len(content),
            converted=converted_md_key is not None,
            converted_md_key=converted_md_key,
            uploaded_by=uploaded_by,
            asset_keys=asset_keys,
        )
        attachments = list(entry.attachments or [])
        attachments.append(attachment)
        entry.attachments = attachments
        await db.flush()
    except Exception:
        for stored_key in reversed(stored_keys):
            try:
                _delete_file(stored_key)
            except Exception:  # noqa: BLE001
                logger.exception("清理质量附件对象失败: object_key=%s", stored_key)
        raise
    logger.info(
        "document entry attachment uploaded",
        extra={"component": "quality", "entry_id": str(entry.id), "file": file_name},
    )
    return attachment


def extract_code_and_rev(file_name: str) -> tuple[str, str | None] | None:
    """从文件名提取 (编码前缀, 修订号)；无编码返回 None。"""
    match = CODE_REV_PATTERN.search(file_name or "")
    if not match:
        return None
    return match.group(1), match.group(2)


@dataclass(slots=True)
class VersionUpdateInfo:
    """附件导入触发的条目文件编码版本升级信息。"""

    old_code: str
    new_code: str


# 条目编码修订号：`SOP-QC-001/08` 的 /08，或结尾 `-08`/`_08` 变体；结尾 3 位
# 数字（如 SOP-QC-001 的 001）属于文件编号本身，不视为修订号。
_ENTRY_CODE_REV_RE = re.compile(
    r"^(?P<prefix>.+?)(?:/(?P<slash_rev>\d{1,3})|[-_](?P<sep_rev>\d{1,2}))$"
)


def _parse_entry_code_revision(code: str | None) -> tuple[int, str] | None:
    """解析条目编码修订号，返回 (数值, 原始文本)；无修订号返回 None。"""
    if not code:
        return None
    match = _ENTRY_CODE_REV_RE.match(code.strip())
    if not match:
        return None
    rev_text = match.group("slash_rev") or match.group("sep_rev")
    return int(rev_text), rev_text


def sync_entry_version(
    entry: DocumentEntry,
    file_name: str,
    rev_source: str | None = None,
) -> VersionUpdateInfo | None:
    """版本号高于条目编码修订号时，升级条目文件编码。

    版本号即编码 `/` 后的数据（如 SOP-QC-001/08 的 08）。按正文匹配绑定时
    以正文编号（rev_source）为版本来源，文件名编号不可信。文件名/正文无
    修订号、或修订号相等/更低时不更新；升级保留条目编码原前缀与补零宽度。
    """
    parsed = extract_code_and_rev(rev_source or file_name)
    if parsed is None or parsed[1] is None:
        return None
    file_rev = int(parsed[1])

    entry_code = (entry.code or "").strip()
    if not entry_code:
        return None
    existing = _parse_entry_code_revision(entry_code)
    if existing is not None and file_rev <= existing[0]:
        return None

    if existing is not None:
        prefix = entry_code[: len(entry_code) - len(existing[1])].rstrip("/-_")
        new_rev = str(file_rev).zfill(max(len(existing[1]), 2))
    else:
        prefix = entry_code
        new_rev = str(file_rev).zfill(2)
    new_code = f"{prefix}/{new_rev}"

    info = VersionUpdateInfo(old_code=entry_code, new_code=new_code)
    entry.code = new_code
    logger.info(
        "document entry code version upgraded",
        extra={
            "component": "quality",
            "entry_id": str(entry.id),
            "old_code": entry_code,
            "new_code": new_code,
            "file": file_name,
        },
    )
    return info


CJK_SEQ_RE = re.compile(r"[\u4e00-\u9fff]{4,}")


def extract_cjk_core(file_name: str) -> str:
    """提取文件名中最长的中文片段（>=4 字），用于按名称匹配条目。"""
    seqs: list[str] = CJK_SEQ_RE.findall(file_name or "")
    if not seqs:
        return ""
    return max(seqs, key=len)


async def find_entry_by_file_name(
    db: AsyncSession, file_name: str
) -> DocumentEntry | None:
    """按文件名中的文件编码自动匹配唯一条目（修订号优先），无法唯一匹配返回 None。"""
    parsed = extract_code_and_rev(file_name)
    if not parsed:
        return None
    prefix, rev = parsed
    # 括号全角/半角双向归一化（库中存在两种写法，如 SOP-QC(YS)-… 与 SOP-QC（YS）-…）
    prefix_half = prefix.replace("（", "(").replace("）", ")")
    prefix_full = prefix.replace("(", "（").replace(")", "）")
    prefixes = {prefix, prefix_half, prefix_full}

    # 1) 修订号精确匹配（数据库 code 形如 SOP-QC-001/08）
    if rev:
        rev_codes: set[str] = set()
        for p in prefixes:
            rev_codes.add(f"{p}/{rev}")
            rev_codes.add(f"{p}-{rev}")
            rev_codes.add(f"{p}_{rev}")
        exact_result = await db.execute(
            select(DocumentEntry).where(
                DocumentEntry.is_deleted.is_(False),
                DocumentEntry.code.in_(rev_codes),
            )
        )
        exact_matches = exact_result.scalars().all()
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            if len({m.code for m in exact_matches}) == 1:
                # 同编码重复行：绑定到附件最少的一条
                return min(exact_matches, key=lambda m: len(m.attachments or []))
            return None

    # 2) 前缀模糊匹配
    conditions = [DocumentEntry.code.ilike(f"{p}%") for p in prefixes]
    result = await db.execute(
        select(DocumentEntry).where(
            DocumentEntry.is_deleted.is_(False),
            or_(*conditions),
        )
    )
    matches = result.scalars().all()
    if len(matches) == 1:
        return matches[0]
    if rev and len(matches) > 1:
        # 多匹配时优先取修订号一致的一条
        rev_filtered = [
            m
            for m in matches
            if (m.code or "").rstrip().endswith(f"/{rev}")
            or (m.code or "").rstrip().endswith(f"-{rev}")
        ]
        if len(rev_filtered) == 1:
            return rev_filtered[0]
    if len(matches) > 1:
        # 文件名中文核心词匹配条目名称（区分多版本/跨部门歧义）
        cjk_core = extract_cjk_core(file_name)
        if cjk_core:
            name_filtered = [m for m in matches if cjk_core in (m.name or "")]
            if len(name_filtered) == 1:
                return name_filtered[0]
    if len(matches) > 1 and len({m.code for m in matches}) == 1:
        # 同编码重复行：绑定到附件最少的一条
        return min(matches, key=lambda m: len(m.attachments or []))
    if rev and len(matches) > 1:
        # 文件名版本高于全部候选（多版本并存）：绑定最新版本条目，
        # 由 sync_entry_version 完成编码升级；存在更高版本候选时不猜
        lower_than_file = [
            _parse_entry_code_revision(m.code) or (0, "") for m in matches
        ]
        if all(parsed_rev[0] < int(rev) for parsed_rev in lower_than_file):
            return matches[lower_than_file.index(max(lower_than_file))]
    return None


def _normalize_identity(value: str) -> str:
    """名称/编号归一化：去空白、全角括号转半角、小写。"""
    return (
        re.sub(r"\s+", "", value).replace("（", "(").replace("）", ")").lower()
    )


CONTENT_CODE_RE = re.compile(r"\*\*文件编号\*\*[:：]\s*(\S+)")
CONTENT_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def extract_content_identity(md_text: str) -> tuple[str | None, str | None]:
    """从转换后 md 头部提取正文身份：(文件编号, 标题)。"""
    head = md_text[:2000]
    code = CONTENT_CODE_RE.search(head)
    title = CONTENT_TITLE_RE.search(head)
    return (
        code.group(1) if code else None,
        title.group(1).strip() if title else None,
    )


async def match_entry_by_content(
    db: AsyncSession, content_code: str | None, content_title: str | None
) -> DocumentEntry | None:
    """正文匹配：优先正文文件编号（主干一致，全串一致优先），其次正文标题
    与条目名称归一化后完全一致。"""
    if content_code:
        # 去掉全部分隔符后比对，兼容 - 与 / 两种修订分隔写法
        nc = re.sub(r"[\s/\-]+", "", content_code).upper()
        head = _escape_like(nc[:8])
        result = await db.execute(
            select(DocumentEntry).where(
                DocumentEntry.is_deleted.is_(False),
                DocumentEntry.code.ilike(f"{head}%"),
            )
        )
        normed = [
            (e, re.sub(r"[\s/\-]+", "", e.code or "").upper())
            for e in result.scalars().all()
        ]
        full = [e for e, c in normed if c == nc]
        if len(full) == 1:
            return full[0]
        related = [
            e for e, c in normed if c and (c.startswith(nc) or nc.startswith(c))
        ]
        if len(related) == 1:
            return related[0]
    if content_title:
        nt = _normalize_identity(content_title)
        result = await db.execute(
            select(DocumentEntry).where(
                DocumentEntry.is_deleted.is_(False),
                DocumentEntry.name.ilike(f"%{_escape_like(content_title)}%"),
            )
        )
        exact = [
            e
            for e in result.scalars().all()
            if _normalize_identity(e.name or "") == nt
        ]
        if len(exact) == 1:
            return exact[0]
    return None


async def match_entry_by_name(db: AsyncSession, file_name: str) -> DocumentEntry | None:
    """名称匹配：文件名中文核心词与条目名称归一化后完全一致，唯一则命中；
    多条同名时绑定附件最少的一条。"""
    core = extract_cjk_core(file_name)
    if not core:
        return None
    result = await db.execute(
        select(DocumentEntry).where(
            DocumentEntry.is_deleted.is_(False),
            DocumentEntry.name.ilike(f"%{_escape_like(core)}%"),
        )
    )
    matches = [
        m
        for m in result.scalars().all()
        if _normalize_identity(m.name or "") == _normalize_identity(core)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return min(matches, key=lambda m: len(m.attachments or []))
    return None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _llm_candidates(db: AsyncSession, file_name: str) -> list[DocumentEntry]:
    """构造 LLM 候选集：编码前缀同部门条目，否则名称相近条目（限量）。"""
    parsed = extract_code_and_rev(file_name)
    if parsed:
        prefix = parsed[0].split("-")
        dept_prefix = "-".join(prefix[:2]) if len(prefix) >= 2 else parsed[0]
        result = await db.execute(
            select(DocumentEntry).where(
                DocumentEntry.is_deleted.is_(False),
                DocumentEntry.code.ilike(f"{dept_prefix}%"),
            )
        )
        candidates = list(result.scalars().all())
        if candidates:
            return candidates[:60]
    core = extract_cjk_core(file_name)
    if core:
        result = await db.execute(
            select(DocumentEntry).where(
                DocumentEntry.is_deleted.is_(False),
                DocumentEntry.name.ilike(f"%{_escape_like(core[:6])}%"),
            )
        )
        return list(result.scalars().all())[:60]
    return []


async def llm_match_entry(db: AsyncSession, file_name: str) -> DocumentEntry | None:
    """LLM 识别匹配：在候选条目中选出与附件文件名最匹配的文件条目。"""
    candidates = await _llm_candidates(db, file_name)
    if not candidates:
        return None
    candidate_text = "\n".join(
        f"{i + 1}. 编码={c.code or '无'} 名称={c.name}"
        for i, c in enumerate(candidates)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是企业文件管理助手。给定一个附件文件名和候选文件条目列表，"
                "选出该附件最可能对应的条目。附件文件名中的编号可能用 - 代"
                "替 / 表示版本。"
                "只输出 JSON，包含 index（候选序号，无匹配时为 0）。"
            ),
        },
        {
            "role": "user",
            "content": f"附件文件名：{file_name}\n候选条目：\n{candidate_text}",
        },
    ]
    try:
        parsed = await llm_client.chat_json(messages, expected_keys=["index"])
    except (
        LLMConfigError,
        LLMOutputError,
        LLMProviderError,
        LLMRateLimitError,
    ) as exc:
        logger.warning(
            "llm attachment match failed",
            extra={"component": "quality", "file": file_name, "error": str(exc)},
        )
        return None
    try:
        index = int(parsed.get("index", 0))
    except (TypeError, ValueError):
        return None
    if 1 <= index <= len(candidates):
        return candidates[index - 1]
    return None


async def match_entry_for_attachment(
    db: AsyncSession,
    file_name: str,
    content_identity: tuple[str | None, str | None] | None = None,
) -> tuple[DocumentEntry | None, str]:
    """四段式匹配：文件名称 → 文件编号 → 正文内容 → LLM 兜底。

    content_identity 为转换后 md 提取的 (正文文件编号, 正文标题)，
    仅在名称与编号均未命中时参与正文匹配。
    """
    entry = await match_entry_by_name(db, file_name)
    if entry is not None:
        return entry, "name"
    entry = await find_entry_by_file_name(db, file_name)
    if entry is not None:
        return entry, "code"
    if content_identity is not None:
        entry = await match_entry_by_content(db, *content_identity)
        if entry is not None:
            return entry, "content"
    entry = await llm_match_entry(db, file_name)
    if entry is not None:
        return entry, "llm"
    return None, "none"


async def delete_attachment_from_entry(
    db: AsyncSession, entry: DocumentEntry, storage_key: str
) -> bool:
    """从条目附件中删除指定附件（按 storage_key），同时删除已存储文件。"""
    attachments = list(entry.attachments or [])
    target = next(
        (
            attachment
            for attachment in attachments
            if attachment.get("storage_key") == storage_key
        ),
        None,
    )
    if target is None:
        return False

    keys = [target.get("storage_key") or ""]
    converted_key = target.get("converted_md_key")
    if converted_key and converted_key not in keys:
        keys.append(converted_key)
    for asset_key in target.get("asset_keys") or []:
        if asset_key and asset_key not in keys:
            keys.append(asset_key)
    backups: dict[str, tuple[bytes, str]] = {}
    deleted_keys: list[str] = []
    try:
        for key in keys:
            if not key:
                continue
            backup = _read_file(key)
            if backup is not None:
                backups[key] = backup
            _delete_file(key)
            deleted_keys.append(key)
        entry.attachments = [
            attachment
            for attachment in attachments
            if attachment.get("storage_key") != storage_key
        ]
        await db.flush()
    except Exception:
        entry.attachments = attachments
        for key in deleted_keys:
            backup = backups.get(key)
            if backup is None:
                continue
            try:
                data, content_type = backup
                _store_file(key, data, content_type)
            except Exception:  # noqa: BLE001
                logger.exception("恢复质量附件对象失败: object_key=%s", key)
        raise AppException(message="附件删除失败，已回滚可恢复的变更", status_code=502)
    logger.info(
        "document entry attachment deleted",
        extra={"component": "quality", "entry_id": str(entry.id), "key": storage_key},
    )
    return True


def read_attachment_preview(
    entry: DocumentEntry, storage_key: str
) -> tuple[bytes, str]:
    """读取附件预览内容：word 返回转换后标准 MD；图片/PDF 返回原文件；
    word 转换提取的图片对象（asset_keys）返回图片本身。"""
    for attachment in entry.attachments or []:
        if attachment.get("storage_key") == storage_key:
            if attachment.get("converted_md_key"):
                stored = _read_file(attachment["converted_md_key"])
                if stored is not None:
                    data, _ = stored
                    return data, TEXT_MD_MIME
            stored = _read_file(storage_key)
            if stored is not None:
                data, _ = stored
                return (
                    data,
                    attachment.get("content_type") or "application/octet-stream",
                )
            break
        if storage_key in (attachment.get("asset_keys") or []):
            stored = _read_file(storage_key)
            if stored is None:
                break
            data, content_type = stored
            if content_type == "application/octet-stream":
                content_type = sniff_upload_mime(storage_key, data)
            return data, content_type
    return b"", "application/octet-stream"


def read_entry_md_contents(entry: DocumentEntry) -> list[dict[str, Any]]:
    """读取条目全部附件中可用的标准 MD 文本内容。

    word 附件读转换产物 converted_md_key，.md 附件读自身；图片/PDF 无转换产物则跳过。
    返回 [{"file_name": str, "md_text": str}]，供培训口试 AI 出题做材料输入。
    """
    contents: list[dict[str, Any]] = []
    for attachment in entry.attachments or []:
        md_key = attachment.get("converted_md_key")
        if not md_key:
            continue
        stored = _read_file(md_key)
        if stored is None:
            continue
        data, _ = stored
        try:
            md_text = data.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(
                "attachment md decode failed",
                extra={
                    "component": "quality",
                    "entry_id": str(entry.id),
                    "key": md_key,
                },
            )
            continue
        # 图片引用对 AI 出题是噪音，剥离后再作为材料输入
        md_text = re.sub(r"\n{3,}", "\n\n", _MD_ANY_IMAGE_RE.sub("", md_text))
        contents.append(
            {"file_name": attachment.get("file_name") or "", "md_text": md_text}
        )
    return contents
