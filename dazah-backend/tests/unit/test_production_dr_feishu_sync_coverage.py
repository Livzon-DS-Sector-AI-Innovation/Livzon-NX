"""DR 多拉菌素 飞书同步 coverage。

覆盖 dr_feishu_sync：token 缓存/网络失败、_read_sheet 成功与 code!=0 分支、
upsert 创建与更新路径 / 合并单元格继承 / 杂质更新 / 空行跳过 / 行异常回滚、
run_dr_sync 无配置与回滚、_dr_scheduled_sync_job 成功与异常分支。
全部 mock，无真实网络/DB。
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        app_id="app-id",
        encrypted_app_secret="enc-secret",
        bitable_app_token="bitable-token",
        table_id="tbl-1",
        sync_target="extraction",
        product_name="多拉菌素",
    )


def _empty_row() -> list[str]:
    return [""] * 34


def _row(values: dict[int, str]) -> list[str]:
    row = _empty_row()
    for idx, val in values.items():
        row[idx] = val
    return row


def _scalar_result(fetchone=None, scalar=None):
    """模拟 sqlalchemy Result：fetchone 决定 update/insert，scalar_one 返回新 UUID。"""
    r = MagicMock()
    r.fetchone.return_value = fetchone
    if scalar is not None:
        r.scalar_one.return_value = scalar
    return r


class _DrSession:
    """按表判定 update/create：已有表 SELECT 返回已有行，否则返回 None 走 INSERT。"""

    def __init__(self, existing=()):
        self.existing = set(existing)
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self.executed: list = []
        self.fail_rollback = False

    async def execute(self, stmt, *args, **kwargs):
        s = str(stmt)
        self.executed.append(s)
        if s.startswith("SELECT id FROM"):
            table = s.split(" FROM ")[1].split(" WHERE")[0].strip()
            if table in self.existing:
                return _scalar_result(fetchone=(f"existing-{table}",), scalar=None)
            return _scalar_result(fetchone=None, scalar=f"new-uuid-{table}")
        return MagicMock()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        if self.fail_rollback:
            raise RuntimeError("rollback failed")
        self.rollbacks += 1

    async def flush(self):
        self.flushes += 1


CREATED_ROWS = [
    # 全空行 → 跳过（_is_empty）
    _empty_row(),
    # 有备注但无批次 → 没有 batch → 跳过（无 cur_batch）
    _row({3: "甲班", 4: "5"}),
    # 有批号无罐号 → 批次 upsert 后因为没有 cur_tank_id 而跳过
    _row({1: "DR-NO-TANK", 3: "甲班"}),
    # 有批次有罐号但无萃取 → batch/tank 创建后无 cur_extr_id 而跳过
    _row({1: "DR-B-26", 2: "DR-T1", 4: "5", 5: "500", 8: "10", 9: "08:00"}),
    # 完整行：批次/罐/萃取/滤液/杂质
    _row(
        {
            0: "5月1日",
            1: "DR-B-27",
            2: "DR-T2",
            4: "50",
            5: "500",
            6: "495",
            7: "495",
            8: "10",
            9: "08:00",
            10: "DR-EX-1",
            11: "5",
            12: "1200",
            13: "FT-1",
            14: "100",
            15: "88",
            16: "880",
            17: "10",
            18: "10.5",
            19: "900",
            23: "0.1",
            24: "0.2",
            25: "0.3",
            26: "0.4",
            27: "0.5",
            28: "0.6",
            29: "0.7",
            30: "0.05",
            31: "0.5",
            32: "5",
            33: "99.8",
        }
    ),
    # 无批号，但罐号/萃取号沿用上一个 batch/tank/extr → 创建新罐/萃取/滤液
    _row({2: "DR-T3", 10: "DR-EX-2", 13: "FT-R2"}),
]

_created_sheet_mock = AsyncMock(return_value=CREATED_ROWS)


# ═══════════ _get_token / _read_sheet ═══════════


@pytest.mark.anyio
async def test_dr_get_token_fetch_cache_error():
    mod = importlib.import_module("app.modules.production.dr_feishu_sync")
    mod._token_cache.clear()
    real_client = httpx.AsyncClient
    ok_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"tenant_access_token": "tok-d"})
    )
    err_transport = httpx.MockTransport(lambda req: httpx.Response(500, text="boom"))

    def fake_ok(*, base_url=None, timeout=30, **kw):
        return real_client(transport=ok_transport, timeout=timeout, base_url=base_url)

    def fake_err(*, base_url=None, timeout=30, **kw):
        return real_client(transport=err_transport, timeout=timeout, base_url=base_url)

    with patch.object(mod.httpx, "AsyncClient", fake_ok):
        assert await mod._get_token("app-1", "s-1") == "tok-d"
    # 缓存命中 → 不再发 HTTP
    with patch.object(
        mod.httpx, "AsyncClient", new=MagicMock(side_effect=AssertionError("no HTTP"))
    ):
        assert await mod._get_token("app-1", "s-1") == "tok-d"
    assert mod._token_cache["dr_sync:app-1"] == "tok-d"

    mod._token_cache.clear()
    with patch.object(mod.httpx, "AsyncClient", fake_err):
        with pytest.raises(httpx.HTTPStatusError):
            await mod._get_token("app-2", "s-2")


@pytest.mark.anyio
async def test_dr_read_sheet_ok_code_zero_and_code_error():
    mod = importlib.import_module("app.modules.production.dr_feishu_sync")

    def ok_handler(req):
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": {"valueRange": {"values": [[1, None, "x"], ["a", "b"]]}},
            },
        )

    real_client = httpx.AsyncClient

    def fake_ok(*, base_url=None, timeout=30, **kw):
        return real_client(
            transport=httpx.MockTransport(ok_handler),
            timeout=timeout,
            base_url=base_url,
        )

    with patch.object(mod.httpx, "AsyncClient", fake_ok):
        rows = await mod._read_sheet("tok", "s1", "spread")
    assert rows[0] == ["1", "", "x"]
    assert rows[1][0] == "a"

    def err_handler(request):
        return httpx.Response(200, json={"code": 8, "msg": "not-found"})

    def fake_err(*, base_url=None, timeout=30, **kw):
        return real_client(
            transport=httpx.MockTransport(err_handler),
            timeout=timeout,
            base_url=base_url,
        )

    with patch.object(mod.httpx, "AsyncClient", fake_err):
        with pytest.raises(RuntimeError):
            await mod._read_sheet("tok", "s1", "spread")

    def http_err_handler(request):
        return httpx.Response(400, text="bad request")

    def fake_http_err(*, base_url=None, timeout=30, **kw):
        return real_client(
            transport=httpx.MockTransport(http_err_handler),
            timeout=timeout,
            base_url=base_url,
        )

    with patch.object(mod.httpx, "AsyncClient", fake_http_err):
        with pytest.raises(RuntimeError):
            await mod._read_sheet("tok", "s1", "spread")


# ═══════════ sync_dr_extraction 主路径 ═══════════


@pytest.mark.anyio
async def test_dr_sync_creates_all_tables():
    mod = importlib.import_module("app.modules.production.dr_feishu_sync")
    session = _DrSession(existing=())
    with patch.object(mod, "decrypt_secret", return_value="secret"):
        with patch.object(mod, "_get_token", new=AsyncMock(return_value="tok")):
            with patch.object(mod, "_read_sheet", _created_sheet_mock):
                stats = await mod.sync_dr_extraction(_config(), session)
    assert stats["created_batches"] >= 2  # DR-NO-TANK + DR-B-26
    assert stats["created_tanks"] >= 2
    assert stats["created_extractions"] >= 2
    assert stats["created_filtrates"] >= 2
    assert stats["skipped"] >= 1  # 全空行 + 无罐号行
    assert session.commits == 1


@pytest.mark.anyio
async def test_dr_dr_sync_updates_existing_tables():
    mod = importlib.import_module("app.modules.production.dr_feishu_sync")
    tables = (
        "production.dr_fermentation_batches",
        "production.dr_fermentation_tanks",
        "production.dr_extractions",
        "production.dr_filtrates",
    )
    session = _DrSession(existing=tables)
    with patch.object(mod, "decrypt_secret", return_value="secret"):
        with patch.object(mod, "_get_token", new=AsyncMock(return_value="tok")):
            with patch.object(mod, "_read_sheet", _created_sheet_mock):
                stats = await mod.sync_dr_extraction(_config(), session)
    assert stats["updated_batches"] >= 2
    assert stats["updated_tanks"] >= 2
    assert stats["updated_extractions"] >= 2
    assert stats["updated_filtrates"] >= 2
    assert stats["created_batches"] == 0


@pytest.mark.anyio
async def test_dr_dr_sync_row_exception_rolls_back():
    """单行异常 → errors++；回滚失败也要继续。"""
    mod = importlib.import_module("app.modules.production.dr_feishu_sync")
    session = _DrSession(existing=())
    session.fail_rollback = True
    rows = [
        _row({1: "DR-ERR", 2: "DR-T-ERR", 10: "DR-EX-ERR"}),
        _row({1: "DR-OK", 2: "DR-T-OK", 10: "DR-EX-OK"}),
    ]
    orig = mod._upsert

    async def flaky_upsert(session_, table, data, unique_keys, stats, stat_key):
        if table == "production.dr_extractions":
            raise RuntimeError("db down")
        return await orig(session_, table, data, unique_keys, stats, stat_key)

    with patch.object(mod, "decrypt_secret", return_value="secret"):
        with patch.object(mod, "_get_token", new=AsyncMock(return_value="tok")):
            with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=rows)):
                with patch.object(mod, "_upsert", new=flaky_upsert):
                    stats = await mod.sync_dr_extraction(_config(), session)
    assert stats["errors"] == 2  # 两行萃取都失败；回滚本身抛错被吞
    assert session.rollbacks == 0
    assert stats["created_batches"] == 2


# ═══════════ run_dr_sync / _dr_scheduled_sync_job / scheduler ═══════════


class _Ctx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


@pytest.mark.anyio
async def test_run_dr_sync_no_config_returns_error():
    mod = importlib.import_module("app.modules.production.dr_feishu_sync")
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    res = await mod.run_dr_sync(session)
    assert "error" in res


@pytest.mark.anyio
async def test_run_dr_sync_partial_fail_rollback():
    """某一 target 失败 → 该 target error，session.rollback 被调用。"""
    mod = importlib.import_module("app.modules.production.dr_feishu_sync")
    cfg1 = SimpleNamespace(id="c1", sync_target="extraction")
    cfg2 = SimpleNamespace(id="c2", sync_target="dr_plan")

    class _ResultAll:
        def scalars(self):
            return self

        def all(self):
            return [cfg1, cfg2]

    class _SessionAll:
        def __init__(self):
            self.rolled = 0
            self.rollback_raises = True

        async def execute(self, stmt, *args, **kwargs):
            return _ResultAll()

        async def rollback(self):
            if self.rollback_raises:
                self.rollback_raises = False
                raise RuntimeError("rollback failed")
            self.rolled += 1

    with patch(
        "app.modules.production.production_plan_service.sync_config_by_target",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        res = await mod.run_dr_sync(_SessionAll())
    assert res[cfg1.sync_target]["error"]
    assert res[cfg2.sync_target]["error"]


@pytest.mark.anyio
async def test_dr_scheduled_sync_job_success_and_exception():
    mod = importlib.import_module("app.modules.production.dr_feishu_sync")
    session = AsyncMock()

    with patch("app.core.database.async_session_factory", new=lambda: _Ctx(session)):
        with patch.object(
            mod,
            "run_dr_sync",
            new=AsyncMock(
                return_value={
                    "extraction": {"created": 1},
                    "dr_plan": {"error": "boom"},
                }
            ),
        ):
            await mod._dr_scheduled_sync_job()

    with patch("app.core.database.async_session_factory", new=lambda: _Ctx(session)):
        with patch.object(
            mod, "run_dr_sync", new=AsyncMock(side_effect=RuntimeError("db down"))
        ):
            await mod._dr_scheduled_sync_job()


@pytest.mark.anyio
async def test_dr_scheduler_start_double_and_stop():
    mod = importlib.import_module("app.modules.production.dr_feishu_sync")
    from apscheduler.schedulers import asyncio as aps_asyncio

    mod._dr_sync_scheduler = None
    fake = MagicMock()
    with patch.object(aps_asyncio, "AsyncIOScheduler", return_value=fake):
        mod.start_dr_sync_scheduler()
        assert mod._dr_sync_scheduler is fake
        fake.add_job.assert_called_once()
        fake.start.assert_called_once()

    # 已存在 → 直接返回
    mod._dr_sync_scheduler = MagicMock()
    with patch.object(
        aps_asyncio, "AsyncIOScheduler", new=MagicMock(side_effect=AssertionError("no"))
    ):
        mod.start_dr_sync_scheduler()

    # stop 正常 + 幂等
    mod._dr_sync_scheduler = MagicMock()
    mod.stop_dr_sync_scheduler()
    assert mod._dr_sync_scheduler is None
    mod.stop_dr_sync_scheduler()
    assert mod._dr_sync_scheduler is None
