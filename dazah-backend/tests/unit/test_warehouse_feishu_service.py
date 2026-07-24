import asyncio
from typing import Any
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.modules.warehouse import service as warehouse_service
from app.modules.warehouse.models import (
    WarehouseFeishuAnalysisProfile,
    WarehouseFeishuConfig,
    WarehouseFeishuField,
    WarehouseFeishuRecord,
    WarehouseFeishuSourceRoot,
    WarehouseFeishuTable,
)
from app.modules.warehouse.schemas import WarehouseFeishuConfigUpsert
from app.modules.warehouse.service import WarehouseService


def test_build_search_text_flattens_nested_feishu_fields() -> None:
    text = WarehouseService._build_search_text(
        {
            "名称": [{"text": "阿莫西林"}],
            "库存": 12,
            "负责人": {"name": "张三", "email": "demo@example.com"},
        }
    )

    assert "名称" in text
    assert "阿莫西林" in text
    assert "12" in text
    assert "张三" in text
    assert "demo@example.com" in text


class FakeRecordClient:
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def search_records(
        self,
        table_id: str,
        *,
        page_size: int,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(page_token)
        if page_token is None:
            return {
                "items": [{"record_id": "rec1"}],
                "has_more": True,
                "page_token": "next",
            }
        return {
            "items": [{"record_id": "rec2"}],
            "has_more": False,
            "page_token": None,
        }


@pytest.mark.asyncio
async def test_read_all_records_reads_all_pages() -> None:
    service = WarehouseService.__new__(WarehouseService)
    client = FakeRecordClient()

    records, total = await service._read_all_records(client, "tbl1")  # type: ignore[arg-type]

    assert [record["record_id"] for record in records] == ["rec1", "rec2"]
    assert total is None
    assert client.calls == [None, "next"]


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.refreshes = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        return None

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, _instance: object) -> None:
        self.refreshes += 1


class FakeRepo:
    def __init__(self) -> None:
        self.session = FakeSession()

    async def fail_running_sync_runs(self, *args, **kwargs) -> None:
        return None


@pytest.mark.asyncio
async def test_save_feishu_config_uses_unified_credentials_only() -> None:
    service = WarehouseService.__new__(WarehouseService)
    config = WarehouseFeishuConfig(
        id=uuid4(),
        config_name="旧名称",
        app_id="cli_old",
        encrypted_app_secret="encrypted",
        is_active=True,
    )

    class ConfigRepo(FakeRepo):
        async def get_any_feishu_config(self) -> WarehouseFeishuConfig:
            return config

    service.repo = ConfigRepo()

    async def skip_ws_restart(_config: WarehouseFeishuConfig) -> None:
        return None

    service._after_feishu_config_saved = skip_ws_restart  # type: ignore[method-assign]

    response = await service.save_feishu_config(
        WarehouseFeishuConfigUpsert(
            config_name="统一配置",
            app_id="cli_new",
            is_active=True,
            timezone="Asia/Shanghai",
            daily_sync_time="03:15",
        )
    )

    assert response.config_name == "统一配置"
    assert response.app_id == "cli_new"
    assert response.daily_sync_time == "03:15"
    assert not hasattr(response, "bitable_app_token")
    assert service.repo.session.refreshes == 1


@pytest.mark.asyncio
async def test_discover_feishu_source_root_maps_remote_error_to_business_error() -> None:
    service = WarehouseService.__new__(WarehouseService)
    config_id = uuid4()
    root_id = uuid4()
    config = WarehouseFeishuConfig(
        id=config_id,
        config_name="仓储飞书配置",
        app_id="cli_123",
        encrypted_app_secret="encrypted",
        is_active=True,
    )
    root = WarehouseFeishuSourceRoot(
        id=root_id,
        config_id=config_id,
        name="无效入口",
        source_type="base",
        source_url="https://example.feishu.cn/base/invalid",
        root_token="invalid",
        is_active=True,
        discovery_status="pending",
    )

    class RootRepo(FakeRepo):
        async def get_active_feishu_config(self) -> WarehouseFeishuConfig:
            return config

        async def get_feishu_source_root(
            self, requested_root_id: object
        ) -> WarehouseFeishuSourceRoot:
            assert requested_root_id == root_id
            return root

    class FailedClient:
        async def list_tables(self, *, page_size: int) -> list[dict[str, Any]]:
            assert page_size == 100
            raise RuntimeError("app_token invalid")

    service.repo = RootRepo()
    service._build_feishu_client = (  # type: ignore[method-assign]
        lambda _config, _token: FailedClient()
    )

    with pytest.raises(AppException, match="飞书数据入口发现失败：app_token invalid"):
        await service.discover_feishu_source_root(root_id)

    assert root.discovery_status == "failed"
    assert root.discovery_error == "app_token invalid"
    assert service.repo.session.rollbacks == 1


@pytest.mark.asyncio
async def test_sync_feishu_table_marks_failed_when_sync_timeout(monkeypatch) -> None:
    service = WarehouseService.__new__(WarehouseService)
    table_id = uuid4()
    table = WarehouseFeishuTable(
        id=table_id,
        business_domain="hardware",
        app_token="base",
        table_id="tbl",
        name="五金",
    )
    config = WarehouseFeishuConfig(
        config_name="仓储飞书配置",
        app_id="cli_123",
        encrypted_app_secret="encrypted",
        is_active=True,
    )
    service.repo = FakeRepo()

    async def fake_get_table(table_pk):
        assert table_pk == table_id
        return table

    async def slow_snapshot(_config, _table, *, trigger_type):
        await asyncio.sleep(0.05)

    service._get_table_by_id_or_raise = fake_get_table  # type: ignore[method-assign]
    service._sync_feishu_table_snapshot = slow_snapshot  # type: ignore[method-assign]
    monkeypatch.setattr(
        warehouse_service,
        "WAREHOUSE_FEISHU_TABLE_SYNC_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(AppException):
        await service._sync_feishu_table(config, table)

    assert table.sync_status == "failed"
    assert table.sync_error == "同步超过 0.01 秒未完成，已自动标记失败"
    assert service.repo.session.commits == 2
    assert service.repo.session.rollbacks == 1


class FakeAnalysisRepo:
    async def list_feishu_fields(self, *args) -> list[WarehouseFeishuField]:
        return [
            WarehouseFeishuField(field_id="fld_name", field_name="姓名"),
            WarehouseFeishuField(field_id="fld_token", field_name="API Token"),
            WarehouseFeishuField(field_id="fld_value", field_name="库存量"),
        ]

    async def list_analysis_records(
        self, table: WarehouseFeishuTable, limit: int
    ) -> list[WarehouseFeishuRecord]:
        return [
            WarehouseFeishuRecord(
                business_domain=table.business_domain,
                app_token=table.app_token,
                table_id=table.table_id,
                record_id="rec1",
                fields={"姓名": "张三", "API Token": "do-not-send", "库存量": 12},
            )
        ]


@pytest.mark.asyncio
async def test_analysis_input_excludes_credentials_and_masks_personal_data() -> None:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = FakeAnalysisRepo()  # type: ignore[assignment]
    table = WarehouseFeishuTable(
        business_domain="hardware",
        app_token="base",
        table_id="tbl",
        name="库存",
        record_count=1,
        active_mirror_version="mirror-v1",
    )
    profile = WarehouseFeishuAnalysisProfile(
        name="库存分析",
        resource_ids=[str(uuid4())],
        analysis_goal="识别库存风险",
        input_field_ids=["fld_name", "fld_token", "fld_value"],
        metric_field_ids=["fld_value"],
        max_raw_rows=100,
        allow_sensitive_fields=False,
    )

    algorithm, _, rows = await service._prepare_analysis_input(profile, [table])

    assert rows[0]["fld_name"] == "***"
    assert "fld_token" not in rows[0]
    assert rows[0]["fld_value"] == 12
    assert algorithm["numeric_summary"]["fld_value"]["mean"] == 12


class HugeRecordClient:
    async def search_records(
        self,
        table_id: str,
        *,
        page_size: int,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        start = int(page_token or 0)
        end = min(start + page_size, 20_000)
        return {
            "items": [
                {"record_id": f"rec-{index}", "fields": {"序号": index}}
                for index in range(start, end)
            ],
            "has_more": end < 20_000,
            "page_token": str(end) if end < 20_000 else None,
            "total": 20_000,
        }


@pytest.mark.asyncio
async def test_read_all_records_keeps_twenty_thousand_rows_complete() -> None:
    service = WarehouseService.__new__(WarehouseService)

    records, total = await service._read_all_records(  # type: ignore[arg-type]
        HugeRecordClient(), "tbl-large"
    )

    assert total == 20_000
    assert len(records) == 20_000
    assert len({item["record_id"] for item in records}) == 20_000
    assert records[0]["record_id"] == "rec-0"
    assert records[-1]["record_id"] == "rec-19999"


class BrokenPageChainClient:
    async def search_records(self, *args, **kwargs) -> dict[str, Any]:
        return {
            "items": [{"record_id": "rec-1"}],
            "has_more": True,
            "page_token": None,
            "total": 2,
        }


@pytest.mark.asyncio
async def test_read_all_records_rejects_missing_next_page_token() -> None:
    service = WarehouseService.__new__(WarehouseService)

    with pytest.raises(AppException, match="分页链不完整"):
        await service._read_all_records(  # type: ignore[arg-type]
            BrokenPageChainClient(), "tbl-broken"
        )
