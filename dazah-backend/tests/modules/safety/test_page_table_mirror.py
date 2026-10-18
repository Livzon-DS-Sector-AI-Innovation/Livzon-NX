"""页面本地镜像（全量副本）测试：同步 upsert/软删、读取切换、写透。"""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.modules.safety.models import (
    SafetyPageFeishuConfig,
    SafetyPageTableMirrorRecord,
)
from app.modules.safety.scheduled import SafetyPageMirrorSyncGenerator
from app.modules.safety.schemas.page_table import PageTableRecordCondition
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

    def all(self) -> list:
        return list(self._list)


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
        fields: list[dict] | None = None,
    ) -> None:
        self.rows = rows or []
        self.error = error
        self.record_fields = record_fields or {}
        self.fields = fields if fields is not None else _FIELDS
        self.search_calls = 0

    async def list_fields(self, table_id: str | None = None) -> list[dict]:
        return self.fields

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
        db, PAGE_KEY,
        conditions=[PageTableRecordCondition(field="值班日期", value="2026-02-09")]
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


# ── 独立同步循环（mirror_sync_loop）──


async def test_mirror_sync_loop_runs_due_pages_and_survives_failures() -> None:
    """独立循环：本轮执行到期的页面；单页失败不中断本轮，整轮异常不退出循环。"""
    from app.modules.safety import scheduled as scheduled_module

    calls: list[str] = []
    failures: set[str] = set()

    class _LoopGenerator:
        async def find_due(self, session: object) -> list[str]:
            return ["page-ok", "page-bad"]

        async def execute_one(self, session: object, item: object) -> None:
            page_key = str(item)
            calls.append(page_key)
            if page_key in failures:
                raise RuntimeError("boom")

    original = scheduled_module.SafetyPageMirrorSyncGenerator
    original_stop = scheduled_module._mirror_sync_stop
    original_interval = scheduled_module.MIRROR_SYNC_INTERVAL
    original_factory = page_table.async_session_factory
    scheduled_module.SafetyPageMirrorSyncGenerator = _LoopGenerator  # type: ignore[misc]
    # 用极短间隔驱动循环快速跑两轮；第二轮前让 find_due 抛整轮异常验证不退出
    scheduled_module.MIRROR_SYNC_INTERVAL = timedelta(milliseconds=50)
    stop = asyncio.Event()
    scheduled_module._mirror_sync_stop = stop

    @contextlib.asynccontextmanager
    async def _fake_factory():
        yield SimpleNamespace(commit=AsyncMock(return_value=None))

    page_table.async_session_factory = _fake_factory
    failures.add("page-bad")
    try:
        task = asyncio.create_task(scheduled_module.mirror_sync_loop())
        await asyncio.sleep(0.3)
        assert calls.count("page-ok") >= 2
        assert "page-bad" in calls  # 单页失败被捕获，本轮继续

        failures.clear()
        calls.clear()
        await asyncio.sleep(0.3)
        assert calls.count("page-bad") >= 1  # 下一轮恢复正常执行失败页
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        scheduled_module.SafetyPageMirrorSyncGenerator = original  # type: ignore[misc]
        scheduled_module._mirror_sync_stop = original_stop
        scheduled_module.MIRROR_SYNC_INTERVAL = original_interval
        page_table.async_session_factory = original_factory


# ── 筛选联动（仪表盘/筛选栏与列表同口径） ──


def _ledger_fields() -> list[dict]:
    return _FIELDS + [
        {"field_id": "fld8", "field_name": "车间/位置", "type": 1},
        {"field_id": "fld9", "field_name": "负责人", "type": 11},
    ]


async def test_mirror_records_text_condition_matches_normalized_bucket(
    monkeypatch,
) -> None:
    """文本条件（部门/车间）按图表桶归一口径：别名原始写法同样命中。"""
    config = _config(
        is_mirrored=True,
        last_synced_at=datetime.now(UTC),
        workshop_aliases={"201-1": "201一车间"},
    )
    row1 = SimpleNamespace(
        record_id="rec-1",
        fields={"车间/位置": [{"text": "201-1车间"}], "整改情况": "未整改"},
    )
    row2 = SimpleNamespace(
        record_id="rec-2",
        fields={"车间/位置": [{"text": "原料罐区"}], "整改情况": "已整改"},
    )
    client = _FakeClient(fields=_ledger_fields())
    db = _FakeSession(
        None,
        results=[
            _FakeResult(config),
            # 文本条件走全量取回 + Python 归一过滤，不再 SQL 分页
            _FakeResult(None, list_value=[row1, row2]),
        ],
    )
    _install(monkeypatch, client, mirror_session=db)

    result = await page_table.list_page_table_records(
        db,
        PAGE_KEY,
        conditions=[PageTableRecordCondition(field="车间/位置", value="201一车间")],
    )

    assert client.search_calls == 0
    assert result.total == 1
    assert result.records[0].record_id == "rec-1"


async def test_stats_applies_keyword_and_date_range_filters(monkeypatch) -> None:
    """仪表盘与筛选联动：关键字 + 日期范围（gte/lte）过滤后再聚合。"""
    config = _config(is_mirrored=True, last_synced_at=datetime.now(UTC))
    client = _FakeClient()
    db = _FakeSession(
        None,
        results=[
            _FakeResult(config),
            # _collect_table_records 选择的是 fields 列本身（解码后的字典）
            _FakeResult(
                None,
                list_value=[
                    ("rec-1", {"值班日期": "2026-02-09", "整改情况": "未整改"}),
                    ("rec-2", {"值班日期": "2026-03-11", "整改情况": "已整改"}),
                ],
            ),
        ],
    )
    _install(monkeypatch, client, mirror_session=db)

    result = await page_table.get_page_table_stats(
        db,
        PAGE_KEY,
        group_by=["整改情况"],
        conditions=[
            PageTableRecordCondition(field="值班日期", value="2026-03-01", op="gte")
        ],
    )

    assert client.search_calls == 0
    assert result.total == 1
    assert [bucket.key for bucket in result.groups[0].buckets] == ["已整改"]


async def test_field_values_splits_person_names_and_normalizes_text(
    monkeypatch,
) -> None:
    """筛选选项接口：人员按个人姓名计数，文本字段按车间归一口径归组。"""
    config = _config(
        is_mirrored=True,
        last_synced_at=datetime.now(UTC),
        workshop_aliases={"201-1": "201一车间"},
    )
    # values 接口选择的是 fields 列本身（解码后的字典）
    owner_fields = [
        {
            "负责人": [
                {"id": "ou1", "name": "李玮"},
                {"id": "ou2", "name": "王思博"},
            ],
            "车间/位置": [{"text": "201-1车间"}],
        },
        {
            "负责人": [{"id": "ou1", "name": "李玮"}],
            "车间/位置": [{"text": "201-1"}],
        },
    ]
    client = _FakeClient(fields=_ledger_fields())
    db = _FakeSession(
        None,
        results=[
            _FakeResult(config),
            _FakeResult(None, list_value=owner_fields),
            _FakeResult(config),
            _FakeResult(None, list_value=owner_fields),
        ],
    )
    _install(monkeypatch, client, mirror_session=db)

    owners = await page_table.list_page_table_field_values(db, PAGE_KEY, "负责人")
    assert [(item.value, item.count) for item in owners.values] == [
        ("李玮", 2),
        ("王思博", 1),
    ]

    departments = await page_table.list_page_table_field_values(
        db, PAGE_KEY, "车间/位置"
    )
    assert [(item.value, item.count) for item in departments.values] == [
        ("201一车间", 2)
    ]


async def test_field_values_rejects_unknown_field(monkeypatch) -> None:
    config = _config(is_mirrored=True, last_synced_at=datetime.now(UTC))
    client = _FakeClient()
    db = _FakeSession(None, results=[_FakeResult(config)])
    _install(monkeypatch, client, mirror_session=db)

    with pytest.raises(AppException) as excinfo:
        await page_table.list_page_table_field_values(db, PAGE_KEY, "不存在的字段")
    assert excinfo.value.status_code == 400


# ── 到期统计与 neq 条件 ──


async def test_stats_returns_due_summary(monkeypatch) -> None:
    fields = _FIELDS + [
        {"field_id": "fld-due", "field_name": "目标完成日期", "type": 5},
        {
            "field_id": "fld-close",
            "field_name": "关闭状态",
            "type": 3,
            "property": {"options": [{"name": "已关闭"}, {"name": "未关闭"}]},
        },
    ]
    """due_summary：未关闭记录按目标完成日期归桶（逾期/7/15/30 天）。"""
    from datetime import date, timedelta

    from app.modules.safety.service.hazard_due_reminder import (
        CLOSE_FIELD,
        DUE_FIELD,
    )

    config = _config(is_mirrored=True, last_synced_at=datetime.now(UTC))
    today = date.today()
    client = _FakeClient(fields=fields)
    db = _FakeSession(
        None,
        results=[
            _FakeResult(config),
            # 镜像取数现在是 (record_id, fields) 元组行
            _FakeResult(
                None,
                list_value=[
                    (
                        "rec-1",
                        {
                            "值班日期": "2026-01-01",
                            "整改情况": "未整改",
                            "目标完成日期": (today - timedelta(days=2)).isoformat(),
                            "关闭状态": "未关闭",
                        },
                    ),
                    (
                        "rec-2",
                        {
                            "值班日期": "2026-01-02",
                            "整改情况": "未整改",
                            "目标完成日期": (today + timedelta(days=5)).isoformat(),
                            "关闭状态": "",
                        },
                    ),
                    (
                        "rec-3",
                        {
                            "值班日期": "2026-01-03",
                            "整改情况": "未整改",
                            "目标完成日期": (today - timedelta(days=9)).isoformat(),
                            "关闭状态": "已关闭",
                        },
                    ),
                ],
            ),
        ],
    )
    _install(monkeypatch, client, mirror_session=db)

    result = await page_table.get_page_table_stats(
        db,
        PAGE_KEY,
        group_by=["整改情况"],
        due_field=DUE_FIELD,
        close_field=CLOSE_FIELD,
    )

    assert result.due_summary is not None
    assert result.due_summary.overdue == 1  # 已关闭的逾期不计
    assert result.due_summary.within_7 == 1  # 5 天内到期（逾期单独计）
    assert result.due_summary.within_30 == 1


async def test_stats_without_due_fields_has_no_summary(monkeypatch) -> None:
    config = _config(is_mirrored=True, last_synced_at=datetime.now(UTC))
    client = _FakeClient()
    db = _FakeSession(
        None,
        results=[
            _FakeResult(config),
            _FakeResult(None, list_value=[]),
        ],
    )
    _install(monkeypatch, client, mirror_session=db)

    result = await page_table.get_page_table_stats(db, PAGE_KEY, group_by=["整改情况"])
    assert result.due_summary is None


async def test_neq_condition_matches_unfilled_and_excludes_value(monkeypatch) -> None:
    fields = _FIELDS + [
        {
            "field_id": "fld-close",
            "field_name": "关闭状态",
            "type": 3,
            "property": {"options": [{"name": "已关闭"}, {"name": "未关闭"}]},
        },
    ]
    """到期下钻条件：关闭状态 ≠ 已关闭（未填写也算未关闭）。"""
    config = _config(is_mirrored=True, last_synced_at=datetime.now(UTC))
    # rec-1 已关闭应被排除；rec-3 未填写关闭状态按未关闭命中
    row2 = SimpleNamespace(
        record_id="rec-2", fields={"整改情况": "未整改", "关闭状态": "未关闭"}
    )
    row3 = SimpleNamespace(record_id="rec-3", fields={"整改情况": "未整改"})
    client = _FakeClient(fields=fields)
    db = _FakeSession(
        None,
        results=[
            _FakeResult(config),
            # neq 走 SQL；非文本条件下推后仍走 SQL 分页（此处给 count + 行）
            _FakeResult(2),
            _FakeResult(None, list_value=[row2, row3]),
        ],
    )
    _install(monkeypatch, client, mirror_session=db)

    result = await page_table.list_page_table_records(
        db,
        PAGE_KEY,
        conditions=[
            PageTableRecordCondition(field="关闭状态", value="已关闭", op="neq")
        ],
    )

    assert [record.record_id for record in result.records] == ["rec-2", "rec-3"]
