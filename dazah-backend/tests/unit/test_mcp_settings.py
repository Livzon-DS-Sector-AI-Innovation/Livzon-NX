"""Legacy MCP cannot be re-enabled by shared keys or stale opt-in settings."""

from __future__ import annotations

import pytest

from app.platform.mcp.middleware import validate_mcp_settings


def test_disabled_by_default_rejects_mount() -> None:
    with pytest.raises(RuntimeError, match="disabled"):
        validate_mcp_settings(enabled=False, api_keys="key-a")


def test_enabled_without_keys_rejects_mount() -> None:
    with pytest.raises(RuntimeError, match="retired"):
        validate_mcp_settings(enabled=True, api_keys=" , ")


def test_old_valid_keys_cannot_reactivate_the_transport() -> None:
    with pytest.raises(RuntimeError, match="retired"):
        validate_mcp_settings(enabled=True, api_keys=" key-a , key-b ,")
