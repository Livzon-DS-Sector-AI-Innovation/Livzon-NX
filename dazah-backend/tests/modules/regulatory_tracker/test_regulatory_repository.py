"""RegulatoryTracker repository 综合分支测试：upsert 全路径、筛选、统计与纯哈希。"""

import uuid
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.regulatory_tracker import repository as repo


def _id() -> uuid.UUID:
    return uuid.uuid4()


# ── 纯哈希 ──────────────────────────────────────────────


def test_build_document_content_hash_stable_and_content_sensitive() -> None:
    data = {
        "title": "指南",
        "publish_date": date(2024, 1, 2),
        "status_text": "现行",
        "source_site_code": "nmpa",
        "summary_text": "摘要",
        "raw_data": {"k": 1},
    }
    h1 = repo.build_document_content_hash(data)
    # 稳定：同输入同输出
    assert h1 == repo.build_document_content_hash(dict(data))
    # 内容敏感：标题变化 → 哈希变化
    data2 = dict(data)
    data2["title"] = "指南2"
    assert h1 != repo.build_document_content_hash(data2)
    # datetime 会带上时间分量（既有序列化行为）
    data3 = dict(data)
    data3["publish_date"] = datetime(2024, 1, 2)
    assert h1 != repo.build_document_content_hash(data3)
    assert repo._serialize_hash_value(date(2024, 1, 1)) == "2024-01-01"
    assert repo._serialize_hash_value(42) == 42


# ── 简单 CRUD 空/缺失分支 ────────────────────────────────


def _scalar_session(value: Any) -> Any:
    return SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: value, scalar=lambda: value)),  # noqa: E501
        add=lambda obj: None,
        add_all=lambda objs: None,
        flush=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_update_document_missing_and_update_sync_job_page_missing() -> None:
    session = _scalar_session(None)
    assert await repo.update_document(session, _id(), {"title": "x"}) is None
    assert await repo.update_sync_job(session, _id(), {"status": "x"}) is None
    assert await repo.update_sync_job_page(session, _id(), {"status": "x"}) is None
    assert await repo.list_documents_by_ids(session, []) == []
    assert await repo.notification_record_exists(
        session, document_id=_id(), recipient_open_id="ou", content_hash=None
    ) is False
    assert await repo.get_document_by_source_channel_document_id(
        session, source_id=None, channel_id=None, document_id=None
    ) is None


@pytest.mark.asyncio
async def test_create_and_notification_records_noop() -> None:
    added: list[Any] = []
    session = SimpleNamespace(
        add=lambda obj: added.append(obj),
        add_all=lambda objs: added.extend(objs),
        flush=AsyncMock(),
    )
    source = await repo.create_data_source(session, {"code": "nmpa"})
    channel = await repo.create_data_channel(session, {"code": "gzh"})
    doc = await repo.create_document(session, {"title": "t"})
    job = await repo.create_sync_job(session, {"status": "running"})
    page = await repo.create_sync_job_page(session, {})
    await repo.create_notification_records(session, [])
    assert source.code == "nmpa" and channel.code == "gzh"
    assert doc.title == "t" and job.status == "running"
    assert page is not None
    assert len(added) == 5
    await repo.create_notification_records(session, [MagicMock()])
    assert len(added) == 6


# ── upsert ──────────────────────────────────────────────


class _UpsertSession:
    def __init__(self, existing: Any | None) -> None:
        self._existing = existing
        self.created: list[Any] = []
        self.updated: list[Any] = []

    async def execute(self, stmt: Any) -> Any:
        if "source_url == :source_url_1" in str(stmt):
            # get_document_by_unique_fields 也走带 source_url 的查询
            return SimpleNamespace(scalar_one_or_none=lambda: self._existing)
        return SimpleNamespace(scalar_one_or_none=lambda: self._existing)

    def add(self, obj: Any) -> None:
        self.created.append(obj)

    async def flush(self) -> None:
        pass


def _existing_doc(**kw: Any) -> Any:
    base: dict[str, Any] = {
        "id": _id(),
        "title": "旧标题",
        "publish_date": date(2024, 1, 1),
        "status_text": "旧状态",
        "source_site_code": "nmpa",
        "content_hash": "old-hash",
        "is_new": True,
        "is_deleted": False,
        "last_checked_at": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _doc_data(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source_site_code": "nmpa",
        "title": "新标题",
        "publish_date": date(2024, 1, 1),
        "source_url": "https://x/1",
        "status_text": "现行",
        "is_new": True,
    }
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_upsert_insert_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _UpsertSession(None)
    monkeypatch.setattr(
        repo,
        "get_document_by_source_channel_document_id",
        AsyncMock(return_value=None),
    )
    result = await repo.upsert_document_by_unique_fields(session, _doc_data())
    assert result.action == "inserted"
    assert len(session.created) == 1
    assert session.created[0].content_hash  # 自动生成哈希


@pytest.mark.asyncio
async def test_upsert_update_with_changed_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _existing_doc()
    session = _UpsertSession(existing)

    async def _update(db: Any, doc_id: Any, data: dict[str, Any]) -> Any:
        for key, value in data.items():
            setattr(existing, key, value)
        session.updated.append(data)
        return existing

    monkeypatch.setattr(repo, "update_document", _update)
    result = await repo.upsert_document_by_unique_fields(
        session,
        _doc_data(
            title="同标题", status_text="现行", content_hash="new-hash"
        ),
    )
    assert result.action == "updated"
    assert existing.status_text == "现行"
    assert existing.is_new is False  # is_new 被清除
    assert existing.ai_summary is None  # 内容变更清空 AI 字段


@pytest.mark.asyncio
async def test_upsert_unchanged_and_deleted_revival(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _existing_doc(
        title="同标题", status_text=None, is_new=False, is_deleted=True,
        content_hash="old-hash",
    )
    session = _UpsertSession(existing)

    async def _revive(db: Any, doc_id: Any, data: dict[str, Any]) -> Any:
        for key, value in data.items():
            setattr(existing, key, value)
        return existing

    monkeypatch.setattr(repo, "update_document", _revive)
    result = await repo.upsert_document_by_unique_fields(
        session,
        _doc_data(title="同标题", status_text=None, content_hash="old-hash"),
    )
    # data 与 existing 无差异 → unchanged；软删行被复活（is_deleted → False）
    assert result.action == "unchanged"
    assert existing.is_deleted is False


# ── 筛选 / 统计 ─────────────────────────────────────────


class _FilterSession:
    def __init__(self, count: int, items: list[Any]) -> None:
        self._count = count
        self._items = items
        self.queries: list[str] = []

    async def execute(self, stmt: Any) -> Any:
        self.queries.append(str(stmt))
        if "count(" in str(stmt):
            return SimpleNamespace(scalar=lambda: self._count)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._items))


@pytest.mark.asyncio
async def test_get_documents_with_filters_all_branches() -> None:
    item = _existing_doc()
    session = _FilterSession(7, [item])
    docs, total = await repo.get_documents_with_filters(
        session,  # type: ignore[arg-type]
        keyword="指南",
        source_site="NMPA",
        publish_date_from=date(2024, 1, 1),
        publish_date_to=date(2024, 1, 31),
        capture_date_from=date(2024, 2, 1),
        capture_date_to=date(2024, 2, 28),
        status_text="现行",
        classification="指南",
        is_new=True,
        page=2,
        page_size=10,
    )
    assert total == 7 and len(docs) == 1
    assert len(session.queries) == 2


@pytest.mark.asyncio
async def test_get_summary_stats_shape() -> None:
    last_sync = SimpleNamespace(
        finished_at=datetime(2024, 1, 1, 12, 0, 0), status="completed"
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar=lambda: 10),
                SimpleNamespace(scalar=lambda: 2),
                SimpleNamespace(scalar=lambda: 3),
                SimpleNamespace(scalar_one_or_none=lambda: last_sync),
            ]
        )
    )
    stats = await repo.get_summary_stats(session)  # type: ignore[arg-type]
    assert stats["totalCount"] == 10
    assert stats["todayNewCount"] == 2
    assert stats["unreadNewCount"] == 3
    assert stats["lastSyncTime"] == "2024-01-01T12:00:00"
    assert stats["lastSyncStatus"] == "completed"


# ── 通知设置与推送记录 ───────────────────────────────────


@pytest.mark.asyncio
async def test_save_notification_setting_create_and_update() -> None:
    added: list[Any] = []
    session = SimpleNamespace(add=lambda s: added.append(s), flush=AsyncMock())
    # setting 不存在 → 新建
    created = await repo.save_notification_setting(
        session,  # type: ignore[arg-type]
        setting=None,
        is_enabled=True,
        recent_days=7,
        recipient_open_id="ou-1",
        recipient_name="张三",
        recipient_department="QA部",
    )
    assert created.is_enabled is True and len(added) == 1
    # 已有 setting → 原地更新
    existing = SimpleNamespace(is_enabled=False, recent_days=1)
    updated = await repo.save_notification_setting(
        session,  # type: ignore[arg-type]
        setting=existing,
        is_enabled=False,
        recent_days=3,
        recipient_open_id=None,
        recipient_name=None,
        recipient_department=None,
    )
    assert existing is updated and updated.recent_days == 3
    assert updated.recipient_open_id is None


@pytest.mark.asyncio
async def test_get_sync_jobs_list_pagination() -> None:
    job = SimpleNamespace(id=_id(), status="completed")
    session = _FilterSession(5, [job])
    jobs, total = await repo.get_sync_jobs_list(session, page=1, page_size=20)  # type: ignore[arg-type]  # noqa: E501
    assert total == 5 and jobs[0].status == "completed"
