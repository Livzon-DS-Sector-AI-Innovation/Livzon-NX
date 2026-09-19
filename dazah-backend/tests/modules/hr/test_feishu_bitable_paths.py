from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.hr.feishu import bitable


def test_timestamp_conversion_accepts_supported_date_shapes() -> None:
    assert bitable._to_ms_timestamp(None) == ""
    assert bitable._to_ms_timestamp("2026-08-26") > 0
    assert bitable._to_ms_timestamp("2026/08/26") > 0
    assert bitable._to_ms_timestamp("20260826") > 0
    assert bitable._to_ms_timestamp("1750000000000") == 1750000000000
    assert bitable._to_ms_timestamp("not-a-date") == "not-a-date"
    assert bitable._to_ms_timestamp(date(2026, 8, 26)) > 0
    assert bitable._to_ms_timestamp(datetime(2026, 8, 26, tzinfo=UTC)) > 0


@pytest.mark.asyncio
async def test_bitable_client_crud_upload_and_paginated_reads() -> None:
    requests: list[tuple[str, str]] = []
    responses = [
        {"record": {"record_id": "created"}},
        {"record": {"record_id": "updated"}},
        {},
        {"file_token": "file-1"},
    ]

    class _Http:
        async def request(
            self, method: str, path: str, **_kwargs: object
        ) -> dict[str, object]:
            requests.append((method, path))
            return responses.pop(0)

        async def upload_file(
            self, *_args: object, **_kwargs: object
        ) -> dict[str, str]:
            return responses.pop(0)  # type: ignore[return-value]

    client = bitable.BitableClient.__new__(bitable.BitableClient)
    client.app_token = "app-token"
    client.client = _Http()
    assert (await client.create_record("table", {"名称": "A"}))[
        "record_id"
    ] == "created"
    assert (await client.update_record("table", "r1", {"名称": "B"}))[
        "record_id"
    ] == "updated"
    await client.delete_record("table", "r1")
    assert await client.upload_attachment("a.txt", b"content") == "file-1"
    assert (
        await client.upload_attachment("large.bin", b"x" * (20 * 1024 * 1024 + 1))
        is None
    )
    assert [method for method, _path in requests] == ["POST", "PUT", "DELETE"]

    client.client = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                {"items": [{"record_id": "r1"}], "has_more": True, "page_token": "p2"},
                {
                    "items": [{"record_id": "r1"}, {"record_id": "r2"}],
                    "has_more": False,
                },
            ]
        )
    )
    records = await client.search_records("table", filter_obj={"conjunction": "and"})
    assert [row["record_id"] for row in records] == ["r1", "r2"]

    client.client.request = AsyncMock(
        side_effect=[
            {"items": [{"record_id": "r1"}], "has_more": True, "page_token": "p2"},
            {"items": [{"record_id": "r2"}], "has_more": False},
        ]
    )
    records = await client.search_records("table")
    assert [row["record_id"] for row in records] == ["r1", "r2"]

    client.client.request = AsyncMock(
        return_value={"items": [{"record_id": "r3"}], "has_more": False}
    )
    assert await client.list_all_records(
        "table", field_names=["名称"], automatic_fields=True
    ) == [{"record_id": "r3"}]


@pytest.mark.asyncio
async def test_bitable_client_configuration_and_sync_branches() -> None:
    client = bitable.BitableClient.__new__(bitable.BitableClient)
    client.app_token = ""
    client.client = SimpleNamespace()
    with pytest.raises(RuntimeError):
        await client.create_record("table", {})
    with pytest.raises(RuntimeError):
        await client.upload_attachment("a.txt", b"x")

    client.app_token = "app"
    client.client = SimpleNamespace(upload_file=AsyncMock(return_value={}))
    assert await client.upload_attachment("a.txt", b"x") is None

    sync = bitable.FeishuBitableSync.__new__(bitable.FeishuBitableSync)
    sync.bitable = SimpleNamespace(
        app_token="app",
        delete_record=AsyncMock(),
        search_records=AsyncMock(return_value=[{"record_id": "found"}]),
    )
    sync.employee_table = "employee"
    assert await sync._find_employee_record("E1") == "found"
    assert await sync._find_employee_record(None) is None
    await sync.sync_employee_deleted("E1")
    assert sync.bitable.delete_record.await_count == 1

    # 部门台账镜像推送已下线：FeishuBitableSync 不再提供 department 方法
    assert not hasattr(bitable.FeishuBitableSync, "sync_department_created")
    assert not hasattr(bitable.FeishuBitableSync, "sync_department_updated")
    assert not hasattr(bitable.FeishuBitableSync, "sync_department_deleted")

    # 绑定缺失（空 token）时静默跳过删除联动
    disabled = bitable.FeishuBitableSync.__new__(bitable.FeishuBitableSync)
    disabled.bitable = SimpleNamespace(app_token="")
    disabled.employee_table = "employee"
    disabled.bitable.delete_record = AsyncMock()
    await disabled.sync_employee_deleted("E1")
    assert disabled.bitable.delete_record.await_count == 0
