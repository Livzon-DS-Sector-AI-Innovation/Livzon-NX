"""偏差工作台 service：独立调查报告生成 + 记录台账检索 + 提示词设置。

每次生成落库为一条可检索的工作台记录（deviation_workbench_reports），
保留来源、附件、检索到的参考内容（context_snapshot）与完整调查报告。
知识来源：偏差管理报告记录 / 手动输入 + 附件 MD；历史偏差（historical_deviations）；
文件管理（document_catalog）；网络知识 = 模型自带知识（不新增联网能力）。
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
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
from app.modules.quality.models import (
    DeviationWorkbenchReport,
    DeviationWorkbenchSettings,
    HistoricalDeviation,
)
from app.modules.quality.models.deviation_workbench import WORKBENCH_SETTINGS_ID
from app.modules.quality.schemas.deviation_workbench import (
    CreateDeviationWorkbenchRequest,
    DeviationWorkbenchAttachmentIn,
    DeviationWorkbenchAttachmentOut,
    DeviationWorkbenchReportDetail,
    DeviationWorkbenchReportListItem,
    DeviationWorkbenchSettingsOut,
    UpdateDeviationWorkbenchSettingsRequest,
)
from app.modules.quality.service.document_catalog_attachment import (
    read_entry_md_contents,
)
from app.modules.quality.service.document_catalog_crud import list_document_entries
from app.modules.quality.service.quality_attachment import (
    MD_IMAGE_REF_RE,
    attachment_storage_keys,
    delete_file,
    generate_code,
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
AI_CONTEXT_TEXT_LIMIT = 120000
RETRIEVAL_LIMIT = 5

# 本地文件存储子目录（配合 quality_attachment 共享 helper 使用）
_STORAGE_SUBDIR = "deviation_workbench"

WORKBENCH_REPORT_KEYS = [
    "deviation_summary",
    "analysis",
    "direct_cause",
    "root_cause",
    "conclusion",
    "recommendations",
    "referenced_sources",
]

_5M1E_DIMS = ["人", "机", "料", "法", "环", "测"]

DEFAULT_REPORT_SYSTEM_PROMPT = """\
你是原料药工厂质量管理调查专家。请基于提供的偏差信息（来源报告记录 / 用户输入 /
附件内容）以及检索到的参考内容（历史偏差、文件管理制度、人员培训记录），结合你
掌握的通用行业知识，从"人、机、料、法、环、测"（5M1E）六个维度展开调查分析，
得出偏差的直接原因与根本原因，并生成完整调查报告。

约束：
- 只能基于提供的信息与你的行业知识分析，不得虚构不存在的证据；
- "人"维度分析须结合检索到的培训台账记录，评估人员培训与资质是否到位；
- 直接原因关注直接触发偏差的环节，根本原因关注深层/系统性因素；
- 引用历史偏差、体系文件或培训记录时注明来源（编号或名称）；
- 对不确定的信息明确标注"待核实"。

请严格输出 JSON，字段必须完整：
{
  "deviation_summary": "偏差概述（一句话）",
  "analysis": {
    "人": "人员/培训/操作因素分析",
    "机": "设备/仪器/维保因素分析",
    "料": "物料/原辅料因素分析",
    "法": "方法/工艺/SOP因素分析",
    "环": "环境/温湿度/洁净度因素分析",
    "测": "检验/测量/数据因素分析"
  },
  "direct_cause": "直接原因",
  "root_cause": "根本原因",
  "conclusion": "调查结论",
  "recommendations": ["纠正预防建议1", "纠正预防建议2"],
  "referenced_sources": [
    "参考来源描述1（如：历史偏差 HD-xxx / 文件 SOP-xxx / 培训记录 / 模型通用知识）"
  ]
}"""


def _attachment_content_url(storage_key: str) -> str:
    return (
        f"/api/v1/quality/deviation-workbench/attachments/"
        f"{quote(storage_key, safe='/')}/content"
    )


def _truncate(value: str | None, limit: int = 800) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


# ─── 设置 ────────────────────────────────────────────────────────────


async def _get_or_create_settings(db: AsyncSession) -> DeviationWorkbenchSettings:
    result = await db.execute(
        select(DeviationWorkbenchSettings).where(
            DeviationWorkbenchSettings.id == uuid.UUID(WORKBENCH_SETTINGS_ID)
        )
    )
    settings = result.scalar_one_or_none()
    if settings:
        return settings
    settings = DeviationWorkbenchSettings(
        id=uuid.UUID(WORKBENCH_SETTINGS_ID),
        report_system_prompt="",
    )
    db.add(settings)
    await db.flush()
    return settings


async def _fetch_settings_row(
    db: AsyncSession, settings_id: uuid.UUID
) -> DeviationWorkbenchSettings:
    result = await db.execute(
        select(DeviationWorkbenchSettings).where(
            DeviationWorkbenchSettings.id == settings_id
        )
    )
    return result.scalar_one()


async def get_workbench_settings(db: AsyncSession) -> DeviationWorkbenchSettingsOut:
    """读取设置（只读，不写库；settings 行已由迁移预置）。"""
    result = await db.execute(
        select(DeviationWorkbenchSettings).where(
            DeviationWorkbenchSettings.id == uuid.UUID(WORKBENCH_SETTINGS_ID),
            DeviationWorkbenchSettings.is_deleted.is_(False),
        )
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        # 迁移应已预置该行；极端缺失时回退默认提示词，保持 GET 无写副作用
        return DeviationWorkbenchSettingsOut(report_system_prompt="", updated_at=None)
    return DeviationWorkbenchSettingsOut(
        report_system_prompt=settings.report_system_prompt,
        updated_at=settings.updated_at,
    )


async def update_workbench_settings(
    db: AsyncSession,
    data: UpdateDeviationWorkbenchSettingsRequest,
    user_id: str,
) -> DeviationWorkbenchSettingsOut:
    settings = await _get_or_create_settings(db)
    settings.report_system_prompt = data.report_system_prompt.strip()
    settings.updated_by = persisted_user_id(user_id)
    await db.commit()
    settings = await _fetch_settings_row(db, settings.id)
    return DeviationWorkbenchSettingsOut(
        report_system_prompt=settings.report_system_prompt,
        updated_at=settings.updated_at,
    )


# ─── 附件上传（返回描述符，供 analyze 引用） ─────────────────────────


async def upload_workbench_attachment(
    db: AsyncSession,
    file: UploadFile,
    user_id: str,
) -> DeviationWorkbenchAttachmentIn:
    if not file.filename:
        raise AppException(message="附件文件名不能为空")
    file_name, content = await read_upload_secure(
        file,
        max_bytes=ATTACHMENT_MAX_SIZE,
        allowed_extensions=ALLOWED_EXT,
        what="偏差工作台附件",
    )
    content_type = sniff_upload_mime(file_name, content)

    safe_file_name = safe_upload_filename(file_name, fallback="attachment.bin")
    safe_name = f"{uuid.uuid4().hex}_{safe_file_name}"
    original_key = f"deviation-workbench/attachments/{safe_name}"
    stored_keys: list[str] = []
    try:
        store_file(_STORAGE_SUBDIR, original_key, content, content_type)
        stored_keys.append(original_key)

        converted_md_key: str | None = None
        asset_keys: list[str] = []
        ext = Path(file_name).suffix.lower()
        if ext in WORD_EXT:
            try:
                md_text, images = await asyncio.to_thread(
                    render_word_to_md, file_name, content
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "deviation workbench word convert failed, stored as-is",
                    extra={"component": "quality", "file": file_name},
                )
            else:
                name_to_url: dict[str, str] = {}
                for image in images:
                    asset_key = (
                        "deviation-workbench/attachments/"
                        f"{uuid.uuid4().hex}_{image.name}"
                    )
                    store_file(
                        _STORAGE_SUBDIR, asset_key, image.data, image.content_type
                    )
                    stored_keys.append(asset_key)
                    asset_keys.append(asset_key)
                    name_to_url[image.name] = _attachment_content_url(asset_key)
                md_text = MD_IMAGE_REF_RE.sub(
                    lambda m: f"![image]({name_to_url[m.group(1)]})", md_text
                )
                md_key = (
                    "deviation-workbench/attachments/"
                    f"{uuid.uuid4().hex}_{Path(file_name).stem}.md"
                )
                store_file(
                    _STORAGE_SUBDIR, md_key, md_text.encode("utf-8"), TEXT_MD_MIME
                )
                stored_keys.append(md_key)
                converted_md_key = md_key
        elif ext == ".md":
            converted_md_key = original_key

        descriptor = DeviationWorkbenchAttachmentIn(
            id=str(uuid.uuid4()),
            file_name=file_name,
            storage_key=original_key,
            content_type=content_type,
            file_size=len(content),
            converted=converted_md_key is not None,
            converted_md_key=converted_md_key,
            asset_keys=asset_keys,
        )
    except Exception:
        for stored_key in reversed(stored_keys):
            try:
                delete_file(_STORAGE_SUBDIR, stored_key)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "清理偏差工作台附件对象失败: object_key=%s", stored_key
                )
        raise
    await db.commit()
    return descriptor


def read_workbench_attachment_content(storage_key: str) -> tuple[bytes, str]:
    """按存储 key 读取工作台附件内容（md/原文件/图片资产）。"""
    stored = read_file(_STORAGE_SUBDIR, storage_key)
    if stored is None:
        return b"", "application/octet-stream"
    data, content_type = stored
    if content_type == "application/octet-stream":
        content_type = sniff_upload_mime(storage_key, data)
    return data, content_type


def delete_workbench_attachment_files(keys: list[str]) -> None:
    """删除已上传但未被报告消费的工作台附件对象（原件 + 转换 md + 图片资产）。"""
    for key in keys:
        if not key:
            continue
        try:
            delete_file(_STORAGE_SUBDIR, key)
        except Exception:  # noqa: BLE001
            logger.exception("清理偏差工作台附件对象失败: object_key=%s", key)


def _attachment_out(
    report_id: uuid.UUID, attachment: dict[str, Any]
) -> DeviationWorkbenchAttachmentOut:
    preview_key = attachment.get("converted_md_key") or attachment.get("storage_key")
    return DeviationWorkbenchAttachmentOut(
        id=str(attachment.get("id") or ""),
        file_name=attachment.get("file_name") or "",
        url=_attachment_content_url(preview_key or ""),
        content_type=attachment.get("content_type"),
        file_size=attachment.get("file_size"),
        converted=bool(attachment.get("converted")),
        uploaded_at=attachment.get("uploaded_at"),
    )


# ─── 记录台账 ────────────────────────────────────────────────────────


def _list_item_to_schema(
    report: DeviationWorkbenchReport,
) -> DeviationWorkbenchReportListItem:
    return DeviationWorkbenchReportListItem(
        id=report.id,
        code=report.code,
        source_type=report.source_type,
        deviation_summary=report.deviation_summary,
        status=report.status,
        error_message=report.error_message,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def _detail_to_schema(
    report: DeviationWorkbenchReport,
) -> DeviationWorkbenchReportDetail:
    detail = _list_item_to_schema(report).model_dump()
    detail["source_record_id"] = report.source_record_id
    detail["manual_text"] = report.manual_text
    detail["attachments"] = [
        _attachment_out(report.id, attachment).model_dump(mode="json")
        for attachment in report.attachments or []
    ]
    detail["context_snapshot"] = report.context_snapshot
    detail["report_payload"] = report.report_payload
    detail["report_md"] = report.report_md
    detail["model_name"] = report.model_name
    return DeviationWorkbenchReportDetail.model_validate(detail)


async def _get_report_or_raise(
    db: AsyncSession, report_id: uuid.UUID
) -> DeviationWorkbenchReport:
    report = await db.get(DeviationWorkbenchReport, report_id)
    if not report or report.is_deleted:
        raise NotFoundException(resource="偏差工作台记录")
    return report


async def list_workbench_reports(
    db: AsyncSession,
    *,
    keyword: str | None,
    source_type: str | None,
    status: str | None,
    date_from: str | None,
    date_to: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    filters: list[ColumnElement[bool]] = [
        DeviationWorkbenchReport.is_deleted.is_(False)
    ]
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(
            or_(
                DeviationWorkbenchReport.code.ilike(pattern),
                DeviationWorkbenchReport.deviation_summary.ilike(pattern),
                DeviationWorkbenchReport.report_md.ilike(pattern),
            )
        )
    if source_type:
        filters.append(DeviationWorkbenchReport.source_type == source_type)
    if status:
        filters.append(DeviationWorkbenchReport.status == status)
    if date_from:
        try:
            start = datetime.fromisoformat(date_from)
            filters.append(DeviationWorkbenchReport.created_at >= start)
        except ValueError:
            raise AppException(message="开始日期格式不合法") from None
    if date_to:
        try:
            end = datetime.fromisoformat(date_to) + timedelta(days=1)
            filters.append(DeviationWorkbenchReport.created_at < end)
        except ValueError:
            raise AppException(message="结束日期格式不合法") from None

    count_query = (
        select(func.count()).select_from(DeviationWorkbenchReport).where(*filters)
    )
    total = (await db.execute(count_query)).scalar() or 0
    query = (
        select(DeviationWorkbenchReport)
        .where(*filters)
        .order_by(DeviationWorkbenchReport.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = [_list_item_to_schema(item) for item in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_workbench_report_detail(
    db: AsyncSession, report_id: uuid.UUID
) -> DeviationWorkbenchReportDetail:
    report = await _get_report_or_raise(db, report_id)
    return _detail_to_schema(report)


async def delete_workbench_report(
    db: AsyncSession,
    report_id: uuid.UUID,
    user_id: str,
) -> None:
    report = await _get_report_or_raise(db, report_id)
    for attachment in report.attachments or []:
        for key in attachment_storage_keys(attachment):
            try:
                delete_file(_STORAGE_SUBDIR, key)
            except Exception:  # noqa: BLE001
                logger.exception("清理偏差工作台附件对象失败: object_key=%s", key)
    report.is_deleted = True
    report.deleted_by = persisted_user_id(user_id)
    report.deleted_at = datetime.now(UTC)
    await db.commit()


async def _attachment_context_text(attachment: dict[str, Any]) -> str:
    """读取附件正文供 AI 上下文：正文用纯文本提取（模板化转换可能丢弃无标题正文）。"""
    from app.platform.ai.document_text_extractor import extract_document_text

    file_name = attachment.get("file_name") or ""
    stored = read_file(_STORAGE_SUBDIR, attachment.get("storage_key") or "")
    if stored is None:
        return ""
    content, _ = stored
    ext = Path(file_name).suffix.lower()
    try:
        if ext in IMAGE_EXT:
            import pytesseract  # type: ignore[import-untyped]
            from PIL import Image

            image = Image.open(io.BytesIO(content))
            return str(
                pytesseract.image_to_string(image, lang="chi_sim+eng").strip()
            )
        return extract_document_text(file_name, content)
    except Exception:  # noqa: BLE001
        logger.warning("偏差工作台附件解析失败: %s", file_name)
        return ""


# ─── 上下文构建与检索 ────────────────────────────────────────────────


def _split_keywords(text: str) -> list[str]:
    """切分检索关键词：按空白/标点分隔，去重，过滤过短词，最多 8 个。"""
    if not text:
        return []
    raw = re.split(r"[\s，。；、,.;:：!！?？/\\|（）()\[\]【】\"'\n\r]+", text)
    keywords: list[str] = []
    for item in raw:
        kw = item.strip()
        if len(kw) < 2 or kw in keywords:
            continue
        keywords.append(kw)
        if len(keywords) >= 8:
            break
    return keywords


async def _retrieve_historical_deviations(
    db: AsyncSession, keywords: list[str]
) -> list[dict[str, Any]]:
    if not keywords:
        return []
    match_clause = or_(
        *[
            column.ilike(f"%{_escape_like(kw)}%")
            for column in (
                HistoricalDeviation.deviation_event,
                HistoricalDeviation.deviation_content,
                HistoricalDeviation.direct_cause,
                HistoricalDeviation.root_cause,
            )
            for kw in keywords
        ]
    )
    result = await db.execute(
        select(HistoricalDeviation)
        .where(HistoricalDeviation.is_deleted.is_(False), match_clause)
        .order_by(HistoricalDeviation.created_at.desc())
        .limit(RETRIEVAL_LIMIT)
    )
    return [
        {
            "code": item.code,
            "deviation_event": _truncate(item.deviation_event, 300),
            "deviation_content": _truncate(item.deviation_content, 500),
            "direct_cause": _truncate(item.direct_cause, 300),
            "root_cause": _truncate(item.root_cause, 300),
        }
        for item in result.scalars().all()
    ]


async def _retrieve_documents(
    db: AsyncSession, keywords: list[str]
) -> list[dict[str, Any]]:
    if not keywords:
        return []
    seen: dict[str, dict[str, Any]] = {}
    for kw in keywords:
        entries, _ = await list_document_entries(
            db,
            department_id=None,
            keyword=kw[:20],
            page=1,
            page_size=RETRIEVAL_LIMIT,
            scope_dept_ids=None,
        )
        for entry in entries:
            key = str(entry.id)
            if key in seen:
                continue
            contents = read_entry_md_contents(entry)
            md_text = "\n\n".join(
                item.get("md_text") or "" for item in contents
            ).strip()
            seen[key] = {
                "code": entry.code or "",
                "name": entry.name or "",
                "content": _truncate(md_text, 2000),
            }
        if len(seen) >= RETRIEVAL_LIMIT:
            break
    return list(seen.values())[:RETRIEVAL_LIMIT]


async def _retrieve_training_ledgers(
    db: AsyncSession, keywords: list[str]
) -> list[dict[str, Any]]:
    """检索人事培训台账（跨模块只读，hr 模块异常时降级为空）。"""
    if not keywords:
        return []
    try:
        from app.modules.hr.public_api import query_training_ledgers

        return await query_training_ledgers(db, keywords, limit=RETRIEVAL_LIMIT)
    except Exception:  # noqa: BLE001
        logger.warning("培训台账检索失败，已降级跳过", exc_info=True)
        return []


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _build_context(
    db: AsyncSession, data: CreateDeviationWorkbenchRequest
) -> tuple[dict[str, Any], str, str]:
    """构建 (context_snapshot, 输入上下文文本, deviation_summary)。"""
    snapshot: dict[str, Any] = {
        "source": {},
        "historical_deviations": [],
        "documents": [],
        "training_ledgers": [],
    }
    input_parts: list[str] = []
    search_keyword = (data.manual_text or "").strip() or ""
    deviation_summary = ""

    if data.source_type == "report_record" and data.source_record_id:
        try:
            from app.modules.quality.service.tracking_records import (
                get_deviation_report_record_from_feishu,
            )

            source = await get_deviation_report_record_from_feishu(
                db, data.source_record_id
            )
        except AppException:
            source = None
        if source:
            snapshot["source"] = {
                "deviation_code": source.get("deviation_code"),
                "description": source.get("description"),
                "product_batch": source.get("product_batch"),
                "department": source.get("department"),
                "report_time": source.get("report_time"),
                "attachments": [
                    {"name": a.get("name"), "url": a.get("url"), "type": a.get("type")}
                    for a in (source.get("attachments") or [])
                ],
            }
            deviation_summary = source.get("description") or ""
            product_batch = source.get("product_batch") or ""
            search_keyword = " ".join(
                x for x in (search_keyword, deviation_summary, product_batch) if x
            )
            input_parts.append(
                "【来源：偏差管理报告记录】\n"
                f"偏差编号：{source.get('deviation_code') or '-'}\n"
                f"涉及产品/批号：{source.get('product_batch') or '-'}\n"
                f"部门：{source.get('department') or '-'}\n"
                f"偏差内容：{source.get('description') or '-'}"
            )

    if data.manual_text and data.manual_text.strip():
        snapshot["source"]["manual_text"] = data.manual_text.strip()
        input_parts.append(f"【用户输入】\n{data.manual_text.strip()}")
        if not deviation_summary:
            deviation_summary = data.manual_text.strip()

    if data.affected_items and data.affected_items.strip():
        snapshot["source"]["affected_items"] = data.affected_items.strip()
        search_keyword = f"{search_keyword} {data.affected_items.strip()}".strip()
        input_parts.append(f"【涉及产品名称/批号】\n{data.affected_items.strip()}")

    if data.supplement_text and data.supplement_text.strip():
        snapshot["source"]["supplement_text"] = data.supplement_text.strip()
        search_keyword = f"{search_keyword} {data.supplement_text.strip()}".strip()
        input_parts.append(f"【补充说明】\n{data.supplement_text.strip()}")

    for attachment in data.attachments:
        context_text = await _attachment_context_text(attachment.model_dump())
        if context_text.strip():
            input_parts.append(
                f"【附件：{attachment.file_name}】\n{_truncate(context_text, 6000)}"
            )

    if search_keyword:
        keywords = _split_keywords(search_keyword)
        snapshot["historical_deviations"] = await _retrieve_historical_deviations(
            db, keywords
        )
        snapshot["documents"] = await _retrieve_documents(db, keywords)
        snapshot["training_ledgers"] = await _retrieve_training_ledgers(
            db, keywords
        )
        if snapshot["historical_deviations"]:
            input_parts.append(
                "【检索到的历史偏差】\n"
                + "\n".join(
                    f"- {item['code']}: 事件={item['deviation_event'] or '-'}；"
                    f"内容={item['deviation_content'] or '-'}；"
                    f"根因={item['root_cause'] or '-'}"
                    for item in snapshot["historical_deviations"]
                )
            )
        if snapshot["documents"]:
            input_parts.append(
                "【检索到的文件管理制度】\n"
                + "\n".join(
                    f"- {item['code']} {item['name']}: {item['content'] or '-'}"
                    for item in snapshot["documents"]
                )
            )
        if snapshot["training_ledgers"]:
            input_parts.append(
                "【检索到的培训台账】\n"
                + "\n".join(
                    f"- {item.get('training_date') or ''} "
                    f"{item.get('training_subject') or '-'}"
                    f"（{item.get('training_type') or '未分类'}，"
                    f"授课：{item.get('teaching_dept') or '-'}）："
                    f"{item.get('training_content') or '-'}"
                    for item in snapshot["training_ledgers"]
                )
            )

    context_text = "\n\n".join(part for part in input_parts if part).strip()
    if len(context_text) > AI_CONTEXT_TEXT_LIMIT:
        context_text = context_text[:AI_CONTEXT_TEXT_LIMIT]
    if not context_text:
        raise AppException(message="请选择报告记录、输入内容或上传附件后生成调查报告")
    return snapshot, context_text, _truncate(deviation_summary, 200)


# ─── 调查报告生成 ────────────────────────────────────────────────────


def _normalize_analysis(analysis: Any) -> dict[str, str]:
    if not isinstance(analysis, dict):
        return {dim: "" for dim in _5M1E_DIMS}
    normalized: dict[str, str] = {}
    for dim in _5M1E_DIMS:
        value = ""
        for key, raw in analysis.items():
            if str(key).strip() == dim or str(key).strip().startswith(dim):
                value = str(raw or "").strip()
                break
        normalized[dim] = value
    return normalized


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _validate_report(raw: dict[str, Any]) -> dict[str, Any]:
    deviation_summary = str(raw.get("deviation_summary") or "").strip()
    direct_cause = str(raw.get("direct_cause") or "").strip()
    root_cause = str(raw.get("root_cause") or "").strip()
    conclusion = str(raw.get("conclusion") or "").strip()
    if not any([deviation_summary, direct_cause, root_cause, conclusion]):
        raise AppException(status_code=502, message="AI 未生成有效调查报告，请重试")
    return {
        "deviation_summary": deviation_summary,
        "analysis": _normalize_analysis(raw.get("analysis")),
        "direct_cause": direct_cause,
        "root_cause": root_cause,
        "conclusion": conclusion,
        "recommendations": _normalize_string_list(raw.get("recommendations")),
        "referenced_sources": _normalize_string_list(raw.get("referenced_sources")),
    }


def _payload_to_md(payload: dict[str, Any]) -> str:
    lines = [
        "# 偏差调查报告",
        "",
        "## 一、偏差概述",
        payload.get("deviation_summary") or "-",
        "",
    ]
    lines.append("## 二、人机料法环测（5M1E）分析")
    analysis = payload.get("analysis") or {}
    for dim in _5M1E_DIMS:
        value = (analysis.get(dim) or "").strip()
        lines.append(f"### {dim}")
        lines.append(value if value else "-")
        lines.append("")
    lines.append("## 三、直接原因")
    lines.append(payload.get("direct_cause") or "-")
    lines.append("")
    lines.append("## 四、根本原因")
    lines.append(payload.get("root_cause") or "-")
    lines.append("")
    lines.append("## 五、调查结论")
    lines.append(payload.get("conclusion") or "-")
    lines.append("")
    lines.append("## 六、纠正预防建议")
    recommendations = payload.get("recommendations") or []
    if recommendations:
        lines.extend(f"- {item}" for item in recommendations)
    else:
        lines.append("-")
    lines.append("")
    lines.append("## 七、参考来源")
    sources = payload.get("referenced_sources") or []
    if sources:
        lines.extend(f"- {item}" for item in sources)
    else:
        lines.append("-")
    return "\n".join(lines).strip()


async def analyze_workbench(
    db: AsyncSession,
    data: CreateDeviationWorkbenchRequest,
    user_id: str,
) -> DeviationWorkbenchReportDetail:
    code = await generate_code(db, DeviationWorkbenchReport, "WB")
    report = DeviationWorkbenchReport(
        code=code,
        source_type=data.source_type,
        source_record_id=data.source_record_id,
        manual_text=data.manual_text,
        attachments=[attachment.model_dump() for attachment in data.attachments],
        status="processing",
        created_by=persisted_user_id(user_id),
        updated_by=persisted_user_id(user_id),
    )
    db.add(report)
    await db.flush()

    settings = await _get_or_create_settings(db)
    context_snapshot, context_text, deviation_summary = await _build_context(db, data)
    report.context_snapshot = context_snapshot
    report.deviation_summary = deviation_summary
    await db.flush()

    system_prompt = (
        settings.report_system_prompt.strip() or DEFAULT_REPORT_SYSTEM_PROMPT
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_text},
    ]

    try:
        config = await get_config("text")
    except LLMConfigError:
        report.status = "failed"
        report.error_message = "AI 服务尚未配置"
        await db.commit()
        result = await db.execute(
            select(DeviationWorkbenchReport).where(
                DeviationWorkbenchReport.id == report.id
            )
        )
        return _detail_to_schema(result.scalar_one())

    try:
        raw: dict[str, Any] = {}
        max_retries = 3
        for attempt in range(max_retries):
            try:
                raw = await llm_client.chat_json(
                    messages,
                    expected_keys=WORKBENCH_REPORT_KEYS,
                    temperature=0.3,
                )
                break
            except LLMRateLimitError:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
        payload = _validate_report(raw)
        report.report_payload = payload
        report.report_md = _payload_to_md(payload)
        report.model_name = config.model_name
        report.status = "completed"
        report.error_message = None
    except LLMRateLimitError:
        report.status = "failed"
        report.error_message = "AI 限流，请稍后重试"
    except LLMOutputError:
        report.status = "failed"
        report.error_message = "AI 输出格式错误，请重试"
    except LLMProviderError:
        report.status = "failed"
        report.error_message = "AI 服务调用失败，请稍后重试"
    except AppException as exc:
        # 覆盖 _validate_report 等业务校验失败：落 failed 记录而非让 502 逃逸
        report.status = "failed"
        report.error_message = exc.message

    await db.commit()
    result = await db.execute(
        select(DeviationWorkbenchReport).where(DeviationWorkbenchReport.id == report.id)
    )
    return _detail_to_schema(result.scalar_one())
