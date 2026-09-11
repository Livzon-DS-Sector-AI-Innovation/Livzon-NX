"""成品异常报告（finished-product-anomaly）路由的 AsyncClient 集成测试（真实路由栈）。

覆盖：非法年份 400、年度参数 → 实体路由、未配置飞书时列表返回
table_configured=False、成功路径（mock BitableClient）、附件代理下载、
分享链接、单条详情。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


class _FakeEntity:
    app_token = "app_token_anomaly"
    table_id = "tbl_anomaly_2026"
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
            {"field_name": "不合格项目描述", "ui_type": "Text"},
            {"field_name": "相关照片", "ui_type": "Attachment"},
        ]

    async def create_record(
        self, table_id: str, fields: dict, *, user_id_type: str | None = None
    ) -> dict:
        self.created.append(fields)
        return {"record_id": "rec_new"}

    async def update_record(
        self,
        table_id: str,
        record_id: str,
        fields: dict,
        *,
        user_id_type: str | None = None,
    ) -> dict:
        return {"record_id": record_id}

    async def delete_record(self, table_id: str, record_id: str) -> dict:
        return {}

    async def get_record(
        self, table_id: str, record_id: str, *, user_id_type: str = "open_id"
    ) -> dict | None:
        return {
            "record_id": record_id,
            "fields": {
                "不合格项目描述": "某批次含量测定超标",
                "相关照片": [
                    {
                        "file_token": "ft_1",
                        "name": "photo.jpeg",
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
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records?year=2030"
    )
    assert resp.status_code == 400
    assert "不支持的成品异常报告年份" in resp.json().get("message", "")


@pytest.mark.anyio
async def test_years_report_configuration_status(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as api_mod

    async def _reference(db, entity_code: str):
        if entity_code == "finished_product_anomaly_2026":
            return {"app_token": "tok_2026", "table_id": "tbl_2026"}
        return None

    monkeypatch.setattr(api_mod, "get_bitable_entity_reference", _reference)
    resp = await client.get("/api/v1/quality/finished-product-anomaly/years")
    assert resp.status_code == 200
    years = resp.json()["data"]["years"]
    assert [item["year"] for item in years] == [2025, 2026, 2027, 2028]
    by_year = {item["year"]: item for item in years}
    assert by_year[2025]["entity_code"] == "finished_product_anomaly_2025"
    assert by_year[2026]["table_configured"] is True
    assert (
        by_year[2026]["feishu_url"]
        == "https://www.feishu.cn/base/tok_2026?table=tbl_2026"
    )
    assert by_year[2027]["table_configured"] is False
    assert by_year[2027]["feishu_url"] is None


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
                    "fields": {"不合格项目描述": "含量测定超标"},
                }
            ]
        ),
    )
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records?year=2026"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["table_configured"] is True
    assert data["total"] == 1
    assert data["items"][0]["不合格项目描述"] == "含量测定超标"

    # 字段元数据：附件只读、文本可编辑
    resp = await client.get("/api/v1/quality/finished-product-anomaly/fields?year=2026")
    assert resp.status_code == 200
    fields = {f["field_name"]: f for f in resp.json()["data"]["fields"]}
    assert fields["不合格项目描述"]["editable"] is True
    assert fields["相关照片"]["editable"] is False


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
        "/api/v1/quality/finished-product-anomaly/records?year=2026",
        json={"fields": {"不合格项目描述": "2026新增异常"}},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["record_id"] == "rec_new"

    resp = await client.put(
        "/api/v1/quality/finished-product-anomaly/records/rec-1?year=2026",
        json={"fields": {"不合格项目描述": "2026编辑异常"}},
    )
    assert resp.status_code == 200

    resp = await client.delete(
        "/api/v1/quality/finished-product-anomaly/records/rec-1?year=2026"
    )
    assert resp.status_code == 200
    assert seen_entities == ["finished_product_anomaly_2026"] * 3


@pytest.mark.anyio
async def test_unconfigured_year_records_reports_flag(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as api_mod

    async def _reference(db, entity_code: str):
        return None

    monkeypatch.setattr(api_mod, "get_bitable_entity_reference", _reference)
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records?year=2027"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["table_configured"] is False
    assert data["items"] == []


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
        "/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft_1/content?year=2026"
    )
    assert resp.status_code == 200
    assert resp.content == b"IMAGEBYTES"


class _PdfDownloadHttpxClient:
    """伪造飞书附件下载：返回带 pdf 名义类型的响应。"""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, headers=None, **kwargs):
        response = AsyncMock()
        response.content = b"%PDF-bytes"
        response.headers = {"content-type": "application/octet-stream"}
        response.status_code = 200
        response.raise_for_status = lambda: None
        return response


def _patch_record_with_file(monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
    """让 get_record 返回含指定文件名的附件记录，下载走假 httpx。"""
    import app.modules.quality.service.inspection_feishu_crud as svc

    class _FileBitable(_FakeBitable):
        async def get_record(
        self, table_id: str, record_id: str, *, user_id_type: str = "open_id"
    ) -> dict | None:
            return {
                "record_id": record_id,
                "fields": {
                    "调查结果说明": [
                        {
                            "file_token": "ft_doc",
                            "name": filename,
                            "url": "https://open.feishu.cn/file/ft_doc",
                            "size": 10,
                        }
                    ],
                },
            }

    _patch_success(monkeypatch)
    monkeypatch.setattr(svc, "BitableClient", _FileBitable)
    monkeypatch.setattr(svc.httpx, "AsyncClient", _PdfDownloadHttpxClient)


@pytest.mark.anyio
async def test_attachment_preview_pdf_passthrough_inline(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_record_with_file(monkeypatch, "说明.pdf")
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft_doc/preview?year=2026"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.content == b"%PDF-bytes"


@pytest.mark.anyio
async def test_attachment_preview_office_converted_to_pdf(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.service.feishu_attachment_preview as preview_mod

    _patch_record_with_file(monkeypatch, "调查报告.docx")
    monkeypatch.setattr(
        preview_mod, "convert_office_to_pdf", lambda content, name: b"%PDF-converted"
    )
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft_doc/preview?year=2026"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content == b"%PDF-converted"
    from urllib.parse import quote

    assert quote("调查报告.pdf") in resp.headers["content-disposition"]


@pytest.mark.anyio
async def test_attachment_preview_office_convert_failure_returns_502(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.service.feishu_attachment_preview as preview_mod

    _patch_record_with_file(monkeypatch, "调查报告.wps")
    monkeypatch.setattr(preview_mod, "convert_office_to_pdf", lambda content, name: b"")
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft_doc/preview?year=2026"
    )
    assert resp.status_code == 502
    assert "转换失败" in resp.json().get("message", "")


@pytest.mark.anyio
async def test_attachment_preview_unsupported_extension_returns_400(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_record_with_file(monkeypatch, "打包资料.zip")
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft_doc/preview?year=2026"
    )
    assert resp.status_code == 400
    assert "不支持在线预览" in resp.json().get("message", "")


@pytest.mark.anyio
async def test_attachment_preview_missing_file_token_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_record_with_file(monkeypatch, "说明.pdf")
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft_absent/preview?year=2026"
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_batch_share_links_endpoint_returns_mapping(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as api_mod

    async def _links(db, entity_code: str, record_ids: list[str]):
        return {
            rid: f"https://j0eukrlohu.feishu.cn/record/{rid}-tok"
            for rid in record_ids
        }

    monkeypatch.setattr(api_mod, "batch_create_record_share_links", _links)
    resp = await client.post(
        "/api/v1/quality/finished-product-anomaly/records/share-links?year=2026",
        json={"fields": {"record_ids": ["rec-1", "rec-2"]}},
    )
    assert resp.status_code == 200
    links = resp.json()["data"]["record_share_links"]
    assert links["rec-1"].endswith("rec-1-tok")
    assert links["rec-2"].endswith("rec-2-tok")


@pytest.mark.anyio
async def test_api_get_anomaly_record_detail(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as api_mod

    monkeypatch.setattr(
        api_mod,
        "get_inspection_feishu_record",
        AsyncMock(return_value={"record_id": "rec-1", "不合格项目描述": "含量超标"}),
    )
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records/rec-1?year=2026"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["record_id"] == "rec-1"
    assert data["不合格项目描述"] == "含量超标"


@pytest.mark.anyio
async def test_record_detail_missing_maps_to_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """飞书 1254043（记录不存在/已删除）应映射为 404 而非 500。"""
    import app.modules.quality.service.inspection_feishu_crud as svc

    class _MissingBitable(_FakeBitable):
        async def get_record(
        self, table_id: str, record_id: str, *, user_id_type: str = "open_id"
    ) -> dict | None:
            raise RuntimeError(
                "Feishu API error: code=1254043, msg=RecordIdNotFound"
            )

    _patch_success(monkeypatch)
    monkeypatch.setattr(svc, "BitableClient", _MissingBitable)
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records/rec-gone?year=2026"
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_dashboard_endpoint_returns_aggregation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as api_mod

    async def _agg(db, year):
        return {
            "years": [year] if year else [2025, 2026],
            "total": 486,
            "analyzed": 400,
            "unclassified": 86,
            "ai_configured": True,
            "last_analyzed_at": None,
            "products": [],
            "type_totals": [],
        }

    monkeypatch.setattr(api_mod, "get_dashboard_aggregation", _agg)
    resp = await client.get("/api/v1/quality/finished-product-anomaly/dashboard")
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 486
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/dashboard?year=2025"
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["years"] == [2025]
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/dashboard?year=2030"
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_analysis_run_submits_background_job(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as api_mod

    submit_mock = AsyncMock(return_value="job:fp-anomaly-analysis:u1")
    monkeypatch.setattr(api_mod, "is_job_running", AsyncMock(return_value=False))
    monkeypatch.setattr(api_mod, "submit_job", submit_mock)
    resp = await client.post("/api/v1/quality/finished-product-anomaly/analysis/run")
    assert resp.status_code == 202
    assert resp.json()["data"]["job_id"] == "job:fp-anomaly-analysis:u1"
    assert resp.json()["data"]["years"] == [2025, 2026, 2027, 2028]
    submit_mock.assert_awaited_once()

    # 已有任务在跑 → 409
    monkeypatch.setattr(api_mod, "is_job_running", AsyncMock(return_value=True))
    resp = await client.post("/api/v1/quality/finished-product-anomaly/analysis/run")
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_analysis_status_endpoint(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as api_mod

    monkeypatch.setattr(
        api_mod,
        "get_job_status",
        AsyncMock(
            return_value={"state": "running", "progress": "2025 年分类进度 30/274"}
        ),
    )
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/analysis/status?job_id=job:x"
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["state"] == "running"

    monkeypatch.setattr(api_mod, "get_job_status", AsyncMock(return_value=None))
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/analysis/status?job_id=job:x"
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_analysis_export_returns_attachment_json(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as api_mod

    async def _export(db):
        return {
            "entity_type": "fp_anomaly_classification",
            "exported_at": "2026-09-09T00:00:00+00:00",
            "count": 1,
            "rows": [
                {"year": 2026, "record_id": "rec-1", "content_hash": "h",
                 {
                     "product": "霉酚酸",
                     "anomaly_type": "杂质异常",
                     "reason": "RRT",
                     "model_name": "q"
                 }
            ],
        }

    monkeypatch.setattr(api_mod, "export_classifications", _export)
    resp = await client.get("/api/v1/quality/finished-product-anomaly/analysis/export")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.json()["count"] == 1


@pytest.mark.anyio
async def test_analysis_import_validates_and_reports_counts(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as api_mod

    imported: list = []

    async def _import(db, rows):
        imported.append(rows)
        return {"imported": len(rows), "skipped": 0}

    monkeypatch.setattr(api_mod, "import_classifications_from_rows", _import)
    resp = await client.post(
        "/api/v1/quality/finished-product-anomaly/analysis/import",
        json={
            "entity_type": "fp_anomaly_classification",
            "rows": [{"year": 2026, "record_id": "rec-1", "anomaly_type": "杂质异常"}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["imported"] == 1

    resp = await client.post(
        "/api/v1/quality/finished-product-anomaly/analysis/import",
        json={"entity_type": "unknown_type", "rows": []},
    )
    assert resp.status_code == 400
