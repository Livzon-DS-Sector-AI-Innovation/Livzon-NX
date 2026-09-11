"""固体/液体物料镜像：全量落库、增量水位、镜像读取、实时降级（mock 飞书）。"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.repository import inspection_items_mirror as repo
from app.modules.quality.service import inspection_finished_material as mat_svc
from app.modules.quality.service import inspection_material_mirror as mirror

pytestmark = pytest.mark.anyio

ENTITY = "qc_solid_ys002"

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


def _records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return records


class _Runtime:
    app_id = "a"
    app_secret = "s"


class _Entity:
    app_token = "tok"
    table_id = "tblMaterial"
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
        {"field_name": "生产厂家", "ui_type": "Text", "type": 1},
        {"field_name": "结果判断", "ui_type": "SingleSelect", "type": 3,
         "property": {"options": [
             {"id": "optP", "name": "合格"},
             {"id": "optF", "name": "不合格"},
         ]}},
        {"field_name": "不合格项目", "ui_type": "Text", "type": 1},
    ]


async def test_sync_full_writes_mirror_and_reads_local(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = _records(
        [
            {
                "record_id": "rec1",
                "fields": {
                    "批号": "YS002-2506001",
                    "生产厂家": "济宁双华",
                    "结果判断": "optP",
                    "不合格项目": "",
                },
                "last_modified_time": 1_700_000_000_000,
            },
            {
                "record_id": "rec2",
                "fields": {
                    "批号": "YS002-2507003",
                    "生产厂家": "内蒙金弘源",
                    "结果判断": "optF",
                    "不合格项目": "干燥失重超标",
                },
                "last_modified_time": 1_700_000_000_100,
            },
        ]
    )
    _install_feishu_mocks(monkeypatch, records, _fields())

    result = await mirror.sync_material_page(db_session, ENTITY, incremental=False)
    assert result["synced"] == 2

    read = await mirror.list_material_mirror(db_session, ENTITY, page=1, page_size=20)
    assert read["configured"] is True
    assert read["total"] == 2
    assert read["fields"] == ["批号", "生产厂家", "结果判断", "不合格项目"]
    first = read["items"][0]
    # 按 updated_at 倒序：rec2 更新更晚在前
    assert first["record_id"] == "rec2"
    # 单选选项 id 已映射回文字
    assert first["结果判断"] == "不合格"
    assert first["不合格项目"] == "干燥失重超标"


async def test_sync_incremental_only_writes_newer_rows(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = _records(
        [
            {
                "record_id": "rec1",
                "fields": {"批号": "YS002-2506001"},
                "last_modified_time": 1_700_000_000_000,
            },
            {
                "record_id": "rec2",
                "fields": {"批号": "YS002-2507003"},
                "last_modified_time": 1_700_000_000_100,
            },
        ]
    )
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_material_page(db_session, ENTITY, incremental=False)

    # 增量轮：只返回修改时间更新的一条（大于快照水线）
    newer = _records(
        [
            {
                "record_id": "rec1",
                "fields": {"批号": "YS002-2506001", "生产厂家": "已更新"},
                "last_modified_time": 1_800_000_000_000,
            }
        ]
    )
    _install_feishu_mocks(monkeypatch, newer, _fields())
    await mirror.sync_material_page(db_session, ENTITY, incremental=True)

    read = await mirror.list_material_mirror(db_session, ENTITY)
    assert read["total"] == 2  # 历史保留
    updated = next(
        it for it in read["items"] if it["record_id"] == "rec1"
    )
    assert updated["生产厂家"] == "已更新"


async def test_sync_incremental_batch_driven_only_new_batches(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 全量同步两条（批号 A/B）
    records = _records(
        [
            {
                "record_id": "recA",
                "fields": {"批号": "YS002-2506001", "生产厂家": "厂商A"},
                "last_modified_time": 1_700_000_000_000,
            },
            {
                "record_id": "recB",
                "fields": {"批号": "YS002-2507003", "生产厂家": "厂商B"},
                "last_modified_time": 1_700_000_000_100,
            },
        ]
    )
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_material_page(db_session, ENTITY, incremental=False)

    # 增量：一条新批号 C + 一条已同步批号 A（内容未变、修改时间旧）→ 只写 C
    inc_records = _records(
        [
            {
                "record_id": "recC",
                "fields": {"批号": "YS002-2608001", "生产厂家": "厂商C"},
                "last_modified_time": 1_800_000_000_000,
            },
            {
                "record_id": "recA",
                "fields": {"批号": "YS002-2506001", "生产厂家": "厂商A"},
                "last_modified_time": 1_700_000_000_000,
            },
        ]
    )
    _install_feishu_mocks(monkeypatch, inc_records, _fields())
    await mirror.sync_material_page(db_session, ENTITY, incremental=True)

    read = await mirror.list_material_mirror(db_session, ENTITY)
    assert read["total"] == 3
    batches = {it["批号"] for it in read["items"]}
    assert batches == {"YS002-2506001", "YS002-2507003", "YS002-2608001"}


async def test_sync_incremental_updates_modified_known_batch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = _records(
        [
            {
                "record_id": "recA",
                "fields": {"批号": "YS002-2506001", "生产厂家": "厂商A"},
                "last_modified_time": 1_700_000_000_000,
            }
        ]
    )
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_material_page(db_session, ENTITY, incremental=False)

    # 已同步批号但近期被修改 → 增量应更新内容
    updated = _records(
        [
            {
                "record_id": "recA",
                "fields": {"批号": "YS002-2506001", "生产厂家": "厂商A-已更新"},
                "last_modified_time": 1_800_000_000_000,
            }
        ]
    )
    _install_feishu_mocks(monkeypatch, updated, _fields())
    await mirror.sync_material_page(db_session, ENTITY, incremental=True)

    read = await mirror.list_material_mirror(db_session, ENTITY)
    assert read["total"] == 1
    assert read["items"][0]["生产厂家"] == "厂商A-已更新"


async def test_fetch_incremental_paginates_and_early_stops(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 全量同步两条（批号 A/B）
    records = _records(
        [
            {
                "record_id": "recA",
                "fields": {"批号": "YS002-2506001", "生产厂家": "厂商A"},
                "last_modified_time": 1_700_000_000_000,
            },
            {
                "record_id": "recB",
                "fields": {"批号": "YS002-2507003", "生产厂家": "厂商B"},
                "last_modified_time": 1_700_000_000_100,
            },
        ]
    )
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_material_page(db_session, ENTITY, incremental=False)

    # 增量：第1页有新批号 C（has_more，翻页）；第2页全是已同步批号 → 提前停止
    page1 = _records(
        [
            {
                "record_id": "recC",
                "fields": {"批号": "YS002-2608001", "生产厂家": "厂商C"},
                "last_modified_time": 1_800_000_000_000,
            },
            {
                "record_id": "recA",
                "fields": {"批号": "YS002-2506001", "生产厂家": "厂商A"},
                "last_modified_time": 1_700_000_000_000,
            },
        ]
    )
    page2 = _records(
        [
            {
                "record_id": "recB",
                "fields": {"批号": "YS002-2507003", "生产厂家": "厂商B"},
                "last_modified_time": 1_700_000_000_100,
            }
        ]
    )

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

    await mirror.sync_material_page(db_session, ENTITY, incremental=True)

    read = await mirror.list_material_mirror(db_session, ENTITY)
    assert read["total"] == 3
    batches = {it["批号"] for it in read["items"]}
    assert batches == {"YS002-2506001", "YS002-2507003", "YS002-2608001"}


async def test_sync_incremental_records_hits_mirror(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 未同步：sync_material_page 写入独立会话并 commit，list 读镜像能取到
    records = _records(
        [
            {
                "record_id": "rec1",
                "fields": {"批号": "YS002-2506001", "结果判断": "optP"},
                "last_modified_time": 1_700_000_000_000,
            }
        ]
    )
    _install_feishu_mocks(monkeypatch, records, _fields())

    res = await mirror.sync_material_page(db_session, ENTITY, incremental=True)
    assert res["synced"] == 1
    read = await mirror.list_material_mirror(db_session, ENTITY)
    assert read["total"] == 1
    assert read["items"][0]["record_id"] == "rec1"
    assert "结果判断" in read["fields"]


async def test_sync_unknown_entity_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(AppException):
        await mirror.sync_material_page(db_session, "qc_solid_not_exist")


async def test_list_filters_placeholder_rows(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = _records(
        [
            {
                "record_id": "rec1",
                "fields": {"批号": "YS002-2506001"},
                "last_modified_time": 1_700_000_000_000,
            },
            {
                "record_id": "rec2",
                "fields": {},  # 全空占位行
                "last_modified_time": 1_700_000_000_100,
            },
        ]
    )
    _install_feishu_mocks(monkeypatch, records, _fields())
    await mirror.sync_material_page(db_session, ENTITY, incremental=False)

    read = await mirror.list_material_mirror(db_session, ENTITY)
    assert read["total"] == 1
    assert read["items"][0]["record_id"] == "rec1"


async def test_get_material_mirror_fields_empty_before_sync(
    db_session: AsyncSession,
) -> None:
    fields = await mirror.get_material_mirror_fields(db_session, ENTITY)
    assert fields == []
    snapshot = await repo.get_snapshot(db_session, ENTITY)
    assert snapshot is None
