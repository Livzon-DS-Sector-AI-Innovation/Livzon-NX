"""Durable Feishu control-plane state and safe lark-cli process execution.

This module deliberately contains no shell invocation.  The model can only
select arguments for the single, fixed ``lark-cli`` executable.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken


ALLOWED_ROOT_COMMANDS = frozenset(
    {
        "api",
        "base",
        "docs",
        "drive",
        "im",
        "markdown",
        "mindnotes",
        "minutes",
        "note",
        "schema",
        "sheets",
        "slides",
        "skills",
        "whiteboard",
        "whoami",
        "wiki",
    }
)
CONTROL_COMMANDS = frozenset({"auth", "config", "doctor", "skill"})
SHELL_TOKENS = frozenset({";", "|", "&&", "||", ">", "<", "`", "$(", "\r", "\n", "\x00"})
HIGH_RISK_WORDS = frozenset(
    {"delete", "remove", "move", "permission", "owner", "ownership", "share", "replace", "version"}
)
MEDIUM_RISK_WORDS = frozenset({"create", "update", "write", "edit", "patch", "set", "insert", "copy"})
PROHIBITED_DECISIONS = frozenset({"approve", "approval", "reject", "discipline", "处分", "审批", "驳回"})
RUNTIME_METRICS: dict[str, int] = {
    "cli_calls": 0,
    "cli_failures": 0,
    "cli_last_latency_ms": 0,
}
INBOUND_RECEIPT_RETENTION_SECONDS = 7 * 24 * 60 * 60
INBOUND_PROCESSING_LEASE_SECONDS = 60 * 60


def _home() -> Path:
    return Path(os.getenv("HERMES_HOME", "/data/hermes")).resolve()


def _db_path() -> Path:
    return _home() / "feishu-control.sqlite3"


def _cli_home() -> Path:
    return Path(os.getenv("HERMES_FEISHU_TMPFS", "/run/hermes-feishu")).resolve() / "active"


def _connect() -> sqlite3.Connection:
    _home().mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def initialize_store() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS confirmations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                app_id TEXT NOT NULL,
                resource TEXT NOT NULL,
                action TEXT NOT NULL,
                request_json TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                risk TEXT NOT NULL,
                status TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS grants (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                app_id TEXT NOT NULL,
                resource TEXT NOT NULL,
                action TEXT NOT NULL,
                expires_at REAL NOT NULL,
                revoked_at REAL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_outbox (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS delivery_outbox (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                chat_id TEXT NOT NULL,
                delivery_type TEXT NOT NULL,
                content TEXT NOT NULL,
                card_json TEXT NOT NULL,
                reply_to TEXT,
                metadata_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL,
                message_id TEXT,
                last_error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inbound_message_receipts (
                message_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                claimed_at REAL NOT NULL,
                completed_at REAL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_confirmation_request
                ON confirmations(user_id, request_hash, status);
            """
        )


def claim_inbound_message(
    message_id: str,
    *,
    now: float | None = None,
    retention_seconds: float = INBOUND_RECEIPT_RETENTION_SECONDS,
    processing_lease_seconds: float = INBOUND_PROCESSING_LEASE_SECONDS,
) -> bool:
    """Atomically claim one Feishu message across workers and restarts."""
    normalized = message_id.strip()
    if not normalized:
        return True
    claimed_at = time.time() if now is None else now
    retention_cutoff = claimed_at - retention_seconds
    lease_cutoff = claimed_at - processing_lease_seconds
    with _connect() as conn:
        conn.execute(
            """
            DELETE FROM inbound_message_receipts
            WHERE status='completed' AND completed_at<?
            """,
            (retention_cutoff,),
        )
        cursor = conn.execute(
            """
            INSERT INTO inbound_message_receipts(
                message_id, status, claimed_at, completed_at
            )
            VALUES (?, 'processing', ?, NULL)
            ON CONFLICT(message_id) DO UPDATE SET
                status='processing',
                claimed_at=excluded.claimed_at,
                completed_at=NULL
            WHERE inbound_message_receipts.status='processing'
              AND inbound_message_receipts.claimed_at<?
            """,
            (normalized, claimed_at, lease_cutoff),
        )
    return cursor.rowcount == 1


def complete_inbound_message(message_id: str, *, now: float | None = None) -> None:
    """Keep a durable receipt after the message handler has produced its outcome."""
    normalized = message_id.strip()
    if not normalized:
        return
    completed_at = time.time() if now is None else now
    with _connect() as conn:
        conn.execute(
            """
            UPDATE inbound_message_receipts
            SET status='completed', completed_at=?
            WHERE message_id=?
            """,
            (completed_at, normalized),
        )


def _state_get(key: str) -> tuple[dict[str, Any], float] | None:
    with _connect() as conn:
        row = conn.execute("SELECT value, updated_at FROM state WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return json.loads(row["value"]), float(row["updated_at"])


def _state_put(key: str, value: dict[str, Any]) -> None:
    now = time.time()
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO state(key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, encoded, now),
        )


def _fernet() -> Fernet:
    raw = os.getenv("HERMES_FEISHU_CREDENTIAL_KEY", "")
    if not raw:
        raise RuntimeError("HERMES_FEISHU_CREDENTIAL_KEY is not configured")
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("HERMES_FEISHU_CREDENTIAL_KEY must be a Fernet key") from exc
    if len(decoded) != 32:
        raise RuntimeError("HERMES_FEISHU_CREDENTIAL_KEY must be a Fernet key")
    return Fernet(raw.encode("ascii"))


def save_encrypted_credentials(app_id: str, app_secret: str, version: int) -> None:
    encrypted = _fernet().encrypt(app_secret.encode("utf-8")).decode("ascii")
    _state_put("credentials", {"app_id": app_id, "secret": encrypted, "version": version})


def load_credentials() -> tuple[str, str, int] | None:
    stored = _state_get("credentials")
    if stored is None:
        return None
    value, _ = stored
    try:
        secret = _fernet().decrypt(value["secret"].encode("ascii")).decode("utf-8")
    except (InvalidToken, KeyError) as exc:
        raise RuntimeError("Stored Feishu credentials cannot be decrypted") from exc
    return str(value["app_id"]), secret, int(value["version"])


def save_gateway_settings(*, tenant_id: str, gateway_enabled: bool, version: int) -> None:
    _state_put(
        "gateway_settings",
        {
            "tenant_id": tenant_id,
            "gateway_enabled": gateway_enabled,
            "version": version,
        },
    )


def load_gateway_settings() -> dict[str, Any]:
    stored = _state_get("gateway_settings")
    if stored is None:
        return {
            "tenant_id": "default",
            "gateway_enabled": True,
            "version": 0,
        }
    value, _ = stored
    return {
        "tenant_id": str(value.get("tenant_id") or "default"),
        "gateway_enabled": bool(value.get("gateway_enabled", True)),
        "version": int(value.get("version") or 0),
    }


def classify_risk(args: list[str], llm_risk: str | None = None) -> tuple[str, str]:
    text = " ".join(args).lower()
    if any(word in text for word in PROHIBITED_DECISIONS):
        return "prohibited", "该动作必须由责任人作出决定"
    fixed = "low"
    reason = "查询或可追溯的小范围新增"
    if any(word in text for word in HIGH_RISK_WORDS):
        fixed, reason = "high", "删除、覆盖、移动、权限、共享或版本替换"
    elif any(word in text for word in MEDIUM_RISK_WORDS):
        fixed, reason = "medium", "创建资源或修改既有值"
    ranks = {"low": 0, "medium": 1, "high": 2, "prohibited": 3}
    requested = llm_risk if llm_risk in ranks else "low"
    return (requested, "语义复核上调风险") if ranks[requested] > ranks[fixed] else (fixed, reason)


def validate_args(args: list[str], attachment_refs: list[str] | None = None) -> list[str]:
    if not args or len(args) > 64:
        raise ValueError("lark-cli args must contain 1-64 items")
    cleaned: list[str] = []
    allowed_files = (Path(os.getenv("HERMES_FEISHU_FILES_DIR", str(_home() / "feishu-files"))).resolve(),)
    attachment_set = {str(Path(item).resolve()) for item in (attachment_refs or [])}
    for index, raw in enumerate(args):
        if not isinstance(raw, str) or not raw or len(raw) > 4096:
            raise ValueError("invalid lark-cli argument")
        if any(token in raw for token in SHELL_TOKENS):
            raise ValueError("shell syntax is not allowed")
        if (
            raw == "--as" and index + 1 < len(args) and str(args[index + 1]).lower() == "user"
        ) or raw.lower() == "--as=user":
            raise ValueError("bot-only policy forbids --as user; retry with --as bot")
        if raw.startswith(("/", "\\")) or (len(raw) > 2 and raw[1:3] in {":\\", ":/"}):
            resolved = str(Path(raw).resolve())
            if resolved not in attachment_set or not any(Path(resolved).is_relative_to(root) for root in allowed_files):
                raise ValueError("local path is not an approved attachment reference")
        cleaned.append(raw)
    if cleaned[0] not in ALLOWED_ROOT_COMMANDS:
        raise ValueError("lark-cli control commands are not exposed to the agent")
    return cleaned


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: int


async def run_cli(
    args: list[str],
    *,
    stdin_text: str = "",
    timeout_seconds: float | None = None,
    allow_control: bool = False,
    home_dir: str | None = None,
    hermes_home_dir: str | None = None,
) -> CliResult:
    executable = os.getenv("LARK_CLI_PATH") or shutil.which("lark-cli")
    if not executable:
        raise RuntimeError("fixed lark-cli binary is not installed")
    if not allow_control:
        validate_args(args)
    elif not args or args[0] not in CONTROL_COMMANDS:
        raise ValueError("invalid lark-cli control command")
    env = {
        "PATH": os.getenv("PATH", ""),
        "HOME": home_dir or str(_cli_home()),
        "NO_COLOR": "1",
        "LANG": "C.UTF-8",
    }
    if hermes_home_dir:
        env["HERMES_HOME"] = hermes_home_dir
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        executable,
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(stdin_text.encode("utf-8")),
            timeout=timeout_seconds or float(os.getenv("LARK_CLI_TIMEOUT_SECONDS", "90")),
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("lark-cli execution timed out") from None
    limit = 1_000_000
    result = CliResult(
        returncode=process.returncode or 0,
        stdout=stdout[:limit].decode("utf-8", "replace"),
        stderr=stderr[:20_000].decode("utf-8", "replace"),
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )
    RUNTIME_METRICS["cli_calls"] += 1
    RUNTIME_METRICS["cli_last_latency_ms"] = result.elapsed_ms
    if result.returncode != 0:
        RUNTIME_METRICS["cli_failures"] += 1
    return result


async def stage_credentials(app_id: str, app_secret: str, version: int) -> dict[str, Any]:
    if not app_id.strip() or not app_secret:
        raise ValueError("app_id and app_secret are required")
    current = load_credentials()
    if current and version <= current[2]:
        raise ValueError("credential version must increase")
    tmpfs = _cli_home()
    runtime_root = tmpfs.parent
    runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    candidate = Path(tempfile.mkdtemp(prefix="hermes-feishu-candidate-", dir=runtime_root))
    binding_source = Path(tempfile.mkdtemp(prefix="hermes-bind-source-", dir=runtime_root))
    active = tmpfs
    backup = runtime_root / f".{tmpfs.name}-previous"

    def safe_error(result: CliResult) -> str:
        combined = "\n".join(part for part in (result.stderr, result.stdout) if part)
        return combined.replace(app_secret, "[REDACTED]")[-500:]

    try:
        binding_env = binding_source / ".env"
        binding_env.write_text(
            f"FEISHU_APP_ID={app_id}\nFEISHU_APP_SECRET={app_secret}\n",
            encoding="utf-8",
        )
        binding_env.chmod(0o600)
        init = await run_cli(
            [
                "config",
                "init",
                "--app-id",
                app_id,
                "--app-secret-stdin",
                "--brand",
                "feishu",
                "--force-init",
            ],
            stdin_text=app_secret,
            allow_control=True,
            timeout_seconds=30,
            home_dir=str(candidate),
        )
        if init.returncode != 0:
            raise RuntimeError(f"lark-cli config probe failed: {safe_error(init)}")
        bound = await run_cli(
            [
                "config",
                "bind",
                "--source",
                "hermes",
                "--identity",
                "bot-only",
            ],
            allow_control=True,
            timeout_seconds=30,
            home_dir=str(candidate),
            hermes_home_dir=str(binding_source),
        )
        if bound.returncode != 0:
            raise RuntimeError(f"lark-cli Hermes bot-only binding failed: {safe_error(bound)}")
        strict = await run_cli(
            ["config", "strict-mode", "bot", "--global"],
            allow_control=True,
            timeout_seconds=30,
            home_dir=str(candidate),
        )
        if strict.returncode != 0:
            raise RuntimeError(f"lark-cli bot-only policy failed: {safe_error(strict)}")
        doctor = await run_cli(
            ["doctor"],
            allow_control=True,
            timeout_seconds=30,
            home_dir=str(candidate),
        )
        if doctor.returncode != 0:
            raise RuntimeError(f"lark-cli doctor failed: {safe_error(doctor)}")
        if backup.exists():
            shutil.rmtree(backup)
        if active.exists():
            os.replace(active, backup)
        try:
            os.replace(candidate, active)
        except Exception:
            if backup.exists() and not active.exists():
                os.replace(backup, active)
            raise
        save_encrypted_credentials(app_id, app_secret, version)
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)
        if binding_source.exists():
            shutil.rmtree(binding_source)
    return {"app_id": app_id, "version": version, "status": "active"}


async def restore_credentials() -> dict[str, Any] | None:
    credentials = load_credentials()
    if credentials is None:
        return None
    app_id, app_secret, version = credentials
    # The tmpfs mount point exists even when its contents were lost on restart,
    # so always rehydrate it from the encrypted durable copy.
    with _connect() as conn:
        conn.execute("DELETE FROM state WHERE key='credentials'")
    try:
        return await stage_credentials(app_id, app_secret, version)
    except Exception:
        save_encrypted_credentials(app_id, app_secret, version)
        raise


def enqueue_audit(payload: dict[str, Any], event_type: str = "audit") -> str:
    event_id = str(uuid.uuid4())
    safe_payload = {
        key: value for key, value in payload.items() if key not in {"content", "body", "stdin", "app_secret", "token"}
    }
    now = time.time()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_outbox(id, event_type, payload_json, status, next_attempt_at, created_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (event_id, event_type, json.dumps(safe_payload, ensure_ascii=False), now, now),
        )
    return event_id


def _delivery_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "idempotency_key": row["idempotency_key"],
        "chat_id": row["chat_id"],
        "delivery_type": row["delivery_type"],
        "content": row["content"],
        "card": json.loads(row["card_json"]) if row["card_json"] else None,
        "reply_to": row["reply_to"],
        "metadata": json.loads(row["metadata_json"]),
        "status": row["status"],
        "attempts": int(row["attempts"]),
        "message_id": row["message_id"],
        "last_error": row["last_error"],
    }


def enqueue_delivery(
    *,
    idempotency_key: str,
    chat_id: str,
    content: str = "",
    card: dict[str, Any] | None = None,
    reply_to: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = idempotency_key.strip()
    if not key or len(key) > 128:
        raise ValueError("idempotency_key must contain 1-128 characters")
    if not chat_id.strip() or len(chat_id) > 255:
        raise ValueError("chat_id must contain 1-255 characters")
    if bool(content) == bool(card):
        raise ValueError("exactly one of content or card is required")
    if len(content) > 20_000:
        raise ValueError("delivery content is too large")
    card_json = json.dumps(card or {}, ensure_ascii=False, separators=(",", ":"))
    if len(card_json.encode("utf-8")) > 100_000:
        raise ValueError("delivery card is too large")
    metadata_json = json.dumps(
        metadata or {},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    now = time.time()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM delivery_outbox WHERE idempotency_key=?",
            (key,),
        ).fetchone()
        if existing is not None:
            return _delivery_row(existing)
        delivery_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO delivery_outbox(
                id,idempotency_key,chat_id,delivery_type,content,card_json,
                reply_to,metadata_json,status,next_attempt_at,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                delivery_id,
                key,
                chat_id,
                "card" if card else "text",
                content,
                card_json if card else "",
                reply_to,
                metadata_json,
                "pending",
                now,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM delivery_outbox WHERE id=?",
            (delivery_id,),
        ).fetchone()
    assert row is not None
    return _delivery_row(row)


def claim_due_deliveries(limit: int = 20) -> list[dict[str, Any]]:
    now = time.time()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """
            SELECT * FROM delivery_outbox
            WHERE status IN ('pending','retry') AND next_attempt_at<=?
            ORDER BY created_at ASC LIMIT ?
            """,
            (now, max(1, min(limit, 100))),
        ).fetchall()
        ids = [row["id"] for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE delivery_outbox
                SET status='sending', attempts=attempts+1, updated_at=?
                WHERE id IN ({placeholders})
                """,
                (now, *ids),
            )
            rows = conn.execute(
                f"SELECT * FROM delivery_outbox WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
    return [_delivery_row(row) for row in rows]


def complete_delivery(delivery_id: str, message_id: str | None = None) -> None:
    with _connect() as conn:
        updated = conn.execute(
            """
            UPDATE delivery_outbox
            SET status='delivered', message_id=?, last_error=NULL, updated_at=?
            WHERE id=? AND status='sending'
            """,
            (message_id, time.time(), delivery_id),
        )
    if updated.rowcount != 1:
        raise ValueError("delivery is not being sent")


def fail_delivery(delivery_id: str, error: str, max_attempts: int = 3) -> None:
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT attempts FROM delivery_outbox WHERE id=? AND status='sending'",
            (delivery_id,),
        ).fetchone()
        if row is None:
            raise ValueError("delivery is not being sent")
        attempts = int(row["attempts"])
        status_value = "failed" if attempts >= max_attempts else "retry"
        delay = min(300, 2 ** min(attempts, 8))
        conn.execute(
            """
            UPDATE delivery_outbox
            SET status=?, next_attempt_at=?, last_error=?, updated_at=?
            WHERE id=? AND status='sending'
            """,
            (status_value, now + delay, error[-500:], now, delivery_id),
        )


def get_delivery(delivery_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM delivery_outbox WHERE id=?",
            (delivery_id,),
        ).fetchone()
    return _delivery_row(row) if row is not None else None


async def synchronize_platform_state() -> None:
    base_url = os.getenv("DAZAH_API_BASE_URL", "").rstrip("/")
    token = os.getenv("HERMES_INTERNAL_TOKEN", "")
    if not base_url or not token:
        return
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, event_type, payload_json, attempts
                FROM audit_outbox
                WHERE status IN ('pending','failed') AND next_attempt_at<=?
                ORDER BY created_at ASC LIMIT 100
                """,
                (time.time(),),
            ).fetchall()
        for row in rows:
            endpoint = "audit" if row["event_type"] == "audit" else "resource-changes"
            payload = json.loads(row["payload_json"])
            payload["id"] = row["id"]
            try:
                delivered = await client.post(
                    f"{base_url}/internal/feishu/{endpoint}",
                    headers=headers,
                    json=payload,
                )
                delivered.raise_for_status()
                with _connect() as conn:
                    conn.execute("UPDATE audit_outbox SET status='delivered' WHERE id=?", (row["id"],))
            except httpx.HTTPError:
                attempts = int(row["attempts"]) + 1
                delay = min(300, 2 ** min(attempts, 8))
                with _connect() as conn:
                    conn.execute(
                        """
                        UPDATE audit_outbox
                        SET status='failed', attempts=?, next_attempt_at=?
                        WHERE id=?
                        """,
                        (attempts, time.time() + delay, row["id"]),
                    )


async def platform_sync_loop() -> None:
    while True:
        try:
            await synchronize_platform_state()
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        await asyncio.sleep(300)


def create_confirmation(
    *,
    user_id: str,
    app_id: str,
    resource: str,
    action: str,
    args: list[str],
    stdin_json: dict[str, Any] | list[Any] | None,
    module: str | None,
    risk: str,
    reason: str = "",
    impact_count: int = 1,
    preview: str = "",
) -> dict[str, Any]:
    request = {"args": args, "stdin_json": stdin_json, "module": module}
    normalized = json.dumps(request, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    request_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    confirmation_id = str(uuid.uuid4())
    now = time.time()
    with _connect() as conn:
        existing = conn.execute(
            """
            SELECT id, expires_at FROM confirmations
            WHERE user_id=? AND request_hash=? AND status='pending' AND expires_at>?
            """,
            (user_id, request_hash, now),
        ).fetchone()
        if existing:
            confirmation_id = existing["id"]
            expires_at = float(existing["expires_at"])
        else:
            expires_at = now + 10 * 60
            conn.execute(
                """
                INSERT INTO confirmations(
                    id,user_id,app_id,resource,action,request_json,request_hash,risk,status,expires_at,created_at
                ) VALUES (?,?,?,?,?,?,?,?,'pending',?,?)
                """,
                (confirmation_id, user_id, app_id, resource, action, normalized, request_hash, risk, expires_at, now),
            )
    return {
        "id": confirmation_id,
        "operation": action,
        "summary": f"{action} · {resource}",
        "risk_level": risk,
        "status": "pending",
        "resource_domain": "feishu_native",
        "expires_at": datetime.fromtimestamp(expires_at, UTC).isoformat(),
        "resource": resource,
        "reason": reason,
        "impact_count": impact_count,
        "preview": preview[:2000],
    }


def has_active_grant(*, user_id: str, app_id: str, resource: str, action: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM grants
            WHERE user_id=? AND app_id=? AND resource=? AND action=?
              AND revoked_at IS NULL AND expires_at>?
            """,
            (user_id, app_id, resource, action, time.time()),
        ).fetchone()
    return row is not None


async def resolve_confirmation(confirmation_id: str, *, user_id: str, choice: str) -> dict[str, Any]:
    if choice not in {"allow", "always", "reject"}:
        raise ValueError("choice must be allow, always, or reject")
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM confirmations WHERE id=?",
            (confirmation_id,),
        ).fetchone()
    if row is None or row["user_id"] != user_id:
        raise PermissionError("confirmation does not belong to this sender")
    if row["status"] != "pending" or float(row["expires_at"]) <= time.time():
        raise ValueError("confirmation is no longer pending")
    if choice == "always" and row["risk"] != "medium":
        raise ValueError("high-risk operations cannot be remembered")
    if choice == "reject":
        with _connect() as conn:
            conn.execute(
                "UPDATE confirmations SET status='rejected' WHERE id=? AND status='pending'",
                (confirmation_id,),
            )
        return {"ok": True, "status": "rejected", "id": confirmation_id}

    request = json.loads(row["request_json"])
    with _connect() as conn:
        claimed = conn.execute(
            "UPDATE confirmations SET status='executing' WHERE id=? AND status='pending'",
            (confirmation_id,),
        )
    if claimed.rowcount != 1:
        raise ValueError("confirmation was already handled")
    args = validate_args(request["args"])
    stdin_text = json.dumps(request.get("stdin_json") or {}, ensure_ascii=False)
    preview_args = args if "--dry-run" in args else [*args, "--dry-run"]
    preview = await run_cli(preview_args, stdin_text=stdin_text)
    if preview.returncode != 0:
        with _connect() as conn:
            conn.execute(
                "UPDATE confirmations SET status='stale' WHERE id=? AND status='executing'",
                (confirmation_id,),
            )
        raise RuntimeError("resource changed or dry-run validation failed")
    execution_args = [item for item in args if item != "--dry-run"]
    if row["risk"] == "high" and "--yes" not in execution_args:
        execution_args.append("--yes")
    result = await run_cli(execution_args, stdin_text=stdin_text)
    new_status = "completed" if result.returncode == 0 else "failed"
    with _connect() as conn:
        updated = conn.execute(
            "UPDATE confirmations SET status=? WHERE id=? AND status='executing'",
            (new_status, confirmation_id),
        )
        if updated.rowcount != 1:
            raise ValueError("confirmation was already handled")
        if choice == "always" and result.returncode == 0:
            now = time.time()
            conn.execute(
                """
                INSERT INTO grants(id,user_id,app_id,resource,action,expires_at,created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    row["app_id"],
                    row["resource"],
                    row["action"],
                    now + 30 * 24 * 60 * 60,
                    now,
                ),
            )
    enqueue_audit(
        {
            "user_id": user_id,
            "resource_fingerprint": row["resource"],
            "capability": row["action"],
            "risk": row["risk"],
            "confirmation": choice,
            "result": new_status,
            "duration_ms": result.elapsed_ms,
        }
    )
    if result.returncode == 0 and row["resource"]:
        enqueue_audit(
            {
                "resource_fingerprint": row["resource"],
                "capability": row["action"],
            },
            event_type="resource_change",
        )
    return {
        "ok": result.returncode == 0,
        "status": new_status,
        "id": confirmation_id,
        "output": result.stdout,
        "error": result.stderr,
    }


def list_grants(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id,app_id,resource,action,expires_at
            FROM grants WHERE user_id=? AND revoked_at IS NULL AND expires_at>?
            ORDER BY created_at DESC
            """,
            (user_id, time.time()),
        ).fetchall()
    return [dict(row) for row in rows]


def revoke_grant(grant_id: str, user_id: str) -> bool:
    with _connect() as conn:
        updated = conn.execute(
            """
            UPDATE grants SET revoked_at=?
            WHERE id=? AND user_id=? AND revoked_at IS NULL
            """,
            (time.time(), grant_id, user_id),
        )
    return updated.rowcount == 1


def runtime_metrics() -> dict[str, int]:
    with _connect() as conn:
        outbox_depth = int(
            conn.execute("SELECT count(*) FROM audit_outbox WHERE status IN ('pending','failed')").fetchone()[0]
        )
        pending_confirmations = int(
            conn.execute(
                "SELECT count(*) FROM confirmations WHERE status='pending' AND expires_at>?",
                (time.time(),),
            ).fetchone()[0]
        )
        pending_deliveries = int(
            conn.execute(
                """
                SELECT count(*) FROM delivery_outbox
                WHERE status IN ('pending','retry','sending')
                """
            ).fetchone()[0]
        )
    return {
        **RUNTIME_METRICS,
        "outbox_depth": outbox_depth,
        "pending_confirmations": pending_confirmations,
        "pending_deliveries": pending_deliveries,
    }


initialize_store()
