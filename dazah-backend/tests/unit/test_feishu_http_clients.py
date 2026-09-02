"""HTTP authentication, OAuth, and WebSocket lifecycle failure tests."""

from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest

from app.platform.integrations.feishu import auth, client, oauth, ws_client

SimpleNamespace: Any = _SimpleNamespace


class _HttpContext:
    def __init__(self: Any, http_client: Any) -> None:
        self.http_client = http_client

    async def __aenter__(self: Any) -> Any:
        return self.http_client

    async def __aexit__(self: Any, *_args: Any) -> Any:
        return False


@pytest.fixture(autouse=True)
def reset_feishu_auth_cache() -> Any:
    auth.FeishuAuth._token = None
    auth.FeishuAuth._expire_at = 0
    auth.FeishuAuth._token_cache.clear()
    yield
    auth.FeishuAuth._token = None
    auth.FeishuAuth._expire_at = 0
    auth.FeishuAuth._token_cache.clear()


@pytest.mark.asyncio
async def test_auth_rejects_missing_credentials(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        auth,
        "_settings",
        SimpleNamespace(FEISHU_APP_ID="", FEISHU_APP_SECRET=""),
    )
    with pytest.raises(RuntimeError, match="not configured"):
        await auth.FeishuAuth.get_tenant_access_token()


@pytest.mark.asyncio
async def test_auth_uses_default_and_explicit_caches(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        auth,
        "_settings",
        SimpleNamespace(FEISHU_APP_ID="default", FEISHU_APP_SECRET="secret"),
    )
    monkeypatch.setattr(auth.time, "time", lambda: 100.0)  # type: ignore[attr-defined]
    auth.FeishuAuth._token = "default-token"
    auth.FeishuAuth._expire_at = 1000.0
    assert await auth.FeishuAuth.default().get_token() == "default-token"

    auth.FeishuAuth._token_cache[("custom", "secret")] = (
        "custom-token",
        1000.0,
    )
    assert (
        await auth.FeishuAuth.get_tenant_access_token(
            "custom",
            "secret",
        )
        == "custom-token"
    )


@pytest.mark.asyncio
async def test_auth_fetches_and_rejects_api_errors(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        auth,
        "_settings",
        SimpleNamespace(FEISHU_APP_ID="default", FEISHU_APP_SECRET="secret"),
    )
    response: Any = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "code": 0,
            "tenant_access_token": "fresh",
            "expire": 7200,
        },
    )
    http_client: Any = SimpleNamespace(post=AsyncMock(return_value=response))
    monkeypatch.setattr(
        auth.httpx,  # type: ignore[attr-defined]
        "AsyncClient",
        lambda **_kwargs: _HttpContext(http_client),
    )
    assert await auth.FeishuAuth.get_tenant_access_token() == "fresh"
    assert auth.FeishuAuth._token == "fresh"

    auth.FeishuAuth._token = None
    auth.FeishuAuth._token_cache.clear()
    response.json = lambda: {"code": 1, "msg": "denied"}
    with pytest.raises(RuntimeError, match="auth failed"):
        await auth.FeishuAuth.get_tenant_access_token()


@pytest.mark.asyncio
async def test_feishu_client_health_and_request_outcomes(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        auth.FeishuAuth,
        "get_tenant_access_token",
        AsyncMock(return_value="1234567890token"),
    )
    api = client.FeishuClient(app_id="app", app_secret="secret")
    assert await api.health_check() == {
        "status": "ok",
        "token_prefix": "1234567890...",
    }

    auth.FeishuAuth.get_tenant_access_token.side_effect = RuntimeError("down")  # type: ignore[attr-defined]
    assert (await api.health_check())["status"] == "error"
    auth.FeishuAuth.get_tenant_access_token.side_effect = None  # type: ignore[attr-defined]

    response: Any = SimpleNamespace(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: {"code": 0, "data": {"items": [1]}},
    )
    http_client: Any = SimpleNamespace(request=AsyncMock(return_value=response))
    monkeypatch.setattr(
        client.httpx,  # type: ignore[attr-defined]
        "AsyncClient",
        lambda **_kwargs: _HttpContext(http_client),
    )
    assert await api.request("GET", "/path") == {"items": [1]}
    response.json = lambda: {"code": 1, "msg": "rejected"}
    with pytest.raises(RuntimeError, match="Feishu API error"):
        await api.request("POST", "/path", json={"value": 1})


def test_oauth_normalization_and_authorize_url() -> None:
    assert oauth._normalize_oauth_token_response(
        {"code": 0, "data": {"access_token": "token"}}
    ) == {"access_token": "token"}
    assert oauth._normalize_oauth_token_response({"access_token": "flat"}) == {
        "access_token": "flat"
    }
    with pytest.raises(oauth.OAuthError, match="request failed"):
        oauth._normalize_oauth_token_response(
            {"code": 1, "error": "invalid", "error_description": "bad code"}
        )

    api = oauth.FeishuOAuthClient("app", "secret", "https://callback", "scope")
    query = parse_qs(urlparse(api.build_authorize_url("state")).query)
    assert query["client_id"] == ["app"]
    assert query["state"] == ["state"]


@pytest.mark.asyncio
async def test_oauth_token_refresh_and_user_info(monkeypatch: Any) -> None:
    responses = [
        SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"code": 0, "data": {"access_token": "one"}},
        ),
        SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"code": 0, "access_token": "two"},
        ),
        SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"code": 0, "data": {"open_id": "open"}},
        ),
        SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"code": 1, "msg": "denied"},
        ),
    ]
    http_client: Any = SimpleNamespace(
        post=AsyncMock(side_effect=responses[:2]),
        get=AsyncMock(side_effect=responses[2:]),
    )
    monkeypatch.setattr(
        oauth.httpx,  # type: ignore[attr-defined]
        "AsyncClient",
        lambda **_kwargs: _HttpContext(http_client),
    )
    api = oauth.FeishuOAuthClient("app", "secret", "https://callback", "scope")
    assert (await api.exchange_code("code"))["access_token"] == "one"
    assert (await api.refresh_access_token("refresh"))["access_token"] == "two"
    assert (await api.get_user_info("token"))["open_id"] == "open"
    with pytest.raises(oauth.OAuthError, match="get_user_info failed"):
        await api.get_user_info("token")


def test_ws_lifecycle_skips_missing_credentials_and_stops(monkeypatch: Any) -> None:
    ws_client._stop_flags.clear()
    ws_client._ws_threads.clear()
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(FEISHU_APP_ID="", FEISHU_APP_SECRET=""),
    )
    ws_client.start_ws_client(name="missing")
    assert "missing" not in ws_client._ws_threads

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(FEISHU_APP_ID="app", FEISHU_APP_SECRET="secret"),
    )
    thread: Any = Mock()
    monkeypatch.setattr(ws_client.threading, "Thread", Mock(return_value=thread))  # type: ignore[attr-defined]
    ws_client.start_ws_client(name="running")
    thread.start.assert_called_once()
    flag = ws_client._stop_flags["running"]
    ws_client.stop_ws_client("running")
    assert flag.is_set()

    first = ws_client.threading.Event()  # type: ignore[attr-defined]
    second = ws_client.threading.Event()  # type: ignore[attr-defined]
    ws_client._stop_flags.update({"one": first, "two": second})
    ws_client._ws_threads.update({"one": thread, "two": thread})
    ws_client.stop_ws_client()
    assert first.is_set() and second.is_set()
    assert ws_client._stop_flags == {}


def test_ws_thread_contains_sdk_start_failure(monkeypatch: Any) -> None:
    import lark_oapi.ws as lark_ws  # type: ignore[import-untyped]

    loop: Any = Mock()
    monkeypatch.setattr(ws_client.asyncio, "new_event_loop", Mock(return_value=loop))  # type: ignore[attr-defined]
    monkeypatch.setattr(ws_client.asyncio, "set_event_loop", Mock())  # type: ignore[attr-defined]
    sdk_client: Any = Mock()
    sdk_client.start.side_effect = RuntimeError("connection failed")
    monkeypatch.setattr(lark_ws, "Client", Mock(return_value=sdk_client))

    ws_client._run_ws_in_thread(
        "app",
        "secret",
        object(),
        "test-ws",
        ws_client.threading.Event(),  # type: ignore[attr-defined]
    )
    sdk_client.start.assert_called_once()
    loop.close.assert_called_once()
