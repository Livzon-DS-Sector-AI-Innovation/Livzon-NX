"""Knowledge AI service for extracting structured content from uploaded files."""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundException
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.modules.registration.models.knowledge import KnowledgeAttachment

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM_PROMPT = """你是制药注册领域的知识管理助手。
用户会上传法规文件、学习资料等附件内容，你需要从中提取结构化信息，帮助用户快速创建知识库文章。"""

EXTRACT_USER_TEMPLATE = """请根据以下文件内容，提取并生成知识库文章的结构化信息。

文件名：{file_name}
文件类型：{content_type}

文件内容（截取前6000字符）：
{content}

请以 JSON 格式返回，包含以下字段：
{{
  "title": "文章标题（简洁明了，不超过50字）",
  "content": "文章正文（Markdown格式，包含概述、核心要点、关键结论等结构化内容）",
  "tags": "标签（逗号分隔，3-5个关键词）",
  "country": "适用国家（如美国/欧盟/中国/国际，无法判断则为空）",
  "summary": "整体概述（100字以内）"
}}"""


def _extract_text_from_file(file_name: str, file_content: bytes) -> str:
    """Extract text content from various file formats."""
    ext = Path(file_name).suffix.lower()

    try:
        if ext == ".pdf":
            # PyMuPDF is a runtime dependency, but the package does not expose
            # importable mypy metadata in the CI environment.
            import pymupdf  # type: ignore[import-not-found]

            pdf_doc: Any = pymupdf.open(stream=file_content, filetype="pdf")
            text_parts: list[str] = []
            for page in pdf_doc:
                text_parts.append(page.get_text())
            return "\n".join(text_parts)

        elif ext in (".doc", ".docx"):
            import io

            import docx

            word_doc = docx.Document(io.BytesIO(file_content))
            return "\n".join(para.text for para in word_doc.paragraphs)

        elif ext == ".md":
            return file_content.decode("utf-8", errors="ignore")

        elif ext in (".txt", ".text"):
            return file_content.decode("utf-8", errors="ignore")

        else:
            return file_content.decode("utf-8", errors="ignore")

    except Exception as e:
        logger.exception("Failed to extract text from %s: %s", file_name, e)
        return ""


async def extract_article_from_content(
    file_name: str,
    content_type: str,
    file_content: bytes,
) -> dict[str, Any]:
    """Extract structured article data from uploaded file content using LLM.

    Returns:
        Dict with keys: title, content, tags, country, summary, file_base64, file_name,
        content_type
    """
    text_content = _extract_text_from_file(file_name, file_content)

    if len(text_content) > 6000:
        text_content = text_content[:6000]

    if not text_content.strip():
        text_content = (
            f"文件名：{file_name}\n文件类型：{content_type}\n"
            "（无法提取文本内容，请基于文件名生成合理的文章结构）"
        )

    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": EXTRACT_USER_TEMPLATE.format(
                file_name=file_name,
                content_type=content_type,
                content=text_content,
            ),
        },
    ]

    try:
        result: dict[str, Any] = await llm_client.chat_json(
            messages,
            expected_keys=["title", "content"],
            temperature=0.3,
        )
    except LLMConfigError:
        logger.warning("AI 服务尚未配置，知识库文章提取跳过")
        raise
    except LLMOutputError:
        logger.exception("LLM 输出格式错误，文件: %s", file_name)
        raise
    except LLMProviderError:
        logger.exception("LLM 服务调用失败，文件: %s", file_name)
        raise
    except LLMRateLimitError:
        logger.exception("LLM 速率限制，文件: %s", file_name)
        raise

    return {
        "title": result.get("title", file_name),
        "content": result.get("content", ""),
        "tags": result.get("tags", ""),
        "country": result.get("country", ""),
        "summary": result.get("summary", ""),
        "file_base64": base64.b64encode(file_content).decode("ascii"),
        "file_name": file_name,
        "content_type": content_type,
    }


SUMMARIZE_SYSTEM_PROMPT = """你是制药注册领域的知识管理助手。
用户会上传附件文件，你需要为其生成简洁准确的结构化摘要，帮助用户快速了解文件内容。"""

SUMMARIZE_USER_TEMPLATE = """请为以下附件生成结构化摘要。

文件名：{file_name}
文件类型：{content_type}

文件内容（截取前6000字符）：
{content}

请以 JSON 格式返回，包含以下字段：
{{
  "summary": "结构化摘要（200字以内，包含文件主题、核心内容、关键要点）",
  "key_points": "关键要点（逗号分隔，3-5个要点）"
}}"""


async def generate_attachment_summary(
    db: AsyncSession,
    attachment_id: uuid.UUID,
) -> str:
    """为附件生成 AI 摘要，更新 ai_summary 字段并返回摘要文本。"""
    result = await db.execute(
        select(KnowledgeAttachment).where(KnowledgeAttachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise NotFoundException("附件", str(attachment_id))

    # 尝试从磁盘读取文件内容
    file_content = b""
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR)
    file_path = upload_dir / attachment.file_path
    if file_path.exists():
        try:
            file_content = await asyncio.to_thread(file_path.read_bytes)
        except OSError as e:
            logger.warning("无法读取附件文件 %s: %s", file_path, e)

    # 提取文本内容
    if file_content:
        text_content = _extract_text_from_file(attachment.file_name, file_content)
    else:
        text_content = ""

    if len(text_content) > 6000:
        text_content = text_content[:6000]

    if not text_content.strip():
        text_content = (
            f"文件名：{attachment.file_name}\n"
            f"文件类型：{attachment.content_type}\n"
            "（无法提取文本内容，请基于文件名生成合理摘要）"
        )

    messages = [
        {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": SUMMARIZE_USER_TEMPLATE.format(
                file_name=attachment.file_name,
                content_type=attachment.content_type,
                content=text_content,
            ),
        },
    ]

    # LLM 调用，带 3 次重试（指数退避）
    llm_result: dict[str, Any] = {}
    max_retries = 3
    for attempt in range(max_retries):
        try:
            llm_result = await llm_client.chat_json(
                messages,
                expected_keys=["summary"],
                temperature=0.3,
            )
            break
        except LLMRateLimitError:
            if attempt == max_retries - 1:
                logger.warning(
                    "LLM 速率限制，附件摘要生成失败: %s", attachment.file_name
                )
                raise
            await asyncio.sleep(2**attempt)
        except LLMConfigError:
            logger.warning("AI 服务尚未配置，附件摘要生成跳过")
            raise
        except LLMOutputError:
            logger.exception("LLM 输出格式错误，附件: %s", attachment.file_name)
            raise
        except LLMProviderError:
            logger.exception("LLM 服务调用失败，附件: %s", attachment.file_name)
            raise

    summary = llm_result.get("summary", "")
    key_points = llm_result.get("key_points", "")
    full_summary = summary
    if key_points:
        full_summary = f"{summary}\n\n关键要点：{key_points}"

    # 更新 ai_summary 字段（UPDATE 后必须 select re-fetch）
    attachment.ai_summary = full_summary
    await db.flush()

    re_result = await db.execute(
        select(KnowledgeAttachment).where(KnowledgeAttachment.id == attachment_id)
    )
    updated = re_result.scalar_one()
    return updated.ai_summary or ""
