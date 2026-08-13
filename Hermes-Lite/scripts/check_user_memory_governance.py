#!/usr/bin/env python3
"""Emit a content-free health summary for Hermes user-memory storage."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

from services.memory_service import MemoryCipher, get_memory_db_path


def check_database(db_path: Path, cipher: MemoryCipher) -> dict[str, object]:
    issues: list[str] = []
    counts = {"entries": 0, "pending_jobs": 0, "failed_jobs": 0}
    if not db_path.exists():
        issues.append("database_missing")
        return {"ok": False, "issues": issues, "counts": counts}

    now = time.time()
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA secure_delete=ON")
        if int(connection.execute("PRAGMA secure_delete").fetchone()[0]) != 1:
            issues.append("secure_delete_disabled")
        if str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() != "wal":
            issues.append("wal_disabled")

        entries = connection.execute("SELECT content FROM user_memory_entries").fetchall()
        counts["entries"] = len(entries)
        for row in entries:
            ciphertext = str(row["content"])
            if not ciphertext.startswith("enc:v1:"):
                issues.append("plaintext_entry")
                break
            try:
                cipher.decrypt(ciphertext)
            except ValueError:
                issues.append("undecryptable_entry")
                break

        jobs = connection.execute(
            """SELECT status, created_at, expires_at, payload_ciphertext,
                      user_message, assistant_message, tool_evidence_json
                 FROM user_memory_jobs"""
        ).fetchall()
        counts["pending_jobs"] = sum(
            row["status"] in {"pending", "processing"} for row in jobs
        )
        counts["failed_jobs"] = sum(row["status"] == "failed" for row in jobs)
        for row in jobs:
            if any(
                str(row[name] or "") not in {"", "[]"}
                for name in ("user_message", "assistant_message", "tool_evidence_json")
            ):
                issues.append("plaintext_job_payload")
                break
            ciphertext = str(row["payload_ciphertext"] or "")
            if not ciphertext.startswith("enc:v1:"):
                issues.append("unencrypted_job_payload")
                break
            try:
                cipher.decrypt(ciphertext)
            except ValueError:
                issues.append("undecryptable_job")
                break
            if float(row["expires_at"] or 0) <= now:
                issues.append("expired_job")
                break
            if float(row["expires_at"] or 0) - float(row["created_at"] or 0) > 86_400:
                issues.append("job_retention_exceeds_24h")
                break

    return {"ok": not issues, "issues": sorted(set(issues)), "counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=get_memory_db_path())
    args = parser.parse_args()
    raw_keys = os.getenv("HERMES_USER_MEMORY_KEYS", "").strip()
    if not raw_keys:
        print(json.dumps({"ok": False, "issues": ["memory_keys_missing"]}))
        return 1
    try:
        result = check_database(args.db.resolve(), MemoryCipher(raw_keys))
    except (RuntimeError, sqlite3.Error):
        result = {"ok": False, "issues": ["governance_check_failed"]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
