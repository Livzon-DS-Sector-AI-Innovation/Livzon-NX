"""安全知识库与 EHS 法规库多维表格的镜像同步与附件读取。

飞书字段 → 本地字段映射（以 EHS 法规数据库实际结构为准）：
- 法规编号 → article_no；法律法规及标准名称 → title
- 法规类别 → regulation_category（原始值）+ category（映射到本地枚举）
- 颁布机关 → source；颁布修订日期/实施日期 → promulgation_date/implement_date
- 法规状态 → regulation_status；更新状态 → update_status；法规链接 → regulation_link
- 核心要点总结 → summary；备注 → notes；附件 → feishu_attachments 快照

同步策略：全量拉取 + 按 feishu_record_id upsert；远端消失的镜像行软删；
本地手工创建的文章（无 feishu_record_id）不受影响。附件不落盘，展示时
按 file_token 经安全应用凭证代理下载（平台 AttachmentCache 缓存）。
"""

from __future__ import annotations

import logging
import mimetypes
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.feishu.bitable_client import SafetyBitableClient
from app.modules.safety.feishu.runtime_config import SafetyFeishuConfigError
from app.modules.safety.models import SafetyKnowledgeArticle
from app.platform.integrations.feishu.attachment_cache import get_attachment_cache

if TYPE_CHECKING:
    from app.modules.safety.models import SafetyFeishuAppSettings

logger = logging.getLogger(__name__)

# 飞书字段名 → 本地列（EHS 法规数据库固定结构）
_KNOWLEDGE_FIELD_MAP: dict[str, str] = {
    "法规编号": "article_no",
    "法律法规及标准名称": "title",
    "法规类别": "regulation_category",
    "颁布机关": "source",
    "颁布修订日期": "promulgation_date",
    "实施日期": "implement_date",
    "法规状态": "regulation_status",
    "法规链接": "regulation_link",
    "核心要点总结": "summary",
    "备注": "notes",
}

# 法规类别原始值 → 本地 KnowledgeCategory 枚举
_CATEGORY_FALLBACK = "laws_regulations"


class KnowledgeSyncResult(dict[str, Any]):
    """同步结果（created/updated/removed/failed 计数）。"""


def _join_text(value: Any) -> str:
    """飞书文本段（[{text,type}, ...] / str）拼接为纯文本。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for seg in value:
            if isinstance(seg, dict) and isinstance(seg.get("text"), str):
                parts.append(seg["text"])
            elif isinstance(seg, str):
                parts.append(seg)
        return "".join(parts).strip()
    return str(value).strip()


def _ms_to_datetime(value: Any) -> datetime | None:
    """飞书日期字段（毫秒时间戳）转 datetime。"""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _parse_link(value: Any) -> str:
    """飞书 URL 字段（{link,text,type}）取链接地址。

    仅接受 http(s) 协议：数据源是外部可编辑的多维表格，
    防止 javascript: 等危险协议经前端 href 造成存储型 XSS。
    """
    if isinstance(value, dict):
        link = str(value.get("link") or "").strip()
    elif isinstance(value, str):
        link = value.strip()
    else:
        return ""
    if link.lower().startswith(("http://", "https://")):
        return link
    return ""


def _parse_attachments(value: Any) -> list[dict[str, Any]]:
    """飞书附件字段 → [{file_token, name, size}] 快照。"""
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        token = str(item.get("file_token") or "").strip()
        if not token:
            continue
        result.append(
            {
                "file_token": token,
                "name": str(item.get("name") or token),
                "size": item.get("size") or 0,
            }
        )
    return result


def _map_category(regulation_category: str) -> str:
    """法规类别原始值映射到本地枚举；标准类归 standards，其余归法律法规。"""
    if "标准" in regulation_category:
        return "standards"
    return _CATEGORY_FALLBACK


def _build_article_values(fields: dict[str, Any]) -> dict[str, Any]:
    """把一行飞书记录 fields 转为本地列值。"""
    values: dict[str, Any] = {}
    for feishu_name, column in _KNOWLEDGE_FIELD_MAP.items():
        raw = fields.get(feishu_name)
        if column in {"promulgation_date", "implement_date"}:
            values[column] = _ms_to_datetime(raw)
        elif column == "regulation_link":
            values[column] = _parse_link(raw) or None
        else:
            text = _join_text(raw)
            values[column] = text or None
    regulation_category = values.get("regulation_category") or ""
    values["category"] = _map_category(regulation_category)
    values["feishu_attachments"] = _parse_attachments(fields.get("附件"))
    # 同步镜像行固定以标题兜底，避免飞书缺名称时违反非空约束
    values["title"] = values.get("title") or regulation_category or "未命名法规"
    return values


async def _get_settings_model(db: AsyncSession) -> SafetyFeishuAppSettings | None:
    from app.modules.safety.models import SafetyFeishuAppSettings

    result = await db.execute(
        select(SafetyFeishuAppSettings)
        .where(SafetyFeishuAppSettings.is_deleted.is_(False))
        .order_by(SafetyFeishuAppSettings.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _mark_knowledge_sync(
    db: AsyncSession,
    settings_model: SafetyFeishuAppSettings,
    status: str,
    error: str | None,
) -> None:
    settings_model.knowledge_last_sync_status = status
    settings_model.knowledge_last_sync_error = error
    settings_model.knowledge_last_synced_at = datetime.now(UTC)
    await db.commit()


async def sync_knowledge_from_feishu(db: AsyncSession) -> KnowledgeSyncResult:
    """全量拉取 EHS 法规库并 upsert 本地镜像。"""
    settings_model = await _get_settings_model(db)
    if settings_model is None:
        raise AppException(message="请先在 安全管理 → 系统配置 → 飞书设置 保存应用凭证")
    app_token = (settings_model.knowledge_app_token or "").strip()
    table_id = (settings_model.knowledge_table_id or "").strip()
    if not app_token or not table_id:
        raise AppException(
            message="请先在 飞书设置 中配置 EHS 法规库的 App Token 与 Table ID"
        )

    if not settings_model.is_enabled:
        raise AppException(
            message="安全模块飞书集成未启用，请先在 飞书设置 中启用后再同步"
        )

    client = SafetyBitableClient(app_token=app_token, table_id=table_id)
    try:
        records = await client.search_records(table_id=table_id, page_size=500)
    except SafetyFeishuConfigError as exc:
        await _mark_knowledge_sync(db, settings_model, "failed", str(exc))
        raise AppException(message=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 —— 同步失败要落到状态列并给业务错误
        error_text = f"拉取 EHS 法规库失败：{exc}"
        logger.exception("同步 EHS 法规库失败")
        await _mark_knowledge_sync(db, settings_model, "failed", error_text)
        raise AppException(message=error_text) from exc

    result = KnowledgeSyncResult(
        created=0, updated=0, removed=0, failed=0, total=len(records)
    )

    seen_record_ids: set[str] = set()
    existing_rows = (
        (
            await db.execute(
                select(SafetyKnowledgeArticle).where(
                    SafetyKnowledgeArticle.is_deleted.is_(False),
                    SafetyKnowledgeArticle.feishu_record_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    existing_by_record_id = {
        row.feishu_record_id: row for row in existing_rows if row.feishu_record_id
    }

    for item in records:
        record_id = str(item.get("record_id") or "").strip()
        raw_fields = item.get("fields")
        fields: dict[str, Any] = raw_fields if isinstance(raw_fields, dict) else {}
        if not record_id:
            result["failed"] += 1
            continue
        seen_record_ids.add(record_id)
        try:
            values = _build_article_values(fields)
            is_new = False
            async with db.begin_nested():
                row = existing_by_record_id.get(record_id)
                if row is None:
                    row = SafetyKnowledgeArticle(
                        feishu_record_id=record_id,
                        status="published",
                        **values,
                    )
                    db.add(row)
                    is_new = True
                else:
                    for column, value in values.items():
                        setattr(row, column, value)
                await db.flush()
            # 保存点提交成功才计数，坏行回滚后只计入 failed
            if is_new:
                result["created"] += 1
            else:
                result["updated"] += 1
        except Exception:
            result["failed"] += 1
            logger.exception(
                "同步 EHS 法规记录失败: record_id=%s", record_id
            )

    # 远端已删除的镜像行软删（保留本地手工文章）
    removed = 0
    for record_id, row in existing_by_record_id.items():
        if record_id not in seen_record_ids and not row.is_deleted:
            row.is_deleted = True
            removed += 1
    result["removed"] = removed

    error_summary = None
    if result["failed"]:
        error_summary = f"{result['failed']} 条记录同步失败，详见后端日志"
    sync_status = "success" if not result["failed"] else "partial"
    await _mark_knowledge_sync(db, settings_model, sync_status, error_summary)
    return result


async def get_knowledge_attachment(
    db: AsyncSession,
    record_id: str,
    file_token: str,
) -> tuple[bytes, str, str]:
    """按镜像快照校验并代理下载飞书附件，返回 (content, content_type, filename)。

    file_token 必须属于该记录的附件快照，防止越权读取其他文档。
    """
    row = (
        await db.execute(
            select(SafetyKnowledgeArticle).where(
                SafetyKnowledgeArticle.feishu_record_id == record_id,
                SafetyKnowledgeArticle.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppException(status_code=404, message="知识库记录不存在")
    snapshots = row.feishu_attachments or []
    match = next(
        (item for item in snapshots if item.get("file_token") == file_token),
        None,
    )
    if match is None:
        raise AppException(
            status_code=404, message="附件不存在或不属于该记录"
        )
    filename = str(match.get("name") or file_token)

    settings_model = await _get_settings_model(db)
    app_token = (
        (settings_model.knowledge_app_token or "").strip() if settings_model else ""
    )

    async def _fetch() -> tuple[bytes, str, str] | None:
        client = SafetyBitableClient(app_token=app_token, table_id="")
        content = await client.download_attachment(file_token)
        if content is None:
            return None
        content_type = (
            mimetypes.guess_type(filename)[0] or "application/octet-stream"
        )
        return content, content_type, filename

    cached = await get_attachment_cache().get_or_fetch(
        "safety-knowledge", record_id, file_token, _fetch
    )
    if cached is None:
        raise AppException(
            status_code=502, message=f"附件下载失败：{filename}"
        )
    return cached
