"""回归：视图计数 bulk UPDATE + commit 后必须先 refresh 再读 ORM 属性。

increment_view_count 使用 session.execute(update(...)) 绕过 ORM 同步，commit 后
updated_at 等列会被标记过期；若在 async 上下文直接访问属性会触发
sqlalchemy.exc.MissingGreenlet。本测试用“过期即抛错”的假对象锁定
service 层的 refresh 调用。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.models import KnowledgeArticle, KnowledgeCategory
from app.modules.registration.service.knowledge import RegistrationKnowledgeService


class _ExpiredArticleError(RuntimeError):
    pass


class _FakeArticle:
    """模拟 bulk UPDATE + commit 后属性过期、未 refresh 即读取报错的 ORM 对象。"""

    def __init__(self, **values: object) -> None:
        object.__setattr__(self, "_values", values)
        object.__setattr__(self, "_expired", False)

    @property
    def expired(self) -> bool:
        return object.__getattribute__(self, "_expired")

    def expire(self) -> None:
        object.__setattr__(self, "_expired", True)

    def refresh(self) -> None:
        object.__setattr__(self, "_expired", False)

    def __getattr__(self, name: str) -> object:
        values = object.__getattribute__(self, "_values")
        if name not in values:
            raise AttributeError(name)
        if object.__getattribute__(self, "_expired"):
            raise _ExpiredArticleError(
                "greenlet_spawn has not been called; can't call await_only() here."
            )
        return values[name]


def _make_article() -> _FakeArticle:
    now = datetime(2026, 7, 18, 8, 14, 27)
    return _FakeArticle(
        id=uuid4(),
        title="化学药品注册分类改革工作方案解读",
        category_id=uuid4(),
        content="正文",
        tags="化学药品",
        country="中国",
        product=None,
        is_published=True,
        published_at=now,
        author="admin",
        view_count=10,
        source_url=None,
        created_at=now,
        updated_at=now,
    )


def _make_service(
    article: _FakeArticle,
) -> tuple[RegistrationKnowledgeService, SimpleNamespace]:
    session = SimpleNamespace()

    async def _commit() -> None:
        article.expire()

    async def _refresh(target: _FakeArticle) -> None:
        target.refresh()

    session.commit = AsyncMock(side_effect=_commit)
    session.refresh = AsyncMock(side_effect=_refresh)

    service = RegistrationKnowledgeService(session)  # type: ignore[arg-type]
    repo = service.repository
    repo.get_article_by_id = AsyncMock(return_value=article)  # type: ignore[method-assign]
    repo.increment_view_count = AsyncMock()  # type: ignore[method-assign]
    repo.get_category_by_id = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(name="法规解读")
    )
    repo.list_attachments_by_article = AsyncMock(return_value=[])  # type: ignore[method-assign]
    repo.list_comments_by_article = AsyncMock(return_value=[])  # type: ignore[method-assign]
    return service, session


@pytest.mark.asyncio
async def test_get_article_detail_refreshes_after_view_count_commit() -> None:
    article = _make_article()
    service, session = _make_service(article)

    detail = await service.get_article_detail(article.id)

    assert detail.title == article._values["title"]
    assert detail.view_count == 10
    session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_article_response_refreshes_after_view_count_commit() -> None:
    article = _make_article()
    service, session = _make_service(article)

    response = await service.get_article(article.id)

    assert response.title == article._values["title"]
    session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_article_detail_without_refresh_would_fail() -> None:
    """反向锁定：若去掉 refresh（commit 后未刷新），读属性必然抛错。"""
    article = _make_article()
    service, session = _make_service(article)

    async def _no_refresh(_target: _FakeArticle) -> None:
        return None

    session.refresh = AsyncMock(side_effect=_no_refresh)

    with pytest.raises(_ExpiredArticleError):
        await service.get_article_detail(article.id)


async def _seed_article(
    db_session: AsyncSession,
) -> tuple[KnowledgeCategory, KnowledgeArticle]:
    category = KnowledgeCategory(name="审查测试分类", sort_order=0)
    db_session.add(category)
    await db_session.flush()
    article = KnowledgeArticle(
        title="审查测试文章",
        category_id=category.id,
        content="正文",
        is_published=True,
    )
    db_session.add(article)
    await db_session.flush()
    # client fixture 使用独立连接（NullPool），必须提交后路由侧才能读到种子数据。
    await db_session.commit()
    return category, article


async def _cleanup_article(
    db_session: AsyncSession, category: KnowledgeCategory, article: KnowledgeArticle
) -> None:
    # service 内部会真实 commit（bulk UPDATE + refresh 语义必须落到真实库），
    # fixture 的收尾 rollback 拦不住已提交事务，故显式清理种子数据。
    await db_session.execute(
        delete(KnowledgeArticle).where(KnowledgeArticle.id == article.id)
    )
    await db_session.execute(
        delete(KnowledgeCategory).where(KnowledgeCategory.id == category.id)
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_article_detail_route_200_and_view_count_increments_per_request(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """路由级成功路径（AGENTS.md 接口 500 防范）：真实调用路由，断言
    200/响应 Schema/浏览计数递增。"""
    category, article = await _seed_article(db_session)
    try:
        first = await client.get(
            f"/api/v1/registration/knowledge/articles/{article.id}"
        )
        assert first.status_code == 200
        data = first.json()["data"]
        assert data["title"] == "审查测试文章"
        assert data["category_name"] == "审查测试分类"
        first_view_count = data["view_count"]

        second = await client.get(
            f"/api/v1/registration/knowledge/articles/{article.id}"
        )
        assert second.status_code == 200
        assert second.json()["data"]["view_count"] == first_view_count + 1
    finally:
        await _cleanup_article(db_session, category, article)


@pytest.mark.asyncio
async def test_article_detail_route_missing_article_returns_404(
    client: AsyncClient,
) -> None:
    response = await client.get(f"/api/v1/registration/knowledge/articles/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == 404
