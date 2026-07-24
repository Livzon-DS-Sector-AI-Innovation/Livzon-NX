from __future__ import annotations

import hmac

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.platform.identity.hermes_api import _require_internal


def test_internal_token_is_required() -> None:
    settings = Settings(HERMES_INTERNAL_TOKEN="internal-test-token")
    with pytest.raises(HTTPException) as exc:
        _require_internal("Bearer wrong", settings)
    assert exc.value.status_code == 401


def test_internal_token_accepts_exact_bearer() -> None:
    settings = Settings(HERMES_INTERNAL_TOKEN="internal-test-token")
    assert _require_internal("Bearer internal-test-token", settings) is None


def test_internal_token_comparison_has_no_prefix_match() -> None:
    settings = Settings(HERMES_INTERNAL_TOKEN="internal-test-token")
    assert not hmac.compare_digest("internal-test", settings.HERMES_INTERNAL_TOKEN)
    with pytest.raises(HTTPException):
        _require_internal("Bearer internal-test", settings)
