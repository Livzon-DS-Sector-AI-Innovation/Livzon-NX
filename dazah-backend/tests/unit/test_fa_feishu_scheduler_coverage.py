"""FA 苯丙氨酸 调度/同步 coverage。

覆盖 fa_feishu_scheduler 的 httpx 网络调用（token 缓存/错误分支）、_read_sheet、
全部 _sync_simple 日期格式分支（slash/excel/dot/year_month_day）、
_sync_acidification 数据主路径、run_fa_sync 分派与错误分支，以及 APScheduler
风格的定时任务启停与 scheduled job。全部 mock，无真实网络/DB。
"""
from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _cfg() -> dict[str, Any]:
    return {"spreadsheet_token": "spt", "app_id": "app", "app_secret": "sec"}


def _session() -> AsyncMock:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _config_patch(mod: Any) -> Any:
    """统一 patch run_fa_sync 的数据库配置读取。"""
    return patch.object(
        mod, "_get_fa_spreadsheet_config", AsyncMock(return_value=_cfg())
    )


# ═══════════ _get_token / _read_sheet（httpx.MockTransport） ═══════════


@pytest.mark.anyio
async def test_fa_scheduler_get_token_fetch_cache_and_error() -> Any:
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    mod._token_cache.clear()
    real_client = httpx.AsyncClient
    ok_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"tenant_access_token": "tok-1"})
    )
    err_transport = httpx.MockTransport(lambda req: httpx.Response(500, text="boom"))

    def fake_ok(*, base_url: Any=None, timeout: Any=30, **kw: Any) -> Any:
        return real_client(transport=ok_transport, timeout=timeout, base_url=base_url)

    def fake_err(*, base_url: Any=None, timeout: Any=30, **kw: Any) -> Any:
        return real_client(transport=err_transport, timeout=timeout, base_url=base_url)

    with patch.object(mod.httpx, "AsyncClient", fake_ok):
        assert await mod._get_token("app-1", "s-1") == "tok-1"
    # 命中缓存，不再发 HTTP
    with patch.object(
        mod.httpx, "AsyncClient", new=MagicMock(side_effect=AssertionError("no HTTP"))
    ):
        assert await mod._get_token("app-1", "s-1") == "tok-1"

    mod._token_cache.clear()
    with patch.object(mod.httpx, "AsyncClient", fake_err):
        with pytest.raises(httpx.HTTPStatusError):
            await mod._get_token("app-2", "s-2")


@pytest.mark.anyio
async def test_fa_scheduler_read_sheet_ok() -> Any:
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    mod._token_cache.clear()

    def handler(req: Any) -> Any:
        if req.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "tok-r"})
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": {"valueRange": {"values": [[1, None], ["a", "b"]]}},
            },
        )

    real_client = httpx.AsyncClient

    def fake_client(*, base_url: Any=None, timeout: Any=30, **kw: Any) -> Any:
        return real_client(
            transport=httpx.MockTransport(handler), timeout=timeout, base_url=base_url
        )

    with patch.object(mod.httpx, "AsyncClient", fake_client):
        rows = await mod._read_sheet("sp", "s1", "app-r", "secret-r")
    assert rows == [["1", ""], ["a", "b"]]


@pytest.mark.anyio
async def test_fa_scheduler_sync_fermentation_wrapper() -> Any:
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    session = _session()
    with patch(
        "app.modules.production.fa_feishu_sync.sync_fermentation",
        new=AsyncMock(return_value={"batches": 2, "sub_batches": 1}),
    ) as mocked:
        out = await mod._sync_fermentation(session, _cfg())
    assert out["batches"] == 2
    mocked.assert_awaited_once_with(session, "spt", "app", "sec")


# ═══════════ run_fa_sync 分派 ═══════════


@pytest.mark.anyio
async def test_fa_run_sync_simple_excel_and_year_month_day() -> Any:
    """mvr(excel) 与 mother_liquor(year_month_day) 的解析分支。"""
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")

    # mvr 的 excel 日期：数字日期走 _ed，中文日期走 _pd 更新 cur_date
    mvr_rows = [
        ["", "FA-G0", "", "", "", "", "", "", "", ""],  # FA- 行但无日期 → 非数据行跳过
        ["45356", "", "1", "1", "1", "1", "1", "1", "1", "1"],  # 数字日期
        ["2026年3月5日", "", "2", "2", "2", "2", "2", "2", "2", "2"],  # 中文日期
        ["5月", "", "", "", "", "", "", "", "", ""],  # 月份分隔行跳过
        ["台账合计", "", "", "", "", "", "", "", "", ""],  # 汇总行跳过
    ]
    session1 = _session()
    with _config_patch(mod):
        with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=mvr_rows)):
            res = await mod.run_fa_sync(["mvr"], session1)
    assert res["mvr"]["rows"] >= 2

    # mother_liquor = year_month_day：无 cur_date 时走 _pd(v)
    ml_rows = [
        ["2026年4月2日", "B1", "1", "1", "1", "1", "1"],
        ["", "B2", "1", "1", "1", "1", ""],  # 无日期行沿用
    ]
    session2 = _session()
    with _config_patch(mod):
        with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=ml_rows)):
            res2 = await mod.run_fa_sync(["mother_liquor"], session2)
    assert res2["mother_liquor"]["rows"] >= 1


@pytest.mark.anyio
async def test_fa_run_sync_dot_buffer_and_pending() -> Any:
    """decolor_centrifuge 的 dot 格式：日期前缓冲 FA- 行、日期后 flush、杂项跳过。"""
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    rows = [
        ["FA-BUF1", "", "", "", "", "", "", "", "", "", ""],  # FA- 无日期行 => 缓冲  # noqa: E501
        ["2026.03.06", "FA-A1", "10", "5", "12min30s", "", "", "0.39", "", "", ""],  # noqa: E501 日期行 flush 缓冲 + 当前
        ["", "FA-A2", "", "", "", "", "", "", "", "", ""],  # FA- 已有日期 → 直接解析  # noqa: E501
        ["杂项", "", "", "", "", "", "", "", "", "", ""],  # 非 FA- 非日期 → 跳过  # noqa: E501
    ]
    session = _session()
    with _config_patch(mod):
        with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=rows)):
            res = await mod.run_fa_sync(["decolor_centrifuge"], session)
    assert res["decolor_centrifuge"]["rows"] >= 2


@pytest.mark.anyio
async def test_fa_run_sync_fermentation_acidification_and_error() -> Any:
    """run_fa_sync 分派：fermentation / acidification 成功 + 异常记录 error。"""
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    cfg = _cfg()

    acid_rows = [
        ["", "备注", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # noqa: E501 数据前空行 → 跳过
        [
            "3月5日", "FA-EX1", "10", "98", "980", "500", "4.5", "8.8", "200",
            "5", "100", "200", "500", "1000", "50", "10", "10", "20", "9", "0.95",
            "8", "60", "2", "1", "0.5", "3", "0.3", "0.2", "0.98", "12",
        ],
        ["2026年3月平均值", "1", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # noqa: E501 汇总行 → 跳过
        [
            "3月6日", "FA-EX222", "12", "95", "1140", "400", "4.2", "8.5", "220",
            "5.2", "110", "210", "520", "1200", "60", "12", "12", "22", "10", "0.93",
            "9", "70", "3", "1.2", "0.6", "4", "0.28", "0.22", "0.95", "14",
        ],
        ["3月", ""],  # 月份分隔行
        ["", ""],  # 空行
    ]
    session1 = _session()
    with _config_patch(mod):
        with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=acid_rows)):
            res1 = await mod.run_fa_sync(["acidification"], session1)
    assert res1["acidification"]["rows"] == 2
    assert session1.execute.await_count >= 3  # DELETE + 2 * INSERT

    # fermentation 分派
    with patch(
        "app.modules.production.fa_feishu_sync.sync_fermentation",
        new=AsyncMock(return_value={"batches": 1, "sub_batches": 2}),
    ):
        with _config_patch(mod):
            with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=[])):
                res2 = await mod.run_fa_sync(["fermentation"], session1)
    assert res2["fermentation"]["batches"] == 1

    # 异常 → error 记录，不抛出
    with patch(
        "app.modules.production.fa_feishu_scheduler._sync_fermentation",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with patch.object(
            mod, "_sync_acidification", new=AsyncMock(return_value={"rows": 2})
        ):
            with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=[])):
                with patch.object(
                    mod, "_get_fa_spreadsheet_config", new=AsyncMock(return_value=cfg)
                ):
                    res3 = await mod.run_fa_sync(
                        ["fermentation", "acidification", "decolor1"], session1
                    )
    assert res3["fermentation"]["error"]
    assert res3["acidification"]["rows"] == 2
    assert res3["decolor1"]["rows"] == 0


@pytest.mark.anyio
async def test_fa_run_sync_dot_pending_flush() -> Any:
    """dot 格式：只有 FA- 无日期行 → 全部缓冲，循环结束后以 NULL 日期 flush。"""
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    rows = [
        ["备注P1", "FA-P1", "", "", "", "", "", "", "", "", ""],
        ["备注P2", "FA-P2", "", "", "", "", "", "", "", "", ""],
    ]
    session = _session()
    with _config_patch(mod):
        with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=rows)):
            res = await mod.run_fa_sync(["decolor_centrifuge"], session)
    # 缓冲的无日期行在循环结束后以 NULL 日期生成记录
    assert res["decolor_centrifuge"]["rows"] >= 2


@pytest.mark.anyio
async def test_fa_run_sync_acidification_empty() -> Any:
    """acidification 空数据 → {"rows": 0}。"""
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    session = _session()
    with _config_patch(mod):
        with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=[])):
            res = await mod.run_fa_sync(["acidification"], session)
    assert res["acidification"]["rows"] == 0


# ═══════════ _fa_scheduled_job / start / stop ═══════════


@pytest.mark.anyio
async def test_fa_scheduled_job_success_with_and_without_errors() -> Any:
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    session = AsyncMock()

    class _Ctx:
        async def __aenter__(self) -> Any:
            return session

        async def __aexit__(self, *args: Any) -> Any:
            return False

    with patch("app.core.database.async_session_factory", new=lambda: _Ctx()):
        with patch.object(
            mod,
            "run_fa_sync",
            new=AsyncMock(return_value={"fermentation": {"rows": 1}}),
        ):
            await mod._fa_scheduled_job()

    with patch("app.core.database.async_session_factory", new=lambda: _Ctx()):
        with patch.object(
            mod,
            "run_fa_sync",
            new=AsyncMock(
                return_value={
                    "fermentation": {"rows": 1},
                    "acidification": {"error": "eeee"},
                }
            ),
        ):
            await mod._fa_scheduled_job()


@pytest.mark.anyio
async def test_fa_scheduler_start_stop_and_failure() -> Any:
    mod = importlib.import_module("app.modules.production.fa_feishu_scheduler")
    from apscheduler.schedulers import (  # type: ignore[import-untyped]
        asyncio as aps_asyncio,
    )

    setattr(mod, "_fa_scheduler", None)
    fake_scheduler = MagicMock()
    with patch.object(aps_asyncio, "AsyncIOScheduler", return_value=fake_scheduler):
        mod.start_fa_sync_scheduler()
        assert getattr(mod, "_fa_scheduler") is fake_scheduler
        fake_scheduler.add_job.assert_called_once()
        fake_scheduler.start.assert_called_once()

    # 已存在 → 直接返回（不创建）
    setattr(mod, "_fa_scheduler", MagicMock())
    with patch.object(
        aps_asyncio, "AsyncIOScheduler", new=MagicMock(side_effect=AssertionError("no"))
    ):
        mod.start_fa_sync_scheduler()

    # stop 正常
    setattr(mod, "_fa_scheduler", MagicMock())
    mod.stop_fa_sync_scheduler()
    assert getattr(mod, "_fa_scheduler") is None
    mod.stop_fa_sync_scheduler()
    assert getattr(mod, "_fa_scheduler") is None

    # shutdown 抛异常也要置 None
    broken = MagicMock()
    broken.shutdown.side_effect = RuntimeError("shutdown-fail")
    setattr(mod, "_fa_scheduler", broken)
    mod.stop_fa_sync_scheduler()
    assert getattr(mod, "_fa_scheduler") is None

    # start 失败分支 → 不抛
    setattr(mod, "_fa_scheduler", None)
    with patch.object(
        aps_asyncio, "AsyncIOScheduler", new=MagicMock(side_effect=RuntimeError("boom"))
    ):
        mod.start_fa_sync_scheduler()
    assert getattr(mod, "_fa_scheduler") is None
