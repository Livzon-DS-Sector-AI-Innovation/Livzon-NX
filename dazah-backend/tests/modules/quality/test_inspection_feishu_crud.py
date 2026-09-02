from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.service import inspection_feishu_crud as service


class _FakeEntity:
    app_token = "app_token_1"
    table_id = "tbl_insp"
    enable_push_to_feishu = True
    enable_pull_from_feishu = True
    field_mappings = {}


class _FakeRuntime:
    app_id = "cli_1"
    app_secret = "secret_1"


class _FakeBitableClientWithRecord:
    def __init__(self, record: dict) -> None:
        self._record = record

    async def get_record(self, table_id: str, record_id: str) -> dict | None:
        return self._record


class _FakeHttpxResponse:
    content = b"PDFBYTES"
    headers = {"content-type": "application/pdf"}
    status_code = 200

    def raise_for_status(self) -> None:
        return None


class _FakeHttpxJsonError:
    content = b'{"code":99991661,"msg":"Missing access token"}'
    headers = {"content-type": "application/json"}
    status_code = 200

    def raise_for_status(self) -> None:
        return None


class _FakeHttpxForbidden:
    content = b""
    headers = {}
    status_code = 403

    def raise_for_status(self) -> None:
        return None


class _FakeHttpxClient:
    def __init__(self, *args, **kwargs) -> None:
        self.called_url = ""
        self.called_headers = {}

    async def __aenter__(self) -> _FakeHttpxClient:
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, headers=None, **kwargs):
        self.called_url = url
        self.called_headers = headers or {}
        return _FakeHttpxResponse()


class _FakeHttpxClientSequence:
    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def __aenter__(self) -> _FakeHttpxClientSequence:
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, headers=None, **kwargs):
        self.calls.append(headers or {})
        resp = self._responses.pop(0)
        return resp


def _field_map() -> dict[str, dict]:
    return {
        "物料名称": {"field_name": "物料名称", "ui_type": "Text"},
        "检测日期": {
            "field_name": "检测日期",
            "ui_type": "DateTime",
            "property": {"date_formatter": "yyyy-MM-dd"},
        },
        "合格": {"field_name": "合格", "ui_type": "Checkbox"},
        "数量": {"field_name": "数量", "ui_type": "Number"},
        "报告链接": {"field_name": "报告链接", "ui_type": "Url"},
        "检验人": {"field_name": "检验人", "ui_type": "User"},
        "附件": {"field_name": "附件", "ui_type": "Attachment"},
        "物料": {"field_name": "物料", "ui_type": "DuplexLink"},
    }


def test_validate_inspection_entity_allows_inspection_and_rejects_others() -> None:
    service.validate_inspection_entity("qc_items_inventory")
    service.validate_inspection_entity("qc_finished_fcc14")
    with pytest.raises(AppException):
        service.validate_inspection_entity("capa_ledger")


def test_coerce_write_fields_coerces_by_ui_type_and_skips_readonly() -> None:
    coerced = service._coerce_write_fields(
        _field_map(),
        {
            "物料名称": "葡萄糖",
            "检测日期": "2026-08-01",
            "合格": "是",
            "数量": "3.5",
            "报告链接": "https://example.com/report",
            "检验人": "ou_user_1",  # User 只读 → 跳过
            "附件": [
                {"name": "a.pdf", "url": "https://x/a.pdf"}
            ],  # Attachment 只读 → 跳过
            "物料": "xxx",  # DuplexLink 只读 → 跳过
        },
    )
    assert coerced["物料名称"] == "葡萄糖"
    assert isinstance(coerced["检测日期"], int)
    assert coerced["合格"] is True
    assert coerced["数量"] == 3.5
    assert coerced["报告链接"] == {
        "link": "https://example.com/report",
        "text": "https://example.com/report",
        "type": "url",
    }
    assert "检验人" not in coerced
    assert "附件" not in coerced
    assert "物料" not in coerced


def test_coerce_write_fields_rejects_unknown_field() -> None:
    with pytest.raises(AppException, match="不存在的字段"):
        service._coerce_write_fields(_field_map(), {"不存在的字段": "x"})


@pytest.mark.anyio
async def test_inspection_feishu_crud_api_routes(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.quality import api as quality_api

    monkeypatch.setattr(
        quality_api.inspection_feishu_crud,
        "get_inspection_entity_fields",
        AsyncMock(
            return_value={
                "fields": [
                    {"field_name": "物料名称", "ui_type": "Text", "editable": True}
                ],
                "can_push": True,
            }
        ),
    )
    create_mock = AsyncMock(return_value={"record_id": "rec_new"})
    monkeypatch.setattr(
        quality_api.inspection_feishu_crud,
        "create_inspection_feishu_record",
        create_mock,
    )
    update_mock = AsyncMock(return_value={"record_id": "rec_1"})
    monkeypatch.setattr(
        quality_api.inspection_feishu_crud,
        "update_inspection_feishu_record",
        update_mock,
    )
    delete_mock = AsyncMock(return_value={"record_id": "rec_1"})
    monkeypatch.setattr(
        quality_api.inspection_feishu_crud,
        "delete_inspection_feishu_record",
        delete_mock,
    )

    fields_resp = await client.get(
        "/api/v1/quality/inspection/feishu/qc_items_inventory/fields"
    )
    assert fields_resp.status_code == 200
    assert fields_resp.json()["data"]["can_push"] is True

    create_resp = await client.post(
        "/api/v1/quality/inspection/feishu/qc_items_inventory/records",
        json={"fields": {"物料名称": "葡萄糖"}},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["data"]["record_id"] == "rec_new"
    create_mock.assert_awaited_once()

    update_resp = await client.put(
        "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1",
        json={"fields": {"物料名称": "蔗糖"}},
    )
    assert update_resp.status_code == 200
    update_mock.assert_awaited_once()

    delete_resp = await client.delete(
        "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1"
    )
    assert delete_resp.status_code == 200
    delete_mock.assert_awaited_once()


# ── 附件代理下载 ──


def test_find_attachment_in_record_locates_by_file_token() -> None:
    record = {
        "record_id": "rec_1",
        "fields": {
            "报告单": [
                {
                    "file_token": "tok_report",
                    "name": "报告.pdf",
                    "url": "https://feishu.cn/x/report",
                },
                {
                    "file_token": "tok_img",
                    "name": "图谱.jpg",
                    "tmp_url": "https://feishu.cn/x/img",
                },
            ]
        },
    }
    found = service._find_attachment_in_record(record, "tok_img")
    assert found is not None
    assert found["name"] == "图谱.jpg"
    assert service._find_attachment_in_record(record, "tok_unknown") is None


@pytest.mark.anyio
async def test_get_attachment_content_downloads_with_token(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = {
        "record_id": "rec_1",
        "fields": {
            "报告单": [
                {
                    "file_token": "tok_report",
                    "name": "报告.pdf",
                    "url": "https://feishu.cn/x/report",
                    "type": "pdf",
                    "size": 10,
                },
                {
                    "file_token": "tok_img",
                    "name": "图谱.jpg",
                    "tmp_url": "https://feishu.cn/x/img",
                },
            ]
        },
    }
    fake_client = _FakeBitableClientWithRecord(record)
    monkeypatch.setattr(service, "BitableClient", lambda **kw: fake_client)
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_FakeRuntime(), _FakeEntity())),
    )
    token_mock = AsyncMock(return_value="app_access_token")
    monkeypatch.setattr(service.FeishuAuth, "get_tenant_access_token", token_mock)
    fake_http = _FakeHttpxClient()
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kw: fake_http)

    (
        content,
        content_type,
        filename,
    ) = await service.get_inspection_feishu_attachment_content(
        db_session, "qc_items_inventory", "rec_1", "tok_report"
    )

    assert content == b"PDFBYTES"
    assert content_type == "application/pdf"
    assert filename == "报告.pdf"
    assert fake_http.called_url == "https://feishu.cn/x/report"
    assert fake_http.called_headers == {"Authorization": "Bearer app_access_token"}
    token_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_download_attachment_bytes_falls_back_to_no_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_http = _FakeHttpxClientSequence([_FakeHttpxJsonError(), _FakeHttpxResponse()])
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kw: fake_http)
    result = await service._download_attachment_bytes(
        "https://feishu.cn/x/report", "app_access_token"
    )
    assert result == (b"PDFBYTES", "application/pdf", "")
    # 第一次带 Authorization 返回 JSON 错误 → 第二次无 Authorization 重试成功
    assert fake_http.calls[0] == {"Authorization": "Bearer app_access_token"}
    assert fake_http.calls[1] == {}


@pytest.mark.anyio
async def test_download_attachment_bytes_reports_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_http = _FakeHttpxClientSequence([_FakeHttpxForbidden(), _FakeHttpxForbidden()])
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kw: fake_http)
    result = await service._download_attachment_bytes(
        "https://feishu.cn/x/report", "app_access_token"
    )
    assert result == (None, "", "forbidden")


@pytest.mark.anyio
async def test_get_attachment_content_rejects_foreign_file_token(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = {
        "record_id": "rec_1",
        "fields": {
            "报告单": [
                {
                    "file_token": "tok_report",
                    "name": "报告.pdf",
                    "url": "https://feishu.cn/x/report",
                }
            ]
        },
    }
    fake_client = _FakeBitableClientWithRecord(record)
    monkeypatch.setattr(service, "BitableClient", lambda **kw: fake_client)
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_FakeRuntime(), _FakeEntity())),
    )
    with pytest.raises(NotFoundException):
        await service.get_inspection_feishu_attachment_content(
            db_session, "qc_items_inventory", "rec_1", "tok_NOT_IN_RECORD"
        )


@pytest.mark.anyio
async def test_inspection_feishu_attachment_content_api(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.quality import api as quality_api

    monkeypatch.setattr(
        quality_api.inspection_feishu_crud,
        "get_inspection_feishu_attachment_content",
        AsyncMock(return_value=(b"PDFBYTES", "application/pdf", "报告.pdf")),
    )
    resp = await client.get(
        "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1/attachments/tok_report/content"
    )
    assert resp.status_code == 200
    assert resp.content == b"PDFBYTES"
    assert "attachment" in resp.headers["content-disposition"]
