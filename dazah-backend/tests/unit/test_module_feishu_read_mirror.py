from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.modules.production.models import (
    ProductionFeishuReadField,
    ProductionFeishuReadPageBinding,
    ProductionFeishuReadRecord,
    ProductionFeishuReadResource,
    ProductionFeishuReadSourceRoot,
    ProductionFeishuReadSyncRun,
)
from app.platform.integrations.feishu.read_mirror import (
    ModuleFeishuReadMirrorService,
    ReadMirrorModels,
)

MODELS = ReadMirrorModels(
    root=ProductionFeishuReadSourceRoot,
    resource=ProductionFeishuReadResource,
    field=ProductionFeishuReadField,
    record=ProductionFeishuReadRecord,
    binding=ProductionFeishuReadPageBinding,
    sync_run=ProductionFeishuReadSyncRun,
)


class PagedClient:
    def __init__(self: Any, *, broken: bool = False) -> None:
        self.broken = broken

    async def list_fields(self: Any, _table_id: str, *, page_size: int = 100) -> Any:
        assert page_size == 100
        return [{"field_id": "fld_name", "field_name": "名称", "type": 1}]

    async def search_records(
        self: Any, _table_id: str, *, page_size: int, page_token: str | None
    ) -> Any:
        assert page_size == 500
        if page_token is None:
            return {
                "items": [
                    {"record_id": f"rec-{index}", "fields": {"名称": f"记录 {index}"}}
                    for index in range(500)
                ],
                "has_more": True,
                "page_token": None if self.broken else "page-2",
                "total": 501,
            }
        assert page_token == "page-2"
        return {
            "items": [{"record_id": "rec-500", "fields": {"名称": "记录 500"}}],
            "has_more": False,
            "page_token": None,
            "total": 501,
        }


async def _resource(db_session: Any) -> ProductionFeishuReadResource:
    root = ProductionFeishuReadSourceRoot(
        config_id=uuid4(),
        name="测试 Base",
        source_type="base",
        source_url="base-token",
        root_token="base-token",
    )
    db_session.add(root)
    await db_session.flush()
    resource = ProductionFeishuReadResource(
        source_root_id=root.id,
        app_token=f"base-{uuid4().hex}",
        table_id=f"tbl-{uuid4().hex}",
        title="测试数据表",
        source_path=[],
    )
    db_session.add(resource)
    await db_session.commit()
    return resource


@pytest.mark.asyncio
async def test_read_mirror_stitches_all_pages_and_publishes_only_complete_version(
    db_session: Any, monkeypatch: Any
) -> Any:
    resource = await _resource(db_session)
    service = ModuleFeishuReadMirrorService(
        db_session,
        module_code="production",
        app_id="dummy",
        app_secret="dummy",
        models=MODELS,
    )
    monkeypatch.setattr(service, "_client", lambda _app_token: PagedClient())

    result = await service._sync_resource_locked(resource.id)

    await db_session.refresh(resource)
    count = await db_session.scalar(
        select(func.count())
        .select_from(ProductionFeishuReadRecord)
        .where(
            ProductionFeishuReadRecord.resource_id == resource.id,
            ProductionFeishuReadRecord.mirror_version == resource.active_mirror_version,
        )
    )
    assert result["record_count"] == 501
    assert count == 501
    assert resource.sync_status == "success"

    binding_payload = {
        "resource_id": str(resource.id),
        "tab_name": "测试数据",
        "sort_order": 0,
        "is_default": True,
        "is_enabled": True,
        "visible_field_ids": [],
    }
    await service.replace_bindings("production.data", [binding_payload])
    page_data = await service.replace_bindings("production.data", [binding_payload])
    dataset = await service.page_records(
        page_key="production.data",
        binding_id=UUID(page_data["bindings"][0]["id"]),
        page=2,
        page_size=50,
        keyword=None,
    )
    assert len(page_data["bindings"]) == 1
    assert dataset["pagination"] == {"page": 2, "page_size": 50, "total": 501}
    assert len(dataset["records"]) == 50


@pytest.mark.asyncio
async def test_read_mirror_rejects_broken_page_chain_without_switching_version(
    db_session: Any, monkeypatch: Any
) -> Any:
    resource = await _resource(db_session)
    old_version = uuid4()
    resource.active_mirror_version = old_version
    db_session.add(
        ProductionFeishuReadRecord(
            resource_id=resource.id,
            record_id="old-record",
            mirror_version=old_version,
            raw_fields={"名称": "旧完整版本"},
            normalized_fields={"名称": "旧完整版本"},
            search_text="旧完整版本",
        )
    )
    await db_session.commit()
    service = ModuleFeishuReadMirrorService(
        db_session,
        module_code="production",
        app_id="dummy",
        app_secret="dummy",
        models=MODELS,
    )
    monkeypatch.setattr(service, "_client", lambda _app_token: PagedClient(broken=True))

    with pytest.raises(RuntimeError, match="分页链不完整"):
        await service._sync_resource_locked(resource.id)

    await db_session.refresh(resource)
    assert resource.active_mirror_version == old_version
    assert resource.sync_status == "failed"
