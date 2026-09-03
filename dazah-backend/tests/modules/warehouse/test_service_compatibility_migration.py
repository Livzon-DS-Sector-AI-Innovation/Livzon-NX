from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.modules.warehouse.schemas import (
    WarehouseAnalyticsQuery,
    WarehouseDatasetPagination,
    WarehouseDatasetRecordResponse,
    WarehouseDatasetResponse,
    WarehouseFeishuColumn,
    WarehouseFeishuConfigUpsert,
    WarehouseFeishuFieldResponse,
    WarehouseFeishuMaterialPageResponse,
    WarehouseFeishuSourceRootInput,
    WarehouseFeishuTableResponse,
)
from app.modules.warehouse.service import WarehouseService


def _service() -> WarehouseService:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = SimpleNamespace(
        session=SimpleNamespace(
            commit=AsyncMock(),
            flush=AsyncMock(),
            refresh=AsyncMock(),
            rollback=AsyncMock(),
        ),
        get_any_feishu_config=AsyncMock(return_value=None),
        get_active_feishu_config=AsyncMock(return_value=None),
        get_feishu_table_by_id=AsyncMock(return_value=None),
        get_feishu_source_root=AsyncMock(return_value=None),
        list_feishu_source_roots=AsyncMock(return_value=[]),
        save_feishu_source_root=AsyncMock(),
        save_feishu_config=AsyncMock(),
        list_page_bindings=AsyncMock(return_value=[]),
        get_page_binding_by_id=AsyncMock(return_value=None),
        get_page_binding=AsyncMock(return_value=None),
        replace_page_bindings=AsyncMock(),
        list_feishu_fields=AsyncMock(return_value=[]),
        list_analysis_records=AsyncMock(return_value=[]),
        get_analysis_profile=AsyncMock(return_value=None),
        list_prompt_versions=AsyncMock(return_value=[]),
        next_prompt_version=AsyncMock(return_value=2),
        save_analysis_profile=AsyncMock(),
        save_prompt_version=AsyncMock(),
        save_analysis_run=AsyncMock(),
        save_analysis_result=AsyncMock(),
        get_analysis_result=AsyncMock(return_value=None),
        get_analysis_run=AsyncMock(return_value=None),
    )
    service._page_cache = {}
    service._field_meta_cache = {}
    service._table_fields_cache = {}
    service._dashboard_cache = {}
    return service


def _config(**overrides: object) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "config_name": "仓储配置",
        "app_id": "app-id",
        "encrypted_app_secret": "encrypted-secret",
        "timezone": "Asia/Shanghai",
        "daily_sync_time": "02:00",
        "is_active": True,
        "remark": None,
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _table(table_id: str = "tbl-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=WarehouseService._legacy_table_uuid(table_id),
        app_token="app-token",
        table_id=table_id,
        name="原料台账",
        revision=1,
        last_discovered_at=None,
        last_event_at=None,
        field_count=0,
        record_count=0,
        last_synced_at=None,
        sync_status=None,
        sync_error=None,
        source_root_id=None,
        source_path=[],
        schema_hash=None,
        active_mirror_version=None,
    )


def _binding(table_id: str = "tbl-1") -> object:
    table = WarehouseFeishuTableResponse(
        id=WarehouseService._legacy_table_uuid(table_id),
        app_token="app-token",
        table_id=table_id,
        name="原料台账",
        sync_status="available",
    )
    from app.modules.warehouse.schemas import WarehouseFeishuPageBindingResponse

    return WarehouseFeishuPageBindingResponse(
        id=table.id,
        page_key="raw-summary",
        table_pk=table.id,
        tab_label=table.name,
        is_default=True,
        status="published",
        table=table,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", None), ("12", 12), ("bad", None), (12.4, 12)],
)
def test_legacy_conversion_helpers(value: object, expected: int | None) -> None:
    assert WarehouseService._safe_int(value) == expected
    assert WarehouseService._as_dict(value) == (
        {"summary": str(value)} if value else {"summary": ""}
    )
    assert WarehouseService._as_dict_list(value) == (
        [{"summary": str(value)}] if value else []
    )

    assert WarehouseService._safe_float({"value": "2.5"}) == 2.5
    assert WarehouseService._safe_float([3]) == 3
    assert WarehouseService._safe_float("bad") is None


def test_raw_mapping_and_filter_validation() -> None:
    field = WarehouseService._field_from_raw(
        {"id": "f1", "name": "数量", "type": "2", "property": {}}
    )
    record = WarehouseService._record_from_raw(
        {"record_id": "r1", "fields": {"数量": 2}, "created_time": "3"}
    )
    assert field == WarehouseFeishuFieldResponse(
        field_id="f1", field_name="数量", type=2, property={}
    )
    assert record.record_id == "r1"
    assert record.created_time == 3
    assert WarehouseService._normalize_field_filter(
        field="数量", field_operator=None, field_value=" 2 "
    ) == ("contains", "2")
    assert WarehouseService._normalize_fields(
        {"a": {"value": "x"}, "b": [{"name": "y"}]}
    ) == {"a": "x", "b": ["y"]}
    assert "a x" in WarehouseService._build_search_text({"a": "x"})
    with pytest.raises(AppException):
        WarehouseService._normalize_field_filter(
            field=None, field_operator="eq", field_value="x"
        )
    with pytest.raises(AppException):
        WarehouseService._normalize_field_filter(
            field="数量", field_operator="gt", field_value="x"
        )


@pytest.mark.asyncio
async def test_config_and_table_error_boundaries() -> None:
    service = _service()
    service.repo.get_any_feishu_config.side_effect = RuntimeError("db")
    with pytest.raises(RuntimeError):
        await service._get_any_feishu_config_or_raise()

    service.repo.get_active_feishu_config.return_value = None
    with pytest.raises(AppException) as exc:
        await service._get_active_feishu_config_or_raise()
    assert exc.value.status_code == 400

    config = _config()
    service.repo.get_active_feishu_config.return_value = config
    service.repo.get_feishu_table_by_id.return_value = None
    with pytest.raises(AppException) as exc:
        await service._get_table_by_id_or_raise(uuid4())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_read_records_retries_and_rejects_broken_pagination() -> None:
    service = _service()
    client = SimpleNamespace(
        search_records=AsyncMock(
            side_effect=[
                RuntimeError("large page rejected"),
                {
                    "items": [{"record_id": "r1"}],
                    "has_more": True,
                    "page_token": "next",
                    "total": 2,
                },
                {"items": [{"record_id": "r2"}], "has_more": False, "total": 2},
            ]
        )
    )
    records, total = await service._read_all_records(client, "tbl")
    assert [item["record_id"] for item in records] == ["r1", "r2"]
    assert total == 2
    assert client.search_records.await_args_list[1].kwargs["page_size"] == 200

    broken = SimpleNamespace(
        search_records=AsyncMock(
            return_value={"items": [], "has_more": True, "page_token": ""}
        )
    )
    with pytest.raises(AppException, match="分页链不完整"):
        await service._read_all_records(broken, "tbl")


@pytest.mark.asyncio
async def test_tenant_token_and_connectivity_results_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    steps: list[object] = []
    assert (
        await service._test_tenant_token(
            _config(app_id="", encrypted_app_secret=""), steps
        )
        is None
    )
    assert steps[0].status == "error"  # type: ignore[union-attr]

    client = SimpleNamespace(
        get_tenant_access_token=AsyncMock(return_value="tenant-token")
    )
    monkeypatch.setattr(service, "_build_feishu_client", lambda *_args: client)
    steps = []
    assert await service._test_tenant_token(_config(), steps) == "tenant-token"
    assert steps[0].status == "ok"  # type: ignore[union-attr]

    service.repo.get_any_feishu_config.return_value = None
    result = await service.test_feishu_connectivity()
    assert result.ok is False
    assert "App Secret" in result.steps[0].message

    from app.modules.warehouse import service as service_module

    fake_client = MagicMock()
    fake_client.get_tenant_access_token = AsyncMock(return_value="token")
    monkeypatch.setattr(
        service_module, "WarehouseFeishuClient", lambda **_kwargs: fake_client
    )
    result = await service.test_feishu_connectivity(
        SimpleNamespace(app_id="id", app_secret="secret")
    )
    assert result.ok is True

    fake_client.get_tenant_access_token.side_effect = TimeoutError()
    result = await service.test_feishu_connectivity(
        SimpleNamespace(app_id="id", app_secret="secret")
    )
    assert result.ok is False
    assert "超时" in result.steps[0].message


@pytest.mark.asyncio
async def test_save_config_and_response_never_expose_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    existing = _config()
    service.repo.get_any_feishu_config.return_value = existing
    monkeypatch.setattr(
        "app.modules.warehouse.service.encrypt_secret", lambda value: f"enc:{value}"
    )
    service._after_feishu_config_saved = AsyncMock()
    response = await service.save_feishu_config(
        WarehouseFeishuConfigUpsert(app_id="new-app", app_secret="new-secret")
    )
    assert response.app_secret_masked == "****"
    assert "new-secret" not in response.model_dump_json()
    assert existing.encrypted_app_secret == "enc:new-secret"

    service.repo.get_any_feishu_config.return_value = None
    service.repo.save_feishu_config.side_effect = lambda config: setattr(
        config, "id", uuid4()
    )
    response = await service.save_feishu_config(
        WarehouseFeishuConfigUpsert(app_id="new-app", app_secret="new-secret")
    )
    assert response.app_id == "new-app"
    with pytest.raises(AppException, match="必须填写"):
        await service.save_feishu_config(WarehouseFeishuConfigUpsert(app_id="new-app"))


@pytest.mark.asyncio
async def test_legacy_table_listing_and_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    configs = [
        {
            "page_key": "raw-summary",
            "app_token": "a",
            "table_id": "t1",
            "table_name": "原料汇总",
        },
        {
            "page_key": "product-summary",
            "app_token": "b",
            "table_id": "t2",
            "table_name": "成品汇总",
        },
    ]
    service.get_all_page_feishu_configs = AsyncMock(return_value=configs)
    tables = await service.list_feishu_tables(keyword="原料")
    assert len(tables) == 1
    assert tables[0].id == service._legacy_table_uuid("t1")
    assert (
        await service._legacy_page_key(service._legacy_table_uuid("t2"))
        == "product-summary"
    )

    page = WarehouseFeishuMaterialPageResponse(
        page_key="raw-summary",
        page_title="原料汇总",
        table_name="原料汇总",
        columns=[WarehouseFeishuColumn(key="物料", title="物料", field_type=1)],
        rows=[{"__record_id": "r1", "物料": "乙醇"}],
        total=1,
        page=1,
        page_size=50,
        last_sync_time=datetime.now(UTC),
        source="local",
    )
    service.get_feishu_material_page = AsyncMock(return_value=page)
    result = await service.get_feishu_table_records(service._legacy_table_uuid("t1"))
    assert result.records[0].record_id == "r1"

    with pytest.raises(Exception):
        await service._legacy_page_key(service._legacy_table_uuid("missing"))


@pytest.mark.asyncio
async def test_page_binding_and_dataset_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.repo.get_any_feishu_config.return_value = _config()
    configs = [
        {
            "page_key": "raw-summary",
            "app_token": "a",
            "table_id": "t1",
            "table_name": "原料汇总",
        }
    ]
    service.get_all_page_feishu_configs = AsyncMock(return_value=configs)
    data = await service.get_page_data("raw-summary")
    # 无存储绑定时返回空列表（对齐 energy 契约：未发布 → 前端原样渲染 legacy 页）
    assert data.bindings == []

    binding = _binding("t1")
    service._binding_for_page = AsyncMock(return_value=binding)
    page = WarehouseFeishuMaterialPageResponse(
        page_key="raw-summary",
        page_title="原料汇总",
        table_name="原料汇总",
        columns=[
            WarehouseFeishuColumn(key="物料", title="物料", field_type=1),
            WarehouseFeishuColumn(key="数量", title="数量", field_type=2),
        ],
        rows=[
            {"__record_id": "r1", "物料": "乙醇", "数量": 2},
            {"__record_id": "r2", "物料": "水", "数量": 10},
            {"__record_id": "r3", "物料": "乙醇", "数量": 4},
        ],
        total=3,
        page=1,
        page_size=1000,
        last_sync_time=datetime.now(UTC),
        source="local",
    )
    service.get_feishu_material_page = AsyncMock(return_value=page)
    result = await service.get_page_dataset(
        "raw-summary",
        binding.table_pk,
        filter_fields=["数量"],
        filter_operators=["gt"],
        filter_values=["3"],
        sort_field="数量",
        sort_direction="desc",
    )
    assert [record.record_id for record in result.records] == ["r3", "r2"]
    values = await service.get_page_field_values(
        "raw-summary", binding.table_pk, "物料"
    )
    assert values.values[0].value == "乙醇"
    assert (
        await service.get_page_record("raw-summary", binding.table_pk, "r2")
    ).record_id == "r2"
    with pytest.raises(AppException) as exc:
        await service.get_page_record("raw-summary", binding.table_pk, "missing")
    assert exc.value.status_code == 404


@pytest.mark.parametrize(
    ("operator", "target", "expected"),
    [
        ("contains", "1", True),
        ("eq", "10", True),
        ("ne", "10", False),
        ("gt", "5", True),
        ("gte", "10", True),
        ("lt", "5", False),
        ("lte", "10", True),
    ],
)
def test_dataset_filter_operators(operator: str, target: str, expected: bool) -> None:
    assert WarehouseService._matches_dataset_filter("10", operator, target) is expected
    assert WarehouseService._matches_dataset_filter("not-a-number", "gt", "1") is False
    assert (
        WarehouseService._value_contains_token({"files": [{"token": "x"}]}, "x") is True
    )
    assert WarehouseService._value_contains_token(["y"], "x") is False


@pytest.mark.asyncio
async def test_attachment_download_checks_token_and_maps_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    binding_id = WarehouseService._legacy_table_uuid("t1")
    service.get_page_record = AsyncMock(
        return_value=WarehouseDatasetRecordResponse(
            record_id="r1", fields={"附件": [{"token": "file-1"}]}
        )
    )
    service._get_active_feishu_config_or_raise = AsyncMock(return_value=_config())
    service._get_material_page_config = AsyncMock(
        return_value=SimpleNamespace(app_token="app-token")
    )
    client = SimpleNamespace(
        download_media=AsyncMock(return_value=(b"data", "image/png", None))
    )
    service._build_feishu_client = MagicMock(return_value=client)
    assert await service.download_page_attachment(
        "raw-summary", binding_id, "r1", "附件", "file-1"
    ) == (b"data", "image/png", None)
    with pytest.raises(AppException) as exc:
        await service.download_page_attachment(
            "raw-summary", binding_id, "r1", "附件", "other"
        )
    assert exc.value.status_code == 403
    client.download_media.side_effect = RuntimeError("provider")
    with pytest.raises(AppException) as exc:
        await service.download_page_attachment(
            "raw-summary", binding_id, "r1", "附件", "file-1"
        )
    assert exc.value.status_code == 502
    with pytest.raises(AppException):
        await service.download_page_attachment(
            "raw-summary", binding_id, "r1", "附件", "bad\n"
        )


@pytest.mark.asyncio
async def test_aggregate_dataset_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    binding_id = WarehouseService._legacy_table_uuid("t1")
    service._page_key_for_binding = AsyncMock(return_value="raw-summary")
    dataset = WarehouseDatasetResponse(
        dataset=_binding("t1"),
        fields=[],
        records=[
            WarehouseDatasetRecordResponse(record_id="1", fields={"组": "A", "数": 2}),
            WarehouseDatasetRecordResponse(record_id="2", fields={"组": "A", "数": 4}),
            WarehouseDatasetRecordResponse(record_id="3", fields={"组": "B", "数": 8}),
        ],
        pagination=WarehouseDatasetPagination(page=1, page_size=1000, total=3),
    )
    service.get_page_dataset = AsyncMock(return_value=dataset)
    for metric, expected in [
        ("count", 2),
        ("count_distinct", 2),
        ("sum", 6),
        ("avg", 3),
        ("min", 2),
        ("max", 4),
    ]:
        result = await service.aggregate_page_dataset(
            WarehouseAnalyticsQuery(
                binding_id=binding_id,
                metric=metric,
                metric_field_id="数",
                group_field_id="组",
            )
        )
        assert result.rows[0]["value"] == expected


@pytest.mark.asyncio
async def test_source_root_and_discovery_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    config = _config()
    service.repo.get_active_feishu_config.return_value = config
    service.repo.list_feishu_source_roots.return_value = []
    service.repo.save_feishu_source_root.side_effect = lambda root: setattr(
        root, "id", uuid4()
    )
    service.repo.session.refresh.side_effect = lambda root: None
    root = await service.create_feishu_source_root(
        WarehouseFeishuSourceRootInput(
            name="入口",
            source_type="base",
            source_url="https://feishu.cn/base/app-token",
        )
    )
    assert root.root_token == "app-token"
    service.repo.list_feishu_source_roots.return_value = [
        SimpleNamespace(root_token="app-token")
    ]
    with pytest.raises(AppException) as exc:
        await service.create_feishu_source_root(
            WarehouseFeishuSourceRootInput(
                name="重复", source_type="base", source_url="app-token"
            )
        )
    assert exc.value.status_code == 409

    service.repo.get_any_feishu_config.return_value = config
    service.repo.get_feishu_source_root.return_value = SimpleNamespace(
        config_id=config.id
    )
    result = await service.delete_feishu_source_root(root.id)
    assert result["deleted"] is True


@pytest.mark.asyncio
async def test_analysis_profile_and_run_compatibility() -> None:
    service = _service()
    profile_id = uuid4()
    prompt_id = uuid4()
    service.repo.save_analysis_profile.side_effect = lambda profile: setattr(
        profile, "id", profile_id
    )
    service.repo.save_prompt_version.side_effect = lambda prompt: setattr(
        prompt, "id", prompt_id
    )
    data = SimpleNamespace(
        name="库存分析",
        resource_ids=[profile_id],
        analysis_goal="分析库存",
        input_field_ids=["qty"],
        time_field_id=None,
        metric_field_ids=["qty"],
        dimension_field_ids=[],
        quality_rules={},
        output_schema={},
        max_raw_rows=20,
        auto_run=False,
        allow_sensitive_fields=False,
        system_prompt="请分析",
        business_context=None,
        focus_points=[],
    )
    created = await service.create_analysis_profile(data)
    assert created.id == profile_id
    profile = SimpleNamespace(
        id=profile_id,
        name="库存分析",
        resource_ids=[str(profile_id)],
        analysis_goal="分析库存",
        input_field_ids=["qty"],
        time_field_id=None,
        metric_field_ids=["qty"],
        dimension_field_ids=[],
        max_raw_rows=20,
        auto_run=False,
        allow_sensitive_fields=False,
    )
    prompt = SimpleNamespace(
        id=prompt_id,
        profile_id=profile_id,
        version=1,
        system_prompt="请分析",
        business_context=None,
        focus_points=[],
        status="published",
        published_at=datetime.now(UTC),
    )
    service.repo.get_analysis_profile.return_value = profile
    service.repo.list_prompt_versions.return_value = [prompt]
    assert (await service.get_analysis_profile(profile_id)).prompt_version == 1
    assert len(await service.list_prompt_versions(profile_id)) == 1
    service.repo.get_analysis_profile.return_value = None
    with pytest.raises(AppException) as exc:
        await service.get_analysis_profile(uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_material_record_edit_detail_and_delete_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    page_config = SimpleNamespace(
        page_key="raw-summary", app_token="app", table_id="tbl", title="原料"
    )
    fields = [
        {"field_name": "名称", "type": 1},
        {"field_name": "数量", "type": 2},
        {"field_name": "日期", "type": 5},
        {"field_name": "公式", "type": 19},
        {"field_name": "附件", "type": 17},
        {
            "field_name": "状态",
            "type": 3,
            "property": {"options": [{"id": "opt-1", "name": "正常"}]},
        },
    ]
    monkeypatch.setattr(
        service, "_get_material_page_config", AsyncMock(return_value=page_config)
    )
    monkeypatch.setattr(service, "_get_page_field_meta", AsyncMock(return_value=fields))
    monkeypatch.setattr(
        service, "_build_page_option_map", AsyncMock(return_value={"opt-1": "正常"})
    )
    # 写回走模块自有应用（_get_material_client）的通用 request
    write_client = SimpleNamespace(
        request=AsyncMock(
            return_value={"record": {"record_id": "r1", "fields": {"名称": "新"}}}
        )
    )

    async def _fake_material_client(app_token: str) -> SimpleNamespace:
        return write_client

    monkeypatch.setattr(service, "_get_material_client", _fake_material_client)
    service.feishu_client = SimpleNamespace(
        request=AsyncMock(
            return_value={
                "record": {
                    "record_id": "r1",
                    "fields": {
                        "名称": "乙醇",
                        "数量": 2,
                        "日期": 1_756_000_000_000,
                        "状态": "opt-1",
                        "额外": "保留",
                    },
                }
            }
        )
    )
    monkeypatch.setattr(
        service,
        "_get_feishu_client",
        AsyncMock(return_value=service.feishu_client),
    )

    detail = await service.get_material_page_record_detail("raw-summary", "r1")
    assert detail["record_id"] == "r1"
    assert any(item["field_name"] == "额外" for item in detail["fields"])

    updated = await service.update_material_page_record(
        "raw-summary",
        "r1",
        {
            "名称": "新名称",
            "数量": "1,200",
            "日期": "2026-08-20",
            "公式": "忽略",
            "附件": [],
        },
    )
    assert updated["record_id"] == "r1"
    put_body = write_client.request.await_args.kwargs["json_body"]
    assert put_body["fields"]["数量"] == 1200.0
    assert "公式" not in put_body["fields"]
    assert "附件" not in put_body["fields"]
    put_path = write_client.request.await_args.args[1]
    assert put_path.endswith("/records/r1")
    with pytest.raises(Exception):
        await service.update_material_page_record("raw-summary", "r1", {"未知": "x"})
    with pytest.raises(Exception):
        await service.update_material_page_record("raw-summary", "r1", {"公式": "x"})

    await service.delete_material_page_record("raw-summary", "r1")
    write_client.request.side_effect = RuntimeError("provider")
    with pytest.raises(Exception):
        await service.delete_material_page_record("raw-summary", "r1")


@pytest.mark.asyncio
async def test_feishu_fetch_sync_inventory_and_dashboard_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.feishu_client = SimpleNamespace(request=AsyncMock())
    monkeypatch.setattr(
        service,
        "_get_material_client",
        AsyncMock(return_value=service.feishu_client),
    )
    service.feishu_client.request.side_effect = [
        {"items": [{"field_name": "名称"}], "has_more": True, "page_token": "next"},
        {"items": [{"field_name": "数量"}], "has_more": False},
        {
            "items": [{"record_id": "r1", "fields": {"名称": "乙醇"}}],
            "has_more": True,
            "page_token": "next",
            "total": 2,
        },
        {
            "items": [{"record_id": "r2", "fields": {"名称": "水"}}],
            "has_more": False,
            "total": 2,
        },
    ]
    assert (
        len(await service.fetch_feishu_table_fields(app_token="a", table_id="t")) == 2
    )
    assert (
        len(
            await service.fetch_feishu_table_records(
                app_token="a", table_id="t", page_size=20
            )
        )
        == 2
    )

    page_config = SimpleNamespace(
        page_key="raw-summary", app_token="a", table_id="t", title="原辅料库存总表"
    )
    columns = [
        WarehouseFeishuColumn(key="物料名称", title="物料名称", field_type=1),
        WarehouseFeishuColumn(key="状态", title="状态", field_type=3),
    ]
    monkeypatch.setattr(
        service, "_get_material_page_config", AsyncMock(return_value=page_config)
    )
    monkeypatch.setattr(
        service,
        "fetch_feishu_table_fields",
        AsyncMock(
            return_value=[
                {"field_name": "物料名称", "type": 1},
                {
                    "field_name": "状态",
                    "type": 3,
                    "property": {"options": [{"id": "1", "name": "正常"}]},
                },
            ]
        ),
    )
    monkeypatch.setattr(
        service,
        "fetch_feishu_table_records",
        AsyncMock(
            return_value=[
                {"record_id": "r1", "fields": {"物料名称": "乙醇", "状态": "1"}}
            ]
        ),
    )
    fetched = await service.fetch_material_page_from_feishu("raw-summary")
    assert fetched[2][0]["物料名称"] == "乙醇"

    snapshot = SimpleNamespace(
        id=uuid4(),
        page_key="raw-summary",
        page_title="原辅料",
        table_name="原辅料",
        columns=[{"key": "物料名称", "title": "物料名称"}],
        last_synced_at=datetime.now(UTC),
    )
    service.repo.get_material_page_snapshot = AsyncMock()
    service.repo.list_material_page_rows = AsyncMock()
    service.repo.get_material_page_snapshot.return_value = snapshot
    service.repo.list_material_page_rows.return_value = (
        [
            SimpleNamespace(
                source_record_id="r1",
                cells={
                    "物料名称": "乙醇",
                    "预警": "库存不足",
                    "安全库存（30天）": 10,
                    "本日结存": 2,
                    "出库日期": "2026-08-20",
                },
            )
        ],
        1,
    )
    local = await service.get_local_material_page(
        "raw-summary", keyword="乙醇", page_size=10
    )
    assert local.total == 1

    monkeypatch.setattr(
        service,
        "fetch_material_page_from_feishu",
        AsyncMock(
            return_value=(
                page_config,
                columns,
                [{"物料名称": "乙醇", "__record_id": "r1"}],
                {},
            )
        ),
    )
    service.repo.upsert_material_page_snapshot = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    service.repo.upsert_material_page_rows = AsyncMock()
    synced = await service.sync_material_page_to_local("raw-summary")
    assert synced.total == 1
    service.sync_material_page_to_local = AsyncMock(return_value=synced)
    all_synced = await service.sync_all_material_pages_to_local()
    assert all_synced

    inv_columns = [
        WarehouseFeishuColumn(key="物料名称", title="物料名称", field_type=1),
        WarehouseFeishuColumn(key="可用库存", title="可用库存", field_type=2),
        WarehouseFeishuColumn(
            key="安全库存（30天）", title="安全库存（30天）", field_type=2
        ),
    ]
    inv_rows = [
        {
            "物料名称": "乙醇",
            "可用库存": "2",
            "安全库存（30天）": "10",
            "__record_id": "r1",
        }
    ]
    monkeypatch.setattr(
        service,
        "fetch_material_page_from_feishu",
        AsyncMock(return_value=(page_config, inv_columns, inv_rows, {})),
    )
    service.upsert_raw_material_snapshot = AsyncMock()
    service.upsert_packaging_snapshot = AsyncMock()
    service.upsert_product_snapshot = AsyncMock()
    assert await service._sync_inventory_page("raw-summary") == 1
    assert await service._sync_inventory_page("packaging-summary") == 1
    product_columns = [
        WarehouseFeishuColumn(key="产品名称", title="产品名称", field_type=1),
        WarehouseFeishuColumn(key="剩余量", title="剩余量", field_type=2),
    ]
    product_rows = [{"产品名称": "产品A", "剩余量": "3", "__record_id": "p1"}]
    monkeypatch.setattr(
        service,
        "fetch_material_page_from_feishu",
        AsyncMock(
            side_effect=lambda key: (
                (
                    page_config,
                    product_columns,
                    product_rows,
                    {},
                )
                if key == "product-summary"
                else (page_config, inv_columns, inv_rows, {})
            )
        ),
    )
    assert await service._sync_inventory_page("product-summary") == 1
    assert set(await service.sync_inventory_from_feishu()) == {
        "raw-summary",
        "packaging-summary",
        "product-summary",
    }

    today = datetime.now().date().isoformat()
    page_rows = {
        "raw-summary": [
            {
                "物料名称": "乙醇",
                "安全库存（30天）": 10,
                "本日结存": 20,
                "前台库存": 2,
                "使用产品/类别": "原料",
                "预警": "正常",
            }
        ],
        "raw-detail": [{"质量状态": "待验", "物料名称": "乙醇", "本日结存": 2}],
        "raw-ledger": [{"出库日期": today, "出库数量": 3}],
        "packaging-ledger": [{"出库日期": today, "出库数量": 2}],
        "inbound-ledger": [{"入库日期": today, "入库数量": 4, "物料名称": "乙醇"}],
        "hardware-summary": [{"金额（元）": 10}],
        "hardware-stock-amount": [{"车间A": 20, "总金额": 20}],
        "hardware-inbound-ledger": [
            {"日期": today, "入库量": 2, "单价（元）": 5, "物料名称": "螺栓"}
        ],
        "hardware-outbound-ledger": [
            {"日期": today, "金额": 8, "归属库区": "车间A", "物料名称": "螺栓"}
        ],
        "product-summary": [{"产品名称": "产品A", "合格数量": 5, "待检数量": 1}],
        "product-shipping": [{"日期": today, "产品名称": "产品A", "发货数量": 2}],
        "product-inbound-monthly": [{"月份": "2026-01", "产品A": 1, "产品B": 0}],
        "product-outbound-monthly": [{"月份": "2026-01", "产品A": 0, "产品B": 0}],
    }
    monkeypatch.setattr(
        service,
        "_load_page_rows",
        AsyncMock(side_effect=lambda key, _force: page_rows[key]),
    )
    raw_dashboard = await service._build_raw_dashboard(detail=True)
    hardware_dashboard = await service._build_hardware_dashboard(detail=True)
    product_dashboard = await service._build_product_dashboard(detail=True)
    assert raw_dashboard["safety"]["total"] == 1
    assert hardware_dashboard["stock_amount"] == 10
    assert product_dashboard["qualified"] == 5

    service._dashboard_cache = {}
    assert (await service.get_dashboard_data("raw", force=True))["safety"]["total"] == 1
    assert (await service.get_dashboard_data("raw", detail=True))["safety"][
        "total"
    ] == 1
    with pytest.raises(Exception):
        await service.get_dashboard_data("other", force=True)
    scope = SimpleNamespace(is_all=False, allows=lambda dept: dept == "车间A")
    filtered = service._apply_dashboard_scope(
        {
            "dept_stock": [
                {"dept": "车间A", "value": 1},
                {"dept": "车间B", "value": 2},
            ],
            "dept_outbound_30d": [],
            "stock_amount": 3,
            "outbound_30d_total": 0,
        },
        "hardware",
        scope,
    )
    assert filtered["stock_amount"] == 1
