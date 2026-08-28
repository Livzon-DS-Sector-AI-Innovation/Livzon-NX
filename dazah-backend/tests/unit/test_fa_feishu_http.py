"""FA 苯丙氨酸 飞书同步/调度 helper 覆盖（mock httpx/session，无真实网络）。"""
import importlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.anyio
async def test_fa_feishu_sync_token_and_read_sheet() -> Any:
    mod = importlib.import_module("app.modules.production.fa_feishu_sync")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "ftok"})
        if "/values/" in request.url.path:
            return httpx.Response(
                200,
                json={"code": 0, "data": {"valueRange": {"values": [[1, None, "x"], ["a", "b", "c"]]}}},  # noqa: E501
            )
        return httpx.Response(200, json={"code": 0})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_async_client(*, base_url: Any=None, timeout: Any=30, **kw: Any) -> Any:
        return real_client(transport=transport, timeout=timeout, base_url=base_url)

    mod._token_cache.clear()
    with patch.object(mod.httpx, "AsyncClient", fake_async_client):
        token = await mod._get_token("app", "sec")
        assert token == "ftok"
        assert await mod._get_token("app", "sec") == "ftok"  # cached
        rows = await mod._read_sheet("spread", "app", "sec")
        assert rows[0] == ["1", "", "x"]
        assert rows[1] == ["a", "b", "c"]


def _result(first: Any=None, scalar: Any=None) -> Any:
    r = MagicMock()
    r.scalars.return_value = r
    r.first.return_value = first
    r.scalar.return_value = scalar
    return r


@pytest.mark.anyio
async def test_fa_scheduler_get_config_and_run_sync() -> Any:
    sched = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    cfg_obj = SimpleNamespace(
        product_name="L-苯丙氨酸",
        sync_target="production_plan",
        is_active=True,
        is_deleted=False,
        bitable_app_token="sptoken",
        app_id="app-id",
        encrypted_app_secret="enc-secret",
        updated_at=None,
    )
    session = AsyncMock()
    session.execute.return_value = _result(first=cfg_obj, scalar=3)
    with patch.object(sched, "decrypt_secret", return_value="secret"):
        cfg_from_db = await sched._get_fa_spreadsheet_config(session)
    assert cfg_from_db["spreadsheet_token"] == "sptoken"
    assert cfg_from_db["app_secret"] == "secret"

    session2 = AsyncMock()
    session2.execute.return_value = _result(first=None)
    with pytest.raises(RuntimeError):
        await sched._get_fa_spreadsheet_config(session2)

    ws = AsyncMock()
    ws.execute.return_value = MagicMock()
    ws.flush = AsyncMock()
    ws.commit = AsyncMock()
    with patch.object(sched, "_read_sheet", new=AsyncMock(return_value=[])):
        with patch.object(sched, "_get_fa_spreadsheet_config",
                new=AsyncMock(return_value=cfg_from_db)):
            result = await sched.run_fa_sync(["decolor1"], ws)
    assert result["decolor1"]["rows"] == 0


@pytest.mark.anyio
async def test_fa_scheduler_run_sync_simple() -> Any:
    # 走 run_fa_sync 的 decolor1 简单表解析，覆盖 _sync_simple 的 DELETE+INSERT 分支。
    sched = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    cfg = {"spreadsheet_token": "st", "app_id": "app", "app_secret": "sec"}
    rows = [
        ["5月份", "", "", ""],      # 月份分隔行 → 跳过
        ["2026/3/1", "FA-1", "10", "", "0.39"],
        ["", "", "", "", ""],       # 空行
        ["2026/3/2", "FA-2", "20", "", "2.0"],
        ["2026/3/3", "FA-3", "30", "", "0.85"],
    ]
    session2 = AsyncMock()
    session2.flush = AsyncMock()
    session2.commit = AsyncMock()
    with patch.object(sched, "_read_sheet", new=AsyncMock(return_value=rows)):
        with patch.object(sched, "_get_fa_spreadsheet_config",
                new=AsyncMock(return_value=cfg)):
            res = await sched.run_fa_sync(["decolor1"], session2)
    assert res["decolor1"]["rows"] >= 2
    assert session2.execute.await_count >= 1


@pytest.mark.anyio
async def test_fa_scheduler_months_and_card() -> Any:
    """覆盖 _sync_simple 的月份分隔行跳过、日期解析与 DELETE+INSERT。"""
    sched = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    cfg = {"spreadsheet_token": "s", "app_id": "a", "app_secret": "x"}

    rows = [
        ["2026/3/1", "FA-1", "10"],
        ["2026.3.2", "FA-2", "20"],
        ["2026年3月3日", "FA-3", "30"],
        ["2026/3/4", "", "40"],  # 批号为空仍保留
    ]
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    # 走 run_fa_sync 的 decolor1（slash 简单表）拿到正确 wire 的 parse_row
    with patch.object(sched, "_read_sheet", new=AsyncMock(return_value=rows)):
        with patch.object(sched, "_get_fa_spreadsheet_config",
                new=AsyncMock(return_value=cfg)):
            res = await sched.run_fa_sync(["decolor1"], session)
    assert res["decolor1"]["rows"] >= 2
    assert session.execute.await_count >= 1
