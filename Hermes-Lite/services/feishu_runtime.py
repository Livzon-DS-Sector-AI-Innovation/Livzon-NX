"""Durable Feishu control-plane state and safe lark-cli process execution.

This module deliberately contains no shell invocation.  The model can only
select arguments for the single, fixed ``lark-cli`` executable.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet, InvalidToken


ALLOWED_ROOT_COMMANDS = frozenset(
    {
        "api",
        "base",
        "docs",
        "drive",
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
LITERAL_TEXT_FLAGS = frozenset({"--content", "--pattern"})
HIGH_RISK_WORDS = frozenset(
    {
        "delete",
        "remove",
        "move",
        "clear",
        "overwrite",
        "replace",
        "revert",
        "restore",
        "push",
        "batch",
        "bulk",
    }
)
MEDIUM_RISK_WORDS = frozenset(
    {
        "create",
        "add",
        "update",
        "write",
        "edit",
        "patch",
        "set",
        "insert",
        "put",
        "upsert",
        "copy",
        "import",
        "upload",
        "publish",
        "enable",
        "disable",
        "rename",
        "merge",
        "sort",
        "hide",
        "unhide",
        "freeze",
    }
)
LOW_WRITE_WORDS = frozenset({"append", "comment", "reply"})
PROHIBITED_RESOURCE_WORDS = frozenset(
    {
        "permission",
        "permissions",
        "owner",
        "ownership",
        "share",
        "sharing",
        "member",
        "members",
        "role",
        "roles",
        "advperm",
    }
)
PROHIBITED_DECISIONS = frozenset({"approve", "approval", "reject", "discipline", "处分", "审批", "驳回"})
FILE_API_PATH_MARKERS = (
    "/drive/",
    "/docx/",
    "/sheets/",
    "/bitable/",
    "/wiki/",
    "/slides/",
    "/mindnote/",
    "/note/",
    "/notes/",
    "/minutes/",
    "/whiteboard/",
)
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


def _operation_words(args: list[str]) -> set[str]:
    command_parts: list[str] = []
    flags_started = False
    include_next_value = False
    semantic_value_flags = {"--action", "--command", "--operation", "--method"}
    for index, value in enumerate(args):
        if index == 0:
            command_parts.append(value)
            continue
        if args[0].lower() == "api" and (
            value.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            or value.startswith("/open-apis/")
        ):
            command_parts.append(value)
            continue
        if value.startswith("-"):
            flags_started = True
            command_parts.append(value)
            include_next_value = value.split("=", 1)[0].lower() in semantic_value_flags
            continue
        if not flags_started or include_next_value:
            command_parts.append(value)
        include_next_value = False
    return {
        word
        for value in command_parts
        for word in re.split(r"[^a-z0-9]+", value.lower())
        if word
    }


def is_write_operation(args: list[str]) -> bool:
    words = _operation_words(args)
    if args and args[0].lower() == "api":
        method = next(
            (
                item.upper()
                for item in args[1:]
                if item.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            ),
            "GET",
        )
        return method != "GET"
    destructive_words = HIGH_RISK_WORDS - {"batch", "bulk"}
    return bool(words & (destructive_words | MEDIUM_RISK_WORDS | LOW_WRITE_WORDS))


def classify_risk(args: list[str], llm_risk: str | None = None) -> tuple[str, str]:
    words = _operation_words(args)
    if words & PROHIBITED_DECISIONS:
        return "prohibited", "该动作必须由责任人作出决定"
    if words & PROHIBITED_RESOURCE_WORDS:
        return "prohibited", "文件能力不开放共享、成员、权限、所有权或角色管理"
    fixed = "low"
    reason = "查询或可追溯的小范围新增"
    destructive_words = HIGH_RISK_WORDS - {"batch", "bulk"}
    docs_update_command = ""
    if len(args) >= 2 and args[0].lower() == "docs" and args[1].lower() == "+update":
        try:
            command_index = args.index("--command") + 1
            docs_update_command = args[command_index].lower()
        except (ValueError, IndexError):
            pass
    if docs_update_command in {"str_replace", "block_replace"}:
        # Bounded local edits are ordinary modifications. Whole-document
        # overwrite, deletion, movement, version replacement and batches stay high.
        destructive_words -= {"replace"}
    content_missing = "--content" not in args
    content_empty = bool(
        "--content" in args
        and args.index("--content") + 1 < len(args)
        and args[args.index("--content") + 1] == ""
    )
    text_deletion = docs_update_command == "str_replace" and (
        content_missing or content_empty
    )
    is_batch_write = bool(words & {"batch", "bulk"}) and bool(
        words & (destructive_words | MEDIUM_RISK_WORDS | LOW_WRITE_WORDS)
    )
    if text_deletion:
        fixed, reason = "high", "删除文档中的既有内容"
    elif words & destructive_words or is_batch_write:
        fixed, reason = "high", "删除、清空、覆盖、移动或批量操作"
    elif words & {"append", "comment", "reply"} and not (
        words & (MEDIUM_RISK_WORDS - {"update", "add"})
    ):
        fixed, reason = "low", "可追溯的小范围追加"
    elif words & MEDIUM_RISK_WORDS:
        fixed, reason = "medium", "创建资源或修改既有值"
    elif args and args[0].lower() == "api":
        method = next(
            (
                item.upper()
                for item in args[1:]
                if item.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            ),
            "GET",
        )
        if method == "DELETE":
            fixed, reason = "high", "删除资源"
        elif method in {"POST", "PUT", "PATCH"}:
            fixed, reason = "medium", "通过飞书 Open API 写入资源"
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
        if not isinstance(raw, str) or len(raw) > 4096:
            raise ValueError("invalid lark-cli argument")
        literal_text_value = bool(
            index > 0 and str(args[index - 1]).lower() in LITERAL_TEXT_FLAGS
        )
        empty_str_replace_content = bool(
            raw == ""
            and literal_text_value
            and str(args[index - 1]).lower() == "--content"
            and "--command" in args
            and args.index("--command") + 1 < len(args)
            and str(args[args.index("--command") + 1]).lower() == "str_replace"
        )
        if not raw and not empty_str_replace_content:
            raise ValueError("invalid lark-cli argument")
        if not literal_text_value and any(token in raw for token in SHELL_TOKENS):
            raise ValueError("shell syntax is not allowed")
        if (
            raw == "--as" and index + 1 < len(args) and str(args[index + 1]).lower() == "user"
        ) or raw.lower() == "--as=user":
            raise ValueError("bot-only policy forbids --as user; retry with --as bot")
        is_api_path = bool(cleaned and cleaned[0] == "api" and raw.startswith("/open-apis/"))
        if not is_api_path and (raw.startswith(("/", "\\")) or (len(raw) > 2 and raw[1:3] in {":\\", ":/"})):
            resolved = str(Path(raw).resolve())
            if resolved not in attachment_set or not any(Path(resolved).is_relative_to(root) for root in allowed_files):
                raise ValueError("local path is not an approved attachment reference")
        cleaned.append(raw)
    if cleaned[0] not in ALLOWED_ROOT_COMMANDS:
        raise ValueError("lark-cli control commands are not exposed to the agent")
    if cleaned[0] == "api":
        api_path = next((item.lower() for item in cleaned[1:] if item.startswith("/")), "")
        if not api_path or not any(marker in api_path for marker in FILE_API_PATH_MARKERS):
            raise ValueError("raw api calls are limited to supported Feishu file resources")
    return cleaned


def validate_destructive_intent(args: list[str], user_message: str) -> None:
    """Require explicit whole-document intent before allowing overwrite."""
    if len(args) < 2 or args[0].lower() != "docs" or args[1].lower() != "+update":
        return
    try:
        command = args[args.index("--command") + 1].lower()
    except (ValueError, IndexError):
        return
    if command != "overwrite":
        return
    normalized = re.sub(r"\s+", "", user_message).lower()
    explicit_markers = (
        "覆盖整个文档",
        "覆盖全文",
        "全文覆盖",
        "清空文档",
        "重写整个文档",
        "替换整篇",
        "覆盖整篇",
        "overwriteentiredocument",
        "rewritetheentiredocument",
    )
    if not any(marker in normalized for marker in explicit_markers):
        raise ValueError(
            "docs overwrite requires explicit whole-document intent; "
            "use str_replace or a block operation for a bounded edit"
        )


def resource_fingerprint(resource: str) -> str:
    normalized = resource.strip()
    if not normalized:
        raise ValueError("write operations require an explicit resource or parent location")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


RESOURCE_TARGET_FLAGS = frozenset(
    {
        "--app-token",
        "--base-token",
        "--doc",
        "--document-id",
        "--document-token",
        "--file-token",
        "--folder-token",
        "--markdown-token",
        "--mindnote-token",
        "--minute-token",
        "--node-token",
        "--note-id",
        "--parent-node-token",
        "--parent-token",
        "--presentation-token",
        "--spreadsheet-token",
        "--token",
        "--url",
        "--whiteboard-id",
        "--wiki-token",
    }
)


def infer_explicit_resource(args: list[str]) -> str:
    """Extract an explicit file target already present in typed CLI argv."""
    for index, item in enumerate(args[:-1]):
        if item.lower() in RESOURCE_TARGET_FLAGS:
            value = args[index + 1].strip()
            if value and not value.startswith("--"):
                return value
    if args and args[0].lower() == "api":
        return next((item for item in args[1:] if item.startswith("/open-apis/")), "")
    return ""


def _visible_verification_text(value: str) -> str:
    """Normalize CLI/HTML text without depending on its serialization layout."""
    visible = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", visible).strip()


def _verification_output_text(value: str) -> str:
    """Include strings nested in JSON because lark-cli fetch output is structured."""
    candidates = [value]
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        payload = None

    def collect(item: Any) -> None:
        if isinstance(item, str):
            candidates.append(item)
        elif isinstance(item, dict):
            for nested in item.values():
                collect(nested)
        elif isinstance(item, list):
            for nested in item:
                collect(nested)

    collect(payload)
    return _visible_verification_text(" ".join(candidates))


def _verification_anchors(expected_text: str) -> list[str]:
    """Select bounded anchors across the whole requested payload."""
    normalized = _visible_verification_text(expected_text)
    tokens = re.findall(
        r"[A-Za-z][A-Za-z0-9_.:-]{3,}|"
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|"
        r"\d+(?:\.\d+)?|"
        r"[\u4e00-\u9fff]{2,}",
        normalized,
    )
    distinct = list(dict.fromkeys(token for token in tokens if len(token) >= 2))
    if not distinct:
        return [normalized] if normalized else []
    if len(distinct) <= 5:
        return distinct
    last = len(distinct) - 1
    indexes = (0, last // 4, last // 2, (last * 3) // 4, last)
    return list(dict.fromkeys(distinct[index] for index in indexes))


def expected_verification_text(args: list[str]) -> str:
    """Extract a bounded postcondition from supported typed write flags."""

    def scalar_values(value: Any) -> list[str]:
        if isinstance(value, dict):
            return [item for nested in value.values() for item in scalar_values(nested)]
        if isinstance(value, list):
            return [item for nested in value for item in scalar_values(nested)]
        if value is None or isinstance(value, bool):
            return []
        return [str(value)]

    values: list[str] = []
    for flag in (
        "--content",
        "--cells",
        "--values",
        "--data",
        "--styles",
        "--sheets",
        "--title",
        "--name",
        "--width",
        "--widths",
        "--height",
        "--heights",
        "--tab-color",
        "--rules",
        "--condition",
        "--config",
        "--mermaid",
        "--plantuml",
        "--dsl",
    ):
        try:
            value = args[args.index(flag) + 1]
        except (ValueError, IndexError):
            continue
        if value == "-" or value.startswith("@"):
            return ""
        if flag in {
            "--cells",
            "--values",
            "--data",
            "--styles",
            "--sheets",
            "--widths",
            "--heights",
            "--rules",
            "--condition",
            "--config",
        }:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = value
            value = " ".join(scalar_values(parsed))
        values.append(str(value))
    return _visible_verification_text(" ".join(values))[:20_000]


def expected_absence_text(args: list[str]) -> str:
    """Return text that must disappear for a bounded document deletion."""
    if len(args) < 2:
        return ""
    if args[0].lower() == "sheets" and args[1].lower() == "+sheet-delete":
        for flag in ("--sheet-id", "--sheet-name"):
            try:
                return _confirmation_excerpt(args[args.index(flag) + 1], limit=500)
            except (ValueError, IndexError):
                continue
        return ""
    if args[0].lower() != "docs" or args[1].lower() != "+update":
        return ""
    try:
        command = args[args.index("--command") + 1].lower()
        pattern = args[args.index("--pattern") + 1]
    except (ValueError, IndexError):
        return ""
    content = ""
    if "--content" in args:
        content_index = args.index("--content") + 1
        if content_index >= len(args):
            return ""
        content = args[content_index]
    if command != "str_replace" or content != "":
        return ""
    return _confirmation_excerpt(pattern, limit=500)


def effective_verification_mode(args: list[str], requested: str | None) -> str | None:
    """Infer safe verification semantics for unambiguous write operations."""
    if expected_absence_text(args):
        return "absence"
    if requested is not None:
        return requested
    normalized = [item.lower() for item in args]
    if len(normalized) >= 2 and normalized[0] == "base":
        operation = normalized[1]
        if operation == "+record-batch-create":
            return "creation_receipt"
        if operation == "+record-upsert" and "--record-id" not in normalized:
            return "creation_receipt"
    return None


_VERIFICATION_TARGET_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "base": (
        ("--base-token", "--app-token", "--url"),
        ("--table-id",),
        ("--record-id",),
        ("--field-id", "--field-name"),
        ("--view-id", "--view-name"),
        ("--dashboard-id",),
        ("--workflow-id",),
        ("--form-id",),
    ),
    "sheets": (
        ("--spreadsheet-token", "--url"),
        ("--sheet-id", "--sheet-name"),
        ("--range",),
        ("--chart-id",),
        ("--rule-id", "--conditional-format-id"),
        ("--view-id", "--filter-view-id"),
        ("--float-image-id",),
        ("--pivot-table-id",),
        ("--group-id",),
    ),
    "docs": (
        ("--doc", "--document-id", "--document-token", "--url"),
        ("--block-id", "--start-block-id", "--end-block-id"),
    ),
    "drive": (("--file-token", "--url"),),
    "wiki": (("--node-token", "--token", "--url"),),
    "markdown": (("--file-token", "--markdown-token", "--url"),),
    "slides": (
        ("--presentation", "--presentation-token", "--xml-presentation-id", "--url"),
        ("--slide-id",),
    ),
    "whiteboard": (("--whiteboard-token", "--whiteboard-id"),),
    "minutes": (("--minute-token", "--minute-tokens"),),
}


def _argument_values(args: list[str], flags: tuple[str, ...]) -> set[str]:
    values: set[str] = set()
    for index, item in enumerate(args):
        lowered = item.lower()
        for flag in flags:
            if lowered == flag and index + 1 < len(args):
                value = str(args[index + 1]).strip()
                if value and not value.startswith("--"):
                    values.update(part.strip() for part in value.split(",") if part.strip())
            elif lowered.startswith(f"{flag}="):
                value = item.split("=", 1)[1].strip()
                if value:
                    values.update(part.strip() for part in value.split(",") if part.strip())
    return values


def _structured_identifier_map(
    args: list[str],
    *,
    flags: tuple[str, ...] = ("--params", "--data", "--json"),
) -> dict[str, set[str]]:
    identifiers: dict[str, set[str]] = {}

    def collect(value: Any, key: str = "") -> None:
        normalized_key = key.lower().replace("-", "_")
        if isinstance(value, dict):
            for name, nested in value.items():
                collect(nested, str(name))
        elif isinstance(value, list):
            for nested in value:
                collect(nested, key)
        elif normalized_key.endswith(("_id", "_token")) or normalized_key in {
            "id",
            "token",
        }:
            rendered = str(value).strip()
            if rendered:
                identifiers.setdefault(normalized_key, set()).add(rendered)

    for flag in flags:
        for index, item in enumerate(args[:-1]):
            if item.lower() != flag:
                continue
            try:
                collect(json.loads(args[index + 1]))
            except json.JSONDecodeError:
                continue
    return identifiers


def _structured_identifier_values(args: list[str]) -> set[str]:
    return {
        value
        for values in _structured_identifier_map(args).values()
        for value in values
    }


def validate_verification_target(
    write_args: list[str],
    verification_args: list[str],
) -> None:
    """Require readback to address the same typed resource and sub-target."""
    if not write_args or not verification_args or write_args[0].lower() != verification_args[0].lower():
        raise ValueError("verification command must use the same resource domain as the write")
    root = write_args[0].lower()
    groups = _VERIFICATION_TARGET_GROUPS.get(root, ())
    compared = 0
    for group in groups:
        write_values = _argument_values(write_args, group)
        if not write_values:
            continue
        read_values = _argument_values(verification_args, group)
        if not read_values:
            sheet_delete_list = (
                root == "sheets"
                and write_args[1].lower() == "+sheet-delete"
                and verification_args[1].lower() == "+workbook-info"
                and group in (("--sheet-id", "--sheet-name"),)
            )
            if sheet_delete_list:
                continue
            raise ValueError(
                "verification command is missing a write target identifier"
            )
        compared += 1
        if write_values.isdisjoint(read_values):
            raise ValueError("verification command targets a different resource")
    structured_write = _structured_identifier_values(write_args)
    structured_read = _structured_identifier_values(verification_args)
    if root == "api":
        write_map = _structured_identifier_map(write_args, flags=("--params",))
        read_map = _structured_identifier_map(verification_args, flags=("--params",))
        write_keys = set(write_map)
        if not write_keys or not write_keys.issubset(read_map) or any(
            write_map[key].isdisjoint(read_map[key]) for key in write_keys
        ):
            raise ValueError("raw API verification lacks a matching structured target")
        return
    if groups and compared == 0 and (
        not structured_write or structured_write.isdisjoint(structured_read)
    ):
        raise ValueError("write and verification commands lack a comparable resource target")


def _has_specialized_verifier(args: list[str]) -> bool:
    return len(args) >= 2 and args[0].lower() == "base" and args[1].lower() in {
        "+record-upsert",
        "+record-batch-create",
        "+record-batch-update",
        "+record-delete",
    }


_CREATION_READBACK_SPECS: dict[tuple[str, str], tuple[set[str], str, str]] = {
    ("docs", "+create"): (
        {"document_id", "document_token", "doc_token", "url"},
        "docs",
        "+fetch",
    ),
    ("sheets", "+workbook-create"): (
        {"spreadsheet_token", "spreadsheet_id", "url"},
        "sheets",
        "+workbook-info",
    ),
    ("sheets", "+sheet-create"): (
        {"sheet_id"},
        "sheets",
        "+workbook-info",
    ),
    ("sheets", "+chart-create"): (
        {"chart_id"},
        "sheets",
        "+chart-list",
    ),
    ("sheets", "+cond-format-create"): (
        {"rule_id", "conditional_format_id"},
        "sheets",
        "+cond-format-list",
    ),
    ("sheets", "+filter-view-create"): (
        {"view_id", "filter_view_id"},
        "sheets",
        "+filter-view-list",
    ),
    ("sheets", "+float-image-create"): (
        {"float_image_id"},
        "sheets",
        "+float-image-list",
    ),
    ("sheets", "+pivot-create"): (
        {"pivot_table_id"},
        "sheets",
        "+pivot-list",
    ),
    ("sheets", "+sparkline-create"): (
        {"group_id"},
        "sheets",
        "+sparkline-list",
    ),
    ("drive", "+create-folder"): (
        {"folder_token", "file_token", "url"},
        "drive",
        "+inspect",
    ),
    ("drive", "+upload"): (
        {"file_token", "url"},
        "drive",
        "+inspect",
    ),
    ("drive", "+import"): (
        {"file_token", "document_token", "url"},
        "drive",
        "+inspect",
    ),
    ("wiki", "+node-create"): (
        {"node_token", "obj_token", "url"},
        "wiki",
        "+node-get",
    ),
    ("wiki", "+node-copy"): (
        {"node_token", "obj_token", "url"},
        "wiki",
        "+node-get",
    ),
    ("slides", "+create"): (
        {"presentation_token", "xml_presentation_id", "url"},
        "slides",
        "+xml-get",
    ),
    ("markdown", "+create"): (
        {"file_token", "markdown_token", "url"},
        "markdown",
        "+fetch",
    ),
}


def _supports_creation_receipt(args: list[str]) -> bool:
    if len(args) < 2:
        return False
    normalized = [item.lower() for item in args]
    if normalized[:2] == ["base", "+record-upsert"]:
        return "--record-id" not in normalized
    if normalized[:2] == ["drive", "+upload"] and "--file-token" in normalized:
        return False
    if normalized[:2] == ["drive", "+import"] and "--target-token" in normalized:
        return False
    return tuple(normalized[:2]) in _CREATION_READBACK_SPECS


def _is_exact_absence_lookup(
    write_args: list[str],
    verification_args: list[str],
) -> bool:
    if len(write_args) < 2 or len(verification_args) < 2:
        return False
    return (write_args[0].lower(), write_args[1].lower(), verification_args[1].lower()) in {
        ("drive", "+delete", "+inspect"),
        ("wiki", "+node-delete", "+node-get"),
        ("base", "+table-delete", "+table-get"),
        ("base", "+field-delete", "+field-get"),
        ("base", "+view-delete", "+view-get"),
        ("base", "+dashboard-delete", "+dashboard-get"),
        ("base", "+dashboard-block-delete", "+dashboard-block-get"),
        ("base", "+form-delete", "+form-get"),
    }


def validate_verification_contract(
    write_args: list[str],
    verification_args: list[str] | None,
    verification_mode: str | None,
    verification_text: str = "",
) -> None:
    """Reject writes that cannot produce an authoritative postcondition."""
    mode = effective_verification_mode(write_args, verification_mode)
    if mode == "creation_receipt":
        if not _supports_creation_receipt(write_args):
            raise ValueError("creation_receipt is not valid for this write operation")
        return
    if _has_specialized_verifier(write_args):
        return
    if mode not in {"readback", "absence"}:
        raise ValueError("write operation lacks a supported verification mode")
    if not verification_args:
        raise ValueError("write operation requires a target-bound readback command")
    validate_verification_target(write_args, verification_args)
    expected = (
        verification_text or expected_absence_text(write_args)
        if mode == "absence"
        else verification_text or expected_verification_text(write_args)
    )
    if mode == "absence" and _is_exact_absence_lookup(write_args, verification_args):
        return
    if not expected:
        raise ValueError(
            "write operation lacks a concrete readback assertion; no confirmation was created"
        )


def normalize_base_record_write_args(
    args: list[str],
    *,
    force_single_create: bool = False,
) -> list[str]:
    """Repair bounded legacy aliases and a misplaced inline JSON body."""
    normalized = list(args)
    if len(normalized) < 2 or normalized[0].lower() != "base":
        return normalized
    operation = normalized[1].lower()
    if operation == "+record-create":
        normalized[1] = "+record-upsert"
        operation = "+record-upsert"
    if operation not in {"+record-upsert", "+record-batch-create"}:
        return normalized
    if "--json" in normalized:
        json_index = normalized.index("--json") + 1
    else:
        json_index = -1
        for index in range(2, len(normalized)):
            candidate = normalized[index].strip()
            if not candidate.startswith("{"):
                continue
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                normalized[index:index] = ["--json"]
                json_index = index + 1
                break
    if force_single_create and operation == "+record-batch-create" and json_index > 0:
        try:
            body = json.loads(normalized[json_index])
        except json.JSONDecodeError:
            return normalized
        records = body.get("create_records") or body.get("records") if isinstance(body, dict) else None
        if isinstance(records, list) and len(records) == 1 and isinstance(records[0], dict):
            normalized[1] = "+record-upsert"
            normalized[json_index] = json.dumps(records[0], ensure_ascii=False)
    return normalized


def _base_record_write_payload(args: list[str]) -> list[dict[str, Any]]:
    if len(args) < 2 or args[0].lower() != "base" or "--json" not in args:
        return []
    operation = args[1].lower()
    if operation not in {"+record-upsert", "+record-batch-create"}:
        return []
    try:
        body = json.loads(args[args.index("--json") + 1])
    except (IndexError, json.JSONDecodeError):
        return []
    if not isinstance(body, dict):
        return []
    if operation == "+record-upsert":
        return [body]
    records = body.get("create_records") or body.get("records")
    if not isinstance(records, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        fields = item.get("fields")
        normalized.append(fields if isinstance(fields, dict) else item)
    return normalized


def _base_record_updates(args: list[str]) -> dict[str, dict[str, Any]]:
    if len(args) < 2 or args[0].lower() != "base" or "--json" not in args:
        return {}
    operation = args[1].lower()
    try:
        body = json.loads(args[args.index("--json") + 1])
    except (IndexError, json.JSONDecodeError):
        return {}
    if not isinstance(body, dict):
        return {}
    if operation == "+record-upsert" and "--record-id" in args:
        try:
            record_id = args[args.index("--record-id") + 1]
        except IndexError:
            return {}
        return {record_id: body}
    if operation != "+record-batch-update":
        return {}
    updates = body.get("update_records")
    if not isinstance(updates, dict):
        return {}
    return {
        str(record_id): fields
        for record_id, fields in updates.items()
        if str(record_id).strip() and isinstance(fields, dict)
    }


def _base_date_value(value: Any) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = float(value) / 1000 if abs(float(value)) >= 100_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(
                timestamp,
                ZoneInfo("Asia/Shanghai"),
            ).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        match = re.search(r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", value)
        if match:
            try:
                return datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                    tzinfo=UTC,
                ).date().isoformat()
            except ValueError:
                return None
    return None


def validate_base_record_write_values(
    args: list[str],
    *,
    require_date_strings: bool = False,
) -> None:
    """Reject date arithmetic and cross-field date mismatches before preview."""
    for record in _base_record_write_payload(args):
        embedded_dates: set[str] = set()
        for value in record.values():
            if not isinstance(value, str):
                continue
            for match in re.finditer(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", value):
                try:
                    embedded_dates.add(
                        datetime(
                            int(match.group(1)),
                            int(match.group(2)),
                            int(match.group(3)),
                            tzinfo=UTC,
                        ).date().isoformat()
                    )
                except ValueError:
                    continue
        reference_date = next(iter(embedded_dates)) if len(embedded_dates) == 1 else None
        for field_name, value in record.items():
            if not any(marker in str(field_name) for marker in ("日期", "时间", "Date", "Time")):
                continue
            parsed_date = _base_date_value(value)
            if require_date_strings and isinstance(value, (int, float)):
                hint = reference_date or parsed_date or "YYYY-MM-DD"
                raise ValueError(
                    f"Base 日期字段 {field_name} 必须使用日期字符串（例如 {hint} 00:00:00），"
                    "禁止由模型计算 Unix 时间戳"
                )
            if reference_date and parsed_date and parsed_date != reference_date:
                raise ValueError(
                    f"Base 日期字段 {field_name}={parsed_date} 与同一记录编号中的日期 "
                    f"{reference_date} 不一致，未生成确认项"
                )


def _base_preview_value(field_name: str, value: Any) -> str:
    if any(marker in field_name for marker in ("日期", "时间", "Date", "Time")):
        parsed = _base_date_value(value)
        if parsed:
            return parsed
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        rendered = str(value)
    return _confirmation_excerpt(rendered, limit=80)


def normalize_document_write_content(args: list[str]) -> list[str]:
    """Normalize common model aliases and plain document write content."""
    normalized = list(args)
    if len(normalized) < 2 or normalized[0].lower() != "docs" or normalized[1].lower() != "+update":
        return normalized
    flag_aliases = {
        "--old_str": "--pattern",
        "--old-str": "--pattern",
        "--new_str": "--content",
        "--new-str": "--content",
    }
    for index, value in enumerate(normalized):
        alias = flag_aliases.get(value.lower())
        if alias:
            if alias in normalized:
                raise ValueError(f"ambiguous document update flags: {value} and {alias}")
            normalized[index] = alias
    try:
        command_index = normalized.index("--command") + 1
        content_index = normalized.index("--content") + 1
        command = normalized[command_index].lower()
        content = normalized[content_index]
    except (ValueError, IndexError):
        return normalized
    if command == "replace_all":
        normalized[command_index] = "str_replace"
        command = "str_replace"
    if command not in {"append", "overwrite", "block_insert_after", "block_replace"}:
        return normalized
    if "--doc-format" in normalized:
        format_index = normalized.index("--doc-format") + 1
        if format_index < len(normalized) and normalized[format_index].lower() == "markdown":
            return normalized
    if content == "-" or content.startswith("@") or re.search(r"<[^>]+>", content):
        return normalized
    paragraphs = [line.strip() for line in content.splitlines() if line.strip()]
    normalized[content_index] = "".join(
        f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs
    )
    return normalized


def validate_nonempty_write_content(args: list[str]) -> None:
    if len(args) < 2 or args[0].lower() != "docs" or args[1].lower() != "+update":
        return
    command = ""
    if "--command" in args:
        index = args.index("--command") + 1
        command = args[index].lower() if index < len(args) else ""
    if command in {"append", "overwrite", "block_insert_after", "block_replace"}:
        if not expected_verification_text(args):
            raise ValueError(f"document {command} content must contain visible text")


def safe_resource_label(resource: str) -> str:
    value = resource.strip()
    if not value:
        return "未命名飞书资源"
    if "://" in value:
        tail = value.rstrip("/").rsplit("/", 1)[-1]
        return f"飞书资源 …{tail[-6:]}" if tail else "飞书资源链接"
    if re.fullmatch(r"(?:[a-z]{2,12})?[_-]?[a-z0-9]{12,}", value, flags=re.IGNORECASE):
        return f"飞书资源 …{value[-6:]}"
    return value if len(value) <= 80 else f"{value[:60]}…"


def _confirmation_excerpt(value: str, *, limit: int = 120) -> str:
    visible = html.unescape(re.sub(r"<[^>]+>", "", value))
    visible = re.sub(r"https?://\S+", "[链接已脱敏]", visible, flags=re.IGNORECASE)
    visible = re.sub(
        r"\b(?:docx?|wiki?|sht|tbl|bascn|cli_)[A-Za-z0-9_-]{8,}\b",
        "[标识已脱敏]",
        visible,
        flags=re.IGNORECASE,
    )
    visible = re.sub(r"\s+", " ", visible).strip()
    return visible if len(visible) <= limit else f"{visible[:limit]}…"


def safe_change_preview(
    args: list[str],
    *,
    impact_count: int,
    verification_text: str = "",
) -> str:
    """Build a bounded human summary without retaining CLI dry-run JSON."""

    def value_after(flag: str) -> str:
        try:
            index = args.index(flag) + 1
            return args[index] if index < len(args) else ""
        except ValueError:
            return ""

    operation = " ".join(args[:2]) if args else "飞书资源操作"
    lines = [f"- 操作：{operation}", f"- 影响：{impact_count} 项"]
    if len(args) >= 2 and args[0].lower() == "docs" and args[1].lower() == "+update":
        command = value_after("--command").lower()
        labels = {
            "str_replace": "局部文本替换",
            "block_replace": "局部内容块替换",
            "block_insert_after": "插入内容块",
            "append": "文档末尾追加",
            "overwrite": "覆盖整个文档",
            "block_delete": "删除内容块",
            "block_move_after": "移动内容块",
        }
        if command == "str_replace" and value_after("--content") == "":
            labels["str_replace"] = "删除匹配文本"
        lines[0] = f"- 操作：{labels.get(command, command or '文档修改')}"
        if command == "str_replace":
            if value_after("--content") == "":
                lines.append(f"- 删除内容：{_confirmation_excerpt(value_after('--pattern')) or '-'}")
            else:
                lines.append(f"- 原内容：{_confirmation_excerpt(value_after('--pattern')) or '-'}")
                lines.append(f"- 新内容：{_confirmation_excerpt(value_after('--content')) or '-'}")
        elif command in {"append", "block_insert_after", "block_replace"}:
            lines.append(f"- 内容摘要：{_confirmation_excerpt(value_after('--content')) or '-'}")
        elif command == "block_delete":
            lines.append(f"- 删除内容：{_confirmation_excerpt(verification_text) or '-'}")
        elif command == "overwrite":
            lines.append("- 范围：整个文档（正文不在确认卡中展示）")
    elif len(args) >= 2 and args[0].lower() == "base" and args[1].lower() in {
        "+record-upsert",
        "+record-batch-create",
    }:
        records = _base_record_write_payload(args)
        if records:
            lines.append("- 提交数据（与实际 CLI 参数一致）：")
            for field_name, value in list(records[0].items())[:12]:
                lines.append(
                    f"  - {_confirmation_excerpt(str(field_name), limit=40)}："
                    f"{_base_preview_value(str(field_name), value)}"
                )
            if len(records) > 1:
                lines.append(f"  - 其余记录：{len(records) - 1} 条")
    lines.append("- 校验：dry-run 已通过；执行后将进行只读回查")
    return "\n".join(lines)[:1000]


def infer_impact_count(args: list[str], stdin_json: Any, claimed: int) -> int:
    inferred = 1
    words = _operation_words(args)
    if "batch" in words or "bulk" in words:
        inferred = 21
    candidates = [stdin_json]
    if isinstance(stdin_json, dict):
        candidates.extend(stdin_json.values())
    for value in candidates:
        if isinstance(value, list):
            inferred = max(inferred, len(value))
    return max(claimed, inferred)


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: int


_FAILED_SEMANTIC_STATES = frozenset(
    {
        "error",
        "failed",
        "failure",
        "cancelled",
        "canceled",
        "timeout",
        "expired",
        "partial",
        "partial_success",
        "partially_succeeded",
    }
)
_INCOMPLETE_SEMANTIC_STATES = frozenset(
    {
        "pending",
        "in_progress",
        "in-progress",
        "running",
        "processing",
        "queued",
        "waiting",
    }
)


def cli_result_succeeded(result: CliResult) -> bool:
    """Interpret the pinned CLI JSON contract in addition to its exit code."""
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        normalized = result.stdout.strip().lower()
        return not (
            normalized.startswith(("error:", "failed:", "permission denied"))
            or "\nerror:" in normalized
        )
    if not isinstance(payload, dict):
        return True
    if payload.get("ok") is False or payload.get("success") is False:
        return False
    code = payload.get("code")
    if code not in (None, 0, "0", "success", "ok"):
        return False
    if payload.get("error") not in (None, "", False, {}, []):
        return False

    def has_failed_state(value: Any, key: str = "") -> bool:
        if isinstance(value, dict):
            normalized = {str(name).lower(): item for name, item in value.items()}
            for count_key in (
                "failed_count",
                "failure_count",
                "error_count",
                "failed_record_count",
            ):
                count = normalized.get(count_key)
                if isinstance(count, (int, float)) and count > 0:
                    return True
            for collection_key in ("errors", "failures", "failed_items", "failed_records"):
                if normalized.get(collection_key) not in (None, False, 0, "", [], {}):
                    return True
            total = normalized.get("total_count", normalized.get("total"))
            succeeded = normalized.get(
                "success_count", normalized.get("succeeded_count")
            )
            if (
                isinstance(total, (int, float))
                and isinstance(succeeded, (int, float))
                and succeeded < total
            ):
                return True
            return any(
                has_failed_state(item, str(name).lower())
                for name, item in value.items()
            )
        if isinstance(value, list):
            return any(has_failed_state(item, key) for item in value)
        if key in {"status", "state", "task_status", "task_state"}:
            return str(value).strip().lower() in (
                _FAILED_SEMANTIC_STATES | _INCOMPLETE_SEMANTIC_STATES
            )
        return False

    return not has_failed_state(payload)


def cli_result_reports_not_found(result: CliResult) -> bool:
    """Recognize semantic absence from an exact target lookup."""
    markers = ("not found", "not_found", "record_not_found", "不存在", "未找到")

    def contains_marker(value: Any, key: str = "") -> bool:
        if any(marker in key.lower() for marker in markers):
            if value not in (None, False, 0, "", [], {}):
                return True
        if isinstance(value, dict):
            return any(contains_marker(item, str(name)) for name, item in value.items())
        if isinstance(value, list):
            return any(contains_marker(item, key) for item in value)
        if isinstance(value, str):
            normalized = value.lower()
            return any(marker in normalized for marker in markers)
        return False

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = result.stdout
    return contains_marker(payload) or contains_marker(result.stderr)


def cli_confirmation_required(result: CliResult) -> bool:
    if result.returncode != 10:
        return False
    try:
        payload = json.loads(result.stderr)
    except json.JSONDecodeError:
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    return bool(
        isinstance(error, dict)
        and error.get("type") == "confirmation"
        and error.get("subtype") == "confirmation_required"
    )


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
    resource_label: str = "",
    verification_args: list[str] | None = None,
    verification_mode: str | None = None,
    verification_text: str = "",
    attachment_refs: list[str] | None = None,
    trace_id: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    request = {
        "args": args,
        "stdin_json": stdin_json,
        "module": module,
        "resource_label": resource_label,
        "verification_args": verification_args,
        "verification_mode": verification_mode,
        "verification_text": verification_text,
        "attachment_refs": attachment_refs or [],
        "trace_id": trace_id,
        "run_id": run_id,
    }
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
        "summary": f"{action} · {resource_label or '飞书资源'}",
        "risk_level": risk,
        "status": "pending",
        "resource_domain": "feishu_native",
        "expires_at": datetime.fromtimestamp(expires_at, UTC).isoformat(),
        "resource": resource_label or "飞书资源",
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


async def _reconcile_failed_verifiable_write(
    row: sqlite3.Row,
) -> dict[str, Any] | None:
    """Recheck an already executed write without ever replaying the mutation."""
    request = json.loads(row["request_json"])
    args = validate_args(request["args"], request.get("attachment_refs"))
    verification_args = request.get("verification_args")
    mode = effective_verification_mode(args, request.get("verification_mode"))
    if mode == "creation_receipt":
        return None
    try:
        validate_verification_contract(
            args,
            verification_args,
            mode,
            str(request.get("verification_text") or ""),
        )
    except ValueError:
        return None
    asserted_text = str(request.get("verification_text") or "")
    try:
        verification, verified = await verify_write_result(
            CliResult(0, '{"ok":true}', "", 0),
            verification_args,
            mode,
            (
                asserted_text or expected_verification_text(args)
                if mode == "readback"
                else expected_verification_text(args)
            ),
            (
                asserted_text or expected_absence_text(args)
                if mode == "absence"
                else expected_absence_text(args)
            ),
            write_args=args,
        )
    except (ValueError, PermissionError, RuntimeError):
        return None
    if not verified:
        return None
    with _connect() as conn:
        updated = conn.execute(
            "UPDATE confirmations SET status='completed' "
            "WHERE id=? AND status='verification_failed'",
            (row["id"],),
        )
    if updated.rowcount == 1:
        enqueue_audit(
            {
                "user_id": row["user_id"],
                "resource_fingerprint": row["resource"],
                "capability": row["action"],
                "risk": row["risk"],
                "confirmation": "reconciled",
                "result": "completed",
                "duration_ms": 0,
                "trace_id": request.get("trace_id"),
                "run_id": request.get("run_id"),
            }
        )
        if row["resource"]:
            enqueue_audit(
                {
                    "resource_fingerprint": row["resource"],
                    "capability": row["action"],
                    "trace_id": request.get("trace_id"),
                    "run_id": request.get("run_id"),
                },
                event_type="resource_change",
            )
    return {
        "ok": True,
        "status": "completed",
        "id": row["id"],
        "deduplicated": True,
        "reconciled": True,
        "verification": verification,
    }


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
    if row["status"] == "verification_failed" and choice == "allow":
        reconciled = await _reconcile_failed_verifiable_write(row)
        if reconciled is not None:
            return reconciled
    if row["status"] in {
        "completed",
        "completed_unverified",
        "verification_failed",
    } and choice in {"allow", "always"}:
        return {
            "ok": row["status"] == "completed",
            "status": row["status"],
            "id": confirmation_id,
            "deduplicated": True,
        }
    if row["status"] == "rejected" and choice == "reject":
        return {"ok": True, "status": "rejected", "id": confirmation_id, "deduplicated": True}
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
    args = validate_args(request["args"], request.get("attachment_refs"))
    requested_verification_args = request.get("verification_args")
    safe_verification_args = (
        validate_args(requested_verification_args)
        if requested_verification_args
        else None
    )
    try:
        validate_verification_contract(
            args,
            safe_verification_args,
            request.get("verification_mode"),
            str(request.get("verification_text") or ""),
        )
    except ValueError as exc:
        with _connect() as conn:
            conn.execute(
                "UPDATE confirmations SET status='stale' WHERE id=? AND status='pending'",
                (confirmation_id,),
            )
        raise RuntimeError("confirmation has no enforceable readback contract") from exc
    with _connect() as conn:
        claimed = conn.execute(
            "UPDATE confirmations SET status='executing' WHERE id=? AND status='pending'",
            (confirmation_id,),
        )
    if claimed.rowcount != 1:
        raise ValueError("confirmation was already handled")
    stdin_text = json.dumps(request.get("stdin_json") or {}, ensure_ascii=False)
    preview_args = args if "--dry-run" in args else [*args, "--dry-run"]
    preview = await run_cli(preview_args, stdin_text=stdin_text)
    if not cli_result_succeeded(preview):
        with _connect() as conn:
            conn.execute(
                "UPDATE confirmations SET status='stale' WHERE id=? AND status='executing'",
                (confirmation_id,),
            )
        raise RuntimeError("resource changed or dry-run validation failed")
    execution_args = [item for item in args if item != "--dry-run"]
    result = await run_cli(execution_args, stdin_text=stdin_text)
    if cli_confirmation_required(result):
        result = await run_cli([*execution_args, "--yes"], stdin_text=stdin_text)
    verification: dict[str, Any] | None = None
    execution_succeeded = cli_result_succeeded(result)
    new_status = "completed" if execution_succeeded else "failed"
    if execution_succeeded:
        try:
            write_args = request.get("args") or []
            effective_mode = effective_verification_mode(
                write_args,
                request.get("verification_mode"),
            )
            asserted_text = str(request.get("verification_text") or "")
            verification, verified = await verify_write_result(
                result,
                request.get("verification_args"),
                effective_mode,
                (
                    asserted_text or expected_verification_text(write_args)
                    if effective_mode == "readback"
                    else expected_verification_text(write_args)
                ),
                (
                    asserted_text or expected_absence_text(write_args)
                    if effective_mode == "absence"
                    else expected_absence_text(write_args)
                ),
                write_args=write_args,
            )
        except (ValueError, PermissionError, RuntimeError) as exc:
            verification = {"verified": False, "error": str(exc)[:500]}
            verified = False
        if not verified:
            new_status = "verification_failed"
    with _connect() as conn:
        updated = conn.execute(
            "UPDATE confirmations SET status=? WHERE id=? AND status='executing'",
            (new_status, confirmation_id),
        )
        if updated.rowcount != 1:
            raise ValueError("confirmation was already handled")
        if choice == "always" and new_status == "completed":
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
            "trace_id": request.get("trace_id"),
            "run_id": request.get("run_id"),
        }
    )
    if new_status == "completed" and row["resource"]:
        enqueue_audit(
            {
                "resource_fingerprint": row["resource"],
                "capability": row["action"],
                "trace_id": request.get("trace_id"),
                "run_id": request.get("run_id"),
            },
            event_type="resource_change",
        )
    return {
        "ok": new_status == "completed",
        "status": new_status,
        "id": confirmation_id,
        "output": result.stdout if new_status == "completed" else "",
        "error": result.stderr or (
            "write result could not be verified by readback"
            if new_status == "verification_failed"
            else ""
        ),
        "verification": verification,
    }


def _created_resource_identifiers(
    payload: Any,
    *,
    accepted_keys: set[str] | None = None,
) -> list[str]:
    identifiers: list[str] = []
    effective_keys = accepted_keys or {
        "id",
        "url",
        "token",
        "record_id",
        "record_id_list",
        "document_id",
        "file_token",
        "table_id",
    }

    def collect(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for nested_key, nested_value in item.items():
                collect(nested_value, str(nested_key).lower())
        elif isinstance(item, list):
            for nested in item:
                collect(nested, key)
        elif key in effective_keys and isinstance(item, (str, int)) and str(item).strip():
            identifiers.append(str(item).strip())

    collect(payload)
    return list(dict.fromkeys(identifiers))


def _first_argument_value(args: list[str], *flags: str) -> str:
    for flag in flags:
        try:
            value = args[args.index(flag) + 1].strip()
        except (ValueError, IndexError):
            continue
        if value:
            return value
    return ""


def _creation_readback_args(
    write_args: list[str],
    created_identifier: str,
) -> list[str] | None:
    operation = tuple(item.lower() for item in write_args[:2])
    spec = _CREATION_READBACK_SPECS.get(operation)
    if spec is None:
        return None
    root, read_operation = spec[1:]
    raw: list[str] = [root, read_operation]
    if root == "docs":
        raw.extend(["--doc", created_identifier])
    elif root == "drive":
        file_type = "folder" if operation == ("drive", "+create-folder") else (
            _first_argument_value(write_args, "--type") or "file"
        )
        raw.extend(["--url", created_identifier, "--type", file_type])
    elif root == "wiki":
        raw.extend(["--node-token", created_identifier])
        obj_type = _first_argument_value(write_args, "--obj-type")
        if obj_type:
            raw.extend(["--obj-type", obj_type])
    elif root == "slides":
        raw.extend(["--presentation", created_identifier])
    elif root == "markdown":
        raw.extend(["--file-token", created_identifier])
    elif root == "sheets" and operation == ("sheets", "+workbook-create"):
        raw.extend(["--spreadsheet-token", created_identifier])
    elif root == "sheets":
        spreadsheet = _first_argument_value(write_args, "--spreadsheet-token", "--url")
        if not spreadsheet:
            return None
        raw.extend(["--spreadsheet-token", spreadsheet])
        sheet_id = _first_argument_value(write_args, "--sheet-id", "--sheet-name")
        if sheet_id and operation != ("sheets", "+sheet-create"):
            raw.extend(["--sheet-id", sheet_id])
        object_flags = {
            ("sheets", "+chart-create"): "--chart-id",
            ("sheets", "+cond-format-create"): "--rule-id",
            ("sheets", "+filter-view-create"): "--view-id",
            ("sheets", "+float-image-create"): "--float-image-id",
            ("sheets", "+pivot-create"): "--pivot-table-id",
            ("sheets", "+sparkline-create"): "--group-id",
        }
        object_flag = object_flags.get(operation)
        if object_flag:
            raw.extend([object_flag, created_identifier])
    raw.extend(["--format", "json", "--as", "bot"])
    return validate_args(raw)


async def _verify_created_resource(
    write_result: CliResult,
    write_args: list[str],
) -> tuple[dict[str, Any], bool]:
    operation = tuple(item.lower() for item in write_args[:2])
    spec = _CREATION_READBACK_SPECS.get(operation)
    try:
        receipt = json.loads(write_result.stdout)
    except json.JSONDecodeError:
        receipt = {}
    identifiers = (
        _created_resource_identifiers(receipt, accepted_keys=spec[0]) if spec else []
    )
    if not cli_result_succeeded(write_result) or not identifiers:
        return {
            "mode": "creation_receipt",
            "verified": False,
            "receipt_identifier_count": len(identifiers),
            "error": "creation result has no supported resource identifier",
        }, False
    expected = expected_verification_text(write_args)
    require_content_match = operation in {
        ("docs", "+create"),
        ("slides", "+create"),
        ("markdown", "+create"),
        ("wiki", "+node-create"),
        ("wiki", "+node-copy"),
        ("sheets", "+sheet-create"),
        ("sheets", "+chart-create"),
        ("sheets", "+cond-format-create"),
        ("sheets", "+filter-view-create"),
        ("sheets", "+float-image-create"),
        ("sheets", "+pivot-create"),
        ("sheets", "+sparkline-create"),
        ("drive", "+create-folder"),
        ("drive", "+upload"),
        ("drive", "+import"),
    }
    anchors = _verification_anchors(expected) if require_content_match else []
    attempts = 0
    last_result = CliResult(1, "", "readback was not attempted", 0)
    for identifier in identifiers:
        read_args = _creation_readback_args(write_args, identifier)
        if not read_args:
            continue
        for delay_seconds in (0.0, 0.5, 1.5):
            if delay_seconds:
                await asyncio.sleep(delay_seconds)
            attempts += 1
            last_result = await run_cli(read_args)
            if not cli_result_succeeded(last_result):
                continue
            normalized_output = _verification_output_text(last_result.stdout)
            matched = [anchor for anchor in anchors if anchor in normalized_output]
            if not anchors or len(matched) == len(anchors):
                return {
                    "mode": "creation_receipt",
                    "verified": True,
                    "receipt_identifier_count": len(identifiers),
                    "readback": " ".join(read_args[:2]),
                    "attempts": attempts,
                    "matched_anchor_count": len(matched),
                    "expected_anchor_count": len(anchors),
                }, True
    return {
        "mode": "creation_receipt",
        "verified": False,
        "receipt_identifier_count": len(identifiers),
        "attempts": attempts,
        "expected_anchor_count": len(anchors),
        "readback_returncode": last_result.returncode,
        "error": last_result.stderr[:1000] or "created resource readback did not match",
    }, False


def _base_record_readback(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    fields = data.get("fields")
    rows = data.get("data")
    if (
        isinstance(fields, list)
        and isinstance(rows, list)
        and rows
        and isinstance(rows[0], list)
        and len(fields) == len(rows[0])
    ):
        return {str(field): value for field, value in zip(fields, rows[0], strict=True)}
    for candidate in (data.get("record"), data.get("fields")):
        if isinstance(candidate, dict):
            return candidate
    return None


def _base_record_readbacks(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return {}
    data = payload["data"]
    fields = data.get("fields")
    rows = data.get("data")
    record_ids = data.get("record_id_list")
    if not (
        isinstance(fields, list)
        and isinstance(rows, list)
        and isinstance(record_ids, list)
        and len(rows) == len(record_ids)
    ):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for record_id, row in zip(record_ids, rows, strict=True):
        if isinstance(row, list) and len(row) == len(fields):
            result[str(record_id)] = {
                str(field): value for field, value in zip(fields, row, strict=True)
            }
    return result


def _canonical_base_cell(field_name: str, value: Any) -> Any:
    if any(marker in field_name for marker in ("日期", "时间", "Date", "Time")):
        parsed = _base_date_value(value)
        if parsed:
            return parsed
    if isinstance(value, float):
        return round(value, 10)
    if isinstance(value, list):
        normalized = [_canonical_base_cell(field_name, item) for item in value]
        return normalized[0] if len(normalized) == 1 else normalized
    if isinstance(value, dict):
        return {
            key: _canonical_base_cell(field_name, nested)
            for key, nested in sorted(value.items())
        }
    return value.strip() if isinstance(value, str) else value


async def _verify_base_record_creation(
    write_result: CliResult,
    write_args: list[str],
) -> tuple[dict[str, Any], bool]:
    try:
        receipt = json.loads(write_result.stdout)
    except json.JSONDecodeError:
        receipt = {}
    record_ids = _created_resource_identifiers(
        receipt,
        accepted_keys={"record_id", "record_id_list"},
    )
    records = _base_record_write_payload(write_args)
    if not records or len(record_ids) != len(records):
        return {
            "mode": "creation_receipt",
            "verified": False,
            "receipt_identifier_count": len(record_ids),
            "expected_record_count": len(records),
            "error": "creation receipt record count does not match the request",
        }, False

    def value_after(flag: str) -> str:
        try:
            return write_args[write_args.index(flag) + 1]
        except (ValueError, IndexError):
            return ""

    base_token = value_after("--base-token")
    table_id = value_after("--table-id")
    if not base_token or not table_id:
        return {
            "mode": "creation_receipt",
            "verified": False,
            "receipt_identifier_count": len(record_ids),
            "error": "base record readback target is incomplete",
        }, False
    raw_read_args = [
        "base",
        "+record-get",
        "--base-token",
        base_token,
        "--table-id",
        table_id,
    ]
    for record_id in record_ids:
        raw_read_args.extend(["--record-id", record_id])
    raw_read_args.extend(["--format", "json", "--as", "bot"])
    read_args = validate_args(raw_read_args)
    attempts = 0
    last_result = CliResult(1, "", "readback was not attempted", 0)
    mismatched_fields: list[str] = []
    expected_records = dict(zip(record_ids, records, strict=True))
    for delay_seconds in (0.0, 0.5, 1.5):
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        attempts += 1
        last_result = await run_cli(read_args)
        try:
            read_payload = json.loads(last_result.stdout)
        except json.JSONDecodeError:
            read_payload = {}
        if not cli_result_succeeded(last_result):
            continue
        actual_records = _base_record_readbacks(read_payload)
        if len(record_ids) == 1 and not actual_records:
            single = _base_record_readback(read_payload)
            if single is not None:
                actual_records = {record_ids[0]: single}
        mismatched_fields = []
        for record_id, expected in expected_records.items():
            actual = actual_records.get(record_id)
            if actual is None:
                mismatched_fields.append(f"{record_id}:missing")
                continue
            mismatched_fields.extend(
                f"{record_id}:{field_name}"
                for field_name, expected_value in expected.items()
                if field_name not in actual
                or _canonical_base_cell(str(field_name), actual[field_name])
                != _canonical_base_cell(str(field_name), expected_value)
            )
        if not mismatched_fields:
            return {
                "mode": "creation_receipt",
                "verified": True,
                "receipt_identifier_count": len(record_ids),
                "readback": "record_get",
                "attempts": attempts,
                "record_count": len(records),
                "matched_field_count": sum(len(item) for item in records),
                "expected_field_count": sum(len(item) for item in records),
            }, True
    return {
        "mode": "creation_receipt",
        "verified": False,
        "receipt_identifier_count": len(record_ids),
        "readback": "record_get",
        "attempts": attempts,
        "record_count": len(records),
        "matched_field_count": max(
            sum(len(item) for item in records) - len(mismatched_fields), 0
        ),
        "expected_field_count": sum(len(item) for item in records),
        "mismatched_fields": mismatched_fields[:12],
        "readback_returncode": last_result.returncode,
        "error": last_result.stderr[:1000],
    }, False


async def _verify_base_record_updates(
    write_args: list[str],
) -> tuple[dict[str, Any], bool]:
    updates = _base_record_updates(write_args)

    def value_after(flag: str) -> str:
        try:
            return write_args[write_args.index(flag) + 1]
        except (ValueError, IndexError):
            return ""

    base_token = value_after("--base-token")
    table_id = value_after("--table-id")
    if not updates or not base_token or not table_id:
        return {
            "mode": "readback",
            "verified": False,
            "readback": "record_get",
            "error": "base record update target or payload is incomplete",
        }, False
    read_args = [
        "base",
        "+record-get",
        "--base-token",
        base_token,
        "--table-id",
        table_id,
    ]
    for record_id in updates:
        read_args.extend(["--record-id", record_id])
    read_args.extend(["--format", "json", "--as", "bot"])
    safe_read_args = validate_args(read_args)
    attempts = 0
    last_result = CliResult(1, "", "readback was not attempted", 0)
    mismatches: list[str] = []
    for delay_seconds in (0.0, 0.5, 1.5):
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        attempts += 1
        last_result = await run_cli(safe_read_args)
        if not cli_result_succeeded(last_result):
            continue
        try:
            payload = json.loads(last_result.stdout)
        except json.JSONDecodeError:
            payload = {}
        actual_records = _base_record_readbacks(payload)
        if len(updates) == 1 and not actual_records:
            single = _base_record_readback(payload)
            if single is not None:
                actual_records = {next(iter(updates)): single}
        mismatches = []
        for record_id, expected_fields in updates.items():
            actual_fields = actual_records.get(record_id)
            if actual_fields is None:
                mismatches.append(f"{record_id}:missing")
                continue
            mismatches.extend(
                f"{record_id}:{field_name}"
                for field_name, expected_value in expected_fields.items()
                if field_name not in actual_fields
                or _canonical_base_cell(str(field_name), actual_fields[field_name])
                != _canonical_base_cell(str(field_name), expected_value)
            )
        if not mismatches:
            return {
                "mode": "readback",
                "verified": True,
                "readback": "record_get",
                "attempts": attempts,
                "record_count": len(updates),
                "matched_field_count": sum(len(item) for item in updates.values()),
            }, True
    return {
        "mode": "readback",
        "verified": False,
        "readback": "record_get",
        "attempts": attempts,
        "record_count": len(updates),
        "mismatched_fields": mismatches[:20],
        "readback_returncode": last_result.returncode,
        "error": last_result.stderr[:1000],
    }, False


def _base_record_delete_ids(write_args: list[str]) -> list[str]:
    record_ids = list(_argument_values(write_args, ("--record-id",)))
    if "--json" in write_args:
        try:
            payload = json.loads(write_args[write_args.index("--json") + 1])
        except (IndexError, json.JSONDecodeError):
            payload = {}
        nested = payload.get("record_id_list") if isinstance(payload, dict) else None
        if isinstance(nested, list):
            record_ids.extend(str(item) for item in nested if str(item).strip())
    return list(dict.fromkeys(record_ids))


def _base_missing_record_ids(output: str) -> set[str]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        if "record_not_found=" not in output.lower():
            return set()
        match = re.search(r"Missing records:\s*(.+)", output, flags=re.IGNORECASE)
        return (
            {item.strip() for item in match.group(1).split(",") if item.strip()}
            if match
            else set()
        )

    missing_ids: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            missing = value.get("record_not_found")
            if isinstance(missing, list):
                missing_ids.update(str(item) for item in missing)
            elif isinstance(missing, str):
                missing_ids.add(missing)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(payload)
    return missing_ids


async def _verify_base_record_deletion(
    write_args: list[str],
) -> tuple[dict[str, Any], bool]:
    """Verify a Base deletion by reading the exact record identifier."""

    def value_after(flag: str) -> str:
        try:
            return write_args[write_args.index(flag) + 1]
        except (ValueError, IndexError):
            return ""

    base_token = value_after("--base-token")
    table_id = value_after("--table-id")
    record_ids = _base_record_delete_ids(write_args)
    if not base_token or not table_id or not record_ids:
        return {
            "mode": "absence",
            "verified": False,
            "readback": "record_get",
            "error": "base record deletion target is incomplete",
        }, False
    raw_read_args = [
        "base",
        "+record-get",
        "--base-token",
        base_token,
        "--table-id",
        table_id,
    ]
    for record_id in record_ids:
        raw_read_args.extend(["--record-id", record_id])
    raw_read_args.extend(["--format", "json", "--as", "bot"])
    read_args = validate_args(raw_read_args)
    attempts = 0
    last_result = CliResult(1, "", "readback was not attempted", 0)
    for delay_seconds in (0.0, 0.5, 1.5):
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        attempts += 1
        last_result = await run_cli(read_args)
        # The pinned CLI intentionally returns exit code 0 for a missing Base
        # record and exposes the semantic result in JSON or formatted metadata.
        # Since record-get targets the exact deleted ID, this is authoritative
        # absence evidence and cannot be confused with an empty list page.
        missing_ids = _base_missing_record_ids(last_result.stdout)
        if set(record_ids).issubset(missing_ids):
            return {
                "mode": "absence",
                "verified": True,
                "readback": "record_get",
                "attempts": attempts,
                "record_not_found": True,
                "record_count": len(record_ids),
            }, True
    return {
        "mode": "absence",
        "verified": False,
        "readback": "record_get",
        "attempts": attempts,
        "record_not_found": False,
        "record_count": len(record_ids),
        "readback_returncode": last_result.returncode,
        "error": last_result.stderr[:1000],
    }, False


async def verify_write_result(
    write_result: CliResult,
    verification_args: list[str] | None,
    verification_mode: str | None,
    expected_text: str = "",
    absent_text: str = "",
    write_args: list[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    if verification_mode is None and not verification_args:
        verified = not write_args or not is_write_operation(write_args)
        return {
            "mode": "legacy",
            "verified": verified,
            "error": None if verified else "write operation has no verification contract",
        }, verified
    mode = verification_mode or "readback"
    if (
        write_args
        and len(write_args) >= 2
        and (
            write_args[:2] == ["base", "+record-batch-update"]
            or (
                write_args[:2] == ["base", "+record-upsert"]
                and "--record-id" in write_args
            )
        )
    ):
        return await _verify_base_record_updates(write_args)
    if (
        mode == "absence"
        and write_args
        and len(write_args) >= 2
        and write_args[:2] == ["base", "+record-delete"]
    ):
        return await _verify_base_record_deletion(write_args)
    if mode == "creation_receipt":
        if write_args and len(write_args) >= 2 and write_args[:2] in (
            ["base", "+record-upsert"],
            ["base", "+record-batch-create"],
        ):
            return await _verify_base_record_creation(write_result, write_args)
        if write_args:
            return await _verify_created_resource(write_result, write_args)
        return {
            "mode": mode,
            "verified": False,
            "error": "creation receipt has no write operation",
        }, False
    if not verification_args:
        return {"mode": mode, "verified": False, "error": "missing verification command"}, False
    safe_args = validate_args(verification_args)
    if is_write_operation(safe_args):
        raise ValueError("verification command must be read-only")
    if write_args:
        validate_verification_target(write_args, safe_args)
    verification_result = CliResult(1, "", "readback was not attempted", 0)
    verified = False
    normalized_output = ""
    anchors = _verification_anchors(expected_text) if mode == "readback" else []
    matched_anchors: list[str] = []
    attempts = 0
    for delay_seconds in (0.0, 0.5, 1.5):
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
        attempts += 1
        verification_result = await run_cli(safe_args)
        normalized_output = _verification_output_text(verification_result.stdout)
        compact_output = re.sub(r"\s+", "", normalized_output)
        if mode == "absence":
            normalized_absent = re.sub(
                r"\s+", "", _visible_verification_text(absent_text)
            )
            if (
                write_args
                and _is_exact_absence_lookup(write_args, safe_args)
                and cli_result_reports_not_found(verification_result)
            ):
                verified = True
            elif absent_text:
                verified = (
                    cli_result_succeeded(verification_result)
                    and normalized_absent not in compact_output
                )
            else:
                verified = not cli_result_succeeded(verification_result)
        elif mode == "readback" and expected_text:
            matched_anchors = [
                anchor
                for anchor in anchors
                if re.sub(r"\s+", "", anchor) in compact_output
            ]
            verified = (
                cli_result_succeeded(verification_result)
                and bool(anchors)
                and len(matched_anchors) == len(anchors)
            )
        else:
            verified = False
        if verified:
            break
    return {
        "mode": mode,
        "verified": verified,
        "attempts": attempts,
        "expected_anchor_count": len(anchors) if anchors else None,
        "matched_anchor_count": len(matched_anchors) if anchors else None,
        "expected_text_present": (
            len(matched_anchors) == len(anchors)
            if expected_text
            else None
        ),
        "absent_text_present": (
            re.sub(r"\s+", "", _visible_verification_text(absent_text))
            in re.sub(r"\s+", "", normalized_output)
            if absent_text
            else None
        ),
        "readback_returncode": verification_result.returncode,
        "error": verification_result.stderr[:1000],
    }, verified


def get_confirmation_status(confirmation_id: str, *, user_id: str) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM confirmations WHERE id=?", (confirmation_id,)).fetchone()
    if row is None or row["user_id"] != user_id:
        raise PermissionError("confirmation does not belong to this sender")
    request = json.loads(row["request_json"])
    status_value = str(row["status"])
    if status_value == "pending" and float(row["expires_at"]) <= time.time():
        status_value = "expired"
    return {
        "id": confirmation_id,
        "status": status_value,
        "operation": row["action"],
        "risk_level": row["risk"],
        "resource": request.get("resource_label") or "飞书资源",
        "expires_at": datetime.fromtimestamp(float(row["expires_at"]), UTC).isoformat(),
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
