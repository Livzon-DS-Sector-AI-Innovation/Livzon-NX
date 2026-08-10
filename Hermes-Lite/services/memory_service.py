"""Tenant-scoped, bounded user memory for the Dazah Hermes runtime.

The upstream Hermes ``MEMORY.md``/``USER.md`` store is intentionally not used
by the Dazah adapter: it is profile-scoped rather than tenant/user-scoped.  This
module keeps the product-facing memory in one SQLite database under
``HERMES_HOME`` and exposes only compact, validated projections to the agent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pydantic import BaseModel, ConfigDict, Field, field_validator

from hermes_constants import get_hermes_home
from tools.memory_tool import ENTRY_DELIMITER
from tools.threat_patterns import first_threat_message

logger = logging.getLogger(__name__)

MemoryCategory = Literal[
    "preference",
    "personal_fact",
    "professional_knowledge",
    "task_history",
    "decision_history",
    "interaction_pattern",
]

CATEGORY_LABELS: dict[str, str] = {
    "preference": "偏好",
    "personal_fact": "个人事实",
    "professional_knowledge": "专业知识",
    "task_history": "任务历史",
    "decision_history": "决策历史",
    "interaction_pattern": "交互模式",
}
CATEGORIES = tuple(CATEGORY_LABELS)
HISTORY_CATEGORIES = {"task_history", "decision_history", "interaction_pattern"}

DEFAULT_LIMIT_BYTES = 32 * 1024
DEFAULT_TRIGGER_RATIO = 0.80
DEFAULT_TARGET_RATIO = 0.60
DEFAULT_INJECTION_BYTES = 6 * 1024
MAX_ENTRY_BYTES = 2 * 1024
CLEAR_CONFIRMATION_TTL_SECONDS = 5 * 60
RUN_LEASE_SECONDS = 5 * 60
RUN_RETENTION_SECONDS = 30 * 24 * 60 * 60
FAILED_JOB_RETENTION_SECONDS = 24 * 60 * 60
JOB_RETENTION_SECONDS = 24 * 60 * 60
MAX_JOBS_GLOBAL = 1000
MAX_JOBS_PER_USER = 20
MAX_JOB_ATTEMPTS = 3

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:password|passwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|cookie)\b\s*[:=]"),
    re.compile(
        r"(?:密码|口令|令牌|访问令牌|刷新令牌|接口密钥|API密钥|会话Cookie)"
        r"\s*(?:是|为|[:：=])",
        re.IGNORECASE,
    ),
    re.compile(r"(?i)\b(?:bearer|authorization)\s+[a-z0-9._~+\-/]+=*"),
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
)
_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "identity_document",
        re.compile(
            r"(?<!\d)\d{17}[0-9Xx](?!\d)|"
            r"(?:身份证|护照|港澳通行证|台湾通行证|驾驶证|社保卡|证件号)"
        ),
    ),
    ("payment", re.compile(r"(?<!\d)\d{16,19}(?!\d)|(?:银行卡|支付账户|银行账号)")),
    (
        "phone",
        re.compile(
            r"(?<!\d)1[3-9]\d{9}(?!\d)|"
            r"(?<!\d)(?:\+?86[- ]?)?0\d{2,3}[- ]?\d{7,8}(?!\d)|"
            r"(?:手机号|手机号码|联系电话|联系方式|微信号|QQ号)"
        ),
    ),
    (
        "email",
        re.compile(
            r"(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9.-])",
            re.IGNORECASE,
        ),
    ),
    (
        "precise_location",
        re.compile(
            r"(?:详细地址|家庭住址|居住地址|收货地址|精确位置|定位坐标|经纬度)|"
            r"(?:省|自治区|市).{0,30}(?:区|县).{0,30}(?:路|街|巷|道).{0,20}\d+号"
        ),
    ),
    (
        "health",
        re.compile(
            r"(?:病史|病历|诊断|确诊|过敏史|用药记录|处方|医疗记录|检查结果|"
            r"健康状况|残疾|怀孕|血型|基因|生物识别|指纹|虹膜|声纹|人脸特征)|"
            r"(?:我|本人|用户|患者).{0,12}(?:患有|得了|感染|过敏|正在服用|长期服用)"
        ),
    ),
    ("compensation", re.compile(r"(?:工资|薪资|薪酬|奖金|绩效工资|月薪|年薪|个人收入)")),
    ("discipline", re.compile(r"(?:处分|违纪调查|调查结论|个人绩效结论)")),
    ("permission_context", re.compile(r"(?:权限上下文|完整prompt|原始prompt)", re.IGNORECASE)),
)


class MemoryCipher:
    def __init__(self, raw_keys: str | None = None) -> None:
        values = [item.strip() for item in (raw_keys or "").split(",") if item.strip()]
        self.ephemeral = not values
        if not values:
            values = [Fernet.generate_key().decode("ascii")]
        try:
            self._fernets = [Fernet(value.encode("ascii")) for value in values]
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("HERMES_USER_MEMORY_KEYS must contain Fernet keys") from exc
        self._multi = MultiFernet(self._fernets)

    def encrypt(self, value: str) -> str:
        return "enc:v1:" + self._fernets[0].encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value.startswith("enc:v1:"):
            return value
        try:
            return self._multi.decrypt(value[7:].encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise ValueError("Encrypted user memory cannot be decrypted") from exc


class MemoryCandidate(BaseModel):
    """Validated output from the post-turn memory extractor."""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["upsert", "replace", "forget"] = "upsert"
    category: MemoryCategory
    content: str = Field(min_length=1, max_length=800)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: int = Field(default=3, ge=1, le=5)
    explicit: bool = False
    pinned: bool = False
    match_text: str | None = Field(default=None, max_length=200)
    memory_key: str | None = Field(default=None, max_length=120)
    evidence_source: Literal["user_statement", "tool_result", "repeated_observation"] = "user_statement"
    tool_evidence_ids: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @field_validator("memory_key")
    @classmethod
    def normalize_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = re.sub(r"[^a-z0-9_.-]+", "_", value.strip().casefold()).strip("_")
        return normalized or None


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memories: list[MemoryCandidate] = Field(default_factory=list, max_length=12)


class CompressionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: MemoryCategory
    content: str = Field(min_length=1, max_length=1200)
    source_ids: list[str] = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()


class CompressionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summaries: list[CompressionSummary] = Field(min_length=1)


def get_memory_base_dir() -> Path:
    return get_hermes_home() / "memories"


def get_memory_db_path() -> Path:
    return get_memory_base_dir() / "user-memory.sqlite3"


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _content_hash(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _contains_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def sensitive_memory_category(value: str) -> str | None:
    if _contains_secret(value):
        return "credential"
    for category, pattern in _SENSITIVE_PATTERNS:
        if pattern.search(value):
            return category
    return None


def _unsafe_memory(value: str) -> bool:
    return sensitive_memory_category(value) is not None or first_threat_message(value, scope="strict") is not None


def eligible_for_automatic_memory(
    user_message: str,
    assistant_message: str,
    tool_evidence: list[dict[str, Any]],
) -> bool:
    if _unsafe_memory(user_message) or _unsafe_memory(assistant_message):
        return False
    if any(item.get("verified") is True for item in tool_evidence):
        return True
    return re.search(
        r"(?:我(?:喜欢|偏好|习惯|负责|是|决定|希望)|以后请|请始终|每次都|记住|长期)",
        user_message,
        flags=re.IGNORECASE,
    ) is not None


def _clip_utf8(value: str, limit: int) -> str:
    raw = value.encode("utf-8")
    if len(raw) <= limit:
        return value
    return raw[:limit].decode("utf-8", errors="ignore").rstrip()


class UserMemoryRepository:
    """Synchronous SQLite repository; each operation owns its connection."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        limit_bytes: int = DEFAULT_LIMIT_BYTES,
        trigger_ratio: float = DEFAULT_TRIGGER_RATIO,
        target_ratio: float = DEFAULT_TARGET_RATIO,
        injection_bytes: int = DEFAULT_INJECTION_BYTES,
    ) -> None:
        self.db_path = db_path or get_memory_db_path()
        self.limit_bytes = max(4096, int(limit_bytes))
        safe_trigger_ratio = min(0.95, max(0.20, float(trigger_ratio)))
        safe_target_ratio = min(safe_trigger_ratio - 0.05, max(0.10, float(target_ratio)))
        self.trigger_bytes = int(self.limit_bytes * safe_trigger_ratio)
        self.target_bytes = int(self.limit_bytes * safe_target_ratio)
        self.injection_bytes = max(1024, int(injection_bytes))
        self.cipher = MemoryCipher(os.getenv("HERMES_USER_MEMORY_KEYS"))
        self._schema_lock = threading.Lock()
        self._user_locks: dict[tuple[str, str], threading.RLock] = {}
        self._user_locks_guard = threading.Lock()
        self._schema_ready = False

    def _user_lock(self, tenant_id: str, user_id: str) -> threading.RLock:
        key = (tenant_id, user_id)
        with self._user_locks_guard:
            return self._user_locks.setdefault(key, threading.RLock())

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            self.db_path.chmod(0o600)
        except OSError:
            logger.debug("Could not tighten user memory database permissions", exc_info=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA secure_delete=ON")
        if not self._schema_ready:
            self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        with self._schema_lock:
            if self._schema_ready:
                return
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_memory_entries (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    entry_kind TEXT NOT NULL DEFAULT 'detail',
                    confidence REAL NOT NULL,
                    importance INTEGER NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    evidence_count INTEGER NOT NULL DEFAULT 1,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    source_session_id TEXT,
                    source_run_id TEXT,
                    memory_key TEXT,
                    UNIQUE (tenant_id, user_id, category, content_hash)
                );
                CREATE INDEX IF NOT EXISTS ix_user_memory_scope
                    ON user_memory_entries (tenant_id, user_id, pinned DESC, last_seen DESC);
                CREATE TABLE IF NOT EXISTS user_memory_runs (
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    processed_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    lease_until REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, user_id, run_id)
                );
                CREATE TABLE IF NOT EXISTS user_memory_jobs (
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    assistant_message TEXT NOT NULL,
                    tool_evidence_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    lease_until REAL NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_error TEXT,
                    PRIMARY KEY (tenant_id, user_id, run_id)
                );
                CREATE INDEX IF NOT EXISTS ix_user_memory_jobs_ready
                    ON user_memory_jobs (status, next_attempt_at, lease_until, created_at);
                CREATE TABLE IF NOT EXISTS user_memory_clear_confirmations (
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (tenant_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS user_memory_state (
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    generation INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS user_memory_migrations (
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    migration TEXT NOT NULL,
                    applied_at REAL NOT NULL,
                    PRIMARY KEY (tenant_id, user_id, migration)
                );
                """
            )
            self._ensure_column(conn, "user_memory_entries", "memory_key", "TEXT")
            self._ensure_column(conn, "user_memory_entries", "content_bytes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "user_memory_jobs", "payload_ciphertext", "TEXT")
            self._ensure_column(conn, "user_memory_jobs", "expires_at", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(
                conn, "user_memory_runs", "status", "TEXT NOT NULL DEFAULT 'completed'"
            )
            self._ensure_column(
                conn, "user_memory_runs", "lease_until", "REAL NOT NULL DEFAULT 0"
            )
            self._migrate_encrypted_storage(conn)
            conn.commit()
            self._schema_ready = True

    def _migrate_encrypted_storage(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT id, content FROM user_memory_entries").fetchall()
        for row in rows:
            plaintext = self.cipher.decrypt(str(row["content"]))
            encrypted = self.cipher.encrypt(plaintext)
            conn.execute(
                "UPDATE user_memory_entries SET content=?, content_bytes=? WHERE id=?",
                (encrypted, _utf8_len(plaintext), row["id"]),
            )
        # Queued turns are transient and legacy rows contain plaintext.
        conn.execute("DELETE FROM user_memory_jobs WHERE payload_ciphertext IS NULL OR payload_ciphertext='' ")
        jobs = conn.execute(
            "SELECT tenant_id, user_id, run_id, payload_ciphertext FROM user_memory_jobs"
        ).fetchall()
        for job in jobs:
            try:
                rotated = self.cipher.encrypt(
                    self.cipher.decrypt(str(job["payload_ciphertext"]))
                )
            except ValueError:
                conn.execute(
                    """DELETE FROM user_memory_jobs
                       WHERE tenant_id=? AND user_id=? AND run_id=?""",
                    (job["tenant_id"], job["user_id"], job["run_id"]),
                )
                continue
            conn.execute(
                """UPDATE user_memory_jobs SET payload_ciphertext=?
                   WHERE tenant_id=? AND user_id=? AND run_id=?""",
                (rotated, job["tenant_id"], job["user_id"], job["run_id"]),
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @contextmanager
    def _locked_connection(self, tenant_id: str, user_id: str):
        with self._user_lock(tenant_id, user_id):
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()

    @staticmethod
    def _usage_in_conn(conn: sqlite3.Connection, tenant_id: str, user_id: str) -> int:
        row = conn.execute(
            """SELECT COALESCE(SUM(content_bytes), 0) AS used
               FROM user_memory_entries WHERE tenant_id=? AND user_id=?""",
            (tenant_id, user_id),
        ).fetchone()
        return int(row["used"] or 0)

    def usage_bytes(self, tenant_id: str, user_id: str) -> int:
        with self._connect() as conn:
            return self._usage_in_conn(conn, tenant_id, user_id)

    def generation(self, tenant_id: str, user_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT generation FROM user_memory_state WHERE tenant_id=? AND user_id=?",
                (tenant_id, user_id),
            ).fetchone()
        return int(row["generation"]) if row else 0

    def has_processed_run(self, tenant_id: str, user_id: str, run_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute(
                """SELECT 1 FROM user_memory_runs
                   WHERE tenant_id=? AND user_id=? AND run_id=? AND status='completed'""",
                (tenant_id, user_id, run_id),
            ).fetchone() is not None

    def claim_run(self, tenant_id: str, user_id: str, run_id: str) -> bool:
        now = time.time()
        with self._locked_connection(tenant_id, user_id) as conn:
            row = conn.execute(
                """SELECT status, lease_until FROM user_memory_runs
                   WHERE tenant_id=? AND user_id=? AND run_id=?""",
                (tenant_id, user_id, run_id),
            ).fetchone()
            if row and (row["status"] == "completed" or float(row["lease_until"]) > now):
                return False
            if row:
                conn.execute(
                    """UPDATE user_memory_runs SET status='processing', lease_until=?, processed_at=0
                       WHERE tenant_id=? AND user_id=? AND run_id=?""",
                    (now + RUN_LEASE_SECONDS, tenant_id, user_id, run_id),
                )
            else:
                conn.execute(
                    """INSERT INTO user_memory_runs
                       (tenant_id, user_id, run_id, processed_at, status, lease_until)
                       VALUES (?, ?, ?, 0, 'processing', ?)""",
                    (tenant_id, user_id, run_id, now + RUN_LEASE_SECONDS),
                )
            return True

    def complete_run(self, tenant_id: str, user_id: str, run_id: str) -> None:
        with self._locked_connection(tenant_id, user_id) as conn:
            conn.execute(
                """UPDATE user_memory_runs SET status='completed', processed_at=?, lease_until=0
                   WHERE tenant_id=? AND user_id=? AND run_id=?""",
                (time.time(), tenant_id, user_id, run_id),
            )
            self._prune_metadata_in_conn(conn, tenant_id, user_id)

    def release_run(self, tenant_id: str, user_id: str, run_id: str) -> None:
        with self._locked_connection(tenant_id, user_id) as conn:
            conn.execute(
                """DELETE FROM user_memory_runs
                   WHERE tenant_id=? AND user_id=? AND run_id=? AND status='processing'""",
                (tenant_id, user_id, run_id),
            )

    @staticmethod
    def _prune_metadata_in_conn(conn: sqlite3.Connection, tenant_id: str, user_id: str) -> None:
        now = time.time()
        conn.execute(
            """DELETE FROM user_memory_runs
               WHERE tenant_id=? AND user_id=? AND status='completed' AND processed_at<?""",
            (tenant_id, user_id, now - RUN_RETENTION_SECONDS),
        )
        conn.execute(
            """DELETE FROM user_memory_runs WHERE rowid IN (
                   SELECT rowid FROM user_memory_runs
                   WHERE tenant_id=? AND user_id=? AND status='completed'
                   ORDER BY processed_at DESC LIMIT -1 OFFSET 1000
               )""",
            (tenant_id, user_id),
        )
        conn.execute(
            """DELETE FROM user_memory_jobs
               WHERE created_at<? OR (status='failed' AND updated_at<?)""",
            (now - JOB_RETENTION_SECONDS, now - FAILED_JOB_RETENTION_SECONDS),
        )
        conn.execute(
            """DELETE FROM user_memory_jobs WHERE rowid IN (
                   SELECT rowid FROM user_memory_jobs WHERE status='failed'
                   ORDER BY updated_at DESC LIMIT -1 OFFSET 1000
               )"""
        )

    def enqueue_job(
        self,
        tenant_id: str,
        user_id: str,
        run_id: str,
        *,
        session_id: str,
        user_message: str,
        assistant_message: str,
        tool_evidence: list[dict[str, Any]],
    ) -> bool:
        now = time.time()
        payload = self.cipher.encrypt(
            json.dumps(
                {
                    "session_id": hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
                    "user_message": _clip_utf8(user_message, 4096),
                    "assistant_message": _clip_utf8(assistant_message, 4096),
                    "tool_evidence": tool_evidence[:20],
                },
                ensure_ascii=False,
            )
        )
        with self._locked_connection(tenant_id, user_id) as conn:
            self._prune_metadata_in_conn(conn, tenant_id, user_id)
            if conn.execute(
                "SELECT 1 FROM user_memory_jobs WHERE tenant_id=? AND user_id=? AND run_id=?",
                (tenant_id, user_id, run_id),
            ).fetchone():
                return True
            global_count = int(conn.execute(
                "SELECT COUNT(*) AS count FROM user_memory_jobs WHERE status IN ('pending','processing')"
            ).fetchone()["count"])
            user_count = int(conn.execute(
                """SELECT COUNT(*) AS count FROM user_memory_jobs
                   WHERE tenant_id=? AND user_id=? AND status IN ('pending','processing')""",
                (tenant_id, user_id),
            ).fetchone()["count"])
            if global_count >= MAX_JOBS_GLOBAL or user_count >= MAX_JOBS_PER_USER:
                return False
            conn.execute(
                """INSERT INTO user_memory_jobs
                   (tenant_id, user_id, run_id, session_id, user_message, assistant_message,
                     tool_evidence_json, payload_ciphertext, expires_at, status, attempts,
                     next_attempt_at, lease_until, created_at, updated_at)
                    VALUES (?, ?, ?, ?, '', '', '[]', ?, ?, 'pending', 0, 0, 0, ?, ?)""",
                (
                    tenant_id,
                    user_id,
                    run_id,
                    hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
                    payload,
                    now + JOB_RETENTION_SECONDS,
                    now,
                    now,
                ),
            )
            return True

    def claim_job(self) -> dict[str, Any] | None:
        now = time.time()
        # A global lock is unnecessary: BEGIN IMMEDIATE serializes claimers.
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM user_memory_jobs WHERE expires_at<=?", (now,))
                row = conn.execute(
                    """SELECT * FROM user_memory_jobs
                       WHERE expires_at>?
                         AND ((status='pending' AND next_attempt_at<=?)
                          OR (status='processing' AND lease_until<=?))
                       ORDER BY created_at ASC LIMIT 1""",
                    (now, now, now),
                ).fetchone()
                if not row:
                    conn.commit()
                    return None
                updated = conn.execute(
                    """UPDATE user_memory_jobs
                       SET status='processing', attempts=attempts+1, lease_until=?, updated_at=?
                       WHERE tenant_id=? AND user_id=? AND run_id=?
                          AND expires_at>?
                          AND ((status='pending' AND next_attempt_at<=?)
                            OR (status='processing' AND lease_until<=?))""",
                    (
                        now + RUN_LEASE_SECONDS,
                        now,
                        row["tenant_id"],
                        row["user_id"],
                        row["run_id"],
                        now,
                        now,
                        now,
                    ),
                ).rowcount
                conn.commit()
                if updated != 1:
                    return None
                job = dict(row)
                job["attempts"] = int(row["attempts"]) + 1
                try:
                    decoded = json.loads(self.cipher.decrypt(str(row["payload_ciphertext"])))
                    if not isinstance(decoded, dict):
                        raise ValueError("invalid encrypted job payload")
                    job.update(decoded)
                except (json.JSONDecodeError, ValueError):
                    conn.execute(
                        "DELETE FROM user_memory_jobs WHERE tenant_id=? AND user_id=? AND run_id=?",
                        (row["tenant_id"], row["user_id"], row["run_id"]),
                    )
                    conn.commit()
                    return None
                return job
            except BaseException:
                conn.rollback()
                raise

    def complete_job(self, tenant_id: str, user_id: str, run_id: str) -> None:
        with self._locked_connection(tenant_id, user_id) as conn:
            conn.execute(
                "DELETE FROM user_memory_jobs WHERE tenant_id=? AND user_id=? AND run_id=?",
                (tenant_id, user_id, run_id),
            )

    def retry_job(
        self,
        tenant_id: str,
        user_id: str,
        run_id: str,
        *,
        attempts: int,
        error_code: str,
    ) -> None:
        now = time.time()
        with self._locked_connection(tenant_id, user_id) as conn:
            if attempts >= MAX_JOB_ATTEMPTS:
                conn.execute(
                    """UPDATE user_memory_jobs
                       SET status='failed', user_message='', assistant_message='',
                           tool_evidence_json='[]', payload_ciphertext='', lease_until=0,
                           updated_at=?, last_error=?
                       WHERE tenant_id=? AND user_id=? AND run_id=?""",
                    (now, error_code[:80], tenant_id, user_id, run_id),
                )
            else:
                delay = min(60, 2 ** max(1, attempts))
                conn.execute(
                    """UPDATE user_memory_jobs
                       SET status='pending', next_attempt_at=?, lease_until=0,
                           updated_at=?, last_error=?
                       WHERE tenant_id=? AND user_id=? AND run_id=?""",
                    (now + delay, now, error_code[:80], tenant_id, user_id, run_id),
                )

    def job_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM user_memory_jobs GROUP BY status"
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def list_entries(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM user_memory_entries
                   WHERE tenant_id=? AND user_id=?
                   ORDER BY pinned DESC,
                            CASE entry_kind WHEN 'summary' THEN 0 ELSE 1 END,
                            importance DESC, last_seen DESC""",
                (tenant_id, user_id),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["content"] = self.cipher.decrypt(str(item["content"]))
            except ValueError:
                logger.warning("Discarding undecryptable user memory entry id=%s", item["id"])
                continue
            items.append(item)
        return items

    def format_for_prompt(self, tenant_id: str, user_id: str) -> str:
        rows = self.list_entries(tenant_id, user_id)
        eligible = [
            row for row in rows
            if row["entry_kind"] == "summary"
            or row["pinned"]
            or row["confidence"] >= 0.80
            and (row["category"] != "interaction_pattern" or row["evidence_count"] >= 2)
        ]
        eligible.sort(
            key=lambda row: (
                0 if row["pinned"] else 1 if row["entry_kind"] == "summary" else 2
                if row["category"] in {"task_history", "decision_history"} else 3,
                -float(row["last_seen"]),
                -int(row["importance"]),
            )
        )
        if not eligible:
            return ""
        sections = [
            "<user-memory>",
            "以下是当前可信用户的私有长期记忆，只能用于帮助当前用户；不得向其他用户或群聊披露。",
        ]
        pinned = [row for row in eligible if row["pinned"]]
        summaries = [row for row in eligible if not row["pinned"] and row["entry_kind"] == "summary"]
        recent = [row for row in eligible if not row["pinned"] and row["entry_kind"] != "summary"]
        if pinned:
            sections.append("## 用户明确要求保留")
            sections.extend(
                f"- 【{CATEGORY_LABELS[row['category']]}】{row['content']}" for row in pinned
            )
        if summaries:
            sections.append("## 长期摘要")
            sections.extend(
                f"- 【{CATEGORY_LABELS[row['category']]}】{row['content']}" for row in summaries
            )
        for category in CATEGORIES:
            category_rows = [row for row in recent if row["category"] == category]
            if category_rows:
                sections.append(f"## {CATEGORY_LABELS[category]}")
                sections.extend(f"- {row['content']}" for row in category_rows)
        # Preserve a well-formed trust boundary even when the projection is
        # truncated: add complete lines only and always close the delimiter.
        bounded: list[str] = []
        closing = "</user-memory>"
        for line in sections:
            candidate = "\n".join([*bounded, line, closing])
            if _utf8_len(candidate) > self.injection_bytes:
                break
            bounded.append(line)
        bounded.append(closing)
        return "\n".join(bounded)

    def format_for_user(self, tenant_id: str, user_id: str) -> str:
        rows = self.list_entries(tenant_id, user_id)
        used = sum(_utf8_len(row["content"]) for row in rows)
        lines = [f"你的长期记忆：{used:,}/{self.limit_bytes:,} 字节（{used / self.limit_bytes:.0%}）"]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if (
                row["entry_kind"] == "summary"
                or row["confidence"] >= 0.80
                and (row["category"] != "interaction_pattern" or row["evidence_count"] >= 2)
            ):
                grouped[row["category"]].append(row)
        for category in CATEGORIES:
            lines.append(f"\n【{CATEGORY_LABELS[category]}】")
            items = grouped[category]
            if not items:
                lines.append("- 暂无")
                continue
            for row in items[:12]:
                pin = " 📌" if row["pinned"] else ""
                lines.append(f"- {row['content']}{pin}")
        return "\n".join(lines)

    def upsert_candidates(
        self,
        tenant_id: str,
        user_id: str,
        candidates: Iterable[MemoryCandidate],
        *,
        session_id: str,
        run_id: str,
        expected_generation: int | None = None,
    ) -> dict[str, int]:
        candidates = list(candidates)
        stats = {"added": 0, "updated": 0, "forgotten": 0, "rejected": 0}
        now = time.time()
        with self._locked_connection(tenant_id, user_id) as conn:
            if expected_generation is not None:
                row = conn.execute(
                    "SELECT generation FROM user_memory_state WHERE tenant_id=? AND user_id=?",
                    (tenant_id, user_id),
                ).fetchone()
                current_generation = int(row["generation"]) if row else 0
                if current_generation != expected_generation:
                    stats["rejected"] = len(candidates)
                    return stats
            for candidate in candidates:
                if _unsafe_memory(candidate.content):
                    stats["rejected"] += 1
                    continue
                if candidate.operation == "forget":
                    needle = (candidate.match_text or candidate.content).strip()
                    matches = [
                        row for row in self._decrypted_rows(conn, tenant_id, user_id)
                        if needle.casefold() in str(row["content"]).casefold()
                    ]
                    if len(matches) == 1:
                        conn.execute("DELETE FROM user_memory_entries WHERE id=?", (matches[0]["id"],))
                        stats["forgotten"] += 1
                    else:
                        stats["rejected"] += 1
                    continue
                if candidate.confidence < 0.80 and not candidate.explicit:
                    stats["rejected"] += 1
                    continue
                content = candidate.content.strip()
                if _utf8_len(content) > MAX_ENTRY_BYTES:
                    stats["rejected"] += 1
                    continue
                digest = _content_hash(content)
                exact = conn.execute(
                    """SELECT id, content, content_bytes, evidence_count, pinned FROM user_memory_entries
                       WHERE tenant_id=? AND user_id=? AND category=? AND content_hash=?""",
                    (tenant_id, user_id, candidate.category, digest),
                ).fetchone()
                keyed = None
                if candidate.memory_key:
                    keyed = conn.execute(
                        """SELECT id, content, content_bytes, evidence_count, pinned FROM user_memory_entries
                           WHERE tenant_id=? AND user_id=? AND category=? AND memory_key=?
                           ORDER BY last_seen DESC LIMIT 1""",
                        (tenant_id, user_id, candidate.category, candidate.memory_key),
                    ).fetchone()
                replacement = None
                if candidate.operation == "replace" and not exact and not keyed:
                    needle = (candidate.match_text or "").strip()
                    if not needle:
                        stats["rejected"] += 1
                        continue
                    matches = [
                        row for row in self._decrypted_rows(conn, tenant_id, user_id)
                        if row["category"] == candidate.category
                        and needle.casefold() in str(row["content"]).casefold()
                    ]
                    if len(matches) != 1:
                        stats["rejected"] += 1
                        continue
                    replacement = matches[0]
                if exact and keyed and exact["id"] != keyed["id"]:
                    # The new canonical content already exists separately;
                    # remove the stale keyed fact before promoting the exact row.
                    conn.execute("DELETE FROM user_memory_entries WHERE id=?", (keyed["id"],))
                    keyed = None
                existing = exact or keyed or replacement
                if existing:
                    old_bytes = int(existing["content_bytes"] or 0)
                    projected = (
                        self._usage_in_conn(conn, tenant_id, user_id)
                        - old_bytes
                        + _utf8_len(content)
                    )
                    if projected > self.limit_bytes:
                        stats["rejected"] += 1
                        continue
                    conn.execute(
                        """UPDATE user_memory_entries
                           SET content=?, content_bytes=?, content_hash=?, memory_key=COALESCE(?, memory_key),
                               last_seen=?, confidence=MAX(confidence, ?), importance=MAX(importance, ?),
                               pinned=MAX(pinned, ?), evidence_count=evidence_count+1,
                               source_session_id=?, source_run_id=? WHERE id=?""",
                        (
                            self.cipher.encrypt(content),
                            _utf8_len(content),
                            digest,
                            candidate.memory_key,
                            now,
                            candidate.confidence,
                            candidate.importance,
                            int(candidate.pinned),
                            hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
                            run_id,
                            existing["id"],
                        ),
                    )
                    stats["updated"] += 1
                    continue
                projected = self._usage_in_conn(conn, tenant_id, user_id) + _utf8_len(content)
                if projected > self.limit_bytes:
                    stats["rejected"] += 1
                    continue
                conn.execute(
                    """INSERT INTO user_memory_entries
                       (id, tenant_id, user_id, category, content, content_bytes, content_hash, entry_kind,
                        confidence, importance, pinned, evidence_count, first_seen, last_seen,
                        source_session_id, source_run_id, memory_key)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'detail', ?, ?, ?, 1, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()), tenant_id, user_id, candidate.category,
                        self.cipher.encrypt(content), _utf8_len(content), digest,
                        candidate.confidence, candidate.importance,
                        int(candidate.pinned), now, now,
                        hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
                        run_id, candidate.memory_key,
                    ),
                )
                stats["added"] += 1
        return stats

    def find_matches(self, tenant_id: str, user_id: str, needle: str) -> list[dict[str, Any]]:
        normalized = needle.strip().casefold()
        return [
            row for row in self.list_entries(tenant_id, user_id)
            if normalized in str(row["content"]).casefold()
        ][:10]

    def _decrypted_rows(
        self, conn: sqlite3.Connection, tenant_id: str, user_id: str
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM user_memory_entries WHERE tenant_id=? AND user_id=?",
            (tenant_id, user_id),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["content"] = self.cipher.decrypt(str(item["content"]))
            except ValueError:
                continue
            result.append(item)
        return result

    def forget_unique(self, tenant_id: str, user_id: str, needle: str) -> tuple[bool, list[dict[str, Any]]]:
        with self._locked_connection(tenant_id, user_id) as conn:
            normalized = needle.strip().casefold()
            matches = [
                row for row in self._decrypted_rows(conn, tenant_id, user_id)
                if normalized in str(row["content"]).casefold()
            ][:10]
            if len(matches) != 1:
                return False, matches
            conn.execute("DELETE FROM user_memory_entries WHERE id=?", (matches[0]["id"],))
            return True, matches

    def request_clear(self, tenant_id: str, user_id: str) -> None:
        with self._locked_connection(tenant_id, user_id) as conn:
            conn.execute(
                """INSERT INTO user_memory_clear_confirmations VALUES (?, ?, ?)
                   ON CONFLICT(tenant_id, user_id) DO UPDATE SET expires_at=excluded.expires_at""",
                (tenant_id, user_id, time.time() + CLEAR_CONFIRMATION_TTL_SECONDS),
            )

    def confirm_clear(self, tenant_id: str, user_id: str) -> bool:
        with self._locked_connection(tenant_id, user_id) as conn:
            row = conn.execute(
                "SELECT expires_at FROM user_memory_clear_confirmations WHERE tenant_id=? AND user_id=?",
                (tenant_id, user_id),
            ).fetchone()
            conn.execute(
                "DELETE FROM user_memory_clear_confirmations WHERE tenant_id=? AND user_id=?",
                (tenant_id, user_id),
            )
            if not row or float(row["expires_at"]) <= time.time():
                return False
            conn.execute(
                "DELETE FROM user_memory_entries WHERE tenant_id=? AND user_id=?",
                (tenant_id, user_id),
            )
            conn.execute(
                "DELETE FROM user_memory_jobs WHERE tenant_id=? AND user_id=?",
                (tenant_id, user_id),
            )
            conn.execute(
                """INSERT INTO user_memory_state (tenant_id, user_id, generation) VALUES (?, ?, 1)
                   ON CONFLICT(tenant_id, user_id)
                   DO UPDATE SET generation=user_memory_state.generation+1""",
                (tenant_id, user_id),
            )
        self.reclaim_space(secure=True)
        return True

    def clear_scope(
        self,
        tenant_id: str,
        user_id: str,
        *,
        cleared_at: float | None = None,
    ) -> None:
        with self._locked_connection(tenant_id, user_id) as conn:
            marker = f"backend-clear:{cleared_at:.6f}" if cleared_at is not None else None
            if marker and conn.execute(
                """SELECT 1 FROM user_memory_migrations
                   WHERE tenant_id=? AND user_id=? AND migration=?""",
                (tenant_id, user_id, marker),
            ).fetchone():
                return
            if cleared_at is None:
                conn.execute(
                    "DELETE FROM user_memory_entries WHERE tenant_id=? AND user_id=?",
                    (tenant_id, user_id),
                )
                conn.execute(
                    "DELETE FROM user_memory_jobs WHERE tenant_id=? AND user_id=?",
                    (tenant_id, user_id),
                )
            else:
                conn.execute(
                    """DELETE FROM user_memory_entries
                       WHERE tenant_id=? AND user_id=? AND last_seen<=?""",
                    (tenant_id, user_id, cleared_at),
                )
                conn.execute(
                    """DELETE FROM user_memory_jobs
                       WHERE tenant_id=? AND user_id=? AND created_at<=?""",
                    (tenant_id, user_id, cleared_at),
                )
            conn.execute(
                "DELETE FROM user_memory_clear_confirmations WHERE tenant_id=? AND user_id=?",
                (tenant_id, user_id),
            )
            conn.execute(
                """INSERT INTO user_memory_state (tenant_id, user_id, generation) VALUES (?, ?, 1)
                   ON CONFLICT(tenant_id, user_id)
                   DO UPDATE SET generation=user_memory_state.generation+1""",
                (tenant_id, user_id),
            )
            if marker:
                conn.execute(
                    "INSERT OR IGNORE INTO user_memory_migrations VALUES (?, ?, ?, ?)",
                    (tenant_id, user_id, marker, time.time()),
                )
        self.reclaim_space(secure=True)

    def compression_candidates(
        self,
        tenant_id: str,
        user_id: str,
        *,
        target_bytes: int | None = None,
    ) -> list[dict[str, Any]]:
        used = self.usage_bytes(tenant_id, user_id)
        desired_bytes = self.target_bytes if target_bytes is None else max(0, int(target_bytes))
        if target_bytes is None and used < self.trigger_bytes:
            return []
        if used <= desired_bytes:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, category, content, entry_kind, importance, last_seen
                   FROM user_memory_entries
                   WHERE tenant_id=? AND user_id=? AND pinned=0
                   ORDER BY CASE WHEN category IN ('task_history','decision_history','interaction_pattern')
                                 THEN 0 ELSE 1 END,
                            CASE entry_kind WHEN 'summary' THEN 0 ELSE 1 END,
                            last_seen ASC, importance ASC""",
                (tenant_id, user_id),
            ).fetchall()
        selected: list[dict[str, Any]] = []
        reclaimable = 0
        for row in rows:
            item = dict(row)
            try:
                item["content"] = self.cipher.decrypt(str(item["content"]))
            except ValueError:
                continue
            selected.append(item)
            reclaimable += _utf8_len(item["content"])
            if used - reclaimable <= desired_bytes:
                break
        counts: dict[str, int] = defaultdict(int)
        for row in selected:
            counts[row["category"]] += 1
        return [
            row for row in selected
            if counts[row["category"]] >= 2 or row["entry_kind"] == "summary"
        ]

    def apply_compression(
        self,
        tenant_id: str,
        user_id: str,
        selected: list[dict[str, Any]],
        result: CompressionResult,
    ) -> bool:
        selected_by_id = {row["id"]: row for row in selected}
        supplied_ids = [source_id for summary in result.summaries for source_id in summary.source_ids]
        if len(supplied_ids) != len(set(supplied_ids)) or set(supplied_ids) != set(selected_by_id):
            return False
        for summary in result.summaries:
            if _unsafe_memory(summary.content) or _utf8_len(summary.content) > MAX_ENTRY_BYTES:
                return False
            if any(selected_by_id[source_id]["category"] != summary.category for source_id in summary.source_ids):
                return False
            if len(summary.source_ids) == 1 and selected_by_id[summary.source_ids[0]]["entry_kind"] != "summary":
                return False
        now = time.time()
        with self._locked_connection(tenant_id, user_id) as conn:
            placeholders = ",".join("?" for _ in supplied_ids)
            existing_ids = {
                row["id"] for row in conn.execute(
                    f"""SELECT id FROM user_memory_entries
                        WHERE tenant_id=? AND user_id=? AND id IN ({placeholders})""",
                    (tenant_id, user_id, *supplied_ids),
                ).fetchall()
            }
            if existing_ids != set(supplied_ids):
                return False
            replacement_bytes = sum(_utf8_len(summary.content) for summary in result.summaries)
            current = self._usage_in_conn(conn, tenant_id, user_id)
            removed = sum(_utf8_len(selected_by_id[source_id]["content"]) for source_id in supplied_ids)
            if replacement_bytes >= removed or current - removed + replacement_bytes > self.limit_bytes:
                return False
            conn.execute(
                f"DELETE FROM user_memory_entries WHERE id IN ({placeholders})",
                supplied_ids,
            )
            for summary in result.summaries:
                conn.execute(
                    """INSERT INTO user_memory_entries
                       (id, tenant_id, user_id, category, content, content_bytes, content_hash, entry_kind,
                        confidence, importance, pinned, evidence_count, first_seen, last_seen)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'summary', 1.0, 4, 0, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()), tenant_id, user_id, summary.category,
                        self.cipher.encrypt(summary.content), _utf8_len(summary.content),
                        _content_hash(summary.content), len(summary.source_ids), now, now,
                    ),
                )
        self.reclaim_space()
        return True

    def migrate_legacy_user_file(self, tenant_id: str, user_id: str) -> int:
        migration = "legacy-user-md-v1"
        with self._connect() as conn:
            done = conn.execute(
                "SELECT 1 FROM user_memory_migrations WHERE tenant_id=? AND user_id=? AND migration=?",
                (tenant_id, user_id, migration),
            ).fetchone()
        if done:
            return 0
        # Legacy directories were named with platform IDs. Refuse path-like
        # identifiers even though the current subject is trusted.
        safe_user_segment = user_id if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", user_id) else ""
        legacy_path = get_memory_base_dir() / "users" / safe_user_segment / "USER.md"
        entries: list[str] = []
        if safe_user_segment and legacy_path.exists():
            try:
                raw = legacy_path.read_text(encoding="utf-8")
                entries = [item.strip() for item in raw.split(ENTRY_DELIMITER) if item.strip()]
            except OSError:
                logger.warning("Legacy user memory could not be read", exc_info=True)
        candidates = [
            MemoryCandidate(
                category="personal_fact",
                content=_clip_utf8(entry, 800),
                confidence=1.0,
                importance=3,
                explicit=True,
                pinned=False,
            )
            for entry in entries
            if not _unsafe_memory(entry)
        ]
        stats = self.upsert_candidates(
            tenant_id, user_id, candidates, session_id="legacy-import", run_id="legacy-import"
        )
        with self._locked_connection(tenant_id, user_id) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO user_memory_migrations VALUES (?, ?, ?, ?)",
                (tenant_id, user_id, migration, time.time()),
            )
        return stats["added"]

    def reclaim_space(self, *, secure: bool = False) -> None:
        try:
            with self._connect() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)" if secure else "PRAGMA wal_checkpoint(PASSIVE)")
                conn.execute("PRAGMA incremental_vacuum(32)")
        except sqlite3.Error:
            logger.debug("User memory incremental vacuum failed", exc_info=True)


def parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("LLM memory output must be a JSON object")
    return value


def extraction_prompt(
    existing_memory: str,
    user_message: str,
    assistant_message: str,
    tool_evidence: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    schema = ExtractionResult.model_json_schema()
    return [
        {
            "role": "system",
            "content": (
                "你是用户长期记忆提取器。只提取用户明确陈述、明确决定，或回复中可由真实操作结果支持的事实。"
                "禁止保存模型猜测、临时查询结果、原始业务记录、密码、Token、Cookie、密钥、权限上下文或完整 prompt。"
                "六类 category 只能是 preference、personal_fact、professional_knowledge、task_history、"
                "decision_history、interaction_pattern。稳定画像字段必须给出 memory_key；现有同 key 信息变化时用 replace。"
                "任务执行结果若来自工具，必须设置 evidence_source=tool_result 并引用可信 tool_evidence_ids；"
                "不得从助手文字臆测工具是否成功。用户明确说‘记住’时 explicit=true 且 pinned=true；"
                "明确说‘忘记’时 operation=forget 并给出 match_text。没有值得长期保存的信息时返回 memories=[]。"
                "只输出 JSON，不要 Markdown。JSON Schema：" + json.dumps(schema, ensure_ascii=False)
            ),
        },
        {
            "role": "user",
            "content": (
                f"现有记忆摘要：\n{existing_memory or '（空）'}\n\n"
                f"本轮用户消息：\n{_clip_utf8(user_message, 12000)}\n\n"
                f"本轮助手回复：\n{_clip_utf8(assistant_message, 12000)}\n\n"
                "可信工具证据（仅此处可证明工具结果）：\n"
                + json.dumps(tool_evidence or [], ensure_ascii=False)
            ),
        },
    ]


def compression_prompt(
    selected: list[dict[str, Any]],
    *,
    replacement_budget_bytes: int | None = None,
) -> list[dict[str, str]]:
    schema = CompressionResult.model_json_schema()
    payload = [
        {"id": row["id"], "category": row["category"], "content": row["content"]}
        for row in selected
    ]
    return [
        {
            "role": "system",
            "content": (
                "你是记忆压缩器。按 category 合并较早记录，保留所有仍有效的事实、任务结果和决策结论，"
                "不得增加来源中不存在的信息。每个 source id 必须且只能出现一次；通常每个摘要至少覆盖两个同类来源，"
                "仅重新缩短已经是 summary 的单条来源时允许一个 source id。"
                + (
                    f"所有摘要正文的 UTF-8 总字节数不得超过 {replacement_budget_bytes}。"
                    if replacement_budget_bytes is not None else ""
                )
                + "只输出 JSON，不要 Markdown。JSON Schema："
                + json.dumps(schema, ensure_ascii=False)
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


async def review_turn(
    repository: UserMemoryRepository,
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    run_id: str,
    user_message: str,
    assistant_message: str,
    tool_evidence: list[dict[str, Any]] | None = None,
    llm_call: Callable[[list[dict[str, str]], str], Any],
) -> dict[str, int]:
    """Extract, persist, and if necessary compact one completed turn."""

    repository.migrate_legacy_user_file(tenant_id, user_id)
    if not repository.claim_run(tenant_id, user_id, run_id):
        return {"added": 0, "updated": 0, "forgotten": 0, "rejected": 0}
    try:
        generation = repository.generation(tenant_id, user_id)
        existing = repository.format_for_prompt(tenant_id, user_id)
        raw = await llm_call(
            extraction_prompt(existing, user_message, assistant_message, tool_evidence),
            "memory_extraction",
        )
        extraction = ExtractionResult.model_validate(parse_json_object(raw))
        verified_evidence_ids = {
            str(item.get("evidence_id"))
            for item in (tool_evidence or [])
            if item.get("verified") is True and item.get("evidence_id")
        }
        valid_memories: list[MemoryCandidate] = []
        evidence_rejections = 0
        explicit_remember_intent = re.search(
            r"(?:记住|记一下|保存到(?:长期)?记忆|长期记忆)",
            user_message,
            flags=re.IGNORECASE,
        ) is not None
        for candidate in extraction.memories:
            if candidate.evidence_source == "tool_result" and (
                not candidate.tool_evidence_ids
                or not set(candidate.tool_evidence_ids).issubset(verified_evidence_ids)
            ):
                evidence_rejections += 1
                continue
            if (
                candidate.category == "task_history"
                and candidate.evidence_source != "tool_result"
                and not (candidate.explicit and candidate.pinned and explicit_remember_intent)
            ):
                evidence_rejections += 1
                continue
            valid_memories.append(candidate)
        extraction = ExtractionResult(memories=valid_memories)
    except BaseException:
        repository.release_run(tenant_id, user_id, run_id)
        raise
    try:
        incoming_bytes = sum(
            _utf8_len(candidate.content)
            for candidate in extraction.memories
            if candidate.operation in {"upsert", "replace"}
        )
        if repository.usage_bytes(tenant_id, user_id) + incoming_bytes >= repository.trigger_bytes:
            try:
                prewrite_target = min(
                    repository.target_bytes,
                    max(0, repository.limit_bytes - incoming_bytes),
                )
                await compact_user_memory_to_target(
                    repository,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    llm_call=llm_call,
                    target_bytes=prewrite_target,
                )
            except Exception:
                logger.warning("User memory pre-write compression failed", exc_info=True)
        stats = repository.upsert_candidates(
            tenant_id,
            user_id,
            extraction.memories,
            session_id=session_id,
            run_id=run_id,
            expected_generation=generation,
        )
        if repository.usage_bytes(tenant_id, user_id) >= repository.trigger_bytes:
            try:
                await compact_user_memory_to_target(
                    repository,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    llm_call=llm_call,
                )
            except Exception:
                logger.warning("User memory post-write compression failed", exc_info=True)
        stats["rejected"] += evidence_rejections
        repository.complete_run(tenant_id, user_id, run_id)
        return stats
    except BaseException:
        repository.release_run(tenant_id, user_id, run_id)
        raise


async def compact_user_memory(
    repository: UserMemoryRepository,
    *,
    tenant_id: str,
    user_id: str,
    llm_call: Callable[[list[dict[str, str]], str], Any],
    target_bytes: int | None = None,
) -> bool:
    selected = repository.compression_candidates(
        tenant_id,
        user_id,
        target_bytes=target_bytes,
    )
    if not selected:
        return False
    current_bytes = repository.usage_bytes(tenant_id, user_id)
    removed_bytes = sum(_utf8_len(str(row["content"])) for row in selected)
    desired_bytes = repository.target_bytes if target_bytes is None else max(0, int(target_bytes))
    replacement_budget = max(1, desired_bytes - max(0, current_bytes - removed_bytes))
    raw = await llm_call(
        compression_prompt(selected, replacement_budget_bytes=replacement_budget),
        "memory_compression",
    )
    result = CompressionResult.model_validate(parse_json_object(raw))
    return repository.apply_compression(tenant_id, user_id, selected, result)


async def compact_user_memory_to_target(
    repository: UserMemoryRepository,
    *,
    tenant_id: str,
    user_id: str,
    llm_call: Callable[[list[dict[str, str]], str], Any],
    target_bytes: int | None = None,
    max_passes: int = 4,
) -> bool:
    desired_bytes = repository.target_bytes if target_bytes is None else max(0, int(target_bytes))
    changed = False
    for _ in range(max(1, max_passes)):
        before = repository.usage_bytes(tenant_id, user_id)
        if before <= desired_bytes:
            break
        applied = await compact_user_memory(
            repository,
            tenant_id=tenant_id,
            user_id=user_id,
            llm_call=llm_call,
            target_bytes=desired_bytes,
        )
        after = repository.usage_bytes(tenant_id, user_id)
        if not applied or after >= before:
            break
        changed = True
    return changed


# Backward-compatible factory retained for non-Dazah upstream callers. Dazah
# explicitly uses ``skip_memory=True`` and the tenant-scoped repository above.
def create_memory_store_for_user(
    user_id: str | None = None,
    memory_char_limit: int = 2200,
    user_char_limit: int = 1375,
):
    import types

    from tools.memory_tool import MemoryStore

    store = MemoryStore(memory_char_limit=memory_char_limit, user_char_limit=user_char_limit)
    if not user_id or not user_id.strip():
        return store

    # Non-Dazah upstream callers still expect the old MemoryStore interface.
    # Keep them isolated without the previous monkey-patch bug where
    # load_from_disk() bypassed _path_for() and loaded the global USER.md.
    safe_segment = user_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", safe_segment):
        raise ValueError("Unsafe user id for legacy memory store")
    user_dir = get_memory_base_dir() / "users" / safe_segment
    user_dir.mkdir(parents=True, exist_ok=True)

    def scoped_path(self_or_target, target=None):
        selected = target if target is not None else self_or_target
        filename = "USER.md" if selected == "user" else "MEMORY.md"
        return user_dir / filename

    def scoped_load(self):
        self.memory_entries = list(dict.fromkeys(self._read_file(self._path_for("memory"))))
        self.user_entries = list(dict.fromkeys(self._read_file(self._path_for("user"))))
        sanitized_memory = self._sanitize_entries_for_snapshot(self.memory_entries, "MEMORY.md")
        sanitized_user = self._sanitize_entries_for_snapshot(self.user_entries, "USER.md")
        self._system_prompt_snapshot = {
            "memory": self._render_block("memory", sanitized_memory),
            "user": self._render_block("user", sanitized_user),
        }

    store._path_for = types.MethodType(scoped_path, store)
    store.load_from_disk = types.MethodType(scoped_load, store)
    return store
