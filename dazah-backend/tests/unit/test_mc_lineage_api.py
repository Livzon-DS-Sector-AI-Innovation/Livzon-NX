"""MC 全链路追溯 API 测试（SQL 全 mock，覆盖 BFS/兄弟/统计端点）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.modules.production import mc_lineage_api as api

_MISSING = object()


def make_fetch_result(fetchone=_MISSING, fetchall=_MISSING, scalar=_MISSING):
    r = MagicMock()
    if fetchone is not _MISSING:
        r.fetchone.return_value = fetchone
    if fetchall is not _MISSING:
        r.fetchall.return_value = fetchall
    if scalar is not _MISSING:
        r.scalar.return_value = scalar
    return r


def make_iter_result(rows):
    r = MagicMock()
    r.__iter__.return_value = iter(rows)
    return r


def make_session(execute_results):
    s = AsyncMock()
    s.execute.side_effect = execute_results
    return s


def make_smart_session(router):
    """按 SQL 文本路由 execute 返回，避免查询顺序计数脆弱。"""
    s = AsyncMock()

    async def _execute(sql, params=None):
        return router(str(sql), params)

    s.execute.side_effect = _execute
    return s


def trace_router(
    upstream_rows, downstream_rows, conn_rows, yield_val=90.0, qty_val=100.0
):
    def _route(sql, params):
        if "upstream_batch = :b AND" in sql:  # conn_map 查询
            return make_fetch_result(fetchall=conn_rows)
        if "downstream_batch = :batch" in sql:  # _SIBLING_SQL（查上游）
            return make_fetch_result(fetchall=upstream_rows)
        if "upstream_batch = :batch" in sql:  # _DOWNSTREAM_SQL（查下游）
            return make_fetch_result(fetchall=downstream_rows)
        if "quantity" in sql:
            return make_fetch_result(fetchone=SimpleNamespace(quantity=qty_val))
        if "yield_rate" in sql:
            return make_fetch_result(fetchone=SimpleNamespace(yield_rate=yield_val))
        return make_fetch_result(fetchall=[])

    return _route


# ═══════════ 纯辅助 ═══════════


def test_fmt_val():
    assert api.fmt_val(None) == 0.0
    assert api.fmt_val(88.5) == 88.5


def test_normalize_batch():
    assert api._normalize_batch("MC-1") == "MC-1"
    assert api._normalize_batch("MC-1 (FIS)") == "MC-1"
    assert api._normalize_batch("MC-1（Fis）") == "MC-1"
    assert api._normalize_batch("  MC-2  ") == "MC-2"


def test_fmt_detail():
    assert api._fmt_detail({"y": 90.0, "q": 100}) == "yr90.0%, 100kg"
    assert api._fmt_detail({"yield_rate": 85.5, "quantity": 0}) == "yr85.5%"
    assert api._fmt_detail({"y": None, "q": None}) == ""
    assert api._fmt_detail({}) == ""


# ═══════════ _resolve_batch ═══════════


def test_resolve_batch_branches():
    import asyncio

    s = make_session([make_fetch_result(fetchone=SimpleNamespace(batch_no="MC-1"))])
    assert asyncio.run(api._resolve_batch("na_batch", "MC-1", s)) == (
        "sub_tank",
        "MC-1",
    )
    s = make_session([make_fetch_result(fetchone=None)])
    assert asyncio.run(api._resolve_batch("crude_product", "MC-9", s)) == (None, None)
    s = make_session([make_fetch_result(fetchone=SimpleNamespace(batch_no="MC-E1"))])
    assert asyncio.run(api._resolve_batch("wet_powder", "MC-E1", s)) == (
        "extraction",
        "MC-E1",
    )
    s = make_session([make_fetch_result(fetchone=SimpleNamespace(batch_no="MC-Q1"))])
    assert asyncio.run(api._resolve_batch("front_batch", "MC-Q1", s)) == ("qc", "MC-Q1")
    assert asyncio.run(api._resolve_batch("single_batch_blend", "MC-F2-1", s)) == (
        "refinement",
        "MC-F2-1",
    )
    assert asyncio.run(api._resolve_batch("single_batch_qc", "B1", s)) == (
        "blending",
        "B1",
    )
    assert asyncio.run(api._resolve_batch("extraction", "MC-1 (FIS)", s)) == (
        "extraction",
        "MC-1",
    )


# ═══════════ lineage_trace ═══════════


def test_lineage_trace_simple_path():
    import asyncio

    s = make_smart_session(trace_router([], [], []))
    resp = asyncio.run(
        api.lineage_trace(batch_no="MC-1", stage="extraction", session=s)
    )
    data = json.loads(resp.body)["data"]
    assert data["target_stage"] == "extraction"
    assert data["cumulative_yield"] == 90.0
    assert data["max_loss_stage"] == "extraction"
    assert len(data["stages"]) == 1
    node = data["stages"][0]["nodes"][0]
    assert node["batch_no"] == "MC-1"
    assert node["detail"] == "yr90.0%, 100kg"


def test_lineage_trace_invalid_stage_400():
    import asyncio

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.lineage_trace(batch_no="MC-1", stage="bogus", session=make_session([]))
        )
    assert exc.value.status_code == 400


def test_lineage_trace_not_found_404():
    import asyncio

    s = make_session([make_fetch_result(fetchone=None)])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.lineage_trace(batch_no="MC-9", stage="na_batch", session=s))
    assert exc.value.status_code == 404


def test_lineage_trace_with_upstream_and_downstream():
    import asyncio

    s = make_smart_session(
        trace_router(
            [
                SimpleNamespace(
                    upstream_type="sub_tank",
                    upstream_batch="MC-S1",
                    yield_rate=85.0,
                    quantity=200,
                )
            ],
            [
                SimpleNamespace(
                    downstream_type="blending",
                    downstream_batch="B1",
                    yield_rate=95.0,
                    quantity=10,
                )
            ],
            [],
        )
    )
    resp = asyncio.run(
        api.lineage_trace(
            batch_no="MC-1", stage="extraction", include_siblings=True, session=s
        )
    )
    data = json.loads(resp.body)["data"]
    stages = {sg["stage"]: sg for sg in data["stages"]}
    assert "sub_tank" in stages
    assert "blending" in stages
    assert stages["sub_tank"]["nodes"][0]["batch_no"] == "MC-S1"
    assert stages["blending"]["nodes"][0]["batch_no"] == "B1"
    # 按工段顺序连乘首个节点收率：0.85 × 0.9 × 0.95
    assert data["cumulative_yield"] == 72.7


def test_lineage_trace_with_sibling_expansion():
    import asyncio

    sibling_rows = [
        SimpleNamespace(
            upstream_type="sub_tank",
            upstream_batch="MC-S1",
            yield_rate=88.0,
            quantity=50,
        )
    ]
    sib_dn_rows = [
        SimpleNamespace(
            downstream_type="extraction",
            downstream_batch="MC-E9",
            yield_rate=90.0,
            quantity=0,
        )
    ]
    dn_rows = [
        SimpleNamespace(
            downstream_type="blending",
            downstream_batch="B1",
            yield_rate=95.0,
            quantity=10,
        )
    ]

    def _sibling_router(sql, params):
        if "upstream_batch = :b AND" in sql:  # conn_map
            return make_fetch_result(fetchall=[])
        if "downstream_batch = :batch" in sql:  # _SIBLING_SQL
            if "B1" in str(params or {}):
                return make_fetch_result(fetchall=sibling_rows)
            return make_fetch_result(fetchall=[])
        if "upstream_batch = :batch" in sql:  # _DOWNSTREAM_SQL
            if "MC-S1" in str(params or {}):
                return make_fetch_result(fetchall=sib_dn_rows)
            return make_fetch_result(fetchall=dn_rows)
        if "quantity" in sql:
            return make_fetch_result(fetchone=SimpleNamespace(quantity=100))
        return make_fetch_result(fetchone=SimpleNamespace(yield_rate=90.0))

    s = make_smart_session(_sibling_router)
    resp = asyncio.run(
        api.lineage_trace(
            batch_no="MC-1", stage="extraction", include_siblings=True, session=s
        )
    )
    data = json.loads(resp.body)["data"]
    sib_nodes = [n for sg in data["stages"] for n in sg["nodes"] if n.get("is_sibling")]
    assert any(n["batch_no"] == "MC-S1" for n in sib_nodes)
    assert any(n["batch_no"] == "MC-E9" for n in sib_nodes)
    assert any("50kg" in (n.get("connects_to") or "") for n in sib_nodes)


# ═══════════ 统计端点 ═══════════


def test_lineage_yield_distribution():
    import asyncio

    s = make_session(
        [
            make_iter_result(
                [
                    SimpleNamespace(
                        stage="sub_tank",
                        n=5,
                        min_y=80.0,
                        q1=85.0,
                        median=90.0,
                        mean=89.0,
                        q3=93.0,
                        max_y=95.0,
                        below_80=1,
                        above_110=0,
                    ),
                    SimpleNamespace(
                        stage="extraction",
                        n=3,
                        min_y=70.0,
                        q1=75.0,
                        median=80.0,
                        mean=79.0,
                        q3=83.0,
                        max_y=88.0,
                        below_80=2,
                        above_110=0,
                    ),
                ]
            )
        ]
    )
    resp = asyncio.run(api.lineage_yield_distribution(session=s))
    data = json.loads(resp.body)["data"]
    assert len(data) == 2
    assert data[0]["stage"] == "sub_tank"
    assert data[0]["median"] == 90.0
    assert data[0]["label"] == "钠化批号"
    assert data[1]["below_80"] == 2


def test_lineage_material_reuse():
    import asyncio

    s = make_session(
        [
            make_iter_result(
                [
                    SimpleNamespace(
                        upstream_type="sub_tank",
                        upstream_batch="MC-S1",
                        usage_count=3,
                        used_by="B1, B2",
                    ),
                ]
            )
        ]
    )
    resp = asyncio.run(api.lineage_material_reuse(session=s))
    data = json.loads(resp.body)["data"]
    assert data[0]["usage_count"] == 3
    assert data[0]["used_by"] == "B1, B2"


def test_lineage_coverage():
    import asyncio

    s = make_session(
        [
            make_iter_result([SimpleNamespace(seg="sub_tank -> extraction", n=4)]),
            make_fetch_result(scalar=10),
            make_fetch_result(scalar=2),
        ]
    )
    resp = asyncio.run(api.lineage_coverage(session=s))
    data = json.loads(resp.body)["data"]
    assert data["segments"][0]["count"] == 4
    assert data["extraction_total"] == 10
    assert data["extraction_missing"] == 2
    assert data["extraction_coverage_pct"] == 80.0


def test_lineage_coverage_empty_total():
    import asyncio

    s = make_session(
        [
            make_iter_result([]),
            make_fetch_result(scalar=0),
            make_fetch_result(scalar=0),
        ]
    )
    resp = asyncio.run(api.lineage_coverage(session=s))
    data = json.loads(resp.body)["data"]
    assert data["extraction_coverage_pct"] == 0
