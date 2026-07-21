from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REDACTED_VALUE = "***"
DEFAULT_SENSITIVE_TOKENS = frozenset(
    {
        "access_token",
        "api_key",
        "app_secret",
        "authorization",
        "cookie",
        "credential",
        "encrypt_key",
        "key",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "session_token",
        "token",
    }
)


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return any(
        normalized == token
        or normalized.endswith(f"_{token}")
        or normalized.startswith(f"{token}_")
        for token in DEFAULT_SENSITIVE_TOKENS
    )


def redact_sensitive(
    value: Any,
    *,
    max_depth: int = 12,
    max_string_length: int | None = None,
) -> Any:
    """Return a JSON-compatible copy with secrets masked recursively."""
    return _redact_value(
        value,
        depth=0,
        max_depth=max_depth,
        max_string_length=max_string_length,
    )


def _redact_value(
    value: Any,
    *,
    depth: int,
    max_depth: int,
    max_string_length: int | None,
) -> Any:
    if depth >= max_depth:
        return "[maximum depth reached]"
    if isinstance(value, Mapping):
        return {
            str(key): (
                REDACTED_VALUE
                if is_sensitive_key(key)
                else _redact_value(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_string_length=max_string_length,
                )
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [
            _redact_value(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_string_length=max_string_length,
            )
            for item in value
        ]
    if isinstance(value, bytes):
        return f"[bytes:{len(value)}]"
    if isinstance(value, str) and max_string_length is not None:
        if len(value) > max_string_length:
            return f"{value[:max_string_length]}[truncated]"
    return value
