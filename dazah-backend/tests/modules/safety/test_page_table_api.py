"""页面镜像 API 路由测试。

重点是**页面上下文与 URL 中 page_key 的一致性校验**：数据接口的 page_key 出现在
URL 里，而权限校验用的是请求头携带的页面标识；若不做一致性校验，持有 A 页权限的
用户就能用 B 的 page_key 读到别人的表。这里用一个把请求头写入 contextvar 的依赖
模拟 `require_module_view`，验证一致/不一致两种情形。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.safety.api import page_table as api
from app.modules.safety.schemas.page_table import (
    PageFeishuConfigItem,
    PageFeishuConfigListResponse,
    PageTableRecordsResponse,
)
from app.platform.identity.data_scope import current_page_key

PAGE_KEY = "safety:risk-hazard:hazard-inspection:hazard-duty"
SETTINGS_PAGE_KEY = "safety:system-config:safety-feishu-settings"


@pytest.fixture
def sub_app() -> FastAPI:
    application = FastAPI()

    async def _page_context(request: Request) -> None:
        # 模拟 require_module_view：把已授权页面写入 contextvar
        current_page_key.set(request.headers.get("X-Dazah-Page-Key"))

    application.include_router(
        api.page_table_router,
        prefix="/api/v1/safety",
        dependencies=[Depends(_page_context)],
    )
    application.dependency_overrides[get_db] = lambda: None
    application.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    return application


@pytest.fixture
def client(sub_app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=sub_app), base_url="http://test")


def _records_response() -> PageTableRecordsResponse:
    return PageTableRecordsResponse(
        page_key=PAGE_KEY,
        page_name="24小时值班隐患",
        columns=[],
        records=[],
        total=0,
        page=1,
        page_size=20,
    )


async def test_records_returns_200_when_page_context_matches(
    client: AsyncClient, monkeypatch
) -> None:
    fake = AsyncMock(return_value=_records_response())
    monkeypatch.setattr(api.page_table, "list_page_table_records", fake)

    resp = await client.get(
        f"/api/v1/safety/page-tables/{PAGE_KEY}/records",
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["page_name"] == "24小时值班隐患"
    assert fake.await_args.args[1] == PAGE_KEY


async def test_records_rejects_page_context_mismatch(
    client: AsyncClient, monkeypatch
) -> None:
    """URL 用别的页面 key、请求头是已授权页面时必须 403。"""
    fake = AsyncMock(return_value=_records_response())
    monkeypatch.setattr(api.page_table, "list_page_table_records", fake)

    resp = await client.get(
        "/api/v1/safety/page-tables/safety:other-page/records",
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )

    assert resp.status_code == 403
    assert "不一致" in resp.json()["detail"]
    fake.assert_not_awaited()


async def test_records_requires_page_context(client: AsyncClient, monkeypatch) -> None:
    fake = AsyncMock(return_value=_records_response())
    monkeypatch.setattr(api.page_table, "list_page_table_records", fake)

    resp = await client.get(f"/api/v1/safety/page-tables/{PAGE_KEY}/records")

    assert resp.status_code == 403
    fake.assert_not_awaited()


async def test_update_record_passes_fields_and_rejects_mismatch(
    client: AsyncClient, monkeypatch
) -> None:
    from app.modules.safety.schemas.page_table import PageTableRecord

    fake = AsyncMock(
        return_value=PageTableRecord(record_id="rec-1", fields={"记录编号": "YH-9"})
    )
    monkeypatch.setattr(api.page_table, "update_page_table_record", fake)

    ok = await client.put(
        f"/api/v1/safety/page-tables/{PAGE_KEY}/records/rec-1",
        json={"fields": {"记录编号": "YH-9"}},
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["fields"]["记录编号"] == "YH-9"
    assert fake.await_args.args[3] == {"记录编号": "YH-9"}

    fake.reset_mock()
    mismatch = await client.put(
        "/api/v1/safety/page-tables/safety:other-page/records/rec-1",
        json={"fields": {"记录编号": "YH-9"}},
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert mismatch.status_code == 403
    fake.assert_not_awaited()


async def test_upload_attachment_accepts_multipart(
    client: AsyncClient, monkeypatch
) -> None:
    from app.modules.safety.schemas.page_table import (
        PageTableAttachmentItem,
        PageTableAttachmentUploadResponse,
    )

    fake = AsyncMock(
        return_value=PageTableAttachmentUploadResponse(
            record_id="rec-1",
            field_name="照片",
            attachments=[
                PageTableAttachmentItem(
                    file_token="tok-1", name="a.jpg", type="image/jpeg"
                )
            ],
        )
    )
    monkeypatch.setattr(api.page_table, "upload_page_table_attachment", fake)

    resp = await client.post(
        f"/api/v1/safety/page-tables/{PAGE_KEY}/records/rec-1/attachments/照片",
        files={"file": ("a.jpg", b"jpeg-bytes", "image/jpeg")},
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["attachments"][0]["file_token"] == "tok-1"


async def test_download_attachment_sets_disposition(
    client: AsyncClient, monkeypatch
) -> None:
    fake = AsyncMock(return_value=(b"pdf-bytes", "application/pdf", "规范.pdf"))
    monkeypatch.setattr(api.page_table, "fetch_page_table_attachment", fake)

    resp = await client.get(
        f"/api/v1/safety/page-tables/{PAGE_KEY}/records/rec-1/attachments/照片/tok-1/content",
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )

    assert resp.status_code == 200
    assert resp.content == b"pdf-bytes"
    assert "attachment" in resp.headers["content-disposition"]

    inline = await client.get(
        f"/api/v1/safety/page-tables/{PAGE_KEY}/records/rec-1/attachments/照片/tok-1/content",
        params={"inline": "true"},
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert inline.headers["content-type"].startswith("application/pdf")
    assert "inline" in inline.headers["content-disposition"]


async def test_thumbnail_attachment_returns_scaled_jpeg(
    client: AsyncClient, monkeypatch
) -> None:
    fake = AsyncMock(return_value=(b"jpeg-thumb", "image/jpeg", "thumb.jpg"))
    monkeypatch.setattr(
        api.attachment_thumbnail,
        "get_page_table_attachment_thumbnail",
        fake,
    )

    resp = await client.get(
        f"/api/v1/safety/page-tables/{PAGE_KEY}/records/rec-1/attachments/照片/tok-1/thumbnail",
        params={"max_width": 120, "max_height": 90},
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )

    assert resp.status_code == 200
    assert resp.content == b"jpeg-thumb"
    assert resp.headers["content-type"] == "image/jpeg"
    # 尺寸参数透传给缩略图服务
    assert fake.await_args.args[5] == 120
    assert fake.await_args.args[6] == 90


async def test_thumbnail_attachment_rejects_non_image(
    client: AsyncClient, monkeypatch
) -> None:
    from app.core.exceptions import AppException

    monkeypatch.setattr(
        api.attachment_thumbnail,
        "get_page_table_attachment_thumbnail",
        AsyncMock(
            side_effect=AppException(
                message="该附件暂不支持生成缩略图", status_code=400
            )
        ),
    )

    resp = await client.get(
        f"/api/v1/safety/page-tables/{PAGE_KEY}/records/rec-1/attachments/照片/tok-1/thumbnail",
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert resp.status_code == 400


async def test_config_routes_do_not_require_target_page_context(
    client: AsyncClient, monkeypatch
) -> None:
    """配置接口的 {page_key} 是「要配置哪个镜像页」，调用者是飞书设置页。"""
    fake = AsyncMock(
        return_value=PageFeishuConfigListResponse(
            items=[
                PageFeishuConfigItem(
                    page_key=PAGE_KEY,
                    page_name="24小时值班隐患",
                    route_path="/safety/hazard-duty",
                )
            ]
        )
    )
    monkeypatch.setattr(api.page_table, "list_page_feishu_configs", fake)

    resp = await client.get(
        "/api/v1/safety/page-feishu-configs",
        headers={"X-Dazah-Page-Key": SETTINGS_PAGE_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["items"][0]["page_key"] == PAGE_KEY

    save = AsyncMock(
        return_value=PageFeishuConfigItem(
            page_key=PAGE_KEY,
            page_name="24小时值班隐患",
            route_path="/safety/hazard-duty",
            app_token="bascnX",
            table_id="tblX",
            is_configured=True,
        )
    )
    monkeypatch.setattr(api.page_table, "save_page_feishu_config", save)

    saved = await client.put(
        f"/api/v1/safety/page-feishu-configs/{PAGE_KEY}",
        json={"app_token": "bascnX", "table_id": "tblX"},
        headers={"X-Dazah-Page-Key": SETTINGS_PAGE_KEY},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["is_configured"] is True
    assert save.await_args.args[1] == PAGE_KEY


async def test_stats_endpoint_passes_page_key_and_group_by(
    client: AsyncClient, monkeypatch
) -> None:
    from app.modules.safety.schemas.page_table import (
        PageTableStatBucket,
        PageTableStatGroup,
        PageTableStatsResponse,
    )

    fake = AsyncMock(
        return_value=PageTableStatsResponse(
            page_key=PAGE_KEY,
            page_name="24小时值班隐患",
            total=3,
            groups=[
                PageTableStatGroup(
                    field="整改情况",
                    kind="select",
                    mode="value",
                    buckets=[
                        PageTableStatBucket(key="已整改", count=2),
                        PageTableStatBucket(key="未整改", count=1),
                    ],
                )
            ],
        )
    )
    monkeypatch.setattr(api.page_table, "get_page_table_stats", fake)

    resp = await client.get(
        f"/api/v1/safety/page-tables/{PAGE_KEY}/stats",
        params={"group_by": ["整改情况"]},
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 3
    assert body["groups"][0]["buckets"][0]["key"] == "已整改"
    assert fake.await_args.args[2] == ["整改情况"]

    # 页面上下文不一致时拒绝
    mismatch = await client.get(
        "/api/v1/safety/page-tables/safety:other-page/stats",
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert mismatch.status_code == 403


async def test_service_errors_become_http_status(
    client: AsyncClient, monkeypatch
) -> None:
    from app.core.exceptions import AppException

    monkeypatch.setattr(
        api.page_table,
        "list_page_table_records",
        AsyncMock(
            side_effect=AppException(status_code=503, message="尚未配置多维表格")
        ),
    )

    resp = await client.get(
        f"/api/v1/safety/page-tables/{PAGE_KEY}/records",
        headers={"X-Dazah-Page-Key": PAGE_KEY},
    )
    assert resp.status_code == 503


async def test_sync_endpoint_invokes_mirror_sync_and_returns_item(
    client: AsyncClient, monkeypatch
) -> None:
    """立即同步归设置页调用：执行同步并回读绑定（含最近同步状态）。"""
    sync = AsyncMock(return_value=42)
    monkeypatch.setattr(api.page_table, "sync_page_table_mirror", sync)
    listing = AsyncMock(
        return_value=PageFeishuConfigListResponse(
            items=[
                PageFeishuConfigItem(
                    page_key=PAGE_KEY,
                    page_name="24小时值班隐患",
                    route_path="/safety/hazard-duty",
                    is_configured=True,
                    is_mirrored=True,
                    last_sync_status="success",
                    last_sync_record_count=42,
                )
            ]
        )
    )
    monkeypatch.setattr(api.page_table, "list_page_feishu_configs", listing)

    resp = await client.post(
        f"/api/v1/safety/page-feishu-configs/{PAGE_KEY}/sync",
        headers={"X-Dazah-Page-Key": SETTINGS_PAGE_KEY},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["last_sync_status"] == "success"
    assert data["last_sync_record_count"] == 42
    assert sync.await_args.args[1] == PAGE_KEY


async def test_sync_endpoint_surfaces_conflict(
    client: AsyncClient, monkeypatch
) -> None:
    from app.core.exceptions import AppException

    monkeypatch.setattr(
        api.page_table,
        "sync_page_table_mirror",
        AsyncMock(side_effect=AppException(status_code=409, message="同步已在执行")),
    )

    resp = await client.post(
        f"/api/v1/safety/page-feishu-configs/{PAGE_KEY}/sync",
        headers={"X-Dazah-Page-Key": SETTINGS_PAGE_KEY},
    )
    assert resp.status_code == 409


def test_parse_conditions_rejects_invalid_json() -> None:
    from fastapi import HTTPException

    from app.modules.safety.api.page_table import _parse_conditions

    assert _parse_conditions(None) == []
    assert _parse_conditions("[]") == []
    with pytest.raises(HTTPException) as excinfo:
        _parse_conditions("not-json")
    assert excinfo.value.status_code == 400
    assert "conditions" in excinfo.value.detail


@pytest.mark.anyio
async def test_sync_endpoint_returns_404_when_binding_missing(
    sub_app: FastAPI, monkeypatch
) -> None:
    from unittest.mock import AsyncMock

    from app.modules.safety.schemas.page_table import PageFeishuConfigListResponse
    from app.modules.safety.service import page_table as service

    monkeypatch.setattr(
        service, "sync_page_table_mirror", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        service,
        "list_page_feishu_configs",
        AsyncMock(return_value=PageFeishuConfigListResponse(items=[], total=0)),
    )

    async with AsyncClient(
        transport=ASGITransport(app=sub_app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/safety/page-feishu-configs/k/sync")
    assert resp.status_code == 404
