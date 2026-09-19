"""仓储模块飞书收口改造的防御分支补测。

覆盖：未绑定守卫（400/降级/跳过）、form-links 服务方法、
WS 事件匹配的 DB 绑定路径、repository upsert 新行分支。
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.modules.warehouse.feishu_material_pages import (
    FeishuWarehouseMaterialPage,
)
from app.modules.warehouse.service import WarehouseService

PAGE_KEY = "inbound-ledger"


def _service_with_repo() -> tuple[WarehouseService, AsyncMock]:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = AsyncMock()
    service._page_cache = {}
    service._MATERIAL_SYNC_CLIENTS = {}
    return service, service.repo


def _bound_config(page_key: str = PAGE_KEY) -> FeishuWarehouseMaterialPage:
    return FeishuWarehouseMaterialPage(
        page_key=page_key, title="入库总账", table_id="tbl-x", app_token="app-x"
    )


def _unbound_config(page_key: str = PAGE_KEY) -> FeishuWarehouseMaterialPage:
    return FeishuWarehouseMaterialPage(page_key=page_key, title="入库总账")


@pytest.mark.asyncio
async def test_is_material_page_bound_reflects_db_binding() -> None:
    service, repo = _service_with_repo()
    repo.get_page_feishu_config = AsyncMock(
        return_value={"page_key": PAGE_KEY, "app_token": "app-x", "table_id": "tbl-x"}
    )
    assert await service.is_material_page_bound(PAGE_KEY) is True

    repo.get_page_feishu_config = AsyncMock(return_value=None)
    assert await service.is_material_page_bound(PAGE_KEY) is False


@pytest.mark.asyncio
async def test_fetch_raises_400_when_page_unbound() -> None:
    service, repo = _service_with_repo()
    repo.get_page_feishu_config = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.fetch_material_page_from_feishu(PAGE_KEY)
    assert exc.value.status_code == 400
    assert "未配置" in exc.value.detail

    with pytest.raises(HTTPException) as exc:
        await service.fetch_material_page_from_feishu_incremental(
            PAGE_KEY, last_synced_at=None
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_sync_raises_400_when_page_unbound() -> None:
    service, repo = _service_with_repo()
    repo.get_page_feishu_config = AsyncMock(return_value=None)
    repo.get_material_page_snapshot = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.sync_material_page_to_local(PAGE_KEY)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_page_form_links_reads_db_config() -> None:
    service, repo = _service_with_repo()
    repo.get_page_feishu_config = AsyncMock(
        return_value={
            "page_key": PAGE_KEY,
            "app_token": "app-x",
            "table_id": "tbl-x",
            "table_name": "入库总账",
            "view_id": None,
            "feishu_inbound_form_url": "https://www.feishu.cn/share/base/form/shrcn_in",
            "feishu_outbound_form_url": None,
        }
    )
    links = await service.get_page_form_links(PAGE_KEY)
    assert links == {
        "inbound_form_url": "https://www.feishu.cn/share/base/form/shrcn_in",
        "outbound_form_url": None,
    }

    # DB 查询异常时按未配置处理，不抛错
    repo.get_page_feishu_config = AsyncMock(side_effect=RuntimeError("db down"))
    links = await service.get_page_form_links(PAGE_KEY)
    assert links == {"inbound_form_url": None, "outbound_form_url": None}


@pytest.mark.asyncio
async def test_get_home_quick_form_links_only_returns_configured() -> None:
    service, repo = _service_with_repo()
    repo.list_page_feishu_configs = AsyncMock(
        return_value=[
            {
                "page_key": PAGE_KEY,
                "app_token": "app-x",
                "table_id": "tbl-x",
                "table_name": "入库总账",
                "feishu_inbound_form_url": "https://www.feishu.cn/share/base/form/shrcn_in",
                "feishu_outbound_form_url": None,
            },
            {
                "page_key": "raw-summary",
                "app_token": "app-x",
                "table_id": "tbl-y",
                "table_name": "原辅料库存总表",
                "feishu_inbound_form_url": None,
                "feishu_outbound_form_url": None,
            },
        ]
    )
    links = await service.get_home_quick_form_links()
    assert set(links) == {PAGE_KEY}
    assert links[PAGE_KEY]["inbound_form_url"].endswith("shrcn_in")

    repo.list_page_feishu_configs = AsyncMock(side_effect=RuntimeError("db down"))
    assert await service.get_home_quick_form_links() == {}


@pytest.mark.asyncio
async def test_ws_event_match_uses_db_bindings() -> None:
    service, repo = _service_with_repo()
    repo.list_page_feishu_configs = AsyncMock(
        return_value=[
            {
                "page_key": PAGE_KEY,
                "app_token": "app-x",
                "table_id": "tbl-x",
                "table_name": "入库总账",
            }
        ]
    )
    service.sync_material_page_to_local = AsyncMock()

    result = await service.handle_feishu_bitable_record_changed(
        file_token="app-x", table_id="tbl-x", revision=None, update_time=None,
        actions=[],
    )
    assert result == {
        "matched": True, "status": "synced", "table_kind": PAGE_KEY,
    }
    service.sync_material_page_to_local.assert_awaited_once_with(PAGE_KEY)

    # 无匹配 → 忽略
    result = await service.handle_feishu_bitable_record_changed(
        file_token="other", table_id="other", revision=None, update_time=None,
        actions=[],
    )
    assert result == {"matched": False, "status": "ignored"}

    # DB 查询失败 → 忽略（不抛错）
    repo.list_page_feishu_configs = AsyncMock(side_effect=RuntimeError("db down"))
    result = await service.handle_feishu_bitable_record_changed(
        file_token="app-x", table_id="tbl-x", revision=None, update_time=None,
        actions=[],
    )
    assert result == {"matched": False, "status": "ignored"}


@pytest.mark.asyncio
async def test_repository_upsert_page_feishu_config_insert_and_update() -> None:
    """repository 双路径：新页 insert、已有页 update（含表单链接字段）。"""

    from app.modules.warehouse.models import WarehousePageFeishuConfig
    from app.modules.warehouse.repository import WarehouseRepository

    service, repo = _service_with_repo()

    class _FakeResult:
        def __init__(self, row: object) -> None:
            self._row = row

        def scalar_one_or_none(self):
            return self._row

    class _FakeSession:
        def __init__(self) -> None:
            self.row: WarehousePageFeishuConfig | None = None
            self.added: WarehousePageFeishuConfig | None = None
            self.committed = 0

        def add(self, obj: WarehousePageFeishuConfig) -> None:
            self.added = obj

        async def execute(self, _stmt):
            return _FakeResult(self.row)

        async def commit(self):
            self.committed += 1

    session = _FakeSession()
    fake_repo = WarehouseRepository(session)  # type: ignore[arg-type]

    config = {
        "page_key": PAGE_KEY,
        "app_token": "app-x",
        "table_id": "tbl-x",
        "table_name": "入库总账",
        "view_id": None,
        "feishu_inbound_form_url": "https://example.test/in",
        "feishu_outbound_form_url": None,
    }

    # insert 路径（无已有行）
    await fake_repo.upsert_page_feishu_config(config)
    assert session.added is not None
    assert session.added.feishu_inbound_form_url == "https://example.test/in"

    # update 路径（已有行，覆盖表单链接）
    session.row = session.added
    session.row.feishu_inbound_form_url = None
    await fake_repo.upsert_page_feishu_config(config)
    assert session.row.feishu_inbound_form_url == "https://example.test/in"
    assert session.committed == 2
