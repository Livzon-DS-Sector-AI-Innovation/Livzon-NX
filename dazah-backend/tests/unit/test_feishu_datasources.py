"""Unit tests for Feishu datasource success and failure isolation."""

from datetime import date
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.platform.integrations.feishu.datasource import BitableDataSource
from app.platform.integrations.feishu.employee_datasource import (
    EmployeeBitableDataSource,
    EmployeeRecord,
    _extract_multi_select,
    _extract_number,
    _extract_text,
)

SimpleNamespace: Any = _SimpleNamespace


def _datasource() -> BitableDataSource:
    datasource = BitableDataSource.__new__(BitableDataSource)
    datasource.client = AsyncMock()
    datasource.table_id = "table"
    datasource.app_token = "token"
    return datasource


def _employee_datasource() -> EmployeeBitableDataSource:
    datasource = EmployeeBitableDataSource.__new__(EmployeeBitableDataSource)
    datasource.client = AsyncMock()
    datasource.client.app_token = "token"
    datasource.table_id = "employees"
    return datasource


@pytest.mark.asyncio
async def test_generic_datasource_crud_and_lookup() -> None:
    datasource = _datasource()
    datasource.client.create_record.return_value = {"record_id": "created"}  # type: ignore[attr-defined]
    datasource.client.search_records.side_effect = [  # type: ignore[attr-defined]
        [{"record_id": "found"}],
        [],
    ]

    assert await datasource.create({"name": "A"}) == "created"
    await datasource.update("record", {"name": "B"})
    await datasource.delete("record")
    assert await datasource.query(filter_str="filter", page_size=20) == [
        {"record_id": "found"}
    ]
    assert await datasource.get_by_field("工号", "E1") is None

    datasource.client.update_record.assert_awaited_once_with(  # type: ignore[attr-defined]
        "table",
        "record",
        {"name": "B"},
    )
    datasource.client.delete_record.assert_awaited_once_with("table", "record")  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_generic_datasource_upsert_uses_update_and_create_paths(
    monkeypatch: Any,
) -> None:
    datasource = _datasource()
    monkeypatch.setattr(
        datasource,
        "get_by_field",
        AsyncMock(side_effect=[{"record_id": "existing"}, None]),
    )
    monkeypatch.setattr(datasource, "update", AsyncMock())
    monkeypatch.setattr(datasource, "create", AsyncMock(return_value="created"))

    assert (
        await datasource.upsert_by_key(
            key_field="工号",
            key_value="E1",
            fields={"姓名": "张三"},
        )
        == "existing"
    )
    assert (
        await datasource.upsert_by_key(
            key_field="工号",
            key_value="E2",
            fields={"姓名": "李四"},
        )
        == "created"
    )


@pytest.mark.asyncio
async def test_generic_datasource_bulk_upsert_skips_empty_keys_and_classifies(
    monkeypatch: Any,
) -> None:
    datasource = _datasource()
    monkeypatch.setattr(
        datasource,
        "upsert_by_key",
        AsyncMock(side_effect=["updated-id", "created-id"]),
    )
    monkeypatch.setattr(
        datasource,
        "get_by_field",
        AsyncMock(side_effect=[{"record_id": "updated-id"}, None]),
    )
    rows = [
        {"工号": "E1", "姓名": "张三"},
        {"工号": "", "姓名": "跳过"},
        {"工号": "E2", "姓名": "李四"},
    ]

    result = await datasource.bulk_upsert(key_field="工号", rows=rows)
    assert result == {
        "created": ["created-id"],
        "updated": ["updated-id"],
    }
    assert rows[0] == {"姓名": "张三"}


def test_generic_datasource_prepares_dates_and_omits_nulls() -> None:
    prepared = BitableDataSource.prepare_fields(
        {
            "日期": date(2026, 1, 1),
            "字符串日期": "2026-01-02",
            "布尔": False,
            "空值": None,
        },
        {"日期", "字符串日期"},
    )
    assert prepared["日期"] == 1_767_225_600_000
    assert prepared["字符串日期"] == 1_767_312_000_000
    assert prepared["布尔"] is False
    assert "空值" not in prepared


def test_employee_value_extractors_cover_malformed_values() -> None:
    assert _extract_text([{"text": "A"}]) == "A"
    assert _extract_text({"text": "B"}) == "B"
    assert _extract_text("C") == "C"
    assert _extract_text(4) == "4"
    assert _extract_text(None) == ""
    assert _extract_number(3) == 3
    assert _extract_number({"value": [4]}) == 4
    assert _extract_number([5]) == 5
    assert _extract_number({}) is None
    assert _extract_multi_select(["A", 2]) == ["A", "2"]
    assert _extract_multi_select(None) == []
    assert _extract_multi_select("A") == ["A"]


@pytest.mark.asyncio
async def test_employee_datasource_rejects_disabled_search() -> None:
    datasource = _employee_datasource()
    datasource.client.app_token = ""
    with pytest.raises(RuntimeError, match="not configured"):
        await datasource._search()


@pytest.mark.asyncio
async def test_employee_datasource_query_filters_and_find_failures(
    monkeypatch: Any,
) -> None:
    datasource = _employee_datasource()
    search: Any = AsyncMock(
        side_effect=[
            [{"record_id": "one", "fields": {"姓名": "张三"}}],
            [],
            [{"record_id": "two", "fields": {"姓名": "李四"}}],
            [],
        ]
    )
    monkeypatch.setattr(datasource, "_search", search)

    records = await datasource.query(
        department="生产部",
        gender="男",
        status="在职",
        page_size=10,
    )
    assert records[0].name == "张三"
    assert "CurrentValue.[部门]" in search.await_args_list[0].kwargs["filter_str"]
    assert await datasource.find_by_employee_number("missing") is None
    assert (await datasource.find_by_name("李"))[0].record_id == "two"
    assert await datasource.find_by_domain_account("missing") is None


@pytest.mark.asyncio
async def test_employee_datasource_crud_and_upsert_paths(monkeypatch: Any) -> None:
    datasource = _employee_datasource()
    datasource.client.create_record.return_value = {"record_id": "created"}  # type: ignore[attr-defined]

    assert (
        await datasource.create(
            {
                "工号": "E1",
                "进厂时间": "2026-01-01",
                "年龄": 30,
                "空值": None,
            }
        )
        == "created"
    )
    await datasource.update("record", {"姓名": "张三"})
    await datasource.update("record", {"年龄": 30})
    await datasource.delete("record")

    existing: Any = SimpleNamespace(record_id="existing")
    monkeypatch.setattr(
        datasource,
        "find_by_employee_number",
        AsyncMock(side_effect=[existing, None]),
    )
    monkeypatch.setattr(datasource, "update", AsyncMock())
    monkeypatch.setattr(datasource, "create", AsyncMock(return_value="new"))
    assert await datasource.upsert_by_employee_number({"工号": "E1"}) == "existing"
    assert await datasource.upsert_by_employee_number({"工号": "E2"}) == "new"
    with pytest.raises(ValueError, match="工号"):
        await datasource.upsert_by_employee_number({})


@pytest.mark.asyncio
async def test_employee_bulk_sync_contains_each_record_failure(
    monkeypatch: Any,
) -> None:
    datasource = _employee_datasource()

    async def upsert(data: Any) -> Any:
        if data["工号"] == "bad":
            raise RuntimeError("Feishu unavailable")
        return data["工号"]

    monkeypatch.setattr(datasource, "upsert_by_employee_number", upsert)
    monkeypatch.setattr(
        datasource,
        "find_by_employee_number",
        AsyncMock(
            side_effect=[
                SimpleNamespace(record_id="E1"),
                None,
            ]
        ),
    )
    result = await datasource.sync_from_db(
        [{"工号": "E1"}, {"工号": "E2"}, {"工号": "bad"}]
    )
    assert result == {"created": 1, "updated": 1, "failed": 1}


def test_employee_record_maps_fields_dates_and_plain_dict() -> None:
    timestamp = 1_767_225_600_000
    fields = {
        "姓名": [{"text": "张三"}],
        "工号": {"text": "E1"},
        "域账号": "zhangsan",
        "部门": "生产部",
        "班组": "甲班",
        "性别": "男",
        "职位": "操作员",
        "职类": "生产",
        "级别": "P1",
        "身份证号": "masked",
        "身份证到期日": "2030-01-01",
        "手机": "masked",
        "邮箱地址": "a@example.com",
        "籍贯": "珠海",
        "政治面貌": "群众",
        "婚姻状况": "未婚",
        "户籍类型": "城镇",
        "学历": "本科",
        "毕业学校": "学校",
        "专业": "化学",
        "职称／职业资格": ["资格A"],
        "职称类型": "初级",
        "分类": "在职",
        "统计类别": "正式",
        "合同期限": "三年",
        "参加工作时间": timestamp,
        "进厂时间": timestamp,
        "入丽珠时间": timestamp,
        "毕业时间": timestamp,
        "银行卡号": "masked",
        "紧急联系人电话": "masked",
        "紧急联系人|关系": "李四/家属",
        "身份证地址|家庭地址": "地址",
        "现住址": "现址",
        "培训档案编号": "T1",
        "异动（含曾经工作部门、岗位)": "无",
        "备注": ["备注"],
        "年龄": 30,
        "工作年限": {"value": [5]},
        "厂龄": "3",
        "司龄": "2",
    }
    record = EmployeeRecord.from_api({"record_id": "record", "fields": fields})
    payload = record.to_dict()

    assert payload["record_id"] == "record"
    assert payload["employee_number"] == "E1"
    assert payload["work_start_date"] == "2026-01-01"
    assert payload["factory_entry_date"] == "2026-01-01"
    assert payload["livo_entry_date"] == "2026-01-01"
    assert payload["graduation_date"] == "2026-01-01"
    assert payload["work_years"] == 5
    assert EmployeeRecord._ms_to_date(0) is None
