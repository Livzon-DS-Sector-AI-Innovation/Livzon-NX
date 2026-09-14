"""成品检验镜像：全量落库、批号增量、镜像读取、实时降级（mock 飞书）。"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.service import inspection_finished_material as fin_svc
from app.modules.quality.service import inspection_finished_mirror as mirror

pytestmark = pytest.mark.anyio

ENTITY = "qc_finished_pf"

_SNAPSHOT_DDL = """
    CREATE TABLE IF NOT EXISTS quality.quality_items_page_snapshots (
        page_key VARCHAR(64) NOT NULL,
        page_title VARCHAR(255) NOT NULL,
        table_name VARCHAR(255) NOT NULL,
        table_id VARCHAR(64) NOT NULL,
        source VARCHAR(64) NOT NULL DEFAULT 'feishu_bitable',
        columns JSONB NOT NULL DEFAULT '[]',
        total_rows INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NULL,
        last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        id UUID PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by UUID NULL,
        updated_by UUID NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT FALSE
    )
"""

_ROWS_DDL = """
    CREATE TABLE IF NOT EXISTS quality.quality_items_page_rows (
        page_snapshot_id UUID NOT NULL,
        source_record_id VARCHAR(64) NOT NULL,
        row_order INTEGER NOT NULL DEFAULT 0,
        cells JSONB NOT NULL DEFAULT '{}',
        search_text TEXT NOT NULL DEFAULT '',
        last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        id UUID PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by UUID NULL,
        updated_by UUID NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT FALSE
    )
"""


@pytest.fixture(autouse=True)
async def _prepare_tables(db_session: AsyncSession) -> Any:
    from sqlalchemy import text

    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(text(_SNAPSHOT_DDL))
    await db_session.execute(text(_ROWS_DDL))
    await db_session.execute(text("DELETE FROM quality.quality_items_page_rows"))
    await db_session.execute(
        text("DELETE FROM quality.quality_items_page_snapshots")
    )
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM quality.quality_items_page_rows"))
    await db_session.execute(
        text("DELETE FROM quality.quality_items_page_snapshots")
    )
    await db_session.commit()


class _Runtime:
    app_id = "a"
    app_secret = "s"


class _Entity:
    app_token = "tok"
    table_id = "tblFinished"
    enable_push_to_feishu = True
    enable_pull_from_feishu = True


def _install_feishu_mocks(
    monkeypatch: pytest.MonkeyPatch,
    records: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    class _ClientObj:
        async def request(self, method, path, params=None, json=None, timeout=None):
            return {"items": records, "has_more": False, "total": len(records)}

    class _Client:
        def __init__(self, *, app_token, app_id, app_secret):
            self.app_token = app_token
            self.client = _ClientObj()

        async def list_fields(self, table_id):
            return fields

    async def fake_resolve(_db, entity_code, *, direction):
        return _Runtime(), _Entity()

    monkeypatch.setattr(mirror, "_resolve_runtime_entity", fake_resolve)
    monkeypatch.setattr(mirror, "BitableClient", _Client)
    monkeypatch.setattr(
        "app.modules.quality.service.quality_feishu_sync._require_table_id",
        lambda entity: entity.table_id,
    )


def _fields() -> list[dict[str, Any]]:
    return [
        {"field_name": "批号", "ui_type": "Text", "type": 1},
        {"field_name": "含量:≥70%", "ui_type": "Text", "type": 1},
        {"field_name": "报告单", "ui_type": "Attachment", "type": 17},
    ]


async def test_sync_full_writes_mirror_and_reads_local(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_id": "rec1",
            "fields": {
                "批号": "PF-2608001",
                "含量:≥70%": "72.5",
                "报告单": [
                    {
                        "name": "报告单.pdf",
                        "file_token": "ft1",
                        "url": "",
                        "type": "pdf",
                    }
                ],
            },
            "last_modified_time": 1_700_000_000_000,
        },
        {
            "record_id": "rec2",
            "fields": {"批号": "PF-2609002", "含量:≥70%": "71.0"},
            "last_modified_time": 1_700_000_000_100,
        },
    ]
    _install_feishu_mocks(monkeypatch, records, _fields())

    result = await mirror.sync_finished_page(db_session, ENTITY, incremental=False)
    assert result["synced"] == 2

    read = await mirror.list_finished_mirror(db_session, ENTITY, page=1, page_size=20)
    assert read["configured"] is True
    assert read["total"] == 2
    assert read["fields"] == ["批号", "含量:≥70%", "报告单"]
    assert read["last_sync_time"] is not None
    first = read["items"][0]
    # 按 updated_at 倒序：rec2 更新更晚在前
    assert first["record_id"] == "rec2"
    # 附件归一化为前端可渲染结构
    att = next(
        it for it in read["items"] if it["record_id"] == "rec1"
    )["报告单"]
    assert isinstance(att, list) and att[0]["file_token"] == "ft1"


async def test_sync_incremental_only_writes_new_batches(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_id": "recA",
            "fields": {"批号": "PF-2607001", "含量:≥70%": "70.5"},
            "last_modified_time": 1_700_000_000_000,
        },
        {
            "record_id": "recB",
            "fields": {"批号": "PF-2608002", "含量:≥70%": "71.5"},
            "last_modified_time": 1_700_000_000_100,
        },
    ]
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_finished_page(db_session, ENTITY, incremental=False)

    # 增量：新批号 C + 已同步批号 A（内容未变）→ 只写 C
    inc_records = [
        {
            "record_id": "recC",
            "fields": {"批号": "PF-2609003", "含量:≥70%": "73.0"},
            "last_modified_time": 1_800_000_000_000,
        },
        {
            "record_id": "recA",
            "fields": {"批号": "PF-2607001", "含量:≥70%": "70.5"},
            "last_modified_time": 1_700_000_000_000,
        },
    ]
    _install_feishu_mocks(monkeypatch, inc_records, _fields())
    await mirror.sync_finished_page(db_session, ENTITY, incremental=True)

    read = await mirror.list_finished_mirror(db_session, ENTITY)
    assert read["total"] == 3
    batches = {it["批号"] for it in read["items"]}
    assert batches == {"PF-2607001", "PF-2608002", "PF-2609003"}


async def test_sync_incremental_updates_modified_known_batch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_id": "recA",
            "fields": {"批号": "PF-2607001", "含量:≥70%": "70.5"},
            "last_modified_time": 1_700_000_000_000,
        }
    ]
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_finished_page(db_session, ENTITY, incremental=False)

    # 已同步批号但内容变化 → 增量应更新
    updated = [
        {
            "record_id": "recA",
            "fields": {"批号": "PF-2607001", "含量:≥70%": "70.6"},
            "last_modified_time": 1_800_000_000_000,
        }
    ]
    _install_feishu_mocks(monkeypatch, updated, _fields())
    await mirror.sync_finished_page(db_session, ENTITY, incremental=True)

    read = await mirror.list_finished_mirror(db_session, ENTITY)
    assert read["total"] == 1
    assert read["items"][0]["含量:≥70%"] == "70.6"


async def test_full_sync_reconciles_remote_deletions(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_id": "recA",
            "fields": {"批号": "PF-2607001"},
            "last_modified_time": 1_700_000_000_000,
        },
        {
            "record_id": "recB",
            "fields": {"批号": "PF-2608002"},
            "last_modified_time": 1_700_000_000_100,
        },
    ]
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_finished_page(db_session, ENTITY, incremental=False)

    # 远端只剩 recB → 全量轮软删 recA
    records_after = [
        {
            "record_id": "recB",
            "fields": {"批号": "PF-2608002"},
            "last_modified_time": 1_700_000_000_100,
        }
    ]
    _install_feishu_mocks(monkeypatch, records_after, _fields())
    await mirror.sync_finished_page(db_session, ENTITY, incremental=False)

    read = await mirror.list_finished_mirror(db_session, ENTITY)
    assert read["total"] == 1
    assert read["items"][0]["record_id"] == "recB"


async def test_fetch_incremental_paginates_and_early_stops(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_id": "recA",
            "fields": {"批号": "PF-2607001"},
            "last_modified_time": 1_700_000_000_000,
        },
        {
            "record_id": "recB",
            "fields": {"批号": "PF-2608002"},
            "last_modified_time": 1_700_000_000_100,
        },
    ]
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_finished_page(db_session, ENTITY, incremental=False)

    # 增量：第1页有新批号 C（has_more，翻页）；第2页全是已同步批号 → 提前停止
    page1 = [
        {
            "record_id": "recC",
            "fields": {"批号": "PF-2609003"},
            "last_modified_time": 1_800_000_000_000,
        },
        {
            "record_id": "recA",
            "fields": {"批号": "PF-2607001"},
            "last_modified_time": 1_700_000_000_000,
        },
    ]
    page2 = [
        {
            "record_id": "recB",
            "fields": {"批号": "PF-2608002"},
            "last_modified_time": 1_700_000_000_100,
        }
    ]

    class _PagedClientObj:
        def __init__(self) -> None:
            self.calls = 0

        async def request(self, method, path, params=None, json=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return {"items": page1, "has_more": True, "page_token": "p2"}
            return {"items": page2, "has_more": False}

    class _PagedClient:
        def __init__(self, *, app_token, app_id, app_secret):
            self.app_token = app_token
            self.client = _PagedClientObj()

        async def list_fields(self, table_id):
            return _fields()

    async def fake_resolve(_db, entity_code, *, direction):
        return _Runtime(), _Entity()

    monkeypatch.setattr(mirror, "_resolve_runtime_entity", fake_resolve)
    monkeypatch.setattr(mirror, "BitableClient", _PagedClient)
    monkeypatch.setattr(
        "app.modules.quality.service.quality_feishu_sync._require_table_id",
        lambda entity: entity.table_id,
    )

    await mirror.sync_finished_page(db_session, ENTITY, incremental=True)

    read = await mirror.list_finished_mirror(db_session, ENTITY)
    assert read["total"] == 3
    batches = {it["批号"] for it in read["items"]}
    assert batches == {"PF-2607001", "PF-2608002", "PF-2609003"}


async def test_list_finished_by_entity_mirror_first_with_live_fallback(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    mirror_session_factory,
) -> None:
    # 列表触发同步走独立会话：指向测试库，避免写进主库导致断言落空
    import app.modules.quality.service.inspection_finished_material as fin_mod

    monkeypatch.setattr(
        fin_mod, "async_session_factory", lambda: mirror_session_factory()
    )
    # 未同步：list 应先触发全量同步再读镜像（不依赖实时飞书列表）
    records = [
        {
            "record_id": "rec1",
            "fields": {"批号": "PF-2607001", "含量:≥70%": "70.5"},
            "last_modified_time": 1_700_000_000_000,
        }
    ]
    _install_feishu_mocks(monkeypatch, records, _fields())

    result = await fin_svc.list_finished_by_entity(
        db_session, ENTITY, page=1, page_size=20
    )
    assert result["total"] == 1
    assert result["items"][0]["record_id"] == "rec1"
    assert result["configured"] is True
    # 镜像已就绪，字段来自镜像快照（全列）
    assert result["fields"] == ["批号", "含量:≥70%", "报告单"]

    # 再次读取直接命中镜像（不会重复触发同步）
    result2 = await fin_svc.list_finished_by_entity(
        db_session, ENTITY, page=1, page_size=20
    )
    assert result2["total"] == 1


async def test_pull_finished_by_entity_full_syncs_mirror(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_id": "rec1",
            "fields": {"批号": "PF-2607001"},
            "last_modified_time": 1_700_000_000_000,
        }
    ]
    _install_feishu_mocks(monkeypatch, records, _fields())

    result = await fin_svc.pull_finished_by_entity(db_session, ENTITY)
    assert result["synced"] == 1

    read = await mirror.list_finished_mirror(db_session, ENTITY)
    assert read["configured"] is True
    assert read["total"] == 1


async def test_sync_unknown_entity_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(AppException):
        await mirror.sync_finished_page(db_session, "qc_finished_not_exist")


async def test_list_filters_placeholder_rows(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_id": "rec1",
            "fields": {"批号": "PF-2607001"},
            "last_modified_time": 1_700_000_000_000,
        },
        {
            "record_id": "rec2",
            "fields": {},  # 全空占位行
            "last_modified_time": 1_700_000_000_100,
        },
    ]
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_finished_page(db_session, ENTITY, incremental=False)

    read = await mirror.list_finished_mirror(db_session, ENTITY)
    assert read["total"] == 1
    assert read["items"][0]["record_id"] == "rec1"
