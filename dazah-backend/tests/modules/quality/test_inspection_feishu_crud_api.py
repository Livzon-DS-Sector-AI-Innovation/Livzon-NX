"""检验飞书通用 CRUD 路由的 AsyncClient 集成测试（真实路由栈）。

覆盖：非法实体 400、未配置飞书全路由 4xx+中文消息、只读权限 403、
mock BitableClient 成功路径（断言审计调用）、附件代理下载多策略。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


class _FakeEntity:
    app_token = "app_token_1"
    table_id = "tbl_insp"
    enable_push_to_feishu = True
    enable_pull_from_feishu = True
    field_mappings = {}


class _FakeRuntime:
    app_id = "cli_1"
    app_secret = "secret_1"
    is_enabled = lambda self: True  # noqa: E731


class _FakeBitable:
    def __init__(self, *args, **kwargs) -> None:
        self.created = []

    async def list_fields(self, table_id: str) -> list[dict]:
        return [
            {"field_name": "批号", "ui_type": "Text"},
            {"field_name": "含量", "ui_type": "Number"},
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
            "fields": {"批号": "B-1", "含量": 99.5},
        }


def _patch_feishu_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """让未配置飞书的场景返回明确 400（默认 dev 环境未启用）。"""
    import app.modules.quality.service.inspection_feishu_crud as svc
    from app.core.exceptions import AppException

    async def _raise(db, entity_code: str, *, direction: str):
        raise AppException(
            message=f"{entity_code} 飞书 Base 未启用", status_code=400
        )

    monkeypatch.setattr(svc, "_resolve_runtime_entity", _raise)


def _patch_feishu_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.quality.service.inspection_feishu_crud as svc
    from app.platform.integrations.feishu.auth import FeishuAuth

    async def _resolve(db, entity_code: str, *, direction: str):
        return _FakeRuntime(), _FakeEntity()

    monkeypatch.setattr(svc, "_resolve_runtime_entity", _resolve)
    monkeypatch.setattr(svc, "BitableClient", _FakeBitable)
    monkeypatch.setattr(
        FeishuAuth, "get_tenant_access_token", AsyncMock(return_value="token-x")
    )


# ─── 非法实体 / 未配置飞书 4xx ────────────────────────────────────


@pytest.mark.anyio
async def test_unknown_entity_returns_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/quality/inspection/feishu/not_real/records",
        json={"fields": {"批号": "B-1"}},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "不支持的检验实体" in body.get("message", "")


@pytest.mark.anyio
async def test_unconfigured_feishu_returns_400_with_message(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_feishu_enabled(monkeypatch)
    checks = [
        ("GET", "/api/v1/quality/inspection/feishu/qc_items_inventory/fields", None),
        (
            "POST",
            "/api/v1/quality/inspection/feishu/qc_items_inventory/records",
            {"fields": {"批号": "B-1"}},
        ),
        (
            "PUT",
            "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1",
            {"fields": {"批号": "B-2"}},
        ),
        (
            "DELETE",
            "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1",
            None,
        ),
        (
            "GET",
            "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1/attachments/ft/content",
            None,
        ),
    ]
    for method, url, payload in checks:
        resp = await client.request(method, url, json=payload)
        assert resp.status_code == 400, f"{method} {url} -> {resp.status_code}"
        assert "飞书 Base 未启用" in resp.json().get("message", "")

    # pull 端点未配置时优雅降级（200 + 0），不报错
    pull = await client.post(
        "/api/v1/quality/inspection/feishu/qc_items_inventory/pull"
    )
    assert pull.status_code == 200
    assert pull.json()["data"] == {"synced": 0, "failed": 0}


# ─── 只读权限 403 ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_readonly_permission_forbidden_on_write(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.quality.api import deps as quality_deps

    async def _readonly(db, user_id):
        return ["quality:read"]

    _patch_feishu_success(monkeypatch)
    monkeypatch.setattr(quality_deps, "resolve_user_permissions", _readonly)

    for method, url in [
        ("PUT", "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1"),
        (
            "DELETE",
            "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1",
        ),
    ]:
        resp = await client.request(method, url, json={"fields": {"批号": "B-2"}})
        assert resp.status_code == 403, f"{method} -> {resp.status_code}"


# ─── 成功路径（mock Bitable + 审计断言） ──────────────────────────


@pytest.mark.anyio
async def test_create_record_success_and_audit(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.service.inspection_feishu_crud as svc

    _patch_feishu_success(monkeypatch)
    audit = AsyncMock()
    monkeypatch.setattr(svc, "record_audit_log", audit)

    resp = await client.post(
        "/api/v1/quality/inspection/feishu/qc_items_inventory/records",
        json={"fields": {"批号": "B-1", "含量": 99.5}},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["record_id"] == "rec_new"
    audit.assert_awaited_once()
    call_kwargs = audit.call_args.kwargs
    assert call_kwargs["action"] == "feishu_record_created"
    assert "qc_items_inventory" in call_kwargs["resource_type"]
