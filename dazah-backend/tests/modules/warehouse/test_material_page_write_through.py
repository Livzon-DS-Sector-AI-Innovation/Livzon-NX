"""仓储页面编辑/删除后单条写穿本地镜像测试。

Covers:
- repo 写穿 upsert：更新已有行（保留行序、不影响其他行）
- repo 写穿 upsert：本地缺失行新增（返回 True）
- repo 写穿 upsert：复活本地软删行（以飞书 GET 结果为准）
- repo 删除写穿：软删镜像行、重复删/删不存在行返回 False
- service 编辑成功后调用写穿（cells 归一化 + record_meta + total_rows 维护）
- service 删除成功后写穿软删（total_rows 递减）
- 写穿失败不影响保存/删除结果（回滚会话，仅记日志）
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.feishu_material_pages import (
    FeishuWarehouseMaterialPage,
)
from app.modules.warehouse.models import MaterialPageRow
from app.modules.warehouse.service import WarehouseService


def _binding(page_key: str) -> FeishuWarehouseMaterialPage:
    return FeishuWarehouseMaterialPage(
        page_key=page_key, title=page_key, table_id="tblWtp", app_token="app-wtp"
    )


async def _create_snapshot(
    service: WarehouseService, page_key: str, table_id: str
) -> None:
    await service.repo.upsert_material_page_snapshot(
        page_key=page_key,
        page_title=page_key,
        table_name=page_key,
        table_id=table_id,
        columns=[{"key": "物料名称", "title": "物料名称"}],
        total_rows=0,
        source="test",
        last_synced_at=datetime.now(UTC),
    )


def _row_models(
    snapshot_id: object,
    records: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[MaterialPageRow]:
    now = now or datetime.now(UTC)
    return [
        MaterialPageRow(
            page_snapshot_id=snapshot_id,
            source_record_id=str(record["__record_id"]),
            row_order=index,
            cells={k: v for k, v in record.items() if k != "__record_id"},
            search_text=str(record.get("物料名称", "")),
            last_synced_at=now,
        )
        for index, record in enumerate(records, start=1)
    ]


async def _all_page_rows(
    service: WarehouseService, page_key: str
) -> list[MaterialPageRow]:
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None
    result = await service.repo.session.execute(
        select(MaterialPageRow).where(MaterialPageRow.page_snapshot_id == snapshot.id)
    )
    return list(result.scalars().all())


async def test_write_through_upsert_updates_existing_row_preserving_order(
    db_session: AsyncSession,
) -> None:
    """写穿更新已有行：cells 更新、行序保留、其他行不受影响。"""
    service = WarehouseService(db_session)
    page_key = "wtp-test-update"
    await _create_snapshot(service, page_key, "tbl-wtp-1")
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None
    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(
            snapshot.id,
            [
                {"__record_id": "rec-1", "物料名称": "物料A"},
                {"__record_id": "rec-2", "物料名称": "物料B"},
            ],
        ),
    )

    inserted = await service.repo.upsert_material_page_row_write_through(
        snapshot.id,
        _row_models(
            snapshot.id, [{"__record_id": "rec-1", "物料名称": "物料A-写穿"}]
        )[0],
    )

    assert inserted is False
    rows = await _all_page_rows(service, page_key)
    by_id = {row.source_record_id: row for row in rows}
    assert len(rows) == 2
    assert by_id["rec-1"].cells["物料名称"] == "物料A-写穿"
    assert by_id["rec-1"].row_order == 1
    assert by_id["rec-1"].is_deleted is False
    assert by_id["rec-2"].is_deleted is False


async def test_write_through_upsert_inserts_missing_row(
    db_session: AsyncSession,
) -> None:
    """写穿本地缺失的记录：新增行并返回 True（调用方据此 +total_rows）。"""
    service = WarehouseService(db_session)
    page_key = "wtp-test-insert"
    await _create_snapshot(service, page_key, "tbl-wtp-2")
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None

    inserted = await service.repo.upsert_material_page_row_write_through(
        snapshot.id,
        _row_models(snapshot.id, [{"__record_id": "rec-new", "物料名称": "新记录"}])[0],
    )

    assert inserted is True
    rows = await _all_page_rows(service, page_key)
    assert [row.source_record_id for row in rows] == ["rec-new"]


async def test_write_through_upsert_revives_soft_deleted_row(
    db_session: AsyncSession,
) -> None:
    """本地软删行写穿复活：以刚 GET 回的飞书记录为准，记录确认存在。"""
    service = WarehouseService(db_session)
    page_key = "wtp-test-revive"
    await _create_snapshot(service, page_key, "tbl-wtp-3")
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None
    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(
            snapshot.id,
            [
                {"__record_id": "rec-1", "物料名称": "物料A"},
                {"__record_id": "rec-2", "物料名称": "物料B"},
            ],
        ),
    )
    # 全量对账软删 rec-2
    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(snapshot.id, [{"__record_id": "rec-1", "物料名称": "物料A"}]),
    )

    inserted = await service.repo.upsert_material_page_row_write_through(
        snapshot.id,
        _row_models(snapshot.id, [{"__record_id": "rec-2", "物料名称": "物料B-改"}])[0],
    )

    assert inserted is False
    rows = await _all_page_rows(service, page_key)
    by_id = {row.source_record_id: row for row in rows}
    assert by_id["rec-2"].is_deleted is False
    assert by_id["rec-2"].cells["物料名称"] == "物料B-改"


async def test_soft_delete_material_page_row(
    db_session: AsyncSession,
) -> None:
    """删除写穿：软删未删行返回 True；重复删/删不存在行返回 False。"""
    service = WarehouseService(db_session)
    page_key = "wtp-test-soft-delete"
    await _create_snapshot(service, page_key, "tbl-wtp-4")
    snapshot = await service.repo.get_material_page_snapshot(page_key)
    assert snapshot is not None
    await service.repo.upsert_material_page_rows(
        snapshot.id,
        _row_models(snapshot.id, [{"__record_id": "rec-1", "物料名称": "物料A"}]),
    )

    first_delete = await service.repo.soft_delete_material_page_row(
        snapshot.id, "rec-1"
    )
    assert first_delete is True
    second_delete = await service.repo.soft_delete_material_page_row(
        snapshot.id, "rec-1"
    )
    assert second_delete is False
    assert (
        await service.repo.soft_delete_material_page_row(snapshot.id, "rec-missing")
        is False
    )
    rows = await _all_page_rows(service, page_key)
    assert rows[0].is_deleted is True


def _mock_service() -> WarehouseService:
    """service 层写穿测试：最小 mock repo（service.__new__ 绕过初始化）。"""
    service = WarehouseService.__new__(WarehouseService)
    service.repo = SimpleNamespace(
        session=SimpleNamespace(rollback=AsyncMock()),
        get_material_page_snapshot=AsyncMock(),
        upsert_material_page_row_write_through=AsyncMock(return_value=False),
        soft_delete_material_page_row=AsyncMock(return_value=False),
    )
    service._page_cache = {}
    service._field_meta_cache = {}
    service._table_fields_cache = {}
    service._dashboard_cache = {}
    return service


def _page_config() -> SimpleNamespace:
    return SimpleNamespace(
        page_key="raw-summary", app_token="app", table_id="tbl", title="原料"
    )


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        columns=[
            {
                "key": "名称",
                "title": "名称",
                "field_type": 1,
                "readonly": False,
                "view_only": False,
                "editable": True,
            },
            {
                "key": "状态",
                "title": "状态",
                "field_type": 3,
                "readonly": False,
                "view_only": False,
                "editable": True,
            },
        ],
        total_rows=3,
    )


_FIELDS_META = [
    {"field_name": "名称", "type": 1},
    {
        "field_name": "状态",
        "type": 3,
        "property": {"options": [{"id": "opt-1", "name": "正常"}]},
    },
]


def _patch_feishu(
    monkeypatch: pytest.MonkeyPatch,
    service: WarehouseService,
    *,
    put_response: dict[str, Any],
    get_record: dict[str, Any],
) -> SimpleNamespace:
    page_config = _page_config()
    monkeypatch.setattr(
        service, "_get_material_page_config", AsyncMock(return_value=page_config)
    )
    monkeypatch.setattr(
        service, "_get_page_field_meta", AsyncMock(return_value=_FIELDS_META)
    )
    monkeypatch.setattr(
        service,
        "_build_page_option_map",
        AsyncMock(return_value={"opt-1": "正常"}),
    )
    write_client = SimpleNamespace(request=AsyncMock(return_value=put_response))
    monkeypatch.setattr(
        service, "_get_material_client", AsyncMock(return_value=write_client)
    )
    read_client = SimpleNamespace(
        request=AsyncMock(return_value={"record": get_record})
    )
    monkeypatch.setattr(
        service, "_get_feishu_client", AsyncMock(return_value=read_client)
    )
    return write_client


@pytest.mark.asyncio
async def test_update_material_page_record_writes_through_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """编辑成功后单条写穿：选项解析进 cells，record_meta 带飞书时间戳。"""
    service = _mock_service()
    service.repo.get_material_page_snapshot.return_value = _snapshot()
    _patch_feishu(
        monkeypatch,
        service,
        put_response={"record": {"record_id": "r1", "fields": {"名称": "新名称"}}},
        get_record={
            "record_id": "r1",
            "fields": {"名称": "新名称", "状态": "opt-1"},
            "created_time": 1_111,
            "last_modified_time": 2_222,
        },
    )

    record = await service.update_material_page_record(
        "raw-summary", "r1", {"名称": "新名称"}
    )

    assert record["record_id"] == "r1"
    service.repo.upsert_material_page_row_write_through.assert_awaited_once()
    args, kwargs = service.repo.upsert_material_page_row_write_through.await_args
    assert args[0] == 11
    row = args[1]
    assert row.source_record_id == "r1"
    assert row.cells == {"名称": "新名称", "状态": "正常"}
    assert kwargs["page_key"] == "raw-summary"
    assert kwargs["record_meta"] == {
        "r1": {"created_ms": 1_111, "modified_ms": 2_222}
    }
    # 更新已有行：total_rows 不变
    assert service.repo.get_material_page_snapshot.return_value.total_rows == 3


@pytest.mark.asyncio
async def test_update_write_through_insert_increments_total_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写穿新增行时 total_rows +1。"""
    service = _mock_service()
    snapshot = _snapshot()
    service.repo.get_material_page_snapshot.return_value = snapshot
    service.repo.upsert_material_page_row_write_through.return_value = True
    _patch_feishu(
        monkeypatch,
        service,
        put_response={"record": {"record_id": "r2", "fields": {"名称": "x"}}},
        get_record={"record_id": "r2", "fields": {"名称": "x"}},
    )

    await service.update_material_page_record("raw-summary", "r2", {"名称": "x"})

    assert snapshot.total_rows == 4


@pytest.mark.asyncio
async def test_update_write_through_failure_keeps_save_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写穿失败不影响保存结果：返回编辑记录并回滚会话。"""
    service = _mock_service()
    service.repo.get_material_page_snapshot.side_effect = RuntimeError("db down")
    _patch_feishu(
        monkeypatch,
        service,
        put_response={"record": {"record_id": "r1", "fields": {"名称": "新名称"}}},
        get_record={"record_id": "r1", "fields": {"名称": "新名称"}},
    )

    record = await service.update_material_page_record(
        "raw-summary", "r1", {"名称": "新名称"}
    )

    assert record["record_id"] == "r1"
    service.repo.upsert_material_page_row_write_through.assert_not_awaited()
    service.repo.session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_material_page_record_write_through_soft_deletes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """删除成功后写穿软删镜像行并递减 total_rows。"""
    service = _mock_service()
    snapshot = _snapshot()
    service.repo.get_material_page_snapshot.return_value = snapshot
    service.repo.soft_delete_material_page_row.return_value = True
    _patch_feishu(
        monkeypatch,
        service,
        put_response={},
        get_record={},
    )

    await service.delete_material_page_record("raw-summary", "r1")

    service.repo.soft_delete_material_page_row.assert_awaited_once_with(11, "r1")
    assert snapshot.total_rows == 2


@pytest.mark.asyncio
async def test_delete_write_through_failure_keeps_delete_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """删除写穿失败不影响删除结果：不抛错并回滚会话。"""
    service = _mock_service()
    service.repo.get_material_page_snapshot.return_value = _snapshot()
    service.repo.soft_delete_material_page_row.side_effect = RuntimeError("db down")
    _patch_feishu(
        monkeypatch,
        service,
        put_response={},
        get_record={},
    )

    await service.delete_material_page_record("raw-summary", "r1")

    service.repo.session.rollback.assert_awaited_once()
