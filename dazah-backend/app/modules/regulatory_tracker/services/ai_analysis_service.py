"""AI 分析服务 - 使用 LLM 分析法规文档。"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMError, llm_client
from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.models.regulatory_document import RegulatoryDocument

logger = logging.getLogger(__name__)


def _build_analysis_source_text(document: RegulatoryDocument) -> str:
    raw_data = document.raw_data or {}

    candidates: list[str] = [
        document.summary_text or "",
        raw_data.get("contentSummary", "") or "",
        raw_data.get("summary", "") or "",
        raw_data.get("detail_excerpt", "") or "",
        raw_data.get("detail_content", "") or "",
    ]

    detail_paragraphs = raw_data.get("detail_paragraphs")
    if isinstance(detail_paragraphs, list):
        candidates.extend(
            item for item in detail_paragraphs if isinstance(item, str) and item.strip()
        )

    merged = " ".join(
        part.strip() for part in candidates if isinstance(part, str) and part.strip()
    )
    return merged[:1200] if merged else ""


def build_analysis_prompt(document: RegulatoryDocument) -> list[dict[str, Any]]:
    """构建文档分析 prompt。"""
    title = document.title or ""
    classification = document.classification or "未知"
    status_text = document.status_text or "未知"
    content_summary = _build_analysis_source_text(document)

    prompt = f"""你是一个制药法规分析专家。请分析以下法规文档并提供结构化分析结果。

## 文档信息
- 标题: {title}
- 分类: {classification}
- 状态: {status_text}
- 内容摘要: {content_summary[:500] if content_summary else "无"}

## 分析任务
请提供以下分析：

1. **摘要 (summary)**: 用 2-3 句话概括该法规的核心内容和目的
2. **关键要点 (key_points)**: 提取 3-5 个关键要点，每个要点一句话
3. **相关性评分 (relevance_score)**: 评估该法规对制药企业的重要性，评分 0-1
   - 1.0: 强制性法规，直接影响生产运营
   - 0.7-0.9: 重要指导原则，强烈建议遵循
   - 0.4-0.6: 参考性文件，有一定价值
   - 0.1-0.3: 一般性通知，影响较小
   - 0.0: 无关或重复文件

## 输出格式
请以 JSON 格式返回：
{{
  "summary": "法规摘要",
  "key_points": ["要点1", "要点2", "要点3"],
  "relevance_score": 0.85
}}

无论原文是中文还是英文，`summary` 和 `key_points` 都必须使用中文输出。
请只返回 JSON，不要其他内容。"""

    return [
        {
            "role": "system",
            "content": "你是专业的制药法规分析师，擅长分析药品监管文件。",
        },
        {"role": "user", "content": prompt},
    ]


async def analyze_document(document: RegulatoryDocument) -> dict[str, Any]:
    """使用 AI 分析单个文档。

    Args:
        document: 待分析的法规文档

    Returns:
        分析结果字典
    """
    messages = build_analysis_prompt(document)

    try:
        result = await llm_client.chat_json(
            messages,
            expected_keys=["summary", "key_points", "relevance_score"],
        )

        # 验证和规范化结果
        summary = result.get("summary", "")
        key_points = result.get("key_points", [])
        relevance_score = result.get("relevance_score", 0.5)

        # 确保 key_points 是列表
        if not isinstance(key_points, list):
            key_points = [str(key_points)] if key_points else []

        # 确保 relevance_score 在 0-1 范围内
        try:
            relevance_score = float(relevance_score)
            relevance_score = max(0.0, min(1.0, relevance_score))
        except (ValueError, TypeError):
            relevance_score = 0.5

        return {
            "summary": summary,
            "key_points": key_points,
            "relevance_score": relevance_score,
            "status": "completed",
        }

    except LLMError as e:
        logger.error(f"AI 分析文档失败 [{document.document_id}]: {e}")
        return {
            "summary": None,
            "key_points": None,
            "relevance_score": None,
            "status": "failed",
            "error": str(e),
        }


async def analyze_and_update(
    db: AsyncSession,
    document: RegulatoryDocument,
) -> bool:
    """分析文档并更新数据库。

    Args:
        db: 数据库会话
        document: 待分析的文档

    Returns:
        是否成功
    """
    logger.info(f"开始 AI 分析文档: {document.title[:50]}...")

    # 标记为分析中
    await repo.update_document(
        db,
        document.id,
        {
            "ai_analysis_status": "pending",
        },
    )
    await db.commit()

    # 执行 AI 分析
    result = await analyze_document(document)

    # 更新分析结果
    update_data = {
        "ai_analysis_status": result["status"],
        "ai_analyzed_at": datetime.now(UTC),
    }

    if result["status"] == "completed":
        update_data.update(
            {
                "ai_summary": result["summary"],
                "ai_key_points": result["key_points"],
                "ai_relevance_score": result["relevance_score"],
            }
        )

    await repo.update_document(db, document.id, update_data)
    await db.commit()

    logger.info(f"AI 分析完成: {document.title[:50]}... (状态: {result['status']})")
    return result.get("status") == "completed"


async def analyze_new_documents(
    db: AsyncSession,
    channel_id: str | None = None,
    limit: int = 10,
) -> dict[str, int]:
    """批量分析新文档。

    Args:
        db: 数据库会话
        channel_id: 可选的栏目 ID 过滤
        limit: 最多分析多少文档

    Returns:
        统计信息 {"analyzed": int, "failed": int, "skipped": int}
    """
    # 查询未分析的文档
    stmt = select(RegulatoryDocument).where(
        and_(
            ~RegulatoryDocument.is_deleted,
            RegulatoryDocument.ai_analysis_status.is_(None),
        )
    )

    if channel_id:
        stmt = stmt.where(RegulatoryDocument.channel_id == channel_id)

    stmt = stmt.order_by(RegulatoryDocument.first_found_at.desc()).limit(limit)

    result = await db.execute(stmt)
    documents = result.scalars().all()

    stats = {"analyzed": 0, "failed": 0, "skipped": 0}

    for doc in documents:
        success = await analyze_and_update(db, doc)
        if success:
            stats["analyzed"] += 1
        else:
            stats["failed"] += 1

    logger.info(f"批量分析完成: {stats}")
    return stats


async def analyze_documents_by_ids(
    db: AsyncSession,
    document_ids: list[uuid.UUID],
) -> dict[str, int]:
    """按指定文档列表执行分析。"""
    if not document_ids:
        return {"analyzed": 0, "failed": 0, "skipped": 0}

    stmt = (
        select(RegulatoryDocument)
        .where(
            and_(
                RegulatoryDocument.id.in_(document_ids),
                RegulatoryDocument.is_deleted == False,  # noqa: E712
            )
        )
        .order_by(RegulatoryDocument.first_found_at.desc())
    )
    result = await db.execute(stmt)
    documents = list(result.scalars().all())

    stats = {"analyzed": 0, "failed": 0, "skipped": 0}
    for document in documents:
        if (
            document.ai_analysis_status == "completed"
            and (document.ai_summary or "").strip()
        ):
            stats["skipped"] += 1
            continue

        success = await analyze_and_update(db, document)
        if success:
            stats["analyzed"] += 1
        else:
            stats["failed"] += 1
    logger.info("指定文档分析完成: %s", stats)
    return stats
