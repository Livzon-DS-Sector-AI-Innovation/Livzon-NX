from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.hr import contract_sync_service
from app.modules.hr.contract_sync_service import ContractSyncService


def _scalar_result(value: object) -> SimpleNamespace:
    return SimpleNamespace(
        scalar_one_or_none=lambda: value,
        scalars=lambda: SimpleNamespace(first=lambda: value, all=lambda: [value]),
    )


def _contract(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "employee_number": "1001",
        "name": "张三",
        "gender": "男",
        "dept_level1": "质量部",
        "dept_level2": "QA",
        "position": "质量员",
        "job_level": "P3",
        "domain_account": "zhangsan",
        "id_card": "440000000000000000",
        "id_card_expiry": "2030-01-01",
        "archive_number": "A-1",
        "contract_sequence": "第二次",
        "contract_start_1": date(2020, 1, 1),
        "contract_end_1": date(2023, 1, 1),
        "contract_start_2": date(2023, 1, 2),
        "contract_end_2": "2026-01-01",
        "contract_start_3": date(2026, 1, 2),
        "contract_end_3": "2029-01-01",
        "contract_start_4": date(2029, 1, 2),
        "contract_end_4": "2032-01-01",
        "contract_start_5": date(2032, 1, 2),
        "contract_end_5": "2035-01-01",
        "contract_start_6": "2035-01-02",
        "contract_end_6": "2038-01-01",
        "feishu_record_id": None,
        "feishu_synced_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_contract_field_mapping_converts_numbers_dates_and_text() -> None:
    fields = contract_sync_service._build_contract_fields(_contract())
    assert fields["工号"] == 1001
    assert fields["姓名"] == "张三"
    assert isinstance(fields["首次签订合同日期"], int)
    assert fields["合同截止日期（2）"] == "2026-01-01"
    assert fields["第六次续签合同日期"] == "2035-01-02"
    assert (
        contract_sync_service._build_contract_fields(
            _contract(employee_number="not-a-number")
        )["工号"]
        == "not-a-number"
    )


@pytest.mark.asyncio
async def test_contract_sync_push_and_find_paths() -> None:
    session = SimpleNamespace(execute=AsyncMock(), flush=AsyncMock(), add=MagicMock())
    service = ContractSyncService(session)
    bitable = SimpleNamespace(
        create_record=AsyncMock(return_value={"record_id": "feishu-new"}),
        update_record=AsyncMock(),
        delete_record=AsyncMock(),
        search_records=AsyncMock(return_value=[{"record_id": "feishu-found"}]),
    )
    service._get_bitable = AsyncMock(return_value=bitable)  # type: ignore[method-assign]
    service._table_id = "tbl-contract"

    record = _contract()
    await service.push_create(record)
    assert record.feishu_record_id == "feishu-new"
    assert bitable.create_record.await_count == 1

    record.feishu_record_id = None
    await service.push_update(record)
    assert bitable.update_record.await_count == 1

    record.feishu_record_id = None
    bitable.update_record.side_effect = RuntimeError("deleted remotely")
    await service.push_update(record)
    assert bitable.create_record.await_count == 2

    record.feishu_record_id = None
    assert await service._find_feishu_record("1001") == "feishu-found"
    await service.push_delete(record)
    assert bitable.delete_record.await_count == 1


@pytest.mark.asyncio
async def test_contract_sync_pull_updates_creates_and_soft_deletes() -> None:
    existing = _contract(feishu_record_id="old")
    stale = _contract(employee_number="9999")
    record = {
        "record_id": "feishu-1",
        "fields": {
            "工号": 1001,
            "姓名": [{"text": "张三"}],
            "一级部门": "质量部",
            "首次签订合同日期": 1_704_067_200_000,
            "合同截止日期（2）": "2026-01-01",
        },
    }
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[_scalar_result(existing), _scalar_result(stale)]
        ),
        flush=AsyncMock(),
        add=MagicMock(),
    )
    service = ContractSyncService(session)
    bitable = SimpleNamespace(search_records=AsyncMock(return_value=[record]))
    service._get_bitable = AsyncMock(return_value=bitable)  # type: ignore[method-assign]
    service._table_id = "tbl-contract"

    result = await service.pull_from_feishu()

    assert result == {"created": 0, "updated": 1, "deleted": 1, "total": 1}
    assert existing.name == "张三"
    assert existing.approval_status == "synced"
    assert stale.is_deleted is True
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_contract_sync_pull_empty_feishu_soft_deletes_local_and_fetch_error() -> (
    None
):
    # 合同对账语义变更：飞书为唯一数据源，空表时本地同样执行软删（不再空表保护跳过）
    empty_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    session = SimpleNamespace(
        execute=AsyncMock(return_value=empty_result), flush=AsyncMock(), add=MagicMock()
    )
    service = ContractSyncService(session)
    service._get_bitable = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(
            search_records=AsyncMock(return_value=[{"fields": {}}])
        )
    )
    service._table_id = "tbl-contract"
    assert await service.pull_from_feishu() == {
        "created": 0,
        "updated": 0,
        "deleted": 0,
        "total": 1,
    }

    service._get_bitable = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(
            search_records=AsyncMock(side_effect=RuntimeError("remote"))
        )
    )
    failed = await service.pull_from_feishu()
    assert failed["error"] == "remote"
