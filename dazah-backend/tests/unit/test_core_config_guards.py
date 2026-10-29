"""生产环境必须拒绝不安全的默认密钥与开发开关。"""

from __future__ import annotations

import pytest

from app.core.config import Settings

_SAFE_PRODUCTION = {
    "APP_ENV": "production",
    "SECRET_KEY": "a" * 40,
    "ENCRYPTION_KEY": "b" * 44,
    "LLM_ENCRYPTION_KEY": "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=",
    "FRONTEND_URL": "https://dazah.example.com",
    "SSO_ADMIN_IDENTIFIERS": "ou_admin",
}


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {**_SAFE_PRODUCTION, **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_safe_production_configuration_passes() -> None:
    _settings().check()


def test_production_rejects_placeholder_secret_key() -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _settings(SECRET_KEY="change-me-in-production").check()


def test_production_rejects_short_secret_key() -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _settings(SECRET_KEY="short-secret").check()


def test_production_rejects_dev_bypass_auth() -> None:
    with pytest.raises(RuntimeError, match="DEV_BYPASS_AUTH"):
        _settings(DEV_BYPASS_AUTH=True).check()


@pytest.mark.parametrize("environment", ["development", "production"])
def test_legacy_mcp_cannot_be_enabled_even_with_valid_keys(environment) -> None:
    with pytest.raises(RuntimeError, match="MCP_ENABLED"):
        _settings(
            APP_ENV=environment, MCP_ENABLED=True, MCP_AGENT_API_KEYS="synthetic"
        ).check()


@pytest.mark.parametrize("key", [None, "", "invalid"])
def test_production_rejects_missing_or_invalid_llm_encryption_key(key) -> None:
    with pytest.raises(RuntimeError, match="LLM_ENCRYPTION_KEY"):
        _settings(LLM_ENCRYPTION_KEY=key).check()


def test_production_requires_explicit_allow_for_local_login() -> None:
    with pytest.raises(RuntimeError, match="ALLOW_PRODUCTION_LOCAL_LOGIN"):
        _settings(LOCAL_LOGIN_MODE="enabled").check()

    _settings(
        LOCAL_LOGIN_MODE="enabled",
        ALLOW_PRODUCTION_LOCAL_LOGIN=True,
        BOOTSTRAP_ADMIN_USERNAME="admin",
        BOOTSTRAP_ADMIN_PASSWORD="a-strong-password",
    ).check()


def test_development_still_allows_dev_bypass() -> None:
    Settings(
        _env_file=None,
        APP_ENV="development",
        DEV_BYPASS_AUTH=True,
        SECRET_KEY="dev",
        FRONTEND_URL="http://localhost:3000",
    ).check()
