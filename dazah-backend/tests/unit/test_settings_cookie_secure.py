"""Settings.cookie_secure：Secure 标志跟随 FRONTEND_URL 协议。

背景：生产 HTTP（裸 IP 无 TLS）部署下，硬编码 secure=True 会让浏览器
静默丢弃 auth cookie，飞书 OAuth 全链路不可用；改为按 FRONTEND_URL
协议判定，升级 HTTPS 后安全属性自动恢复。
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def _settings_with_frontend_url(frontend_url: str) -> Settings:
    return Settings(FRONTEND_URL=frontend_url, APP_ENV="production")


@pytest.mark.parametrize(
    ("frontend_url", "expected"),
    [
        ("https://gmp.example.com", True),
        ("http://180.76.112.99", False),
    ],
)
def test_cookie_secure_follows_frontend_url_protocol(
    frontend_url: str, expected: bool
) -> None:
    assert _settings_with_frontend_url(frontend_url).cookie_secure is expected
