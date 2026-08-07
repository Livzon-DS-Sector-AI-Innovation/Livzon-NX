from __future__ import annotations

import sqlite3
from pathlib import Path

from services.memory_service import UserMemoryRepository
from scripts.check_user_memory_governance import check_database


def test_governance_check_accepts_encrypted_database(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    repository = UserMemoryRepository(db_path=db_path)
    repository.job_counts()

    result = check_database(db_path, repository.cipher)

    assert result["ok"] is True
    assert result["issues"] == []


def test_governance_check_rejects_plaintext_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    repository = UserMemoryRepository(db_path=db_path)
    repository.job_counts()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """INSERT INTO user_memory_entries
               (id, tenant_id, user_id, category, content, content_hash,
                confidence, importance, first_seen, last_seen)
               VALUES ('id', 'tenant', 'user', 'preference', 'plaintext', 'hash',
                       1, 1, 1, 1)"""
        )

    result = check_database(db_path, repository.cipher)

    assert result["ok"] is False
    assert "plaintext_entry" in result["issues"]
