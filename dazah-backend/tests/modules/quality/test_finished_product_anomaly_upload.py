"""成品异常附件上传链路单元测试（mock 飞书 drive 上传，不触网）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.modules.quality.service.inspection_feishu_crud as crud
from app.core.exceptions import AppException


class _Runtime:
    app_id = "cli_1"
    app_secret = "secret_1"


class _Entity:
    app_token = "app_token_x"
    table_id = "tbl_x"
    enable_push_to_feishu = True
    enable_pull_from_feishu = True
    field_mappings = {}


class _FakeBitable:
    def __init__(self, *args, **kwargs) -> None:
        self.uploads: list[tuple] = []

    async def upload_media(
        self, file_name: str, content: bytes, content_type: str
    ) -> str:
        self.uploads.append((file_name, len(content)))
        return "ft_uploaded"


def _patch_client(monkeypatch: pytest.MonkeyPatch) -> _FakeBitable:
    fake = _FakeBitable()

    async def _resolve(db, entity_code, *, direction):
        return _Runtime(), _Entity()

    monkeypatch.setattr(crud, "_resolve_runtime_entity", _resolve)
    monkeypatch.setattr(crud, "BitableClient", lambda **kw: fake)
    return fake


@pytest.mark.asyncio
async def test_upload_attachment_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _patch_client(monkeypatch)
    result = await crud.upload_inspection_feishu_attachment(
        None,  # type: ignore[arg-type]
        "finished_product_anomaly_2026",
        "调查报告.pdf",
        b"%PDF-1.4",
        "application/pdf",
    )
    assert result == {
        "file_token": "ft_uploaded",
        "name": "调查报告.pdf",
        "size": 8,
        "type": "application/pdf",
    }
    assert fake.uploads == [("调查报告.pdf", 8)]


@pytest.mark.asyncio
async def test_upload_attachment_rejects_empty_and_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch)
    with pytest.raises(AppException) as exc_info:
        await crud.upload_inspection_feishu_attachment(
            None, "finished_product_anomaly_2026", "a.pdf", b"", ""  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(AppException) as exc_info:
        await crud.upload_inspection_feishu_attachment(
            None,  # type: ignore[arg-type]
            "finished_product_anomaly_2026",
            "big.bin",
            b"x" * (crud.MAX_ATTACHMENT_UPLOAD_BYTES + 1),
            "application/octet-stream",
        )
    assert exc_info.value.status_code == 400
    assert "20MB" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_upload_attachment_rejects_unknown_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(AppException):
        await crud.upload_inspection_feishu_attachment(
            None,  # type: ignore[arg-type]
            "deviation_ledger",
            "a.pdf",
            b"x",
            "application/pdf",
        )


class _FakeUploadResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeUploadClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, url, headers=None, data=None, files=None):
        self.calls.append({"url": url, "data": data, "files": files})
        return _FakeUploadResponse(self.payload)


@pytest.mark.asyncio
async def test_bitable_upload_media_success_and_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.platform.integrations.feishu.bitable as bitable_mod
    from app.platform.integrations.feishu.auth import FeishuAuth

    monkeypatch.setattr(
        FeishuAuth, "get_tenant_access_token", AsyncMock(return_value="tok")
    )
    client = bitable_mod.BitableClient(
        app_token="app_x", app_id="cli_x", app_secret="s"
    )

    ok = _FakeUploadClient({"code": 0, "data": {"file_token": "ft_9"}})
    monkeypatch.setattr(bitable_mod.httpx, "AsyncClient", lambda **kw: ok)
    token = await client.upload_media("x.pdf", b"12345", "application/pdf")
    assert token == "ft_9"
    sent = ok.calls[0]
    assert sent["url"].endswith("/drive/v1/medias/upload_all")
    assert sent["data"]["parent_type"] == "bitable_file"
    assert sent["data"]["parent_node"] == "app_x"
    assert sent["data"]["size"] == "5"

    fail = _FakeUploadClient({"code": 1001, "msg": "no perm"})
    monkeypatch.setattr(bitable_mod.httpx, "AsyncClient", lambda **kw: fail)
    with pytest.raises(RuntimeError) as exc_info:
        await client.upload_media("x.pdf", b"1", "application/pdf")
    assert "1001" in str(exc_info.value)

    empty = _FakeUploadClient({"code": 0, "data": {}})
    monkeypatch.setattr(bitable_mod.httpx, "AsyncClient", lambda **kw: empty)
    with pytest.raises(RuntimeError, match="no file_token"):
        await client.upload_media("x.pdf", b"1", "application/pdf")


def test_coerce_write_value_attachment_passthrough() -> None:
    """附件字段按 [{file_token}] 直通写入；空/坏形态跳过该字段。"""
    meta = {"ui_type": "Attachment"}
    skip = crud.feishu_sync_service.SKIP_REMOTE_FIELD
    ok = crud._coerce_write_value(
        meta, [{"file_token": "ft1", "name": "a.png", "url": "http://x"}]
    )
    assert ok == [{"file_token": "ft1"}]
    assert crud._coerce_write_value(meta, []) is skip
    assert crud._coerce_write_value(meta, "http://raw-url") is skip
    assert crud._coerce_write_value(meta, None) is skip


def test_coerce_write_value_autonumber_still_skipped() -> None:
    meta = {"ui_type": "AutoNumber"}
    assert (
        crud._coerce_write_value(meta, "1")
        is crud.feishu_sync_service.SKIP_REMOTE_FIELD
    )
