"""行政模块飞书只读镜像 API 测试（AsyncClient 真实调用路由）。"""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administration.models import AdministrationFeishuConfig

API = "/api/v1/administration"


@pytest.fixture
def _encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入测试用 Fernet 密钥：平台加密在非生产无密钥时按设计直通明文。"""
    from cryptography.fernet import Fernet

    from app.core import secrets as secrets_module

    fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr(secrets_module, "_get_fernet", lambda: fernet)


@pytest.fixture
def _mock_feishu_auth(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """只替换飞书 HTTP 调用，保留平台 FeishuAuth 的真实签名与参数校验。

    早期版本用整类替身掩盖了「类方法未传凭证」的调用错误，这里改为
    打桩底层 HTTP，让参数缺失等调用方错误在测试里同样暴露。
    """
    from app.platform.integrations.feishu import auth as feishu_auth_module

    state: dict[str, Any] = {"calls": 0, "ok": True}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            if not state["ok"]:
                return {"code": 10014, "msg": "app secret invalid"}
            return {"code": 0, "tenant_access_token": "t-fake", "expire": 7200}

    class _FakeClient:
        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(self, _url: str, *, json: dict[str, str], **_kw: Any) -> Any:
            state["calls"] += 1
            state["app_id"] = json.get("app_id")
            state["has_secret"] = bool(json.get("app_secret"))
            return _FakeResponse()

    feishu_auth_module.FeishuAuth._token_cache.clear()
    monkeypatch.setattr(feishu_auth_module.httpx, "AsyncClient", _FakeClient)
    yield state
    feishu_auth_module.FeishuAuth._token_cache.clear()


# ---------- 配置读写 ----------


async def test_get_config_returns_default_when_absent(
    client: Any,
    clean_feishu_config: None,
) -> None:
    resp = await client.get(f"{API}/feishu-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["app_id"] == ""
    assert body["data"]["app_secret_configured"] is False


async def test_save_config_first_time_requires_secret(
    client: Any,
    clean_feishu_config: None,
) -> None:
    resp = await client.put(
        f"{API}/feishu-config",
        json={
            "config_name": "行政飞书",
            "app_id": "cli_test_app",
            "app_secret": "",
            "is_active": True,
            "timezone": "Asia/Shanghai",
            "daily_sync_time": "02:00",
        },
    )
    assert resp.status_code == 400
    assert "App Secret" in resp.json()["message"]


async def test_save_config_persists_encrypted_secret(
    client: Any,
    db_session: AsyncSession,
    clean_feishu_config: None,
    _encryption_key: None,
) -> None:
    resp = await client.put(
        f"{API}/feishu-config",
        json={
            "config_name": "行政飞书",
            "app_id": "cli_test_app",
            "app_secret": "super-secret-value",
            "is_active": True,
            "timezone": "Asia/Shanghai",
            "daily_sync_time": "02:00",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["app_id"] == "cli_test_app"
    assert data["app_secret_configured"] is True
    assert data["app_secret_masked"] == "****"
    assert "super-secret-value" not in (data.get("app_secret") or "")

    row = (
        await db_session.execute(
            AdministrationFeishuConfig.__table__.select()
        )
    ).first()
    assert row is not None
    stored = getattr(row, "encrypted_app_secret", None)
    assert stored and stored.startswith("fernet:v1:")
    assert "super-secret-value" not in stored
    from app.core.secrets import decrypt_secret

    assert decrypt_secret(stored) == "super-secret-value"


async def test_save_config_keeps_secret_when_blank_or_masked(
    client: Any,
    db_session: AsyncSession,
    clean_feishu_config: None,
    _encryption_key: None,
) -> None:
    for secret in ("super-secret-value", "", "****"):
        resp = await client.put(
            f"{API}/feishu-config",
            json={
                "config_name": "行政飞书",
                "app_id": "cli_test_app",
                "app_secret": secret,
                "is_active": True,
                "timezone": "Asia/Shanghai",
                "daily_sync_time": "02:00",
            },
        )
        assert resp.status_code == 200
    row = (
        await db_session.execute(AdministrationFeishuConfig.__table__.select())
    ).first()
    stored = getattr(row, "encrypted_app_secret", "")
    from app.core.secrets import decrypt_secret

    assert decrypt_secret(stored) == "super-secret-value"


# ---------- 连通性测试 ----------


async def test_test_connectivity_reports_missing_credentials(
    client: Any,
    clean_feishu_config: None,
    _mock_feishu_auth: dict[str, Any],
) -> None:
    resp = await client.post(f"{API}/feishu-config/test")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ok"] is False
    assert "未配置" in data["steps"][0]["message"]


async def test_test_connectivity_success_and_failure(
    client: Any,
    clean_feishu_config: None,
    _mock_feishu_auth: dict[str, Any],
) -> None:
    save = await client.put(
        f"{API}/feishu-config",
        json={
            "config_name": "行政飞书",
            "app_id": "cli_test_app",
            "app_secret": "s3cret",
            "is_active": True,
            "timezone": "Asia/Shanghai",
            "daily_sync_time": "02:00",
        },
    )
    assert save.status_code == 200

    resp = await client.post(f"{API}/feishu-config/test")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ok"] is True
    assert data["steps"][0]["status"] == "ok"
    assert _mock_feishu_auth["calls"] == 1
    # 回归：保存的凭证必须真正传给飞书认证（曾因类方法未传参而永远"未配置"）
    assert _mock_feishu_auth["app_id"] == "cli_test_app"
    assert _mock_feishu_auth["has_secret"] is True

    from app.platform.integrations.feishu.auth import FeishuAuth

    FeishuAuth._token_cache.clear()
    _mock_feishu_auth["ok"] = False
    resp = await client.post(f"{API}/feishu-config/test")
    data = resp.json()["data"]
    assert data["ok"] is False
    assert data["steps"][0]["status"] == "error"
    assert "s3cret" not in resp.text


# ---------- 飞书上游失败 → 502 ----------


@pytest.fixture
def _failing_mirror_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """镜像服务替换为「飞书调用必失败」的假服务，验证端点的异常映射。"""
    from app.modules.administration import feishu_read_api

    class _FailingService:
        async def discover_root(self, _root_id: Any) -> list[Any]:
            raise RuntimeError("飞书请求重试次数已耗尽")

        async def sync_resource(self, _resource_id: Any) -> dict[str, Any]:
            raise RuntimeError("飞书请求重试次数已耗尽")

    async def _fake_build(_session: Any) -> _FailingService:
        return _FailingService()

    monkeypatch.setattr(feishu_read_api, "build_read_mirror_service", _fake_build)


async def test_discover_maps_feishu_failure_to_502(
    client: Any,
    _failing_mirror_service: None,
) -> None:
    root_id = "3d13fca9-4097-4619-9aa8-f0f15a846e07"
    resp = await client.post(f"{API}/feishu-read/roots/{root_id}/discover")
    assert resp.status_code == 502
    assert "飞书接口调用失败" in resp.json()["message"]


async def test_sync_maps_feishu_failure_to_502(
    client: Any,
    _failing_mirror_service: None,
) -> None:
    resource_id = "95ee3ef4-26af-4e2f-b250-aeef18171c0c"
    resp = await client.post(f"{API}/feishu-read/resources/{resource_id}/sync")
    assert resp.status_code == 502
    assert "飞书接口调用失败" in resp.json()["message"]


# ---------- 页面数据与仪表台 ----------


async def test_page_data_unknown_page_key_returns_404(client: Any) -> None:
    resp = await client.get(
        f"{API}/page-data/not-a-page",
        headers={"X-Dazah-Page-Key": "admin:tobacco-gift:items"},
    )
    assert resp.status_code == 404


async def test_page_data_without_credentials_returns_400(client: Any) -> None:
    resp = await client.get(f"{API}/page-data/admin:tobacco-gift:items")
    assert resp.status_code == 400
    assert "飞书设置" in resp.json()["message"]


async def test_page_records_unknown_page_key_returns_404(client: Any) -> None:
    binding_id = "b0000000-0000-0000-0000-000000000000"
    resp = await client.get(
        f"{API}/page-data/other/{binding_id}/records",
        headers={"X-Dazah-Page-Key": "admin:tobacco-gift:items"},
    )
    assert resp.status_code == 404


# ---------- 页面上下文与越权防护 ----------


async def test_settings_page_can_read_page_bindings(client: Any) -> None:
    """设置页维护映射时读取镜像页绑定：必须放行到业务层（400 凭据未配置）。"""
    resp = await client.get(
        f"{API}/page-data/admin:tobacco-gift:items",
        headers={"X-Dazah-Page-Key": "admin:feishu-settings"},
    )
    assert resp.status_code == 400
    assert "飞书设置" in resp.json()["message"]


async def test_records_route_requires_matching_page_context(client: Any) -> None:
    """持有 A 页上下文请求 B 页记录：403，不得落到业务层。"""
    binding_id = "b0000000-0000-0000-0000-000000000000"
    resp = await client.get(
        f"{API}/page-data/admin:tobacco-gift:records/{binding_id}/records",
        headers={"X-Dazah-Page-Key": "admin:tobacco-gift:items"},
    )
    assert resp.status_code == 403
    assert "上下文不一致" in resp.json()["message"]


async def test_records_route_allows_matching_context(client: Any) -> None:
    binding_id = "b0000000-0000-0000-0000-000000000000"
    resp = await client.get(
        f"{API}/page-data/admin:tobacco-gift:records/{binding_id}/records",
        headers={"X-Dazah-Page-Key": "admin:tobacco-gift:records"},
    )
    # 上下文一致才继续走业务链路（此处未配凭据 → 400，而不是 403）
    assert resp.status_code == 400
    assert "飞书设置" in resp.json()["message"]


async def test_items_viewer_cannot_read_records(
    viewer_client: Any,
    clean_feishu_config: None,
) -> None:
    """仅授权物品清单的普通用户：跨页请求记录被页面授权与上下文双重拦截。"""
    binding_id = "b0000000-0000-0000-0000-000000000000"
    resp = await viewer_client.get(
        f"{API}/page-data/admin:tobacco-gift:records/{binding_id}/records",
        headers={"X-Dazah-Page-Key": "admin:tobacco-gift:records"},
    )
    assert resp.status_code == 403


async def test_items_viewer_can_read_own_page(
    viewer_client: Any,
    clean_feishu_config: None,
) -> None:
    """同一端点：已授权的物品清单页放行到业务层（400 凭据未配置，而非 403）。"""
    resp = await viewer_client.get(f"{API}/page-data/admin:tobacco-gift:items")
    assert resp.status_code == 400
    assert "飞书设置" in resp.json()["message"]


async def test_dashboard_stats_zero_before_setup(client: Any) -> None:
    resp = await client.get(f"{API}/tobacco-gift/dashboard-stats")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["item_categories"] == 0
    assert data["requisitioned_total"] == 0.0
    assert data["inventory_by_item"] == []


async def test_module_root_endpoint_registered(client: Any) -> None:
    resp = await client.get(f"{API}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "administration"
