"""质量检验结果→仓储入库台账 钩子：触发条件、批号解析、best-effort。"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service import warehouse_result_sync as hook

pytestmark = pytest.mark.anyio


def _record(
    result: str | None = None,
    batch: str | None = None,
    unqualified: str | None = None,
) -> dict[str, Any]:
    return {
        "record_id": "rec-1",
        "结果判断": result,
        "批号": batch,
        "不合格项目": unqualified,
    }


def _install_read_mock(
    monkeypatch: pytest.MonkeyPatch, record: dict[str, Any]
) -> None:
    async def fake_get_record(db, entity_code, record_id):
        return record

    monkeypatch.setattr(
        "app.modules.quality.service.inspection_feishu_crud.get_inspection_feishu_record",
        fake_get_record,
    )


def _capture_service_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_update(
        db,
        *,
        material_module,
        material_code,
        batch_no,
        result,
        unqualified_items=None,
    ):
        calls.append(
            {
                "material_module": material_module,
                "material_code": material_code,
                "batch_no": batch_no,
                "result": result,
                "unqualified_items": unqualified_items,
            }
        )
        return {"matched": True, "updated": True}

    monkeypatch.setattr(
        "app.modules.warehouse.public_api.update_inbound_inspection_result",
        fake_update,
    )
    return calls


async def test_non_material_entity_skipped(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    async def fake_sync(db, *, entity_code, record_id):
        called.append(entity_code)

    monkeypatch.setattr(hook, "sync_record_result_to_warehouse", fake_sync)
    await hook.maybe_sync_result_to_warehouse(
        db_session,
        entity_code="qc_items_inventory",
        record_id="r1",
        fields={"结果判断": "合格"},
    )
    assert called == []


async def test_fields_without_result_keys_skipped(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    async def fake_sync(db, *, entity_code, record_id):
        called.append(entity_code)

    monkeypatch.setattr(hook, "sync_record_result_to_warehouse", fake_sync)
    await hook.maybe_sync_result_to_warehouse(
        db_session,
        entity_code="qc_solid_ys002",
        record_id="r1",
        fields={"批号": "YS002-2506001"},
    )
    assert called == []


async def test_material_entity_triggers_sync(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    async def fake_sync(db, *, entity_code, record_id):
        called.append(entity_code)

    monkeypatch.setattr(hook, "sync_record_result_to_warehouse", fake_sync)
    await hook.maybe_sync_result_to_warehouse(
        db_session,
        entity_code="qc_solid_ys002",
        record_id="r1",
        fields={"结果判断": "合格"},
    )
    assert called == ["qc_solid_ys002"]


async def test_best_effort_on_failure(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(db, *, entity_code, record_id):
        raise RuntimeError("warehouse down")

    monkeypatch.setattr(hook, "sync_record_result_to_warehouse", boom)
    # 不应抛异常（best-effort，失败不影响质量写入）
    await hook.maybe_sync_result_to_warehouse(
        db_session,
        entity_code="qc_liquid_yl001",
        record_id="r1",
        fields={"结果判断": "不合格"},
    )


async def test_sync_solid_result_parses_code_and_batch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_read_mock(
        monkeypatch, _record(result="合格", batch="YS606-2609017")
    )
    calls = _capture_service_calls(monkeypatch)

    res = await hook.sync_record_result_to_warehouse(
        db_session, entity_code="qc_solid_ys606", record_id="rec-1"
    )
    assert res == {"matched": True, "updated": True}
    assert calls == [
        {
            "material_module": "solid",
            "material_code": "YS606",
            "batch_no": "2609017",
            "result": "合格",
            "unqualified_items": None,
        }
    ]


async def test_sync_liquid_uses_full_batch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_read_mock(
        monkeypatch,
        _record(result="不合格", batch="YL007-2609001", unqualified="水分超标"),
    )
    calls = _capture_service_calls(monkeypatch)

    res = await hook.sync_record_result_to_warehouse(
        db_session, entity_code="qc_liquid_yl007", record_id="rec-1"
    )
    assert res["matched"] is True
    assert calls == [
        {
            "material_module": "liquid",
            "material_code": "",
            "batch_no": "YL007-2609001",
            "result": "不合格",
            "unqualified_items": "水分超标",
        }
    ]


async def test_sync_skips_when_result_missing(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _capture_service_calls(monkeypatch)
    _install_read_mock(monkeypatch, _record(result=None, batch="YS606-2609017"))

    res = await hook.sync_record_result_to_warehouse(
        db_session, entity_code="qc_solid_ys606", record_id="rec-1"
    )
    assert res is None
    assert calls == []


async def test_sync_skips_solid_batch_without_prefix(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _capture_service_calls(monkeypatch)
    _install_read_mock(monkeypatch, _record(result="合格", batch="2609017"))

    res = await hook.sync_record_result_to_warehouse(
        db_session, entity_code="qc_solid_ys606", record_id="rec-1"
    )
    assert res is None
    assert calls == []
