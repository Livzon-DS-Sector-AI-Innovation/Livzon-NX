from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.llm import LLMRateLimitError
from app.modules.registration.service import knowledge_ai


def _attachment(*, file_path: str = "notes.txt") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        file_path=file_path,
        file_name="法规笔记.txt",
        content_type="text/plain",
        ai_summary=None,
    )


def _settings(upload_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(UPLOAD_DIR=str(upload_dir))


@pytest.mark.asyncio
async def test_generate_attachment_summary_reads_file_and_refetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachment = _attachment()
    (tmp_path / attachment.file_path).write_text(
        "质量体系文件的核心要求是可追溯。", encoding="utf-8"
    )
    first = SimpleNamespace(scalar_one_or_none=lambda: attachment)
    second = SimpleNamespace(
        scalar_one=lambda: SimpleNamespace(ai_summary="摘要\n\n关键要点：可追溯")
    )
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[first, second]), flush=AsyncMock()
    )
    monkeypatch.setattr(knowledge_ai, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(
        type(knowledge_ai.llm_client),
        "chat_json",
        AsyncMock(return_value={"summary": "摘要", "key_points": "可追溯"}),
    )

    result = await knowledge_ai.generate_attachment_summary(db, attachment.id)

    assert result == "摘要\n\n关键要点：可追溯"
    assert attachment.ai_summary == result
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_attachment_summary_retries_rate_limit_and_handles_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attachment = _attachment(file_path="missing.txt")
    first = SimpleNamespace(scalar_one_or_none=lambda: attachment)
    second = SimpleNamespace(
        scalar_one=lambda: SimpleNamespace(ai_summary="基于文件名的摘要")
    )
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[first, second]), flush=AsyncMock()
    )
    chat_json = AsyncMock(
        side_effect=[
            LLMRateLimitError("busy", status_code=429),
            {"summary": "基于文件名的摘要"},
        ]
    )
    monkeypatch.setattr(knowledge_ai, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(type(knowledge_ai.llm_client), "chat_json", chat_json)
    monkeypatch.setattr(knowledge_ai.asyncio, "sleep", AsyncMock())

    result = await knowledge_ai.generate_attachment_summary(db, attachment.id)

    assert result == "基于文件名的摘要"
    assert chat_json.await_count == 2


@pytest.mark.asyncio
async def test_generate_attachment_summary_raises_for_unknown_attachment() -> None:
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )

    with pytest.raises(Exception, match="附件"):
        await knowledge_ai.generate_attachment_summary(db, uuid4())


def test_extract_text_from_supported_formats(tmp_path: Path) -> None:
    assert knowledge_ai._extract_text_from_file("notes.txt", "文本".encode()) == "文本"
    assert (
        knowledge_ai._extract_text_from_file("notes.md", "# 标题".encode()) == "# 标题"
    )
    assert (
        knowledge_ai._extract_text_from_file("notes.unknown", b"fallback") == "fallback"
    )
    assert knowledge_ai._extract_text_from_file("broken.docx", b"not-a-docx") == ""


@pytest.mark.asyncio
async def test_extract_article_from_content_returns_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        knowledge_ai,
        "_extract_text_from_file",
        lambda _name, _content: "正文" * 4000,
    )
    monkeypatch.setattr(
        type(knowledge_ai.llm_client),
        "chat_json",
        AsyncMock(
            return_value={
                "title": "知识文章",
                "content": "正文",
                "tags": "质量,追溯",
                "country": "中国",
                "summary": "摘要",
            }
        ),
    )

    result = await knowledge_ai.extract_article_from_content(
        "notes.txt", "text/plain", b"secret file bytes"
    )

    assert result["title"] == "知识文章"
    assert result["file_base64"]
    assert result["file_name"] == "notes.txt"
