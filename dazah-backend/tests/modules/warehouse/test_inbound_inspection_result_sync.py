"""仓储入库台账检验结果联动：定位最新行、字段写入、无匹配不动（mock 飞书）。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.warehouse.service import WarehouseService

pytestmark = pytest.mark.anyio


def _fields_meta() -> list[dict[str, Any]]:
    return [
        {"field_name": "检测结果", "type": 3},
        {"field_name": "不合格项目", "type": 1},
        {"field_name": "厂内代码", "type": 1},
        {"field_name": "厂内批号", "type": 1},
        {"field_name": "入库批号", "type": 1},
        {"field_name": "入库日期", "type": 5},
    ]


class _FakeWarehouseClient:
    """records/search 按请求 sort 排序后返回预设行；PUT 更新记录到 updates 列表。"""

    def __init__(self, search_items: list[dict[str, Any]]):
        self.search_items = search_items
        self.search_calls: list[dict[str, Any]] = []
        self.updates: list[tuple[str, dict[str, Any]]] = []

    async def request(
        self,
        method,
        path,
        *,
        params=None,
        json_body=None,
        force_token_refresh=False,
        timeout=15.0,
    ):
        if method == "POST":
            self.search_calls.append({"params": params, "body": json_body})
            items = list(self.search_items)
            sort_spec = (json_body or {}).get("sort") or []
            if sort_spec:
                field = sort_spec[0]["field_name"]
                desc = bool(sort_spec[0].get("desc"))

                def _sort_key(item: dict[str, Any]) -> Any:
                    return (item.get("fields") or {}).get(field) or ""

                items.sort(key=_sort_key, reverse=desc)
            return {"items": items, "total": len(items)}
        if method == "PUT":
            record_id = path.rsplit("/", 1)[-1]
            self.updates.append((record_id, json_body.get("fields") or {}))
            return {"record": {"record_id": record_id}}
        raise AssertionError(f"unexpected method {method}")


def _row(record_id: str, inbound_date_ms: float | None = None) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if inbound_date_ms is not None:
        fields["入库日期"] = inbound_date_ms
    return {"record_id": record_id, "fields": fields}


def _install_mocks(
    service: WarehouseService,
    client: _FakeWarehouseClient,
    page_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_config(_page_key):
        return SimpleNamespace(page_key=page_key, app_token="tok", table_id="tblX")

    async def fake_client(_app_token):
        return client

    async def fake_field_meta(_config):
        return _fields_meta()

    async def fake_mirror_sync(_page_key, *, incremental=True):
        return None

    monkeypatch.setattr(service, "_get_material_page_config", fake_config)
    monkeypatch.setattr(service, "_get_material_client", fake_client)
    monkeypatch.setattr(service, "_get_page_field_meta", fake_field_meta)
    monkeypatch.setattr(service, "sync_material_page_to_local", fake_mirror_sync)


async def test_solid_qualified_updates_latest_row(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = WarehouseService(db_session)
    client = _FakeWarehouseClient(
        [_row("rec-old", 1759276800000), _row("rec-new", 1759968000000)]
    )
    _install_mocks(service, client, "inbound-ledger", monkeypatch)

    res = await service.update_inbound_inspection_result(
        material_module="solid",
        material_code="YS606",
        batch_no="2609017",
        result="合格",
    )
    assert res == {"matched": True, "updated": True, "record_id": "rec-new"}
    # search 过滤条件：厂内代码 + 厂内批号 联合匹配（不服务端排序，避免大表超时）
    conds = client.search_calls[0]["body"]["filter"]["conditions"]
    assert {"field_name": "厂内代码", "operator": "is", "value": ["YS606"]} in conds
    assert {"field_name": "厂内批号", "operator": "is", "value": ["2609017"]} in conds
    assert "sort" not in client.search_calls[0]["body"]
    # 多行取入库日期最新一条；合格只写检测结果，不动不合格项目
    assert client.updates == [("rec-new", {"检测结果": "合格"})]


async def test_liquid_unqualified_writes_unqualified_items(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = WarehouseService(db_session)
    client = _FakeWarehouseClient([_row("rec-liq")])
    _install_mocks(service, client, "liquid-raw-inbound", monkeypatch)

    # 生产契约：液体调用方把质量批号整串作为 batch_no 传入（即台账「入库批号」）
    res = await service.update_inbound_inspection_result(
        material_module="liquid",
        material_code="",
        batch_no="YL007-2609001",
        result="不合格",
        unqualified_items="水分超标",
    )
    assert res["matched"] is True
    conds = client.search_calls[0]["body"]["filter"]["conditions"]
    assert {
        "field_name": "入库批号",
        "operator": "is",
        "value": ["YL007-2609001"],
    } in conds
    assert client.updates == [
        ("rec-liq", {"检测结果": "不合格", "不合格项目": "水分超标"})
    ]


async def test_no_match_returns_not_matched(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = WarehouseService(db_session)
    client = _FakeWarehouseClient([])
    _install_mocks(service, client, "inbound-ledger", monkeypatch)

    res = await service.update_inbound_inspection_result(
        material_module="solid",
        material_code="YS606",
        batch_no="2609017",
        result="合格",
    )
    assert res == {"matched": False, "updated": False}
    assert client.updates == []


async def test_unknown_module_rejected(db_session: AsyncSession) -> None:
    service = WarehouseService(db_session)
    with pytest.raises(AppException):
        await service.update_inbound_inspection_result(
            material_module="foo",
            material_code="YS606",
            batch_no="2609017",
            result="合格",
        )
