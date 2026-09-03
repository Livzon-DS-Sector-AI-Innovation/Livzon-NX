"""Cookie secure-flag must follow the FRONTEND_URL protocol.

HTTP deployments (bare-IP staging without TLS) must not mark auth cookies
Secure: browsers silently drop Secure cookies, which breaks the Feishu
OAuth state-cookie round trip and the SSO login cookie.
"""

from app.core.config import Settings


def test_cookie_secure_enabled_for_https_frontend() -> None:
    settings = Settings(
        APP_ENV="production",
        SECRET_KEY="test-secret",
        FRONTEND_URL="https://dazah.example.com",
    )
    assert settings.cookie_secure is True


def test_cookie_secure_disabled_for_http_frontend() -> None:
    settings = Settings(
        APP_ENV="production",
        SECRET_KEY="test-secret",
        FRONTEND_URL="http://180.76.112.99:3000",
    )
    assert settings.cookie_secure is False
