"""FA 发酵液放罐 API 覆盖测试（SQL 全 mock）。"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.production import fa_api as api


def _parse(resp):
    return json.loads(resp.body)["data"]


def _batch(**over):
    data = dict(
        发酵罐号="FA-EX1",
        放罐日期=None,
        放罐体积_kl=10.0,
        放罐含量_gL=50.0,
        主批自身总量_kg=100.0,
        汇总总量_kg=300.0,
        电导_uscm=1.5,
        调酸量_L=2.0,
        酸化液滤速_ml10min=60.0,
        发酵液湿固=2.1,
        产量=280.0,
        收率=0.95,
        created_at=None,
        updated_at=None,
    )
    data.update(over)
    return SimpleNamespace(**data)


def _sub(**over):
    data = dict(
        id="sub-1",
        发酵批号="FA-EX1-1",
        父发酵罐号="FA-EX1",
        子批后缀="1",
        放罐体积_kl=5.0,
        放罐含量_gL=50.0,
        批总量_kg=150.0,
    )
    data.update(over)
    return SimpleNamespace(**data)


def _acid(**over):
    data = dict(
        id=1,
        日期=date(2026, 5, 10),
        批号="FA-A",
        发酵液体积_kl=10.0,
        发酵液含量_gL=50.0,
        发酵液罐产_kg=100.0,
        用酸量=20.0,
        PH酸化后=3.5,
        酸化液体积_kl=9.0,
        理论酸化液含量_gL=48.0,
        PH=3.6,
        膜滤液体积_KL=8.0,
        膜滤液含量_gL=47.0,
        膜滤液产品量_kg=376.0,
        膜滤液产品总量_kg=56.0,
        本批低单位含量_gL=3.0,
        本批低单位体积_KL=2.0,
        本批低单位苯产品_kg=6.0,
        本批低单位量_kg=4.0,
        上批套用低单位量_kg=5.0,
        批收率="85%",
        顶洗前体积_kl=7.0,
        尾液含量_gL=20.0,
        渣含量_gL=15.0,
        体积_罐渣膜渣_kl=3.0,
        渣产品量_kg=9.0,
        渣损失率="2%",
        渣体积_发酵液体积="0.1",
        酸化液_发酵液体积="0.9",
        滤液体积_发酵液体积="0.8",
        平衡率="0.95",
        消泡剂使用量_L=1.5,
    )
    data.update(over)
    return SimpleNamespace(**data)


def _decolor(**over):
    return SimpleNamespace(
        id=2,
        日期=date(2026, 5, 10),
        批号="FA-D1",
        体积_kl=20.0,
        含量_gL=45.0,
        电导_uscm=3000.0,
        调前电导碳柱=3100.0,
        混合含量_gL=44.0,
        母液体积_kl=15.0,
        母液含量_gL=40.0,
        电导2=2900.0,
        活性炭添加量_kg=5.0,
        碳后含量_gL=42.0,
        湿碳_kg=3.0,
        收率=0.95,
        产品量_kg=800.0,
        滤损失率=0.1,
        备注="ok",
        **over,
    )


def _mvr(**over):
    return SimpleNamespace(
        id=3,
        日期=date(2026, 5, 10),
        白班进料="10.0",
        白班出料="8.0",
        白班进料合计="18.0",
        白班进料累计合计="18.0",
        夜班进料="12.0",
        夜班出料="10.0",
        夜班进料合计="22.0",
        夜班进料累计合计="22.0",
        备注="x",
        **over,
    )


def _mother(**over):
    return SimpleNamespace(
        id=4,
        日期=date(2026, 5, 10),
        批号="M1",
        母液打料量="5.0",
        溶解体积="6.0",
        溶解含量="40.0",
        电导="8",
        ph="5",
        备注="y",
        **over,
    )


def _plate(**over):
    return SimpleNamespace(
        id=5,
        日期=date(2026, 5, 10),
        白班板框进料量="10",
        白班板框拆卸回收粉包数="3",
        白班分液罐投回收粉包数="2",
        白班分液罐体积="20",
        复滤粉拆包数="1",
        夜班板框进料量="12",
        夜班板框拆卸回收粉包数="4",
        夜班分液罐投回收粉包数="3",
        夜班分液罐体积="22",
        复滤粉拆包数夜="2",
        白班装车体积="25",
        废液槽接收体积="30",
        总进料体积="22",  # 20 覆盖分支也要走到
        累计进料体积="40",
        **over,
    )


def _count(scalar_val):
    r = MagicMock()
    r.scalar.return_value = scalar_val
    return r


def _scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _mappings(rows):
    r = MagicMock()
    r.mappings.return_value.all.return_value = rows
    return r


def _single(item):
    r = MagicMock()
    r.scalar_one_or_none.return_value = item
    return r


# ═══════════ list_batches ═══════════


@pytest.mark.anyio
async def test_list_batches_success_with_subs():
    s = AsyncMock()

    def exec(stmt, **kw):
        sql = str(stmt)
        if "count(*)" in sql and "fa_fermentation_batches" in sql:
            return _count(2)
        if "sub_batches" in sql:
            return _scalars([_sub()])
        if "fa_fermentation_batches" in sql:
            return _scalars(
                [_batch(), _batch(发酵罐号="FA-EX2", 放罐日期=date(2026, 5, 1))]
            )
        return _count(0)

    s.execute.side_effect = exec
    resp = await api.list_batches(page=1, page_size=5, tank_no=None, session=s)
    data = _parse(resp)
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert len(data["items"]) == 2
    assert data["items"][0]["发酵罐号"] == "FA-EX1"
    assert data["items"][0]["放罐日期"] is None
    assert data["items"][1]["放罐日期"] == "2026-05-01"
    # 每个主批都带子批列表（key 存在）
    assert "子批" in data["items"][0]


@pytest.mark.anyio
async def test_list_batches_tank_filter_and_empty():
    s = AsyncMock()

    def exec(stmt, **kw):
        sql = str(stmt)
        if "count(*)" in sql and "fa_fermentation_batches" in sql:
            return _count(0)
        if "sub_batches" in sql:
            return _scalars([])
        return _scalars([])

    s.execute.side_effect = exec
    resp = await api.list_batches(page=1, page_size=5, tank_no="abc", session=s)
    data = _parse(resp)
    assert data["total"] == 0
    assert data["items"] == []


# ═══════════ list_flat ═══════════


@pytest.mark.anyio
async def test_list_flat_success_flatten():
    s = AsyncMock()
    s.execute.side_effect = [
        _count(2),
        _scalars([_batch(), _batch(发酵罐号="FA-EX2", 放罐日期=date(2026, 5, 2))]),
        _scalars([_sub(), _sub(id="sub-2", 父发酵罐号="FA-EX2", 子批后缀="2")]),
    ]
    resp = await api.list_flat(page=1, page_size=10, tank_no=None, month=None, session=s)  # noqa: E501
    data = _parse(resp)
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["发酵罐号"] == "FA-EX1"
    assert data["items"][0]["子批后缀"] == "1"
    assert "_is_first" in data["items"][0]


@pytest.mark.anyio
async def test_list_flat_month_and_tank_filter_empty():
    s = AsyncMock()
    s.execute.side_effect = [
        _count(0),
        _scalars([]),
        _scalars([]),
    ]
    resp = await api.list_flat(page=1, page_size=5, tank_no=None, month=5, session=s)
    data = _parse(resp)
    assert data["items"] == []


# ═══════════ get_batch ═══════════


@pytest.mark.anyio
async def test_get_batch_found():
    s = AsyncMock()
    s.execute.return_value = _single(_batch())
    resp = await api.get_batch(tank_no="FA-EX1", session=s)
    data = _parse(resp)
    assert data["发酵罐号"] == "FA-EX1"
    assert "子批" in data


@pytest.mark.anyio
async def test_get_batch_not_found():
    s = AsyncMock()
    s.execute.return_value = _single(None)
    resp = await api.get_batch(tank_no="NOPE", session=s)
    assert json.loads(resp.body)["message"] == "记录不存在"
    assert resp.status_code == 404


# ═══════════ update_sub_batch ═══════════


@pytest.mark.anyio
async def test_update_sub_batch_not_found():
    s = AsyncMock()
    s.execute.return_value = _single(None)
    resp = await api.update_sub_batch(sub_id="x", data={}, session=s)
    assert json.loads(resp.body)["message"] == "子批不存在"
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_update_sub_batch_success():
    s = AsyncMock()
    s.execute.return_value = _single(_sub())
    s.commit = AsyncMock()
    resp = await api.update_sub_batch(sub_id="sub-1", data={"批总量_kg": 160.5}, session=s)  # noqa: E501
    data = _parse(resp)
    assert data["id"] == "sub-1"
    assert s.commit.await_count == 1


# ═══════════ list_acidification ═══════════


@pytest.mark.anyio
async def test_list_acidification_date_and_none():
    s = AsyncMock()
    s.execute.side_effect = [_count(2), _scalars([_acid(), _acid(id=6, 日期=None)])]
    resp = await api.list_acidification(page=1, page_size=5, batch_no="FA", month=5, session=s)  # noqa: E501
    data = _parse(resp)
    assert data["total"] == 2
    assert data["items"][0]["日期"] == "5月10日"
    assert data["items"][1]["日期"] is None
    assert data["items"][0]["发酵液体积（kl)"]


@pytest.mark.anyio
async def test_list_acidification_default_filters_empty():
    s = AsyncMock()
    s.execute.side_effect = [_count(0), _scalars([])]
    resp = await api.list_acidification(page=1, page_size=5, batch_no=None, month=None, session=s)  # noqa: E501
    data = _parse(resp)
    assert data["items"] == []
    assert data["total"] == 0


# ═══════════ list_decolor1 ═══════════


@pytest.mark.anyio
async def test_list_decolor1_fields():
    s = AsyncMock()
    s.execute.side_effect = [_count(1), _scalars([_decolor()])]
    resp = await api.list_decolor1(page=1, page_size=5, month=5, session=s)
    data = _parse(resp)
    assert data["items"][0]["批号"] == "FA-D1"
    assert data["items"][0]["日期"] == "5月10日"
    assert data["items"][0]["活性炭添加量(kg)"] == 5.0


@pytest.mark.anyio
async def test_list_decolor1_no_month_empty():
    s = AsyncMock()
    s.execute.side_effect = [_count(0), _scalars([])]
    resp = await api.list_decolor1(page=1, page_size=5, month=None, session=s)
    assert _parse(resp)["items"] == []


# ═══════════ list_mvr ═══════════


@pytest.mark.anyio
async def test_list_mvr_fields():
    s = AsyncMock()
    s.execute.side_effect = [_count(1), _scalars([_mvr()])]
    resp = await api.list_mvr(page=1, page_size=5, month=5, session=s)
    data = _parse(resp)
    assert data["items"][0]["白班进料/m3"] == "10.0"
    assert data["items"][0]["日期"] == "5月10日"


# ═══════════ list_mother_liquor ═══════════


@pytest.mark.anyio
async def test_list_mother_liquor_fields():
    s = AsyncMock()
    s.execute.side_effect = [_count(1), _scalars([_mother()])]
    resp = await api.list_mother_liquor(page=1, page_size=5, month=5, session=s)
    data = _parse(resp)
    assert data["items"][0]["批号"] == "M1"
    assert data["items"][0]["ph"] == "5"


# ═══════════ list_plate_recovery ═══════════


@pytest.mark.anyio
async def test_list_plate_recovery_fields():
    s = AsyncMock()
    s.execute.side_effect = [_count(1), _scalars([_plate()])]
    resp = await api.list_plate_recovery(page=1, page_size=5, month=5, session=s)
    data = _parse(resp)
    assert data["items"][0]["白班板框进料量/方"] == "10"
    assert data["items"][0]["日期"] == "5月10日"


# ═══════════ list_decolor_centrifuge ═══════════


@pytest.mark.anyio
async def test_list_decolor_centrifuge():
    rows = [
        {
            "id": 1,
            "日期": date(2026, 5, 10),
            "批号": "FA-C1",
            "进料体积（kl）": "100",
            "收率": "0.9",
        },
        {
            "id": 2,
            "日期": None,
            "批号": "FA-C2",
            "进料体积（kl）": None,
            "收率": None,
        },
    ]
    s = AsyncMock()
    s.execute.side_effect = [_count(2), _mappings(rows)]
    resp = await api.list_decolor_centrifuge(page=1, page_size=5, month=5, session=s)
    data = _parse(resp)
    assert data["total"] == 2
    assert data["items"][0]["日期"] == "5月10日"
    assert data["items"][1]["日期"] is None


@pytest.mark.anyio
async def test_list_decolor_centrifuge_no_month_empty():
    s = AsyncMock()
    s.execute.side_effect = [_count(0), _mappings([])]
    resp = await api.list_decolor_centrifuge(page=1, page_size=5, month=None, session=s)
    assert _parse(resp)["items"] == []


# ═══════════ list_intermediate ═══════════


@pytest.mark.anyio
async def test_list_intermediate():
    rows = [{"id": 1, "日期": date(2026, 5, 10), "当日母液总体积/方": "5", "合计570": "10"}]  # noqa: E501
    s = AsyncMock()
    s.execute.side_effect = [_count(1), _mappings(rows)]
    resp = await api.list_intermediate(page=1, page_size=5, month=5, session=s)
    data = _parse(resp)
    assert data["items"][0]["当日母液总体积/方"] == "5"
    assert data["items"][0]["日期"] == "5月10日"


# ═══════════ monthly_averages ═══════════


@pytest.mark.anyio
async def test_monthly_averages_unknown_table():
    resp = await api.monthly_averages(table="nope", session=AsyncMock())
    assert json.loads(resp.body)["message"] == "未知表: nope"
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_monthly_averages_success():
    col_rows = [("批收率",), ("created_at",), ("updated_at",), ("is_deleted",), ("电导_uscm",)]  # noqa: E501
    agg_row = {"月份": "5月", "批收率": 88.5}
    s = AsyncMock()
    s.execute.side_effect = [
        MagicMock(fetchall=lambda: col_rows),
        _mappings([agg_row]),
    ]
    resp = await api.monthly_averages(table="acidification_records", session=s)
    data = _parse(resp)
    assert data["columns"] == ["批收率", "电导_uscm"]
    assert data["data"][0]["月份"] == "5月"


@pytest.mark.anyio
async def test_monthly_averages_no_columns():
    s = AsyncMock()
    s.execute.side_effect = [MagicMock(fetchall=lambda: [])]
    resp = await api.monthly_averages(table="decolor1_records", session=s)
    data = _parse(resp)
    assert data["data"] == []
    assert data["columns"] == []


# ═══════════ trigger_fa_sync ═══════════


@pytest.mark.anyio
async def test_trigger_fa_sync_default_and_partial_error():
    s = AsyncMock()
    with patch(
        "app.modules.production.fa_feishu_scheduler.run_fa_sync",
        AsyncMock(return_value={"fermentation": {"error": "boom"}, "mvr": {"ok": 1}}),
    ):
        resp = await api.trigger_fa_sync({}, session=s)
    data = _parse(resp)
    assert data["errors"] == 1
    assert len(data["results"]) == 2
