"""Page operations retain data boundaries and cannot inherit legacy write grants."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import AppException
from app.modules.quality.api import deps, validation_review
from app.modules.quality.service import agent_queries
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)
from app.platform.identity.page_permissions import PagePermissionService


@pytest.fixture
def page_context(monkeypatch):
    user = SimpleNamespace(id=uuid4(), name="测试用户", role="user")
    context = [
        (
            current_page_key,
            current_page_key.set("quality:validation:validation-ai-review"),
        ),
        (current_page_actor, current_page_actor.set(user)),
        (current_page_data_scope, current_page_data_scope.set({"scope_type": "all"})),
    ]
    grant = SimpleNamespace(
        page_key="quality:validation:validation-ai-review",
        permissions=["access", "query", "operate"],
        sensitive_actions=[],
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    legacy = AsyncMock(
        return_value=["*", "quality:write", "quality:validation_qa:write"]
    )
    for target in [deps, validation_review, agent_queries]:
        monkeypatch.setattr(target, "resolve_user_permissions", legacy)
    yield user, grant, legacy
    for variable, token in reversed(context):
        variable.reset(token)


@pytest.mark.asyncio
async def test_page_edit_works_without_legacy_scope_and_revocation_denies_owner(
    page_context,
):
    user, grant, legacy = page_context
    legacy.return_value = []
    await deps.assert_quality_edit_scope(
        None, user, scope_permission="quality:validation_qa:write"
    )
    grant.permissions = ["access", "query"]
    legacy.return_value = ["*"]
    with pytest.raises(AppException, match="当前质量页面操作权限"):
        await deps.assert_quality_edit_scope(
            None, user, record=SimpleNamespace(created_by=user.id)
        )
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_page_edit_retains_record_department_scope(page_context, monkeypatch):
    from app.modules.quality import page_access

    user, _, legacy = page_context
    monkeypatch.setattr(
        page_access,
        "resolve_user_department_scope",
        AsyncMock(
            return_value=DepartmentScope(department_names={"质量部"}),
        ),
    )
    await deps.assert_quality_edit_scope(
        None, user, record=SimpleNamespace(department="质量部")
    )
    with pytest.raises(HTTPException) as denied:
        await deps.assert_quality_edit_scope(
            None, user, record=SimpleNamespace(department="生产部", created_by=user.id)
        )
    assert denied.value.status_code == 403
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_review_read_and_agent_list_use_page_scope_and_revocation(
    page_context, monkeypatch
):
    user, grant, legacy = page_context
    record = SimpleNamespace(created_by=uuid4())
    listing = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(agent_queries.validation_review, "list_review_records", listing)

    async def list_reviews():
        return await agent_queries.list_validation_reviews(
            None, keyword=None, status=None, review_mode=None, page=1, page_size=20
        )

    await validation_review._assert_review_view(None, user, record)
    assert await validation_review._can_view_all(None, user)
    await list_reviews()
    assert listing.await_args.kwargs["all_visible"] is True
    token = current_page_data_scope.set({"scope_type": "self"})
    try:
        assert not await validation_review._can_view_all(None, user)
        with pytest.raises(AppException):
            await validation_review._assert_review_view(None, user, record)
        await validation_review._assert_review_view(
            None, user, SimpleNamespace(created_by=user.id)
        )
        await list_reviews()
        assert listing.await_args.kwargs["all_visible"] is False
    finally:
        current_page_data_scope.reset(token)
    grant.permissions = []
    with pytest.raises(AppException):
        await validation_review._assert_review_view(
            None, user, SimpleNamespace(created_by=user.id)
        )
    listing.reset_mock()
    with pytest.raises(AppException):
        await list_reviews()
    listing.assert_not_awaited()
    legacy.assert_not_awaited()
