from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import DuplicateException, NotFoundException
from app.modules.energy import service as energy_service
from app.modules.product import service as product_service

SimpleNamespace: Any = _SimpleNamespace


class Dump:
    def __init__(self: Any, **values: Any) -> None:
        self.values = values
        for key, value in values.items():
            setattr(self, key, value)

    def model_dump(self: Any, **_kwargs: Any) -> Any:
        return dict(self.values)


def _product_service() -> Any:
    service = product_service.ProductService.__new__(product_service.ProductService)
    service.repo = AsyncMock()
    service.bitable = AsyncMock()
    return service


def test_product_feishu_value_parsing_covers_supported_shapes() -> Any:
    assert product_service._extract_text([{"text": "A"}, "B", {"text": ""}]) == "A, B"
    assert product_service._extract_text([]) is None
    assert product_service._extract_text({"text": "A"}) == "A"
    assert product_service._extract_text({"text": ""}) is None
    assert product_service._extract_text({"value": [{"text": "B"}]}) == "B"
    assert product_service._extract_text({"value": []}) == "{'value': []}"
    assert product_service._extract_text(None) is None
    assert product_service._extract_text(12) == "12"

    parsed = product_service._parse_feishu_record(
        {
            "record_id": "rec-1",
            "updated_time": "2026-01-01T00:00:00Z",
            "fields": {
                "产品名称": [{"text": "原料药"}],
                "产品代码": "P-1",
                "制剂代码": "F-1",
                "产品剂型": "粉针",
                "生产规格": "1g",
                "生产批量": "100",
                "单位": "kg",
                "适应症": "test",
            },
        }
    )
    assert parsed["name"] == "原料药"
    assert parsed["feishu_synced_at"].isoformat() == "2026-01-01"
    assert (
        product_service._parse_feishu_record(
            {"record_id": "rec-2", "updated_time": "bad"}
        )["feishu_synced_at"]
        is not None
    )
    assert (
        product_service._parse_feishu_record({"record_id": "rec-3"})["feishu_synced_at"]
        is not None
    )


@pytest.mark.asyncio
async def test_product_crud_boundaries_and_non_blocking_feishu(monkeypatch: Any) -> Any:
    service = _product_service()
    product_id = uuid4()
    service.repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await service.get_product(product_id)

    created: Any = SimpleNamespace(
        id=product_id,
        name="P",
        major_category=None,
        formulation_code=None,
        product_type=None,
        spec=None,
        capacity_range=None,
        unit=None,
        indication=None,
        feishu_record_id=None,
    )
    service.repo.create.return_value = created
    monkeypatch.setattr(service, "_sync_to_feishu", AsyncMock(return_value="rec-1"))
    result = await service.create_product(cast(Any, Dump)(name="P"))
    assert result.feishu_record_id == "rec-1"
    service.repo.update.assert_awaited()

    service._sync_to_feishu.side_effect = RuntimeError("offline")
    service.repo.create.return_value = created
    assert await service.create_product(cast(Any, Dump)(name="P")) is created

    service.repo.get_by_id.return_value = created
    service.repo.update.return_value = created
    assert (
        await service.update_product(product_id, cast(Any, Dump)(name="P2")) is created
    )
    assert created.name == "P2"

    created.feishu_record_id = "rec-delete"
    service.bitable.delete.side_effect = RuntimeError("offline")
    await service.delete_product(product_id)
    service.repo.soft_delete.assert_awaited_once_with(created)

    service.repo.list_products.return_value = ([created], 1)
    assert await service.list_products(
        name="P",
        category="C",
        product_type="T",
        keyword="K",
        page=2,
        page_size=5,
    ) == ([created], 1)


@pytest.mark.asyncio
async def test_product_sync_created_updated_invalid_and_failed(monkeypatch: Any) -> Any:
    service = _product_service()
    now = datetime.utcnow()
    service.bitable.query.return_value = [
        {"record_id": "new", "fields": {"产品名称": "A"}},
        {"record_id": "old", "fields": {"产品名称": "B"}},
        {"record_id": "blank", "fields": {}},
        {"record_id": "broken", "fields": {"产品名称": "C"}},
    ]
    service.repo.get_by_feishu_record_id.side_effect = [
        SimpleNamespace(created_at=now),
        SimpleNamespace(created_at=now - timedelta(days=1)),
        RuntimeError("db"),
    ]
    stats = await service.sync_from_feishu()
    assert stats == {"created": 1, "updated": 1, "failed": 2, "total": 4}

    product: Any = SimpleNamespace(
        name="A",
        major_category="M",
        formulation_code="F",
        product_type="T",
        spec="S",
        capacity_range="C",
        unit="U",
        indication="I",
        feishu_record_id="rec-1",
    )
    service.repo.get_by_id.return_value = product
    assert await service.sync_to_feishu(uuid4()) == "rec-1"
    service.bitable.update.assert_awaited_once()

    product.feishu_record_id = None
    service.bitable.create.return_value = "rec-2"
    assert await service._sync_to_feishu(product) == "rec-2"
    service.repo.update.assert_awaited()

    service.repo.count_total.return_value = 5
    service.repo.count_synced.return_value = 3
    service.bitable.query.return_value = [{}, {}]
    status = await service.get_sync_status()
    assert (status.local_total, status.feishu_total, status.unsynced_count) == (5, 2, 2)
    service.bitable.query.side_effect = RuntimeError("offline")
    assert (await service.get_sync_status()).feishu_total == 0


@pytest.mark.asyncio
async def test_energy_device_config_boundaries_and_delegation(monkeypatch: Any) -> Any:
    db: Any = object()
    config_id = uuid4()
    existing: Any = SimpleNamespace(
        id=config_id,
        platform_code="p1",
        platform_device_code="d1",
    )
    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "exists_device_config",
        AsyncMock(return_value=True),
    )
    with pytest.raises(DuplicateException):
        await energy_service.create_device_config(
            db, cast(Any, Dump)(platform_code="p1", platform_device_code="d1")
        )

    energy_service.repo.exists_device_config.return_value = False  # type: ignore[attr-defined]
    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "create_device_config",
        AsyncMock(return_value=existing),
    )
    assert (
        await energy_service.create_device_config(
            db, cast(Any, Dump)(platform_code="p1", platform_device_code="d1")
        )
        is existing
    )

    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "get_device_config_by_id",
        AsyncMock(return_value=None),
    )
    with pytest.raises(NotFoundException):
        await energy_service.get_device_config(db, config_id)
    with pytest.raises(NotFoundException):
        await energy_service.update_device_config(
            db, config_id, cast(Any, Dump)(platform_code="p2")
        )
    with pytest.raises(NotFoundException):
        await energy_service.delete_device_config(db, config_id)

    energy_service.repo.get_device_config_by_id.return_value = existing  # type: ignore[attr-defined]
    energy_service.repo.exists_device_config.return_value = True  # type: ignore[attr-defined]
    with pytest.raises(DuplicateException):
        await energy_service.update_device_config(
            db, config_id, cast(Any, Dump)(platform_code="p2")
        )

    energy_service.repo.exists_device_config.return_value = False  # type: ignore[attr-defined]
    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "update_device_config",
        AsyncMock(return_value=existing),
    )
    assert (
        await energy_service.update_device_config(
            db, config_id, cast(Any, Dump)(platform_device_code="d2")
        )
        is existing
    )
    monkeypatch.setattr(energy_service.repo, "delete_device_config", AsyncMock())  # type: ignore[attr-defined]
    await energy_service.delete_device_config(db, config_id)
    energy_service.repo.delete_device_config.assert_awaited_once_with(db, config_id)  # type: ignore[attr-defined]

    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "list_device_configs",
        AsyncMock(return_value=([existing], 1)),
    )
    assert await energy_service.list_device_configs(
        db,
        platform_code="p1",
        energy_type="water",
        workshop="W",
        is_enabled=True,
        keyword="D",
        page=2,
        page_size=3,
    ) == ([existing], 1)


@pytest.mark.asyncio
async def test_energy_collection_all_platform_outcomes(monkeypatch: Any) -> Any:
    db: Any = object()
    device_a: Any = SimpleNamespace(
        id=uuid4(), platform_device_code="a", api_endpoint="http://example.test"
    )
    device_b: Any = SimpleNamespace(
        id=uuid4(), platform_device_code="b", api_endpoint="http://example.test"
    )
    adapter_partial: Any = SimpleNamespace(
        fetch_energy_data=AsyncMock(
            return_value=[
                SimpleNamespace(
                    device_code="a",
                    timestamp=datetime(2026, 1, 1),
                    value=1,
                    unit="kWh",
                    raw_data={},
                ),
                SimpleNamespace(
                    device_code="unknown",
                    timestamp=datetime(2026, 1, 1),
                    value=2,
                    unit="kWh",
                    raw_data={},
                ),
            ]
        )
    )
    adapter_failed: Any = SimpleNamespace(
        fetch_energy_data=AsyncMock(side_effect=RuntimeError("timeout"))
    )
    monkeypatch.setattr(
        energy_service,
        "ADAPTERS",
        {"empty": object(), "partial": adapter_partial, "failed": adapter_failed},
    )

    async def devices(_db: Any, platform: Any) -> Any:
        if platform == "empty":
            return []
        return [device_a, device_b]

    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "get_enabled_devices_by_platform",
        AsyncMock(side_effect=devices),
    )
    monkeypatch.setattr(energy_service.repo, "upsert_energy_data", AsyncMock())  # type: ignore[attr-defined]
    monkeypatch.setattr(energy_service.repo, "create_collect_log", AsyncMock())  # type: ignore[attr-defined]
    result = await energy_service.trigger_collection(
        db, cast(Any, Dump)(platform_code=None)
    )
    assert result["empty"]["status"] == "success"
    assert result["partial"]["status"] == "partial"
    assert result["failed"]["status"] == "failed"
    assert result["failed"]["error"] == "timeout"

    result = await energy_service.trigger_collection(
        db, cast(Any, Dump)(platform_code="missing")
    )
    assert result["missing"]["status"] == "failed"
    assert "未找到平台适配器" in result["missing"]["error"]


@pytest.mark.asyncio
async def test_energy_read_models_and_overview(monkeypatch: Any) -> Any:
    db: Any = object()
    log_id = uuid4()
    start = datetime(2026, 1, 1, 8)
    end = start + timedelta(hours=2)
    log: Any = SimpleNamespace(
        id=log_id,
        platform_code="p",
        collect_time=end,
        status="success",
        device_count=2,
        success_count=2,
        error_message=None,
        created_at=end,
    )
    rows = [
        (
            SimpleNamespace(value=1.5, unit="kWh", timestamp=end),
            SimpleNamespace(
                device_name="D2", platform_device_code="2", energy_type="electricity"
            ),
        ),
        (
            SimpleNamespace(value=1, unit="m3", timestamp=start),
            SimpleNamespace(
                device_name="D1",
                platform_device_code="1",
                energy_type="water",
            ),
        ),
    ]
    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "get_collect_log_detail",
        AsyncMock(return_value=(None, [])),
    )
    with pytest.raises(NotFoundException):
        await energy_service.get_collect_log_detail(db, log_id)
    energy_service.repo.get_collect_log_detail.return_value = (log, rows)  # type: ignore[attr-defined]
    detail = await energy_service.get_collect_log_detail(db, log_id)
    assert detail["time_range_start"] == start
    assert detail["time_range_end"] == end
    assert detail["devices"][0]["value"] == 1.5

    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "get_overview_summary",
        AsyncMock(
            return_value=[
                {"energy_type": "electricity", "total_value": 10},
                {"energy_type": "other", "total_value": 99},
            ]
        ),
    )
    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "get_overview_trend",
        AsyncMock(return_value=[{"v": 1}]),
    )
    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "get_energy_statistics",
        AsyncMock(return_value=[{"workshop": "W"}]),
    )
    overview = await energy_service.get_overview(
        db, start, end, energy_type="electricity"
    )
    assert overview["summary"] == {
        "total_electricity": 10,
        "total_water": 0,
        "total_gas": 0,
    }


@pytest.mark.asyncio
async def test_energy_alert_boundaries_and_simple_queries(monkeypatch: Any) -> Any:
    db: Any = object()
    item_id = uuid4()
    obj: Any = SimpleNamespace(id=item_id)

    for name, expected in (
        ("list_energy_data", ([obj], 1)),
        ("list_collect_logs", ([obj], 1)),
        ("list_alert_rules", ([obj], 1)),
        ("list_alert_records", ([obj], 1)),
    ):
        monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        name,
            AsyncMock(return_value=expected),
        )

    assert (await energy_service.list_energy_data(db, page=1, page_size=2))[1] == 1
    assert (await energy_service.list_collect_logs(db, page=1, page_size=2))[1] == 1
    assert (await energy_service.list_alert_rules(db, page=1, page_size=2))[1] == 1
    assert (await energy_service.list_alert_records(db, page=1, page_size=2))[1] == 1

    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "get_energy_statistics",
        AsyncMock(return_value=[{"v": 1}]),
    )
    assert await energy_service.get_energy_statistics(
        db,
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 1, 2),
    ) == [{"v": 1}]

    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "create_alert_rule",
        AsyncMock(return_value=obj),
    )
    assert (
        await energy_service.create_alert_rule(db, cast(Any, Dump)(name="rule")) is obj
    )

    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "get_alert_rule_by_id",
        AsyncMock(return_value=None),
    )
    with pytest.raises(NotFoundException):
        await energy_service.get_alert_rule(db, item_id)
    with pytest.raises(NotFoundException):
        await energy_service.update_alert_rule(db, item_id, cast(Any, Dump)(name="new"))
    with pytest.raises(NotFoundException):
        await energy_service.delete_alert_rule(db, item_id)

    energy_service.repo.get_alert_rule_by_id.return_value = obj  # type: ignore[attr-defined]
    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "update_alert_rule",
        AsyncMock(return_value=obj),
    )
    monkeypatch.setattr(energy_service.repo, "delete_alert_rule", AsyncMock())  # type: ignore[attr-defined]
    assert await energy_service.get_alert_rule(db, item_id) is obj
    assert (
        await energy_service.update_alert_rule(db, item_id, cast(Any, Dump)(name="new"))
        is obj
    )
    await energy_service.delete_alert_rule(db, item_id)

    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "get_alert_record_by_id",
        AsyncMock(return_value=None),
    )
    with pytest.raises(NotFoundException):
        await energy_service.process_alert_record(
            db, item_id, cast(Any, Dump)(status="processed", process_note="ok")
        )
    energy_service.repo.get_alert_record_by_id.return_value = obj  # type: ignore[attr-defined]
    monkeypatch.setattr(
        energy_service.repo,  # type: ignore[attr-defined]
        "update_alert_record",
        AsyncMock(return_value=obj),
    )
    assert (
        await energy_service.process_alert_record(
            db, item_id, cast(Any, Dump)(status="processed", process_note="ok")
        )
        is obj
    )
