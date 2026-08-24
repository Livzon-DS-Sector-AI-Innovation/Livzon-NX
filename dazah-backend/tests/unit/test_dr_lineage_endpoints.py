"""DR 多拉菌素 追溯/分布/覆盖/漏斗 端点测试（SQL 全 mock）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.production import dr_lineage_api as dr


def _result(fetchone=False, fetchall=None, scalar=None):
    r = MagicMock()
    r.fetchone.return_value = fetchone
    r.fetchall.return_value = fetchall if fetchall is not None else []
    r.scalar.return_value = scalar
    return r


def _session():
    return AsyncMock()


@pytest.mark.anyio
async def test_dr_lineage_trace_full_flow():
    """主端点全流程：明确工段 → BFS 展开 → 组装 stage groups → 输出。"""
    s = AsyncMock()
    branch, _ = _route_all()
    s.execute.side_effect = branch
    resp = await dr.dr_lineage_trace(batch_no="DR-26026", stage="extraction", session=s)
    data = json.loads(resp.body)["data"]
    assert data["target_batch"] == "DR-26026"
    assert data["target_stage"] == "extraction"
    s2 = AsyncMock()
    branch2, _ = _route_all()
    s2.execute.side_effect = branch2
    with pytest.raises(BaseException):
        await dr.dr_lineage_trace(batch_no="", stage="", session=s2)


def _route_all():
    """一条通用路由：合理返回 fetchall/fetchone/scalar。"""
    def branch(sql, params=None):
        s = str(sql)
        r = MagicMock()
        if "SELECT 1 FROM" in s:
            r.fetchone.return_value = (True,)
        elif "total_qty" in s:
            r.fetchall.return_value = [SimpleNamespace(total_qty=10.0, single_batch_yield=0.9)]  # noqa: E501
        elif "chromatography_yield" in s:
            r.fetchall.return_value = [SimpleNamespace(  # noqa: E501
                product_qty_kg=5.0, chromatography_yield=0.9,
                crystallization_yield=0.85)]
        elif "SUM(mother_liquor_product_kg) AS ml" in s:
            r.fetchone.return_value = SimpleNamespace(ml=2.0, rp=1.0)
        elif "SUM(mother_liquor_product_kg)" in s:
            r.fetchone.return_value = (3.0,)
        elif "DISTINCT e.extraction_batch_no" in s:
            r.fetchall.return_value = [SimpleNamespace(extraction_batch_no="DR-E")]
            r.fetchone.return_value = None
        elif "DISTINCT extraction_batch_no FROM production.dr_chromatography_crystal" in s:  # noqa: E501
            r.fetchall.return_value = [SimpleNamespace(extraction_batch_no="DR-E")]
        elif "DISTINCT chromatography_batch_no" in s:
            r.fetchall.return_value = [SimpleNamespace(chromatography_batch_no="DR-C")]
        elif "DISTINCT wet_powder_batch_no" in s:
            r.fetchall.return_value = [SimpleNamespace(wet_powder_batch_no="DR-24019-1")]  # noqa: E501
        elif "Batch_no FROM dr_fermentation" in s or "batch_no FROM" in s:
            r.fetchone.return_value = SimpleNamespace(batch_no="DR-F")
        elif "fermentation_batch_id" in s:
            r.fetchone.return_value = SimpleNamespace(fermentation_batch_id="fb")
        elif "feed_batch_no, feed_pure_kg" in s:
            r.fetchall.return_value = [SimpleNamespace(feed_batch_no="DR-F1-1", feed_pure_kg=3.0)]  # noqa: E501
        elif "product_pure_kg" in s and "yield_rate" in s:
            r.fetchone.return_value = SimpleNamespace(product_pure_kg=7.0, yield_rate=0.98)  # noqa: E501
        elif "dry_weight_kg" in s:
            r.fetchone.return_value = SimpleNamespace(dry_weight_kg=9.0, yield_rate=0.99)  # noqa: E501
        elif "feed_pure_kg" in s:
            r.fetchone.return_value = SimpleNamespace(feed_pure_kg=4.0)
        elif "dr_fourth_refinement" in s and "feed_batch_no" in s:
            r.fetchall.return_value = []
        elif "COUNT(DISTINCT" in s:
            r.scalar.return_value = 2
        elif "COALESCE(SUM(" in s:
            r.scalar.return_value = 5.0
        elif "GROUP BY" in s:
            r.fetchall.return_value = [SimpleNamespace(  # noqa: E501
                stage="extraction", n=3, min_y=80.0, q1=85.0, median=90.0,
                mean=90.5, q3=95.0, max_y=100.0, below_80=1, above_110=0)]
        else:
            r.fetchall.return_value = []
            r.fetchone.return_value = None
        return r
    return branch, MagicMock()


@pytest.mark.anyio
async def test_dr_distribution_reuse_coverage():
    """三条聚合端点：yield-distribution / material-reuse / coverage 返回空。"""
    s = AsyncMock()
    branch, _ = _route_all()
    s.execute.side_effect = _dist_branch
    dist = await dr.dr_yield_distribution(session=s)
    assert json.loads(dist.body)["data"] == []
    reuse = await dr.dr_material_reuse(session=s)
    assert json.loads(reuse.body)["data"] == []
    cov = await dr.dr_coverage(session=s)
    cov_data = json.loads(cov.body)["data"]
    assert cov_data["segments"]  # 7 个工段段覆盖（count=0）
    assert isinstance(cov_data["broken"], dict)


def _dist_branch(sql, params=None):
    r = MagicMock()
    # 让所有查询返回空，覆盖三端点的空数据路径
    r.fetchall.return_value = []
    r.fetchone.return_value = None
    r.scalar.return_value = 0
    return r


@pytest.mark.anyio
async def test_dr_loss_funnel_and_stats():
    s = AsyncMock()
    branch, _ = _route_all()
    s.execute.side_effect = branch
    resp = await dr.dr_loss_funnel(batch_no="DR-26026", stage="chromatography", session=s)  # noqa: E501
    data = json.loads(resp.body)["data"]
    assert data["target_batch"] == "DR-26026"

    with pytest.raises(BaseException):
        await dr.dr_loss_funnel(batch_no="", stage="", session=s)


def test_route_all_return_value():
    # 验证 _route_all 对所有 SQL 类型都能安全返回
    branch, _ = _route_all()
    r = branch("SELECT 1 FROM production.dr_extractions WHERE ...")
    assert r.fetchone.return_value == (True,)
    r2 = branch("SELECT total_qty, single_batch_yield FROM production.dr_extractions")
    assert len(r2.fetchall.return_value) >= 1


# ═══════════ dr_coverage / dr_material_reuse / dr_loss_stats ═══════════

_MAIN_TABLES = {
    "fermentation": ("dr_fermentation_batches", "batch_no"),
    "extraction": ("dr_extractions", "extraction_batch_no"),
    "chromatography": ("dr_chromatography_crystal", "chromatography_batch_no"),
}


@pytest.mark.anyio
async def test_dr_coverage_full():
    """覆盖完整性：各工段计数 + 断链 _missing 无前缀/有前缀 + 特殊投料标签。"""
    s = AsyncMock()
    s.execute.return_value = SimpleNamespace(
        fetchall=lambda: [("DR-EX-1",)], scalar=lambda: 3,
    )
    resp = await dr.dr_coverage(session=s)
    data = json.loads(resp.body)["data"]
    assert len(data["segments"]) == 7  # _MAIN_TABLES 有 7 个工段
    assert data["broken"]["extraction_feeds_not_in_extraction"]["count"] == 1
    assert data["broken"]["third_feeds_not_in_second"]["count"] == 1
    assert "DR-EX-1" in data["broken"]["special_feeds"]["batches"]


@pytest.mark.anyio
async def test_dr_material_reuse_full():
    """物料复用：单 union 查询返回多个投料复用项。"""
    s = AsyncMock()
    rows = [
        SimpleNamespace(up_type="third_refinement", up_batch="DR-F2-1", usage_count=2, used_by="DR-2, DR-3"),  # noqa: E501
        SimpleNamespace(up_type="chromatography", up_batch="DR-EX-1", usage_count=3, used_by="DR-C-1, DR-C-2"),  # noqa: E501
    ]
    s.execute.return_value = SimpleNamespace(fetchall=lambda: rows)
    resp = await dr.dr_material_reuse(session=s)
    data = json.loads(resp.body)["data"]
    assert len(data) == 2
    assert data[0]["upstream_type"] == "third_refinement"
    assert data[1]["upstream_batch"] == "DR-EX-1"


@pytest.mark.anyio
async def test_dr_loss_stats_full():
    """损耗统计：按年月聚合行 + 三次/四次未闭合投料。"""
    s = AsyncMock()

    def branch(sql, params=None):
        ssql = str(sql)
        r = MagicMock()
        if "SELECT stage, ym, COUNT(*)" in ssql:
            r.fetchall.return_value = [
                SimpleNamespace(stage="second_refinement", ym="2026.05", n=2, avg_y=88.0, min_y=80.0, max_y=96.0),  # noqa: E501
            ]
        elif "SELECT DISTINCT refinement_batch_no, feed_batch_no" in ssql and "dr_third_refinement" in ssql:  # noqa: E501
            r.fetchall.return_value = [SimpleNamespace(refinement_batch_no="DR-3-1", feed_batch_no="DR-F2-X")]  # noqa: E501
        elif "SELECT DISTINCT refinement_batch_no, feed_batch_no" in ssql and "dr_fourth_refinement" in ssql:  # noqa: E501
            r.fetchall.return_value = [SimpleNamespace(refinement_batch_no="DR-4-1", feed_batch_no="DR-F3-X")]  # noqa: E501
        else:
            r.fetchall.return_value = []
        return r

    s.execute.side_effect = branch
    resp = await dr.dr_loss_stats(session=s)
    data = json.loads(resp.body)["data"]
    assert len(data["by_segment_month"]) == 1
    assert data["by_segment_month"][0]["year_month"] == "2026.05"
    assert len(data["unclosed"]) == 2
    assert data["unclosed"][0]["reason"] == "三次投料在二次表查不到"


@pytest.mark.anyio
async def test_dr_loss_stats_empty():
    s = AsyncMock()
    s.execute.return_value = MagicMock(fetchall=lambda: [])
    resp = await dr.dr_loss_stats(session=s)
    data = json.loads(resp.body)["data"]
    assert data["by_segment_month"] == []
    assert data["unclosed"] == []


# ═══════════ dr_lineage_api 纯函数 ═══════════


def test_fmt_val():
    """格式化各种类型的值为浮点数。"""
    from app.modules.production import dr_lineage_api as dr

    assert dr.fmt_val(None) == 0.0
    assert dr.fmt_val(123) == 123.0
    assert dr.fmt_val(12.34) == 12.34
    assert dr.fmt_val("45.6") == 45.6


def test_to_f1_and_f1_to_dr():
    """F1 批号与 DR 批号的相互转换。"""
    from app.modules.production import dr_lineage_api as dr

    # _to_f1: DR-xxx → DR-F1-xxx
    assert dr._to_f1("DR-26026") == "DR-F1-26026"
    assert dr._to_f1("DR-24019-1") == "DR-F1-24019-1"
    assert dr._to_f1("DR-F1-26026") == "DR-F1-26026"  # 已经是 DR-F1 前缀

    # _f1_to_dr: DR-F1-xxx → DR-xxx
    assert dr._f1_to_dr("DR-F1-26026") == "DR-26026"
    assert dr._f1_to_dr("DR-F1-24019-1") == "DR-24019-1"
    assert dr._f1_to_dr("DR-26026") == "DR-26026"  # 不是 DR-F1 前缀，保持原样


def test_detect_stage():
    """根据批号前缀推断工段。"""
    from app.modules.production import dr_lineage_api as dr

    assert dr._detect_stage("DR-F1-xxx") == "first_refinement"
    assert dr._detect_stage("DR-F2-xxx") == "second_refinement"
    assert dr._detect_stage("DR-F3-xxx") == "third_refinement"
    assert dr._detect_stage("DR-GB-xxx") == "fourth_refinement"
    assert dr._detect_stage("DR-H-xxx") is None  # 回收粉特殊标签
    assert dr._detect_stage("DR-26026") is None  # 歧义，DB 探测
    assert dr._detect_stage("UNKNOWN") is None


def test_split_feeds_and_feed_stage():
    """拆分投料字符串并推断投料工段。"""
    from app.modules.production import dr_lineage_api as dr

    # _split_feeds - splits by +、顿号、逗号
    assert dr._split_feeds("DR-E1+DR-E2") == ["DR-E1", "DR-E2"]
    assert dr._split_feeds("DR-E1、DR-E2") == ["DR-E1", "DR-E2"]
    assert dr._split_feeds("DR-E1,DR-E2") == ["DR-E1", "DR-E2"]
    assert dr._split_feeds("") == []
    assert dr._split_feeds("DR-E1") == ["DR-E1"]

    # _feed_stage - returns "recovery" for unknown prefixes
    assert dr._feed_stage("DR-F1-xxx") == "first_refinement"
    assert dr._feed_stage("DR-F2-xxx") == "second_refinement"
    assert dr._feed_stage("DR-F3-xxx") == "third_refinement"
    assert dr._feed_stage("DR-GB-xxx") == "fourth_refinement"
    assert dr._feed_stage("DR-E1") == "recovery"  # unknown prefix → recovery
    assert dr._feed_stage("UNKNOWN") == "recovery"


# ═══════════ dr_lineage_api 异步函数（mock session） ═══════════


@pytest.mark.anyio
async def test_stage_exists():
    """_stage_exists: 查询表是否存在批号。"""
    from unittest.mock import MagicMock

    from app.modules.production import dr_lineage_api as dr

    # 存在的情况
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = ("row",)
    session.execute.return_value = result
    assert await dr._stage_exists(session, "fermentation", "DR-F1") is True

    # 不存在的情况
    result2 = MagicMock()
    result2.fetchone.return_value = None
    session.execute.return_value = result2
    assert await dr._stage_exists(session, "fermentation", "DR-UNKNOWN") is False


@pytest.mark.anyio
async def test_resolve_with_stage():
    """_resolve: 有明确 stage 时直接返回。"""
    from app.modules.production import dr_lineage_api as dr

    session = AsyncMock()
    # Mock _stage_exists to return True for fermentation
    with patch.object(dr, "_stage_exists", new=AsyncMock(return_value=True)):
        stage, batch = await dr._resolve(session, "fermentation", "DR-F1-xxx")
        assert stage == "fermentation"
        assert batch == "DR-F1-xxx"


@pytest.mark.anyio
async def test_resolve_with_detect():
    """_resolve: 无 stage 时通过前缀检测。"""
    from app.modules.production import dr_lineage_api as dr

    session = AsyncMock()
    # Mock _stage_exists to return True for second_refinement
    with patch.object(dr, "_stage_exists", new=AsyncMock(return_value=True)):
        stage, batch = await dr._resolve(session, "", "DR-F2-xxx")
        assert stage == "second_refinement"
        assert batch == "DR-F2-xxx"


@pytest.mark.anyio
async def test_resolve_fallback_probe():
    """_resolve: 前缀检测失败时逐表探测。"""
    from app.modules.production import dr_lineage_api as dr

    session = AsyncMock()
    # Mock _stage_exists to return False for first two stages, True for third
    call_count = [0]

    async def mock_stage_exists(session, stage, batch):
        call_count[0] += 1
        return call_count[0] >= 3  # 第三次返回 True

    with patch.object(dr, "_stage_exists", new=mock_stage_exists):
        stage, batch = await dr._resolve(session, "", "DR-26026")
        assert stage is not None
        assert batch == "DR-26026"


@pytest.mark.anyio
async def test_resolve_not_found():
    """_resolve: 所有探测都失败时返回 None。"""
    from app.modules.production import dr_lineage_api as dr

    session = AsyncMock()
    with patch.object(dr, "_stage_exists", new=AsyncMock(return_value=False)):
        stage, batch = await dr._resolve(session, "", "DR-UNKNOWN")
        assert stage is None
        assert batch is None


# ═══════════ fa_lineage_api._node_info ═══════════


@pytest.mark.anyio
async def test_fa_lineage_node_info_fermentation():
    """_node_info: fermentation 工段返回发酵数据。"""
    from app.modules.production import fa_lineage_api as fa

    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = SimpleNamespace(quantity=100.0)
    session.execute.return_value = result

    # Mock 发酵批次查询
    ferment_result = MagicMock()
    ferment_result.fetchone.return_value = SimpleNamespace(
        汇总总量_kg=500.0, 放罐体积_kl=200.0
    )

    def execute_side_effect(query, params=None):
        sql_str = str(query)
        if "fa_batch_lineage" in sql_str:
            return result
        elif "fa_fermentation_batches" in sql_str:
            return ferment_result
        return MagicMock(fetchone=lambda: None)

    session.execute.side_effect = execute_side_effect

    detail, yr, qty = await fa._node_info(session, "fermentation", "FA-EX1")
    assert "100kg" in detail  # quantity from lineage
    assert "200kl" in detail  # 放罐体积
    assert qty == 100.0


@pytest.mark.anyio
async def test_fa_lineage_node_info_acidification():
    """_node_info: acidification 工段返回酸化数据。"""
    from app.modules.production import fa_lineage_api as fa

    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = SimpleNamespace(quantity=80.0)

    acid_result = MagicMock()
    acid_result.fetchone.return_value = SimpleNamespace(max_qty=300.0)

    def execute_side_effect(query, params=None):
        sql_str = str(query)
        if "fa_batch_lineage" in sql_str:
            return result
        elif "fa_acidification_records" in sql_str:
            return acid_result
        return MagicMock(fetchone=lambda: None)

    session.execute.side_effect = execute_side_effect

    detail, yr, qty = await fa._node_info(session, "acidification", "FA-EX1")
    assert "膜滤300kg" in detail
    assert qty == 80.0


@pytest.mark.anyio
async def test_fa_lineage_node_info_decolor1():
    """_node_info: decolor1 工段返回脱色数据。"""
    from app.modules.production import fa_lineage_api as fa

    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = SimpleNamespace(quantity=60.0)

    decolor_result = MagicMock()
    decolor_result.fetchone.return_value = (150.0, 25.5)  # 体积, 碳后含量

    def execute_side_effect(query, params=None):
        sql_str = str(query)
        if "fa_batch_lineage" in sql_str:
            return result
        elif "fa_decolor1_records" in sql_str:
            return decolor_result
        return MagicMock(fetchone=lambda: None)

    session.execute.side_effect = execute_side_effect

    detail, yr, qty = await fa._node_info(session, "decolor1", "FA-EX1")
    assert "150kl" in detail
    assert "碳后25.5g/L" in detail
    assert qty == 60.0


@pytest.mark.anyio
async def test_fa_lineage_node_info_decolor_centrifuge():
    """_node_info: decolor_centrifuge 工段返回离心数据。"""
    from app.modules.production import fa_lineage_api as fa

    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = SimpleNamespace(quantity=50.0)

    centrifuge_result = MagicMock()
    centrifuge_result.fetchone.return_value = (120.0, 0.95)  # 进料体积, 收率

    def execute_side_effect(query, params=None):
        sql_str = str(query)
        if "fa_batch_lineage" in sql_str:
            return result
        elif "fa_decolor_centrifuge_records" in sql_str:
            return centrifuge_result
        return MagicMock(fetchone=lambda: None)

    session.execute.side_effect = execute_side_effect

    detail, yr, qty = await fa._node_info(session, "decolor_centrifuge", "FA-EX1")
    assert "120kl" in detail
    assert "收率95.0%" in detail
    assert yr == 95.0
    assert qty == 50.0
