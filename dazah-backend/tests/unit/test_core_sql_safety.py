"""静态 SQL 片段中的字符串字面量必须转义。"""

from __future__ import annotations

import pytest

from app.core.sql_safety import quote_literal


def test_quote_literal_doubles_single_quotes() -> None:
    assert quote_literal("O'Brien") == "'O''Brien'"


def test_quote_literal_neutralizes_injection_payload() -> None:
    payload = "12%'); DELETE FROM production.pack; --"

    quoted = quote_literal(payload)

    assert quoted == "'12%''); DELETE FROM production.pack; --'"
    assert quoted.count("''") == 1


def test_quote_literal_rejects_nul() -> None:
    with pytest.raises(ValueError):
        quote_literal("bad\x00value")
