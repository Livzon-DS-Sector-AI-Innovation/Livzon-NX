"""QC验证（validation-qc）路由的 AsyncClient 集成测试（真实路由栈）。

覆盖：非法年份 400、年度参数 → 实体路由、未配置飞书时列表返回
table_configured=False、成功路径（mock BitableClient）、附件代理下载。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


class _FakeEntity:
    app_token = "app_token_qc"
    table_id = "tbl_qc_2026"
    enable_push_to_feishu = True
    enable_pull_from_feishu = True
    field_mappings = {}


class _FakeRuntime:
    app_id = "cli_1"
    app_secret = "secret_1"

    def is_enabled(self) -> bool:
        return True


class _FakeBitable:
    def __init__(self, *args, **kwargs) -> None:
        self.created: list[dict] = []

    async def list_fields(self, table_id: str) -> list[dict]:
        return [
            {"field_name": "方案名称", "ui_type": "Text"},
            {"field_name": "封面照片", "ui_type": "Attachment"},
        ]

    async def create_record(self, table_id: str, fields: dict) -> dict:
        self.created.append(fields)
        return {"record_id": "rec_new"}

    async def update_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        return {"record_id": record_id}

    async def delete_record(self, table_id: str, record_id: str) -> dict:
        return {}

    async def get_record(self, table_id: str, record_id: str) -> dict | None:
        return {
            "record_id": record_id,
            "fields": {
                "方案名称": "生化培养箱再确认方案",
                "封面照片": [
                    {
                        "file_token": "ft_1",
                        "name": "cover.jpeg",
                        "url": "https://open.feishu.cn/file/ft_1",
                        "size": 10,
                    }
                ],
            },
        }


def _patch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.quality.service.inspection_feishu_crud as svc
    from app.platform.integrations.feishu.auth import FeishuAuth

    async def _resolve(db, entity_code: str, *, direction: str):
        return _FakeRuntime(), _FakeEntity()

    monkeypatch.setattr(svc, "_resolve_runtime_entity", _resolve)
    monkeypatch.setattr(svc, "BitableClient", _FakeBitable)
    monkeypatch.setattr(
        FeishuAuth, "get_tenant_access_token", AsyncMock(return_value="token-x")
    )


@pytest.mark.anyio
async def test_invalid_year_returns_400(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/quality/validation-qc/records?year=2030")
    assert resp.status_code == 400
    assert "不支持的QC验证年份" in resp.json().get("message", "")


@pytest.mark.anyio
async def test_years_report_configuration_status(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.service.inspection_feishu_crud as svc

    async def _configured(db, entity_code: str) -> bool:
        return entity_code == "validation_qc_2026"

    monkeypatch.setattr(svc, "get_bitable_entity_configured", _configured)
    resp = await client.get("/api/v1/quality/validation-qc/years")
    assert resp.status_code == 200
    years = resp.json()["data"]["years"]
    assert [item["year"] for item in years] == [2024, 2025, 2026, 2027, 2028]
    by_year = {item["year"]: item["table_configured"] for item in years}
    assert by_year[2026] is True
    assert by_year[2025] is False


@pytest.mark.anyio
async def test_records_list_success_with_mapped_fields(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.service.inspection_feishu_crud as svc

    _patch_success(monkeypatch)
    monkeypatch.setattr(
        svc,
        "_search_entity_records",
        AsyncMock(
            return_value=[
                {
                    "record_id": "rec-1",
                    "created_time": "2026-08-01T00:00:00+00:00",
                    "fields": {"方案名称": "方法学验证方案"},
                }
            ]
        ),
    )
    resp = await client.get("/api/v1/quality/validation-qc/records?year=2026")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["table_configured"] is True
    assert data["total"] == 1
    assert data["items"][0]["方案名称"] == "方法学验证方案"

    # 字段元数据：附件只读、文本可编辑
    resp = await client.get("/api/v1/quality/validation-qc/fields?year=2026")
    assert resp.status_code == 200
    fields = {f["field_name"]: f for f in resp.json()["data"]["fields"]}
    assert fields["方案名称"]["editable"] is True
    assert fields["封面照片"]["editable"] is False


@pytest.mark.anyio
async def test_create_update_delete_route_to_year_entity(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.service.inspection_feishu_crud as svc

    seen_entities: list[str] = []

    async def _resolve(db, entity_code: str, *, direction: str):
        seen_entities.append(entity_code)
        return _FakeRuntime(), _FakeEntity()

    monkeypatch.setattr(svc, "_resolve_runtime_entity", _resolve)
    monkeypatch.setattr(svc, "BitableClient", _FakeBitable)
    monkeypatch.setattr(svc, "record_audit_log", AsyncMock())

    # 删除链路在 inspection_feishu_crud 内直连 _delete_entity_record，直接打桩
    async def _fake_delete(db, entity_code, record_id, actor_user_id=None):
        seen_entities.append(entity_code)

    monkeypatch.setattr(svc, "_delete_entity_record", _fake_delete)

    resp = await client.post(
        "/api/v1/quality/validation-qc/records?year=2027",
        json={"fields": {"方案名称": "2027新增方案"}},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["record_id"] == "rec_new"

    resp = await client.put(
        "/api/v1/quality/validation-qc/records/rec-1?year=2027",
        json={"fields": {"方案名称": "2027编辑方案"}},
    )
    assert resp.status_code == 200

    resp = await client.delete("/api/v1/quality/validation-qc/records/rec-1?year=2027")
    assert resp.status_code == 200
    assert seen_entities == ["validation_qc_2027"] * 3


@pytest.mark.anyio
async def test_attachment_download_proxied(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.service.inspection_feishu_crud as svc

    class _FakeHttpxResponse:
        content = b"IMAGEBYTES"
        headers = {"content-type": "image/jpeg"}
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class _FakeHttpxClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> bool:
            return False

        async def get(self, url, headers=None, **kwargs):
            return _FakeHttpxResponse()

    _patch_success(monkeypatch)
    monkeypatch.setattr(svc.httpx, "AsyncClient", _FakeHttpxClient)
    resp = await client.get(
        "/api/v1/quality/validation-qc/records/rec-1/attachments/ft_1/content?year=2026"
    )
    assert resp.status_code == 200
    assert resp.content == b"IMAGEBYTES"
