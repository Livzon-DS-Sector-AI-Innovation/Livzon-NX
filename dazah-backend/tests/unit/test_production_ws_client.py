"""生产计划飞书 WebSocket 启动逻辑测试（多 Base 订阅/去重）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.production import ws_client as production_ws


class _FakeSession:
    """只支撑 start_ws_from_db 用到的 execute / async-context 协议。"""

    def __init__(self, configs: list) -> None:
        self._configs = configs

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, stmt: object) -> MagicMock:
        result = MagicMock()
        result.scalars.return_value.all.return_value = self._configs
        return result


def _config(name: str, token: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        product_name=name,
        name=name,
        bitable_app_token=token,
        app_id="cli_test",
        encrypted_app_secret=None,
    )


async def test_start_ws_subscribes_all_config_bases(monkeypatch) -> None:
    """WS 订阅全部启用配置的 Base 并按 token 去重，不再只取第一个配置。"""
    configs = [
        _config("生产计划", "tok-a"),
        _config("产销计划", "tok-b"),
        _config("FL批次", "tok-a"),  # 与生产计划同 Base，应去重
    ]
    monkeypatch.setattr(
        production_ws, "async_session_factory", lambda: _FakeSession(configs)
    )
    captured: dict[str, object] = {}

    async def fake_restart(
        app_id: str, app_secret: str, app_tokens: dict[str, str]
    ) -> dict[str, object]:
        captured["app_id"] = app_id
        captured["app_tokens"] = app_tokens
        return {"connected": True}

    monkeypatch.setattr(production_ws, "restart_ws_with_config", fake_restart)

    status = await production_ws.start_ws_from_db()

    assert status == {"connected": True}
    assert captured["app_id"] == "cli_test"
    assert captured["app_tokens"] == {"生产计划": "tok-a", "产销计划": "tok-b"}


async def test_start_ws_without_configs_stops_channel(monkeypatch) -> None:
    """无启用配置时停止通道并记录错误，不触发重启。"""
    monkeypatch.setattr(
        production_ws, "async_session_factory", lambda: _FakeSession([])
    )
    stopped: list[bool] = []

    async def fake_stop() -> None:
        stopped.append(True)

    async def fail_restart(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("无配置时不应重启 WS")

    monkeypatch.setattr(production_ws, "stop_ws", fake_stop)
    monkeypatch.setattr(production_ws, "restart_ws_with_config", fail_restart)

    status = await production_ws.start_ws_from_db()

    assert stopped == [True]
    assert status["last_error"] == "未启用生产飞书配置"
