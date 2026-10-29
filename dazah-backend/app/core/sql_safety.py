"""Helpers for safely embedding values into static SQL fragments.

Prefer bound parameters everywhere. Some legacy Feishu sync jobs still build
``VALUES`` lists as text; the helpers below make that path safe by escaping
quotes and rejecting NUL characters instead of interpolating raw cell content.
"""

from __future__ import annotations


def quote_literal(value: str) -> str:
    """Return a single-quoted PostgreSQL string literal for ``value``.

    Standard-conforming strings are enabled in PostgreSQL, so doubling single
    quotes is sufficient and backslashes stay literal. NUL cannot be stored in
    PostgreSQL text and is rejected instead of being silently dropped.
    """
    if "\x00" in value:
        raise ValueError("SQL literal must not contain NUL")
    return "'" + value.replace("'", "''") + "'"
