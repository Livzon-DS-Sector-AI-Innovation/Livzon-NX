"""Business knowledge and page hints against the dedicated PostgreSQL database."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import NotFoundException
from app.modules.agent.page_context import resolve_page_context
from app.modules.registration.agent_tools import (
    KnowledgeReadInput,
    read_knowledge_article,
)
from app.modules.registration.models.knowledge import (
    KnowledgeArticle,
    KnowledgeCategory,
)
from app.platform.identity.models import User
from app.platform.identity.page_policy import PAGE_DEFINITIONS


@pytest.mark.asyncio
async def test_published_body_continuation_is_read_only_and_drafts_are_hidden(
    db_session,
):
    category = KnowledgeCategory(name=f"acceptance-{uuid4().hex}")
    db_session.add(category)
    await db_session.flush()
    article = KnowledgeArticle(
        title="验收参考资料",
        category_id=category.id,
        content="abcdefgh",
        is_published=True,
        view_count=7,
        country="CN",
        product="acceptance",
    )
    draft = KnowledgeArticle(
        title="未发布验收资料",
        category_id=category.id,
        content="private",
        is_published=False,
    )
    db_session.add_all([article, draft])
    await db_session.flush()
    updated_at = article.updated_at
    context = SimpleNamespace(db=db_session)
    result = await read_knowledge_article(
        context,
        KnowledgeReadInput(article_id=article.id, offset=2, limit=3),
    )
    assert result["content"] == "cde" and result["next_offset"] == 5
    assert result["country"] == "CN" and result["total_characters"] == 8
    tail = await read_knowledge_article(
        context,
        KnowledgeReadInput(article_id=article.id, offset=5, limit=3),
    )
    assert tail["content"] == "fgh" and tail["next_offset"] is None
    with pytest.raises(NotFoundException):
        await read_knowledge_article(context, KnowledgeReadInput(article_id=draft.id))
    persisted = (
        await db_session.execute(
            select(KnowledgeArticle.view_count, KnowledgeArticle.updated_at).where(
                KnowledgeArticle.id == article.id
            )
        )
    ).one()
    assert persisted == (7, updated_at)
    assert db_session.in_transaction(), "Reader must not commit the fixture transaction"


@pytest.mark.asyncio
async def test_page_context_uses_live_database_permissions_and_drops_private_filters(
    db_session,
):
    user = User(name="页面上下文验收", role="admin", tenant_key="local")
    db_session.add(user)
    await db_session.flush()
    page = next(p for p in PAGE_DEFINITIONS if p.page_key == "registration:knowledge")
    result = await resolve_page_context(
        db_session,
        user=user,
        hint={
            "route_path": page.route_path,
            "filters": {"keyword": "验收", "token": "discard"},
        },
    )
    assert result is not None and result.page_key == page.page_key
    assert result.filters == {"keyword": "验收"}
    assert (
        await resolve_page_context(
            db_session,
            user=user,
            hint={"route_path": "/settings"},
        )
        is None
    )
    user.role = "user"
    await db_session.flush()
    assert (
        await resolve_page_context(
            db_session,
            user=user,
            hint={"route_path": page.route_path},
        )
        is None
    )
