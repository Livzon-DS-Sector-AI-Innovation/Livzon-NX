"""HR 员工档案页面访问校验（hr:employee:read）测试。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.hr.api import _assert_employee_page_access


class FakeUser:
    id = "00000000-0000-0000-0000-00000000f001"


async def _fake_resolve(db, user_id):
    return _fake_resolve.perms


@pytest.mark.asyncio
async def test_employee_access_allows_hr_write(monkeypatch) -> None:
    """hr:write（人力资源部）→ 通过。"""
    _fake_resolve.perms = ["hr:read", "hr:write"]
    monkeypatch.setattr(
        "app.platform.identity.rbac.resolve_user_permissions", _fake_resolve
    )
    await _assert_employee_page_access(None, FakeUser())


@pytest.mark.asyncio
async def test_employee_access_allows_subscope_code(monkeypatch) -> None:
    """hr:employee:read → 通过。"""
    _fake_resolve.perms = ["hr:read", "hr:employee:read"]
    monkeypatch.setattr(
        "app.platform.identity.rbac.resolve_user_permissions", _fake_resolve
    )
    await _assert_employee_page_access(None, FakeUser())


@pytest.mark.asyncio
async def test_employee_access_allows_wildcard(monkeypatch) -> None:
    """通配（super_admin）→ 通过。"""
    _fake_resolve.perms = ["*"]
    monkeypatch.setattr(
        "app.platform.identity.rbac.resolve_user_permissions", _fake_resolve
    )
    await _assert_employee_page_access(None, FakeUser())


@pytest.mark.asyncio
async def test_employee_access_forbidden_read_only(monkeypatch) -> None:
    """仅 hr:read（人事查看员）→ 403（员工档案仅人力资源部）。"""
    _fake_resolve.perms = ["hr:read"]
    monkeypatch.setattr(
        "app.platform.identity.rbac.resolve_user_permissions", _fake_resolve
    )
    with pytest.raises(HTTPException) as exc:
        await _assert_employee_page_access(None, FakeUser())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_employee_access_forbidden_no_login() -> None:
    """未登录 → 401。"""
    with pytest.raises(HTTPException) as exc:
        await _assert_employee_page_access(None, None)
    assert exc.value.status_code == 401
