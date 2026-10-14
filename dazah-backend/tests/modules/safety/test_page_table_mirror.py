"""页面本地镜像（全量副本）测试：同步 upsert/软删、读取切换、写透。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.modules.safety.models import (
    SafetyPageFeishuConfig,
    SafetyPageTableMirrorRecord,
)
from app.modules.safety.scheduled import SafetyPageMirrorSyncGenerator
from app.modules.safety.service import page_table

PAGE_KEY = "safety:risk-hazard:hazard-inspection:hazard-duty"
APP_TOKEN = "bascnTest"
TABLE_ID = "tblTest"

_FIELDS = [
    {"field_id": "fld1", "field_name": "记录编号", "type": 1, "is_primary": True},
    {"field_id": "fld3", "field_name": "值班日期", "type": 5},
    {
        "field_id": "fld4",
        "field_name": "整改情况",
        "type": 3,
        "property": {"options": [{"name": "未整改"}, {"name": "已整改"}]},
    },
]


class _FakeResult:
    def __init__(self, value: object = None, list_value: list | None = None) -> None:
        self._value = value
        self._list = (
            list_value
            if list_value is not None
            else ([value] if value is not None else [])
        )

    def scalar_one_or_none(self) -> object:
        return self._value

    def scalar_one(self) -> object:
        return self._value

    def scalars(self) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: list(self._list))


class _FakeSession:
    def __init__(
        self,
        value: object = None,
        results: list[_FakeResult] | None = None,
    ) -> None:
        self.config = value if not isinstance(value, list) else None
        self._results = list(results or [])
        self.commits = 0
        self.rollbacks = 0
        self.added: list[object] = []

    async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        if self._results:
            return self._results.pop(0)
        return _FakeResult(self.config)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, obj: object) -> None:
        return None


class _FakeClient:
    def __init__(
        self,
        rows: list[dict] | None = None,
        error: str | None = None,
        record_fields: dict | None = None,
    ) -> None:
        self.rows = rows or []
        self.error = error
        self.record_fields = record_fields or {}
        self.search_calls = 0

    async def list_fields(self, table_id: str | None = None) -> list[dict]:
        return _FIELDS

    async def search_records_with_result(
        self, **kwargs: object
    ) -> tuple[list[dict], str | None]:
        self.search_calls += 1
        return self.rows, self.error

    async def get_record(
        self, record_id: str, table_id: str | None = None, **kwargs: object
    ) -> dict:
        return self.record_fields


class _FakeSessionFactory:
    """替代 async_session_factory：返回持有指定会话的异步上下文。"""

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self) -> "_FakeSessionFactory":
        return self

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        return None


def _config(**overrides: object) -> SafetyPageFeishuConfig:
    values: dict[str, object] = {
        "page_key": PAGE_KEY,
        "app_token": APP_TOKEN,
        "table_id": TABLE_ID,
        "is_enabled": True,
        "hidden_field_names": [],
        "is_mirrored": True,
        "last_synced_at": None,
        "last_sync_status": None,
        "last_sync_error": None,
        "last_sync_record_count": None,
    }
    values.update(overrides)
    return SafetyPageFeishuConfig(**values)


def _install(
    monkeypatch: pytest.MonkeyPatch,
    client: _FakeClient,
    *,
    acquire: bool = True,
    mirror_session: _FakeSession | None = None,
) -> _FakeSession:
    """安装飞书客户端与缓存/锁替身；mirror_session 供写透/失败回写路径使用。"""
    monkeypatch.setattr(page_table, "SafetyBitableClient", lambda **kwargs: client)
    monkeypatch.setattr(page_table, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "cache_set", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "cache_delete", AsyncMock(return_value=None))
    monkeypatch.setattr(
        page_table, "acquire_lock", AsyncMock(return_value=acquire)
    )
    monkeypatch.setattr(page_table, "release_lock", AsyncMock(return_value=None))
    monkeypatch.setattr(page_table, "record_audit_log", AsyncMock(return_value=None))
    monkeypatch.setattr(
        page_table,
        "async_session_factory",
        _FakeSessionFactory(mirror_session or _FakeSession(None)),
    )
    return _FakeSession(_config())


# ── 同步 ──


async def test_sync_upserts_revives_and_soft_deletes(monkeypatch) -> None:
    config = _config()
    existing_kept = SafetyPageTableMirrorRecord(
        page_key=PAGE_KEY, record_id="rec-1", fields={"记录编号": "旧值"},
        search_text="旧值",
    )
    existing_revived = SafetyPageTableMirrorRecord(
        page_key=PAGE_KEY, record_id="rec-2", fields={}, search_text="x",
    )
    existing_revived.is_deleted = True  # 曾被软删、远端仍存在 → 应复活
    existing_stale = SafetyPageTableMirrorRecord(
        page_key=PAGE_KEY, record_id="rec-gone", fields={}, search_text="y",
    )
    rows = [
        {"record_id": "rec-1", "fields": {"记录编号": [{"text": "YH-1"}]}},
        {"record_id": "rec-2", "fields": {"整改情况": "已整改"}},
    ]
    client = _FakeClient(rows=rows)
    db = _FakeSession(
        None,
        results=[
            _FakeResult(config),
            _FakeResult(
                None,
                list_value=[existing_kept, existing_revived, existing_stale],
            ),
        ],
    )
    _install(monkeypatch, client, mirror_session=db)

    count = await page_table.sync_page_table_mirror(db, PAGE_KEY)

    assert count == 2
    # rec-1 原地更新，rec-2 复活，rec-gone 软删，无新增之外的写
    assert existing_kept.fields["记录编号"] == "YH-1"
    assert existing_revived.is_deleted is False
    assert existing_stale.is_deleted is True
    assert db.added == []
    assert db.commits == 1
    assert db.rollbacks == 0
    assert config.last_sync_status == "success"


async def test_sync_writes_status_back_to_config(monkeypatch) -> None:
    config = _config()
    client = _FakeClient(rows=[{"record_id": "rec-1", "fields": {}}])
    db = _FakeSession(
        None,
        results=[
            _FakeResult(config),
            _FakeResult(None, list_value=[]),
        ],
    )
    _install(monkeypatch, client, mirror_session=db)

    count = await page_table.sync_page_table_mirror(db, PAGE_KEY)

    assert count == 1
    assert config.last_sync_status == "success"
    assert config.last_sync_record_count == 1
    assert config.last_synced_at is not None


async def test_sync_deduplicates_overlapping_pages(monkeypatch) -> None:
    """飞书翻页跨页会返回同一条记录，重复插入会撞 (page_key, record_id) 唯一索引。"""
    config = _config()
    rows = [
        {"record_id": "rec-1", "fields": {"记录编号": [{"text": "YH-1"}]}},
        {"record_id": "rec-2", "fields": {"整改情况": "已整改"}},
        # 第二页重叠回来的 rec-1
        {"record_id": "rec-1", "fields": {"记录编号": [{"text": "YH-1"}]}},
    ]
    client = _FakeClient(rows=rows)
    db = _FakeSession(
        None,
        results=[_FakeResult(config), _FakeResult(None, list_value=[])],
    )
    _install(monkeypatch, client, mirror_session=db)

    count = await page_table.sync_page_table_mirror(db, PAGE_KEY)

    assert count == 2
    added = [
        row for row in db.added if isinstance(row, SafetyPageTableMirrorRecord)
    ]
    assert [row.record_id for row in added] == ["rec-1", "rec-2"]
    assert config.last_sync_record_count == 2


async def test_sync_failure_rolls_back_and_records_error(monkeypatch) -> None:
    config = _config()
    client = _FakeClient(error="Permission denied")
    db = _FakeSession(None, results=[_FakeResult(config)])
    failure_session = _FakeSession(None, results=[_FakeResult(config)])
    _install(monkeypatch, client, mirror_session=failure_session)

    with pytest.raises(AppException) as excinfo:
        await page_table.sync_page_table_mirror(db, PAGE_KEY)

    assert excinfo.value.status_code == 502
    assert db.rollbacks == 1
    assert config.last_sync_status == "failed"
    assert "Permission denied" in (config.last_sync_error or "")


async def test_sync_lock_conflict_returns_409(monkeypatch) -> None:
    client = _FakeClient()
    db = _FakeSession(None, results=[_FakeResult(_config())])
    _install(monkeypatch, client, acquire=False)

    with pytest.raises(AppException) as excinfo:
        await page_table.sync_page_table_mirror(db, PAGE_KEY)
    assert excinfo.value.status_code == 409


# ── 读取切换 ──


async def test_mirror_read_path_uses_local_rows(monkeypatch) -> None:
    config = _config(is_mirrored=True, last_synced_at=datetime.now(UTC))
    row1 = SimpleNamespace(
        record_id="rec-1", fields={"值班日期": "2026-02-09", "整改情况": "未整改"}
    )
    row2 = SimpleNamespace(record_id="rec-2", fields={})
    client = _FakeClient()
    db = _FakeSession(
        None,
        results=[
            _FakeResult(config),
            _FakeResult(2),                                # count
            _FakeResult(None, list_value=[row1, row2]),    # 当前页行
        ],
    )
    _install(monkeypatch, client, mirror_session=db)

    result = await page_table.list_page_table_records(
        db, PAGE_KEY, conditions=[("值班日期", "2026-02-09")]
    )

    # 镜像路径不触发飞书搜索，也不出现截断
    assert client.search_calls == 0
    assert result.truncated is False
    assert result.total == 2
    assert [record.record_id for record in result.records] == ["rec-1", "rec-2"]
    assert result.records[0].fields["整改情况"] == "未整改"


async def test_unsynced_mirror_falls_back_to_live(monkeypatch) -> None:
    config = _config(is_mirrored=True, last_synced_at=None)
    scheduled: list[str] = []
    monkeypatch.setattr(
        page_table, "_schedule_mirror_sync", lambda page_key: scheduled.append(page_key)
    )
    rows = [{"record_id": "rec-1", "fields": {"记录编号": [{"text": "YH-1"}]}}]
    client = _FakeClient(rows=rows)
    db = _FakeSession(None, results=[_FakeResult(config)])
    _install(monkeypatch, client, mirror_session=db)

    result = await page_table.list_page_table_records(db, PAGE_KEY)

    assert scheduled == [PAGE_KEY]
    assert client.search_calls == 1
    assert result.total == 1


async def test_mirror_disabled_keeps_live_path(monkeypatch) -> None:
    config = _config(is_mirrored=False)
    rows = [{"record_id": "rec-1", "fields": {"记录编号": [{"text": "YH-1"}]}}]
    client = _FakeClient(rows=rows)
    db = _FakeSession(None, results=[_FakeResult(config)])
    _install(monkeypatch, client, mirror_session=db)

    result = await page_table.list_page_table_records(db, PAGE_KEY)

    assert client.search_calls == 1
    assert result.total == 1


# ── 写透 ──


async def test_write_through_updates_existing_mirror_row(monkeypatch) -> None:
    config = _config(is_mirrored=True)
    row = SafetyPageTableMirrorRecord(
        page_key=PAGE_KEY, record_id="rec-1", fields={"记录编号": "旧值"},
        search_text="旧值",
    )
    client = _FakeClient()
    mirror_session = _FakeSession(
        None, results=[_FakeResult(config), _FakeResult(row)]
    )
    _install(monkeypatch, client, mirror_session=mirror_session)

    ok = await page_table._write_through_mirror(
        PAGE_KEY, "rec-1", {"记录编号": [{"text": "YH-9"}]}
    )

    assert ok is True
    assert row.fields["记录编号"] == "YH-9"
    assert row.is_deleted is False


async def test_write_through_skips_when_mirror_disabled(monkeypatch) -> None:
    client = _FakeClient()
    mirror_session = _FakeSession(
        None, results=[_FakeResult(_config(is_mirrored=False))]
    )
    _install(monkeypatch, client, mirror_session=mirror_session)

    ok = await page_table._write_through_mirror(
        PAGE_KEY, "rec-1", {"记录编号": [{"text": "YH-9"}]}
    )

    assert ok is False
    assert mirror_session.added == []


# ── 调度 ──


async def test_mirror_sync_generator_finds_due_pages() -> None:
    generator = SafetyPageMirrorSyncGenerator()
    session = _FakeSession(
        None,
        results=[
            _FakeResult(
                None, list_value=["safety:ops-safety:daily-risk-report"]
            )
        ],
    )

    due = await generator.find_due(session)

    assert due == ["safety:ops-safety:daily-risk-report"]
