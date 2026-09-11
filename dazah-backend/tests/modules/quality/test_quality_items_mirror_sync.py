"""质量检验-物品管理本地镜像：写库三态、读取回填、同步编排（mock 飞书）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.inspection_items_mirror import (
    QualityItemsPageRow,
)
from app.modules.quality.repository import inspection_items_mirror as repo
from app.modules.quality.service import inspection_items_mirror as mirror
from app.modules.quality.service.inspection_items_mirror import (
    PAGE_INBOUND,
    PAGE_INVENTORY,
)

pytestmark = pytest.mark.anyio

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


def _row(record_id: str, order: int, cells: dict[str, Any]) -> QualityItemsPageRow:
    return QualityItemsPageRow(
        page_snapshot_id=None,
        source_record_id=record_id,
        row_order=order,
        cells=cells,
        search_text=" ".join(str(v) for v in cells.values()),
        last_synced_at=datetime.now(UTC),
    )


async def test_upsert_full_softdeletes_missing(db_session: AsyncSession) -> None:
    snapshot = await repo.upsert_snapshot(
        db_session,
        page_key=PAGE_INVENTORY,
        page_title="关键物资库存",
        table_name="关键物资库存",
        table_id="tbl1",
        columns=[{"key": "物资名称"}],
        total_rows=2,
    )
    rows = [_row("r1", 1, {"物资名称": "A"}), _row("r2", 2, {"物资名称": "B"})]
    for row in rows:
        row.page_snapshot_id = snapshot.id
    await repo.upsert_rows_full(db_session, snapshot.id, rows)
    await db_session.commit()

    # r2 消失 → 全量应软删；r3 新增
    rows2 = [_row("r1", 1, {"物资名称": "A"}), _row("r3", 2, {"物资名称": "C"})]
    for row in rows2:
        row.page_snapshot_id = snapshot.id
    await repo.upsert_rows_full(db_session, snapshot.id, rows2)
    await db_session.commit()

    items, total = await repo.list_rows(db_session, snapshot.id, limit=None)
    assert total == 2
    assert {r.source_record_id for r in items} == {"r1", "r3"}


async def test_upsert_incremental_keeps_history(db_session: AsyncSession) -> None:
    snapshot = await repo.upsert_snapshot(
        db_session,
        page_key=PAGE_INVENTORY,
        page_title="t",
        table_name="t",
        table_id="tbl1",
        columns=[{"key": "物资名称"}],
        total_rows=2,
    )
    rows = [_row("r1", 1, {"物资名称": "A"}), _row("r2", 2, {"物资名称": "B"})]
    for row in rows:
        row.page_snapshot_id = snapshot.id
    await repo.upsert_rows_full(db_session, snapshot.id, rows)
    await db_session.commit()

    # 增量只传 r1 变更 → r2 保留，不软删
    inc = [_row("r1", 1, {"物资名称": "A2"})]
    for row in inc:
        row.page_snapshot_id = snapshot.id
    await repo.upsert_rows_incremental(db_session, snapshot.id, inc)
    await db_session.commit()

    items, total = await repo.list_rows(db_session, snapshot.id, limit=None)
    assert total == 2
    updated = next(r for r in items if r.source_record_id == "r1")
    assert updated.cells["物资名称"] == "A2"


async def test_sync_full_writes_mirror_and_read_backfills(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    inv_records = [
        {
            "record_id": "inv1",
            "fields": {
                "物资名称": "青霉素",
                "规格型号": "50g",
                "当前库存": 2,
                "警戒库存": 5,
                "库存报警": "库存不足",
            },
            "last_modified_time": 1_700_000_000_000,
        }
    ]
    in_records = [
        {
            "record_id": "in1",
            "fields": {"入库数量": 3, "物资名": {"link_record_ids": ["inv1"]}},
            "last_modified_time": 1_700_000_000_000,
        }
    ]

    class _Runtime:
        app_id = "a"
        app_secret = "s"

    class _Entity:
        app_token = "tok"
        table_id = "tblX"
        enable_push_to_feishu = True
        enable_pull_from_feishu = True

    async def fake_resolve(_db, page_key, *, direction):
        return _Runtime(), _Entity()

    calls: dict[str, list] = {}

    class _ClientObj:
        async def request(self, method, path, params=None, timeout=None):
            table_id = path.split("/tables/")[1].split("/")[0]
            if table_id == "tblInventory":
                return {"items": inv_records, "has_more": False, "total": 1}
            return {"items": in_records, "has_more": False, "total": 1}

    class _Client:
        def __init__(self, *, app_token, app_id, app_secret):
            self.app_token = app_token
            self.client = _ClientObj()

        async def list_fields(self, table_id):
            if table_id == "tblInventory":
                return [
                    {"field_name": "物资名称", "ui_type": "Text", "type": 1},
                    {"field_name": "规格型号", "ui_type": "Text", "type": 1},
                    {"field_name": "当前库存", "ui_type": "Number", "type": 2},
                    {"field_name": "警戒库存", "ui_type": "Number", "type": 2},
                    {"field_name": "库存报警", "ui_type": "Text", "type": 1},
                ]
            return [{"field_name": "入库数量", "ui_type": "Number", "type": 2}]

    entity_ids = {PAGE_INVENTORY: "tblInventory", PAGE_INBOUND: "tblInbound"}

    async def fake_resolve2(_db, page_key, *, direction):
        e = _Entity()
        e.table_id = entity_ids[page_key]
        calls.setdefault(page_key, [])
        return _Runtime(), e

    monkeypatch.setattr(mirror, "_resolve_runtime_entity", fake_resolve2)
    monkeypatch.setattr(mirror, "BitableClient", _Client)
    monkeypatch.setattr(
        "app.modules.quality.service.quality_feishu_sync._require_table_id",
        lambda entity: entity.table_id,
    )

    await mirror.sync_items_page(db_session, PAGE_INVENTORY, incremental=False)
    await mirror.sync_items_page(db_session, PAGE_INBOUND, incremental=False)

    result = await mirror.list_items_mirror(db_session, PAGE_INBOUND)
    assert result["configured"] is True
    assert result["total"] == 1
    row = result["items"][0]
    # 物资名 link 回填来自库存镜像
    assert row.get("物资名称") == "青霉素"
    assert row.get("当前库存") == "2"


def test_pure_normalize_and_low_stock() -> None:
    columns = mirror._build_columns(
        [
            {"field_name": "物资名称", "ui_type": "Text", "type": 1},
            {"field_name": "警戒库存", "ui_type": "Number", "type": 2},
        ]
    )
    assert [c["key"] for c in columns] == ["物资名称", "警戒库存"]
    cells = mirror._normalize_record_cells(
        {
            "record_id": "r",
            "fields": {
                "物资名称": "X",
                "警戒库存": 5,
                "物资名": {"link_record_ids": ["i"]},
            },
            "last_modified_time": 1_700_000_000_000,
        },
        columns,
    )
    assert cells["物资名称"] == "X"
    assert cells["__link_record_ids"] == ["i"]
    assert "__last_modified" in cells


def test_select_option_resolution_formula_and_plain() -> None:
    # 普通单选：property.options
    plain = mirror._build_columns(
        [
            {
                "field_name": "存放位置",
                "ui_type": "SingleSelect",
                "property": {
                    "options": [
                        {"id": "optA", "name": "资料室"},
                        {"id": "optB", "name": "物资储存室"},
                    ]
                },
            },
            # 公式返回选项：property.type.ui_property.options（值回读为选项 id）
            {
                "field_name": "库存报警",
                "ui_type": "Formula",
                "property": {
                    "type": {
                        "ui_type": "SingleSelect",
                        "ui_property": {
                            "options": [
                                {"id": "opty0QKXm4", "name": "库存不足"},
                                {"id": "opt2KK1VTA", "name": "正常"},
                            ]
                        },
                    }
                },
            },
        ]
    )
    assert plain[0]["options"][0] == {"id": "optA", "name": "资料室"}
    assert plain[1]["options"][1]["name"] == "正常"

    cells = mirror._normalize_record_cells(
        {
            "record_id": "r",
            "fields": {"存放位置": "optA", "库存报警": "opty0QKXm4"},
        },
        plain,
    )
    assert cells["存放位置"] == "资料室"
    assert cells["库存报警"] == "库存不足"


async def test_maybe_refresh_items_mirror_gate(
    monkeypatch: pytest.MonkeyPatch,
    mirror_session_factory,
) -> None:
    from app.core.exceptions import AppException
    from app.modules.quality.api import inspection_feishu_crud as crud_api

    # 独立会话指向测试库，避免打开主库连接
    monkeypatch.setattr(
        crud_api, "async_session_factory", lambda: mirror_session_factory()
    )
    calls: list[str] = []

    async def fake_sync(db, page_key, *, incremental=True):
        calls.append(page_key)
        return {"synced": 1, "removed": 0, "total": 1}

    monkeypatch.setattr(crud_api, "sync_items_page", fake_sync)

    # 非镜像实体：不触发
    await crud_api._maybe_refresh_entity_mirror("qc_instr_equipment")
    assert calls == []

    # 物品实体：触发一次
    await crud_api._maybe_refresh_entity_mirror(PAGE_INVENTORY)
    assert calls == [PAGE_INVENTORY]

    # 同步失败被吞（不影响已成功的飞书写）
    async def boom(db, page_key, *, incremental=True):
        raise AppException(message="飞书未配置", status_code=503)

    monkeypatch.setattr(crud_api, "sync_items_page", boom)
    await crud_api._maybe_refresh_entity_mirror(PAGE_INVENTORY)


class _FakeClientObj:
    def __init__(self, pages: dict[str, list]):
        self.pages = pages
        self.calls: list[str] = []

    async def request(self, method, path, params=None, json=None, timeout=None):
        sort_name = (json or {}).get("sort", [{}])[0].get("field_name", "")
        self.calls.append(sort_name)
        if sort_name not in self.pages:
            raise RuntimeError("unsupported sort")
        return {"items": self.pages[sort_name], "has_more": False}


class _FakeClient:
    app_token = "tok"

    def __init__(self, pages):
        self.client = _FakeClientObj(pages)


def _dt(y, mo, d):
    return datetime(y, mo, d, tzinfo=UTC)


async def test_incremental_dual_route_merges_by_watermark() -> None:
    # 上次同步 2026-04-03 12:00；业务日期水线取当天零点
    last_synced = _dt(2026, 4, 3).replace(hour=12)
    day0_ms = _dt(2026, 4, 3).timestamp() * 1000
    ms = last_synced.timestamp() * 1000
    new_date_rec = {
        "record_id": "a",
        "fields": {"入库日期": day0_ms + 1000},  # 当天 → 新
        "last_modified_time": ms - 5000,  # 早于同步时刻
    }
    recent_mod_rec = {
        "record_id": "b",
        "fields": {"入库日期": day0_ms - 86_400_000},  # 昨天 → 日期路判旧
        "last_modified_time": ms + 1,  # 但最近被改 → last_modified 路判新
    }
    old_rec = {
        "record_id": "c",
        "fields": {"入库日期": day0_ms - 10 * 86_400_000},
        "last_modified_time": ms - 99999,
    }
    pages = {
        "入库日期": [new_date_rec, old_rec],
        "last_modified_time": [recent_mod_rec, old_rec],
    }
    client = _FakeClient(pages)
    out = await mirror._fetch_incremental_records(
        client, "tblX", sort_field="入库日期", last_synced_at=last_synced
    )
    got = {r["record_id"] for r in out}
    assert got == {"a", "b"}  # c 两路都判旧，被过滤
    assert set(client.client.calls) == {"入库日期", "last_modified_time"}


async def test_incremental_date_route_error_propagates_for_fallback() -> None:
    # 日期路不被支持（pages 无该键→request 抛错）→ 应向上抛，供 sync 回退全量
    last_synced = _dt(2026, 4, 3)
    client = _FakeClient({"last_modified_time": []})
    with pytest.raises(RuntimeError):
        await mirror._fetch_incremental_records(
            client, "tblX", sort_field="入库日期", last_synced_at=last_synced
        )
