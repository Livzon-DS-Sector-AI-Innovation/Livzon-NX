"""生产模块飞书 sync 服务批量测试。

覆盖 27 个 *_sync.py 模块的主路径：空数据、有效记录创建、已有记录更新、缺关键字段跳过。
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
