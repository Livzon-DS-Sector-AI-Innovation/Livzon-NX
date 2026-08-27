"""MCP 写工具认证测试：未登录必须拒绝写操作。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.registration.mcp_tools import (
    registration_create_certificate,
    registration_create_fee,
)
from app.platform.identity.models import User
from app.platform.mcp.deps import reset_context, set_context


@pytest.fixture
async def mcp_no_user(db_session: AsyncSession) -> AsyncIterator[None]:
    """设置 MCP 上下文：有 DB 会话、无认证用户。"""
    db_token, user_token = set_context(db_session, user=None)
    yield
    reset_context(db_token, user_token)


@pytest.fixture
async def mcp_authed_user(db_session: AsyncSession) -> AsyncIterator[User]:
    """设置 MCP 上下文：有 DB 会话和认证用户。"""
    user = User(
        id=uuid.uuid4(),
        feishu_open_id="mcp-test-open-id",
        name="MCP测试用户",
        email="mcp-test@localhost",
    )
    db_token, user_token = set_context(db_session, user=user)
    yield user
    reset_context(db_token, user_token)


@pytest.mark.asyncio
async def test_create_fee_rejects_unauthenticated(mcp_no_user: None) -> None:
    with pytest.raises(AppException) as exc_info:
        await registration_create_fee(
            fee_type="检验费",
            amount=100.0,
            payment_status="未付",
            operator_name="匿名",
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_create_certificate_rejects_unauthenticated(mcp_no_user: None) -> None:
    with pytest.raises(AppException) as exc_info:
        await registration_create_certificate(
            certificate_name="GMP证书",
            operator_name="匿名",
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_create_fee_uses_authenticated_user_as_handler(
    mcp_authed_user: User,
) -> None:
    result = await registration_create_fee(
        fee_type="注册费",
        amount=200.0,
        payment_status="已付",
        operator_name="调用方自报名称",
    )
    assert "id" in result
    assert "已创建" in result["message"]


@pytest.mark.asyncio
async def test_create_certificate_with_authenticated_user(
    mcp_authed_user: User,
) -> None:
    result = await registration_create_certificate(
        certificate_name="CEP证书",
        operator_name="调用方自报名称",
    )
    assert "id" in result
    assert "已登记" in result["message"]
