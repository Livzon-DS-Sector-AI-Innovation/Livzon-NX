"""MC 全链路追溯 API 测试（SQL 全 mock，覆盖 BFS/兄弟/统计端点）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.modules.production import mc_lineage_api as api

_MISSING = object()


def make_fetch_result(
    fetchone: Any = _MISSING, fetchall: Any = _MISSING, scalar: Any = _MISSING
) -> Any:
    r = MagicMock()
    if fetchone is not _MISSING:
        r.fetchone.return_value = fetchone
    if fetchall is not _MISSING:
        r.fetchall.return_value = fetchall
    if scalar is not _MISSING:
        r.scalar.return_value = scalar
    return r


def make_iter_result(rows: Any) -> Any:
    r = MagicMock()
    r.__iter__.return_value = iter(rows)
    return r


def make_session(execute_results: Any) -> Any:
    s = AsyncMock()
    s.execute.side_effect = execute_results
    return s


def make_smart_session(router: Any) -> Any:
    """按 SQL 文本路由 execute 返回，避免查询顺序计数脆弱。"""
    s = AsyncMock()

    async def _execute(sql: Any, params: Any = None) -> Any:
        return router(str(sql), params)

    s.execute.side_effect = _execute
    return s


def trace_router(
    upstream_rows: Any,
    downstream_rows: Any,
    conn_rows: Any,
    yield_val: Any = 90.0,
    qty_val: Any = 100.0,
) -> Any:
    def _route(sql: Any, params: Any) -> Any:
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


def test_fmt_val() -> Any:
    assert api.fmt_val(None) == 0.0
    assert api.fmt_val(88.5) == 88.5


def test_normalize_batch() -> Any:
    assert api._normalize_batch("MC-1") == "MC-1"
    assert api._normalize_batch("MC-1 (FIS)") == "MC-1"
    assert api._normalize_batch("MC-1（Fis）") == "MC-1"
    assert api._normalize_batch("  MC-2  ") == "MC-2"


def test_fmt_detail() -> Any:
    assert api._fmt_detail({"y": 90.0, "q": 100}) == "yr90.0%, 100kg"
    assert api._fmt_detail({"yield_rate": 85.5, "quantity": 0}) == "yr85.5%"
    assert api._fmt_detail({"y": None, "q": None}) == ""
    assert api._fmt_detail({}) == ""


# ═══════════ _resolve_batch ═══════════


def test_resolve_batch_branches() -> Any:
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


def test_lineage_trace_simple_path() -> Any:
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


def test_lineage_trace_invalid_stage_400() -> Any:
    import asyncio

    # 非法工段且批号在任何业务表都探测不到时仍返回 400
    s = make_smart_session(probe_trace_router(hit_table=None, **EMPTY_ROWS))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.lineage_trace(batch_no="UNKNOWN-1", stage="bogus", session=s)
        )
    assert exc.value.status_code == 400


def test_lineage_trace_not_found_404() -> Any:
    import asyncio

    s = make_session([make_fetch_result(fetchone=None)])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.lineage_trace(batch_no="MC-9", stage="na_batch", session=s))
    assert exc.value.status_code == 404


def test_lineage_trace_with_upstream_and_downstream() -> Any:
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


def test_lineage_trace_with_sibling_expansion() -> Any:
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

    def _sibling_router(sql: Any, params: Any) -> Any:
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


def test_lineage_yield_distribution() -> Any:
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


def test_lineage_material_reuse() -> Any:
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


def test_lineage_coverage() -> Any:
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


def test_lineage_coverage_empty_total() -> Any:
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


# ═══════════ 自动层级探测（各追溯入口默认工段与批号不匹配时） ═══════════

_PROBE_TABLES = [
    "qc_inspections",
    "mc_refinement_records",
    "blending_records",
    "extraction_records",
    "sub_tank_records",
    "refining_batches",
    "fermentation_liquids",
]

EMPTY_ROWS = dict(
    has_link=False,
    upstream_rows=[],
    downstream_rows=[],
    conn_rows=[],
)


def probe_trace_router(
    hit_table: str | None,
    has_link: bool,
    upstream_rows: Any,
    downstream_rows: Any,
    conn_rows: Any,
    yield_val: Any = 90.0,
    qty_val: Any = 100.0,
) -> Any:
    """trace_router 之上叠加 _has_lineage/_probe_real_stage 查询路由。"""

    def _route(sql: Any, params: Any) -> Any:
        s = str(sql)
        if "batch_lineage WHERE (upstream_batch" in s and "LIMIT 1" in s:
            # _has_lineage：起点是否有血链关联
            row = SimpleNamespace(hit=1) if has_link else None
            return make_fetch_result(fetchone=row)
        for tbl in _PROBE_TABLES:
            if tbl in s and "LIMIT 1" in s:
                if tbl == hit_table:
                    bn = params.get("bn", "MC-1")
                    return make_fetch_result(fetchone=SimpleNamespace(batch_no=bn))
                return make_fetch_result(fetchone=None)
        if "upstream_batch = :b AND" in s:  # conn_map 查询
            return make_fetch_result(fetchall=conn_rows)
        if "downstream_batch = :batch" in s:  # _SIBLING_SQL（查上游）
            return make_fetch_result(fetchall=upstream_rows)
        if "upstream_batch = :batch" in s:  # _DOWNSTREAM_SQL（查下游）
            return make_fetch_result(fetchall=downstream_rows)
        if "quantity" in s:
            return make_fetch_result(fetchone=SimpleNamespace(quantity=qty_val))
        if "yield_rate" in s:
            return make_fetch_result(fetchone=SimpleNamespace(yield_rate=yield_val))
        return make_fetch_result(fetchall=[])

    return _route


def test_probe_real_stage_priority() -> Any:
    import asyncio

    # 探测按生产主链优先级：提炼最先，入库最后兜底
    order = [s for s, _ in api._PROBE_STAGE_SQL]
    assert order == [
        "refining",
        "fermentation",
        "sub_tank",
        "extraction",
        "refinement",
        "blending",
        "qc",
    ]

    # 单个业务表命中 → 返回对应层级与实际批号
    for tbl, stage in [
        ("refining_batches", "refining"),
        ("fermentation_liquids", "fermentation"),
        ("sub_tank_records", "sub_tank"),
        ("extraction_records", "extraction"),
        ("mc_refinement_records", "refinement"),
        ("blending_records", "blending"),
        ("qc_inspections", "qc"),
    ]:
        s = make_smart_session(
            probe_trace_router(hit_table=tbl, **EMPTY_ROWS)
        )
        assert asyncio.run(api._probe_real_stage(s, "MC-X")) == (
            stage,
            "MC-X",
        )

    # 全部未命中 → None
    s3 = make_smart_session(probe_trace_router(hit_table=None, **EMPTY_ROWS))
    assert asyncio.run(api._probe_real_stage(s3, "UNKNOWN-1")) is None


def test_lineage_trace_invalid_stage_probes_real_stage() -> Any:
    import asyncio

    # 页面遗留非法工段值（如粗提页 "crude"）：探测到提炼层级后正常追溯
    s = make_smart_session(
        probe_trace_router(hit_table="refining_batches", **EMPTY_ROWS)
    )
    resp = asyncio.run(
        api.lineage_trace(batch_no="MC-260709", stage="crude", session=s)
    )
    data = json.loads(resp.body)["data"]
    assert data["target_stage"] == "refining"
    stages = {sg["stage"] for sg in data["stages"]}
    assert "refining" in stages


def test_lineage_trace_mismatched_stage_probes_real_stage() -> Any:
    import asyncio

    # 追溯页默认工段 sub_tank 查询提炼批号：无血链关联 → 自动修正为 refining
    s = make_smart_session(
        probe_trace_router(hit_table="refining_batches", **EMPTY_ROWS)
    )
    resp = asyncio.run(
        api.lineage_trace(batch_no="MC-260709", stage="sub_tank", session=s)
    )
    data = json.loads(resp.body)["data"]
    assert data["target_stage"] == "refining"
    stages = {sg["stage"] for sg in data["stages"]}
    assert "refining" in stages


def test_lineage_trace_matched_stage_does_not_probe() -> Any:
    import asyncio

    # 显式层级与批号匹配（血链有关联）时保持原起点，不做探测
    s = make_smart_session(
        probe_trace_router(
            hit_table="extraction_records",
            has_link=True,
            upstream_rows=[],
            downstream_rows=[],
            conn_rows=[],
        )
    )
    resp = asyncio.run(
        api.lineage_trace(batch_no="MC-1", stage="extraction", session=s)
    )
    data = json.loads(resp.body)["data"]
    assert data["target_stage"] == "extraction"
