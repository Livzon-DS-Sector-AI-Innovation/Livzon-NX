"""Audit retention policy: high-volume requests short, security evidence long."""

from types import SimpleNamespace

import pytest

from app.platform.audit import retention


@pytest.mark.asyncio
async def test_security_audit_is_retained_for_three_years(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    async def _purge(category: str, days: int) -> int:
        calls.append((category, days))
        return 0

    monkeypatch.setattr(retention, "purge_expired_audit_logs", _purge)
    monkeypatch.setattr(
        retention,
        "get_settings",
        lambda: SimpleNamespace(
            USER_OPERATION_AUDIT_RETENTION_DAYS=30,
            AUDIT_NON_OPERATION_RETENTION_DAYS=1095,
        ),
    )

    await retention.run_audit_retention()

    assert calls[0] == ("operations", 30)
    assert set(calls[1:]) == {
        (category, 1095) for category in retention.NON_OPERATION_CATEGORIES
    }


@pytest.mark.asyncio
async def test_zero_disables_security_audit_deletion(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    async def _purge(category: str, days: int) -> int:
        calls.append((category, days))
        return 0

    monkeypatch.setattr(retention, "purge_expired_audit_logs", _purge)
    monkeypatch.setattr(
        retention,
        "get_settings",
        lambda: SimpleNamespace(
            USER_OPERATION_AUDIT_RETENTION_DAYS=30,
            AUDIT_NON_OPERATION_RETENTION_DAYS=0,
        ),
    )

    await retention.run_audit_retention()

    assert calls == [("operations", 30)]
