"""Agent 服务令牌校验必须失败关闭且使用常量时间比较。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.agent.api import _bearer_token, require_service_token


def test_bearer_token_is_extracted() -> None:
    assert _bearer_token("Bearer service-token") == "service-token"
    assert _bearer_token("Basic abc") is None
    assert _bearer_token(None) is None


def test_matching_service_token_passes() -> None:
    require_service_token("service-token", "Bearer service-token")


@pytest.mark.parametrize(
    ("expected", "authorization"),
    [
        ("", "Bearer service-token"),
        ("service-token", None),
        ("service-token", "Bearer wrong-token"),
        ("service-token", "Basic service-token"),
        ("service-token", "Bearer "),
    ],
)
def test_invalid_service_token_is_rejected(
    expected: str, authorization: str | None
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_service_token(expected, authorization)

    assert exc_info.value.status_code == 401
