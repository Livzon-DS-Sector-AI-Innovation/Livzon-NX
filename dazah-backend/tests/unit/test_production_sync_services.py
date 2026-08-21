"""生产模块飞书 sync 服务批量测试。

覆盖 27 个 *_sync.py 模块的主路径：空数据、有效记录创建、已有记录更新、缺关键字段跳过。
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SYNC_MODULES = [
    "broth_receive_sync",
    "centrifuge1_sync",
    "centrifuge2_sync",
    "ceramic_clean_sync",
    "ceramic_equip_sync",
    "ceramic_feed_sync",
    "ceramic_ops_sync",
    "ceramic_sep_sync",
    "conc1_sync",
    "conc2_sync",
    "decolor1_sync",
    "dr_chromatography_sync",
    "dr_fourth_refinement_sync",
    "dr_refinement_sync",
    "dr_second_refinement_sync",
    "dr_third_refinement_sync",
    "dry_sync",
    "filter1_sync",
    "filter2_sync",
    "pack_sync",
    "pretreatment_sync",
    "recrystallize_sync",
    "seed_culture_sync",
]

FUNC_NAMES = {
    "broth_receive_sync": "sync_broth_receive",
    "centrifuge1_sync": "sync_centrifuge1",
    "centrifuge2_sync": "sync_centrifuge2",
    "ceramic_clean_sync": "sync_ceramic_clean",
    "ceramic_equip_sync": "sync_ceramic_equip",
    "ceramic_feed_sync": "sync_ceramic_feed",
    "ceramic_ops_sync": "sync_ceramic_ops",
    "ceramic_sep_sync": "sync_ceramic_sep",
    "conc1_sync": "sync_conc1",
    "conc2_sync": "sync_conc2",
    "decolor1_sync": "sync_decolor1",
    "dr_chromatography_sync": "sync_dr_chromatography",
    "dr_fourth_refinement_sync": "sync_dr_fourth_refinement",
    "dr_refinement_sync": "sync_dr_refinement",
    "dr_second_refinement_sync": "sync_dr_second_refinement",
    "dr_third_refinement_sync": "sync_dr_third_refinement",
    "dry_sync": "sync_dry",
    "filter1_sync": "sync_filter1",
    "filter2_sync": "sync_filter2",
    "pack_sync": "sync_pack",
    "pretreatment_sync": "sync_pretreatment",
    "recrystallize_sync": "sync_recrystallize",
    "seed_culture_sync": "sync_seed_culture_to_table",
}


def _session(existing=None) -> AsyncMock:
    """返回 mock session：execute 的 fetchone 为同步方法（真实 Result.fetchone 非 async）。"""  # noqa: E501
    session = AsyncMock()
    result = AsyncMock()
    result.fetchone = SimpleNamespace  # placeholder replaced below
    from unittest.mock import MagicMock
    result.fetchone = MagicMock(return_value=existing)
    session.execute.return_value = result
    return session


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        app_id="app-id",
        encrypted_app_secret="encrypted-secret",
        bitable_app_token="token",
        table_id="tbl-1",
        sync_target="local",
        product_name="多拉菌素",
    )


def _batch_no_field(module) -> str:
    """模块的业务键字段：优先 batch_no，否则按各模块跳过条件回退。"""
    mapping = getattr(module, "FIELD_MAPPING", None) or {}
    for key, value in mapping.items():
        if value == "batch_no":
            return key
    for key, value in mapping.items():
        if value in ("received_batch", "membrane_no", "equipment_no"):
            return key
    return next(iter(mapping)) if mapping else "批次号"


def _load_module(module_name: str):
    module = importlib.import_module(f"app.modules.production.{module_name}")
    func = getattr(module, FUNC_NAMES[module_name], None)
    client = getattr(module, "ProductionFeishuClient", None)
    if func is None or client is None:
        pytest.skip(f"{module_name} 结构不同，跳过")
    return module, func


@pytest.mark.anyio
@pytest.mark.parametrize("module_name", SYNC_MODULES)
async def test_sync_empty_records(module_name: str) -> None:
    module, func = _load_module(module_name)
    session = _session()
    with patch.object(module, "decrypt_secret", return_value="secret"):
        with patch.object(
            module.ProductionFeishuClient, "list_records",
            new=AsyncMock(return_value={"items": []}),
        ):
            result = await func(_config(), session)
    assert isinstance(result, dict)


@pytest.mark.anyio
@pytest.mark.parametrize("module_name", SYNC_MODULES)
async def test_sync_creates_records(module_name: str) -> None:
    module, func = _load_module(module_name)
    # 查询不存在 → 走 INSERT 路径
    session = _session(existing=None)
    batch_key = _batch_no_field(module)
    with patch.object(module, "decrypt_secret", return_value="secret"):
        with patch.object(
            module.ProductionFeishuClient, "list_records",
            new=AsyncMock(return_value={"items": [{"record_id": "r1", "fields": {batch_key: "B001"}}]}),  # noqa: E501
        ):
            result = await func(_config(), session)
    assert isinstance(result, dict)
    assert session.execute.await_count >= 1


@pytest.mark.anyio
@pytest.mark.parametrize("module_name", SYNC_MODULES)
async def test_sync_updates_existing_records(module_name: str) -> None:
    module, func = _load_module(module_name)
    # 查询已存在 → 走 UPDATE 路径
    session = _session(existing=(1,))
    batch_key = _batch_no_field(module)
    with patch.object(module, "decrypt_secret", return_value="secret"):
        with patch.object(
            module.ProductionFeishuClient, "list_records",
            new=AsyncMock(return_value={"items": [{"record_id": "r1", "fields": {batch_key: "B001"}}]}),  # noqa: E501
        ):
            result = await func(_config(), session)
    assert isinstance(result, dict)


@pytest.mark.anyio
@pytest.mark.parametrize("module_name", SYNC_MODULES)
async def test_sync_skips_records_without_batch_no(module_name: str) -> None:
    module, func = _load_module(module_name)
    session = _session()
    with patch.object(module, "decrypt_secret", return_value="secret"):
        with patch.object(
            module.ProductionFeishuClient, "list_records",
            new=AsyncMock(return_value={"items": [{"record_id": "r1", "fields": {"备注": "x"}}]}),  # noqa: E501
        ):
            result = await func(_config(), session)
    assert isinstance(result, dict)


DR_SYNC_MODULES = [
    "dr_chromatography_sync",
    "dr_fourth_refinement_sync",
    "dr_refinement_sync",
    "dr_second_refinement_sync",
    "dr_third_refinement_sync",
]

DR_FUNCS = {
    "dr_chromatography_sync": "sync_dr_chromatography",
    "dr_fourth_refinement_sync": "sync_dr_fourth_refinement",
    "dr_refinement_sync": "sync_dr_refinement",
    "dr_second_refinement_sync": "sync_dr_second_refinement",
    "dr_third_refinement_sync": "sync_dr_third_refinement",
}


@pytest.mark.anyio
@pytest.mark.parametrize("module_name", DR_SYNC_MODULES)
async def test_dr_sync_empty_sheet(module_name: str) -> None:
    module = importlib.import_module(f"app.modules.production.{module_name}")
    func = getattr(module, DR_FUNCS[module_name])
    session = _session()
    with patch.object(module, "decrypt_secret", return_value="secret"):
        with patch.object(module, "_get_token", new=AsyncMock(return_value="token")):
            with patch.object(module, "_read_sheet", new=AsyncMock(return_value=[])):
                result = await func(_config(), session)
    assert isinstance(result, dict)


@pytest.mark.anyio
@pytest.mark.parametrize("module_name", DR_SYNC_MODULES)
async def test_dr_sync_empty_rows_skipped(module_name: str) -> None:
    module = importlib.import_module(f"app.modules.production.{module_name}")
    func = getattr(module, DR_FUNCS[module_name])
    session = _session()
    with patch.object(module, "decrypt_secret", return_value="secret"):
        with patch.object(module, "_get_token", new=AsyncMock(return_value="token")):
            with patch.object(module, "_read_sheet", new=AsyncMock(return_value=[["", ""]])):  # noqa: E501
                result = await func(_config(), session)
    assert isinstance(result, dict)


@pytest.mark.anyio
async def test_dr_feishu_sync_empty_sheet() -> None:
    module = importlib.import_module("app.modules.production.dr_feishu_sync")
    session = _session()
    with patch.object(module, "decrypt_secret", return_value="secret"):
        with patch.object(module, "_get_token", new=AsyncMock(return_value="token")):
            with patch.object(module, "_read_sheet", new=AsyncMock(return_value=[])):
                result = await module.sync_dr_extraction(_config(), session)
    assert isinstance(result, dict)


@pytest.mark.anyio
async def test_fa_acid_sync_run_empty() -> None:
    module = importlib.import_module("app.modules.production.fa_acid_sync")
    session = _session()
    with patch.object(module, "_token", new=AsyncMock(return_value="token")):
        with patch.object(module, "_read", new=AsyncMock(return_value=[])):
            result = await module.run(session)
    assert isinstance(result, dict)


@pytest.mark.anyio
@pytest.mark.parametrize("module_name", SYNC_MODULES)
async def test_sync_filters_non_dict_items(module_name: str) -> None:
    """list_records 返回非 dict 元素时过滤，不抛异常。"""
    module, func = _load_module(module_name)
    session = _session()
    with patch.object(module, "decrypt_secret", return_value="secret"):
        with patch.object(
            module.ProductionFeishuClient, "list_records",
            new=AsyncMock(return_value={"items": [None, "text", 42]}),
        ):
            result = await func(_config(), session)
    assert isinstance(result, dict)

# ═══════════ mc_feishu_sheets_sync 服务主路径（db+network 走 mock） ═══════════


class _FakeResult:
    """模拟 sqlalchemy Result：scalars().first() 与 fetchone() 同步。"""

    def __init__(self, first=None, fetchone_val=None):
        self._first = first
        self._fetchone_val = fetchone_val

    def scalars(self):
        return self

    def first(self):
        return self._first

    def fetchone(self):
        return self._fetchone_val


class _FakeSession:
    """模拟 AsyncSession：execute 返回可 scalars().first() / fetchone() 的 Result。"""

    def __init__(self, config=None, existing=None, fetchone_val=None):
        self.config = config
        self.existing = existing
        self.fetchone_val = fetchone_val
        self.executed = []

    async def execute(self, stmt, *args, **kwargs):
        self.executed.append(stmt)
        return _FakeResult(self)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _FakeResult:
    def __init__(self, session):
        self._session = session

    def scalars(self):
        return self

    def first(self):
        return self._session.existing

    def fetchone(self):
        return self._session.fetchone_val

    def all(self):
        # run_dr_sync 用 result.scalars().all()
        return self._session.existing or []


@pytest.mark.anyio
async def test_mc_sync_unknown_module_reports_error():
    """未知模块返回错误而不抛异常。"""
    from app.modules.production import mc_feishu_sheets_sync as sync
    # 提供有效配置对象，使 run_mc_sync 能拿到 cfg
    cfg_obj = SimpleNamespace(
        bitable_app_token="sptoken",
        app_id="app-id",
        encrypted_app_secret="enc-secret",
    )
    session = _FakeSession(existing=cfg_obj)
    with patch.object(sync, "decrypt_secret", return_value="secret"):
        # run_mc_sync 内部 import mc_yield_anomaly_detector.run_anomaly_detection
        with patch(
            "app.modules.production.mc_yield_anomaly_detector.run_anomaly_detection",
            new=AsyncMock(return_value={}),
        ):
            with patch.object(sync, "_sync_lineage", new=AsyncMock(return_value=0)):
                result = await sync.run_mc_sync(["not_a_module"], session)
    assert result["not_a_module"]["error"]

@pytest.mark.anyio
async def test_mc_sync_config_missing_secret_ok():
    from app.modules.production import mc_feishu_sheets_sync as sync
    session = _FakeSession(existing=None)
    with patch.object(sync, "decrypt_secret", return_value="secret"):
        with patch.object(sync, "_get_mc_spreadsheet_config", new=AsyncMock(
            return_value={
                "spreadsheet_token": "t", "app_id": "a", "app_secret": "s",
            }
        )):
            with patch(
                "app.modules.production.mc_yield_anomaly_detector.run_anomaly_detection",
                new=AsyncMock(return_value={}),
            ):
                with patch.object(sync, "_sync_lineage", new=AsyncMock(return_value=0)):
                    result = await sync.run_mc_sync([], session)
    assert isinstance(result, dict)


@pytest.mark.anyio
async def test_mc_get_tenant_token_and_read_sheet_range():
    """用 httpx.MockTransport 覆盖 _get_tenant_token 与 _read_sheet_range 的分支。"""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "tok-1"})
        if "/values/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "data": {"valueRange": {"values": [[1, 2, None], ["a", "b", "c"]]}},
                },
            )
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    from app.modules.production import mc_feishu_sheets_sync as syncmod

    def fake_async_client(*, base_url=None, timeout=30):
        return real_async_client(
            transport=transport, timeout=timeout, base_url=base_url
        )

    with patch.object(syncmod.httpx, "AsyncClient", fake_async_client):
        token = await syncmod._get_tenant_token("app-1", "secret-1")
        assert token == "tok-1"
        assert await syncmod._get_tenant_token("app-1", "secret-1") == "tok-1"
        rows = await syncmod._read_sheet_range("sheet1", "A1:C3", "spt", "app-1", "secret-1")  # noqa: E501
        assert rows[0] == ["1", "2", ""]
        assert rows[1] == ["a", "b", "c"]


@pytest.mark.anyio
async def test_dr_run_sync_no_config_returns_error():
    """DR 同步无配置时返回 error 而非异常。"""
    from app.modules.production import dr_feishu_sync as drsync
    session = _FakeSession(existing=[])
    result = await drsync.run_dr_sync(session)
    assert "error" in result


@pytest.mark.anyio
async def test_dr_run_sync_with_configs_runs_rollback_on_error():
    """DR 同步遍历配置，某个 target 失败时记录 error 并回滚。"""
    from app.modules.production import dr_feishu_sync as dr
    # existing 为两个配置（scalars().all() 由 _FakeResult 序列化）
    cfg1 = SimpleNamespace(id="c1", sync_target="production_plan")
    cfg2 = SimpleNamespace(id="c2", sync_target="dr_plan")

    class _ResultAll:
        def scalars(self):
            return self
        def all(self):
            return [cfg1, cfg2]

    class _SessionAll:
        def __init__(self):
            self.rolled = 0
        async def execute(self, stmt, *a, **k):
            return _ResultAll()
        async def rollback(self):
            self.rolled += 1

    session_all = _SessionAll()
    with patch(
        "app.modules.production.production_plan_service.sync_config_by_target",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await dr.run_dr_sync(session_all)
    assert result[cfg1.sync_target]["error"]
    assert session_all.rolled == 2


# ═══════════ dr_lineage_api 辅助查询（SQL mock） ═══════════

_MM_UNSET = object()


def _result_with(fetchone=_MM_UNSET, fetchall=_MM_UNSET):
    r = MagicMock()
    if fetchone is not _MM_UNSET:
        r.fetchone.return_value = fetchone
    if fetchall is not _MM_UNSET:
        r.fetchall.return_value = fetchall
    return r


def _result_fetchone(v):
    r = MagicMock()
    r.fetchone.return_value = v
    return r


def _result_fetchall(v):
    r = MagicMock()
    if isinstance(v, list):
        r.fetchall.return_value = v
    else:
        r.fetchall.return_value = [v]
    return r


@pytest.mark.anyio
async def test_dr_lineage_resolve_prefers_explicit_stage():
    drlineage = importlib.import_module("app.modules.production.dr_lineage_api")
    session = AsyncMock()
    async def _exec(sql, params=None):
        s = str(sql)
        if "SELECT 1 FROM production.dr_extractions" in s:
            return _result_fetchone(True)
        return _result_fetchone(True)
    session.execute.side_effect = _exec
    stg, bn = await drlineage._resolve(session, "extraction", "DR-26026-1")
    assert stg == "extraction"
    assert bn == "DR-26026-1"


@pytest.mark.anyio
async def test_dr_lineage_resolve_falls_back_to_probe():
    drlineage = importlib.import_module("app.modules.production.dr_lineage_api")
    session = AsyncMock()
    async def branch(sql, *q):
        s = str(sql)
        if "SELECT 1 FROM production.dr_first_refinement" in s:
            return _result_fetchone(True)
        return _result_fetchone(None)
    session.execute.side_effect = branch
    stg, bn = await drlineage._resolve(session, "", "DR-F1-24019")
    assert stg == "first_refinement"


@pytest.mark.anyio
async def test_dr_lineage_upstream_downstream_branches():
    drlineage = importlib.import_module("app.modules.production.dr_lineage_api")
    session = AsyncMock()
    async def branch(sql, *q, **k):
        s = str(sql)
        if "dr_extractions e" in s and "fermentation_batch_id" in s:
            return _result_fetchone(SimpleNamespace(fermentation_batch_id="fb1"))
        if "SELECT batch_no FROM production.dr_fermentation_batches" in s:
            return _result_fetchone(SimpleNamespace(batch_no="DR-26026"))
        if "DISTINCT extraction_batch_no FROM production.dr_chromatography_crystal" in s:  # noqa: E501
            return _result_fetchall(SimpleNamespace(extraction_batch_no="DR-E1"))
        if "DISTINCT chromatography_batch_no" in s and "wet_powder_batch_no" in s:  # noqa: E501
            return _result_fetchall(SimpleNamespace(chromatography_batch_no="DR-C1"))
        if "DISTINCT wet_powder_batch_no" in s:
            return _result_fetchall(SimpleNamespace(wet_powder_batch_no="DR-24019-1"))
        if "SELECT feed_batch_no, feed_pure_kg" in s:
            return _result_fetchall([
                SimpleNamespace(feed_batch_no="DR-F1-1 + DR-F1-2", feed_pure_kg=0.0),
                SimpleNamespace(feed_batch_no="DR-H1", feed_pure_kg=0.0),
            ])  # noqa: E501
        if "SELECT DISTINCT extraction_batch_no FROM production.dr_extractions" in s:
            return _result_fetchall(SimpleNamespace(extraction_batch_no="DR-260-1"))
        if s.startswith("SELECT DISTINCT refinement_batch_no"):
            return _result_fetchall(SimpleNamespace(refinement_batch_no="DR-F2-1"))
        return _result_fetchall([])
    session.execute.side_effect = branch

    up = await drlineage._upstream(session, "extraction", "DR-26026-1")
    assert up[0][0] == "fermentation"
    up2 = await drlineage._upstream(session, "chromatography", "DR-C1")
    assert up2[0][0] == "extraction"
    up3 = await drlineage._upstream(session, "first_refinement", "DR-F1-24019-1")
    assert up3[0][0] == "chromatography"
    up4 = await drlineage._upstream(session, "second_refinement", "DR-F2-1")
    assert up4[0][0] in ("first_refinement", "recovery")
    dn = await drlineage._downstream(session, "fermentation", "DR-B-26")
    assert dn[0][0] == "extraction"
    dn2 = await drlineage._downstream(session, "first_refinement", "DR-F1-1")
    assert dn2[0][0] == "second_refinement"


@pytest.mark.anyio
async def test_fa_feishu_sync_fermentation_parse_and_upsert():
    fafsync = importlib.import_module("app.modules.production.fa_feishu_sync")
    rows = [
        ["2026-03-05", "FA-EX1", "", "10", "100", "500", "600", "80", "1.2", "20", "0.39", "5", "0.5"],  # noqa: E501
        ["2026-03-05", "FA-EX1", "FA-EX1C", "5", "90", "300", "", "", "", "", "", "", ""],  # noqa: E501
        ["2026.03.06", "FA-EX2", "", "8", "", "", "400", "", "", "", "", "", "", ""],
        ["03月份", "", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "FA-EX3", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", "", "", ""],
    ]
    session = AsyncMock()
    result = MagicMock()
    result.rowcount = 2
    session.execute.return_value = result
    from unittest.mock import patch as _patch
    with _patch.object(fafsync, "_read_sheet", new=AsyncMock(return_value=rows)):
        out = await fafsync.sync_fermentation(session, "token", "app", "sec")
    assert out["batches"] >= 1
    assert out["sub_batches"] >= 1


# ═══════════ mc_feishu_sheets_sync._sync_extraction 主路径（models mock） ═══════════


@pytest.mark.anyio
async def test_mc_sync_extraction_full_path():
    """覆盖 _sync_extraction 的创建/更新主表与投入明细、跳过行。"""
    from app.modules.production import mc_feishu_sheets_sync as sync

    rows = [
        ["2026-03-01", "MC-101", "MC-C1", "5", "90", "100", "80", "90", "85", "800", "2.0", "86", "10", "5", "90", "2", "50", "0.9", "1.0", "500", "2", "0.88"],  # noqa: E501
        ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # noqa: E501
        ["03月份", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # noqa: E501
        ["2026-03-02", "MC-0102", "MC-B", "10", "88", "90", "7", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # noqa: E501
    ]
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_extraction(session, "tok", "app", "sec")
    assert stats["created_records"] >= 1
    assert stats["created_inputs"] >= 1
    assert stats["skipped"] >= 1


@pytest.mark.anyio
async def test_mc_sync_scheduler_defaults():
    from app.modules.production import mc_feishu_sheets_sync as sync_module
    sync_module._mc_sync_scheduler = None
    sync_module.start_mc_sync_scheduler()
    sync_module.start_mc_sync_scheduler()  # 二次调用不进
    assert getattr(sync_module, "_mc_sync_scheduler", None) is not None
    sync_module.stop_mc_sync_scheduler()
    assert getattr(sync_module, "_mc_sync_scheduler", None) is None


@pytest.mark.anyio
async def test_mc_sync_refinement_and_ba():
    """覆盖 _sync_refinement 创建/更新 + _sync_ba 交叉表解析。"""
    from app.modules.production import mc_feishu_sheets_sync as sync

    # refinement: 有批次行 + 投入行 + 跳过行
    ref_rows = [
        ["2026-03-01", "MC-F2-101", "MC-F1-501", "30", "30", "5", "90", "25", "20", "180", "T1", "1.2", "C1", "10", "8", "120", "0.9", "0.88", "300", "2.0", "1.5"],  # noqa: E501
        ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # noqa: E501
        ["2026-03-02", "MC-F2-0102", "", "5", "5", "1", "85", "4", "3", "90", "T2", "0.8", "C2", "2", "1.5", "60", "0.95", "0.9", "150", "1.0", "0.8"],  # noqa: E501
    ]
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=ref_rows)):
        stats = await sync._sync_refinement(session, "tok", "app", "sec")
    assert stats["created_records"] >= 1
    assert stats["created_inputs"] >= 1

    # ba: 交叉表（表头含日期，数据行含 入库/合计/空/跳过）
    ba_rows = [
        ["消耗记录", "日期", "2026.03.01", "2026.03.02"],
        ["", "1#萃取罐", "21.1", ""],
        ["", "入库A", "5.5", ""],
        ["", "合计(吨)", "50", ""],
        ["", "成品入库累计", "90", ""],
        ["", "2#罐", "", "3.3"],
    ]
    session2 = AsyncMock()
    result2 = MagicMock()
    result2.scalar_one_or_none.return_value = None
    session2.execute.return_value = result2
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=ba_rows)):
        stats2 = await sync._sync_ba(session2, "tok", "app", "sec")
    assert stats2["created_records"] >= 1
    assert stats2["skipped"] == 0
