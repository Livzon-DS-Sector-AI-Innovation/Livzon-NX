from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import NotFoundException
from app.modules.registration import agent_tools
from app.modules.registration.service.knowledge import RegistrationKnowledgeService


@pytest.mark.asyncio
async def test_published_knowledge_read_does_not_commit_or_increment_views():
    db = SimpleNamespace(commit=AsyncMock())
    service = RegistrationKnowledgeService(db)
    article = SimpleNamespace(is_published=True)
    service.repository = SimpleNamespace(
        get_article_by_id=AsyncMock(return_value=article)
    )
    service._build_article_response = AsyncMock(return_value="content")
    assert await service.read_agent_article(uuid4()) == "content"
    db.commit.assert_not_awaited()
    service.repository.get_article_by_id.return_value = SimpleNamespace(
        is_published=False
    )
    with pytest.raises(NotFoundException):
        await service.read_agent_article(uuid4())
    service.repository.get_article_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await service.read_agent_article(uuid4())
    assert service._build_article_response.await_count == 1


@pytest.mark.asyncio
async def test_knowledge_read_preserves_source_scope_and_continuation(monkeypatch):
    article = SimpleNamespace(
        id=uuid4(),
        title="业务资料",
        content="abcdefgh",
        country="CN",
        product="API",
        published_at=None,
        updated_at=datetime(2026, 10, 10, tzinfo=UTC),
        source_url="https://example.org/source",
    )
    read = AsyncMock(return_value=article)
    monkeypatch.setattr(
        agent_tools,
        "RegistrationKnowledgeService",
        lambda db: SimpleNamespace(read_agent_article=read),
    )
    result = await agent_tools.read_knowledge_article(
        SimpleNamespace(db=object()),
        agent_tools.KnowledgeReadInput(article_id=article.id, offset=2, limit=3),
    )
    read.assert_awaited_once_with(article.id)
    assert result["content"] == "cde" and result["next_offset"] == 5
    assert result["truncated"] and result["total_characters"] == 8
    assert result["source_url"] == article.source_url and result["country"] == "CN"
    final = await agent_tools.read_knowledge_article(
        SimpleNamespace(db=object()),
        agent_tools.KnowledgeReadInput(article_id=article.id, offset=5, limit=3),
    )
    assert final["content"] == "fgh" and final["next_offset"] is None


@pytest.mark.parametrize(
    "fields", [{"offset": -1}, {"limit": 12001}, {"user_id": "spoof"}]
)
def test_knowledge_input_rejects_invalid_ranges_and_authority(fields):
    with pytest.raises(ValidationError):
        agent_tools.KnowledgeReadInput(article_id=uuid4(), **fields)
