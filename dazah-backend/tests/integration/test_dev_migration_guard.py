"""Exercise the CLI read boundary against the configured dedicated test DB."""

from unittest.mock import Mock

import pytest

from app.core import dev_migration as guard


def test_database_checks_are_read_only_and_upgrade_noop_releases_lock(monkeypatch):
    with guard._database() as (_, connection):
        assert connection.exec_driver_sql(
            "SHOW transaction_read_only"
        ).scalar_one() == "on"
    before = guard.check_current()
    assert not before.pending_revisions
    assert "test" in before.database.lower()
    apply = Mock()
    monkeypatch.setattr(guard.command, "upgrade", apply)
    assert guard.execute_upgrade(before.confirmation) == before
    apply.assert_not_called()
    # A second connection can acquire the lock after the first socket closes.
    assert guard.execute_upgrade(before.confirmation) == before
    assert guard.check_current() == before


def test_database_mismatched_approval_cannot_change_current_revision(monkeypatch):
    before = guard.check_current()
    apply = Mock()
    monkeypatch.setattr(guard.command, "upgrade", apply)
    with pytest.raises(guard.MigrationGuardError, match="does not match"):
        guard.execute_upgrade(before.confirmation + "-unreviewed")
    apply.assert_not_called()
    assert guard.check_current() == before
