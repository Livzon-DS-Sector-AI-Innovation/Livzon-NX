"""Business modules cannot widen trusted page grants with legacy permissions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.platform.identity.data_scope import current_page_key
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.public_api import has_current_page_permission


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "page,module,permissions,actions,action,expected",
    [
        (None, "quality", ["operate"], [], None, False),
        ("quality:validation:validation-ai-review", "hr", ["operate"], [], None, False),
        (
            "quality:validation:validation-ai-review",
            "quality",
            ["query"],
            [],
            None,
            False,
        ),
        (
            "quality:validation:validation-ai-review",
            "quality",
            ["operate"],
            [],
            None,
            True,
        ),
        (
            "quality:validation:validation-ai-review",
            "quality",
            ["operate"],
            [],
            "delete",
            False,
        ),
        (
            "quality:validation:validation-ai-review",
            "quality",
            ["query"],
            ["delete"],
            "delete",
            False,
        ),
        (
            "quality:validation:validation-ai-review",
            "quality",
            ["operate"],
            ["delete"],
            "delete",
            True,
        ),
    ],
)
async def test_current_page_permission(
    monkeypatch, page, module, permissions, actions, action, expected
):
    service = AsyncMock(
        return_value=[
            SimpleNamespace(
                page_key="quality:validation:validation-ai-review",
                permissions=permissions,
                sensitive_actions=actions,
            )
        ]
    )
    monkeypatch.setattr(PagePermissionService, "effective_grants", service)
    token = current_page_key.set(page)
    try:
        assert (
            await has_current_page_permission(
                None, SimpleNamespace(), module, sensitive_action=action
            )
            is expected
        )
    finally:
        current_page_key.reset(token)


@pytest.mark.asyncio
async def test_sibling_page_grant_cannot_authorize_current_page(monkeypatch):
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    page_key="quality:deviations:deviation-ledger",
                    permissions=["operate"],
                ),
            ]
        ),
    )
    token = current_page_key.set("quality:validation:validation-ai-review")
    try:
        assert not await has_current_page_permission(None, SimpleNamespace(), "quality")
    finally:
        current_page_key.reset(token)
