"""DR 模块覆盖率补充测试：dr_api / dr_schedule_api / dr_lineage_api 未覆盖分支。

全部使用 mock session / mock excel，不触碰真实数据库或网络。

约定：
- 直接调用路由函数（async）并解析 JSONResponse.body；
- 用 AsyncMock + MagicMock Result 模拟 `session.execute` 的各类取值。
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.modules.production import dr_api as dra
from app.modules.production import dr_lineage_api as drl
from app.modules.production import dr_schedule_api as drs

# ── mock 结果构造 ──────────────────────────────────


def _scalars(rows) -> MagicMock:
    """Result: scalars().all() 返回 rows。"""
    r = MagicMock()
    scalar = MagicMock()
    r.scalars.return_value = scalar
    scalar.all.return_value = rows
    return r


def _fetchone(v) -> MagicMock:
    r = MagicMock()
    r.fetchone.return_value = v
    return r


def _fetchall(v) -> MagicMock:
    r = MagicMock()
    r.fetchall.return_value = v
    return r


def _scalar(v) -> MagicMock:
    r = MagicMock()
    r.scalar.return_value = v
    return r


def _scalar_one(v) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = v
    return r


def _session() -> AsyncMock:
    return AsyncMock()


class _FakeFile:
    """模拟 schedule_data 下生效的排产文件。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def stat(self) -> SimpleNamespace:
        return SimpleNamespace(st_mtime=1700000000.0)


class _FakeSheet:
    """二维列表模拟 openpyxl Worksheet 读写。"""

    def __init__(self, rows: list[list]) -> None:
        self.rows = rows
        self.title = "2026.08.20排产"

    @property
    def max_row(self) -> int:
        return len(self.rows)

    @property
    def max_column(self) -> int:
        return max(len(r) for r in self.rows)

    def cell(self, r: int, c: int):
        row = self.rows[r - 1]
        val = row[c - 1] if c - 1 < len(row) else None
        return SimpleNamespace(value=val)


class _FakeUpload:
    def __init__(self, filename: str | None, content: bytes) -> None:
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


# ═════════════════════════════════════════════════════════
# dr_api — 萃取工段完整嵌套 + 年份 + 各台账 CRUD + 仪表盘
# ═════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_get_dr_extraction_full_empty_batches():
    """批次为空 → 立即返回 []。"""
    s = _session()
    s.execute.return_value = _scalars([])
    resp = await dra.get_dr_extraction_full(year=None, month=None, session=s)
    assert json.loads(resp.body)["data"] == []


@pytest.mark.anyio
async def test_get_dr_extraction_full_no_children():
    """有批次但无罐/萃取/滤液 → 空嵌套、rowspan=0。"""
    batch = SimpleNamespace(
        id="b1", batch_no="DR-26026", workshop="201-3", tank_date="2026.08.20",
        impurity_6=None, impurity_1=0.1, impurity_2=0.2, impurity_7=0.3,
        impurity_3=0.4, impurity_4=None, impurity_5=0.5, rrt_068=None,
        unknown_max_single=0.6, total_impurities=1.4, purity=99.1,
    )
    s = _session()
    s.execute.side_effect = [
        _scalars([batch]),
        _scalars([]),
        _scalars([]),
        _scalars([]),
    ]
    resp = await dra.get_dr_extraction_full(year=2026, month=8, session=s)
    data = json.loads(resp.body)["data"]
    assert len(data) == 1
    assert data[0]["tanks"] == []
    assert data[0]["rowspan"] == 0
    assert data[0]["impurities"]["purity"] == 99.1


@pytest.mark.anyio
async def test_get_dr_extraction_full_nested():
    """批次→罐→萃取→滤液 全量嵌套 + 杂质 + rowspan。"""
    rec = SimpleNamespace(
        id="b1", batch_no="DR-26026", workshop="201-3", tank_date="2026.08.20",
        impurity_6=None, impurity_1=0.1, impurity_2=0.2, impurity_7=0.3,
        impurity_3=0.4, impurity_4=None, impurity_5=0.5, rrt_068=None,
        unknown_max_single=0.6, total_impurities=1.4, purity=99.5, remarks="ok",
    )
    tank = SimpleNamespace(
        id="t1", fermentation_batch_id="b1", tank_no="B401",
    )
    extr = SimpleNamespace(
        id="e1", fermentation_tank_id="t1", extraction_batch_no="DR-26026-1",
        total_qty=100.0,
    )
    filtr = SimpleNamespace(extraction_id="e1", tank_no="F1", volume=10.0)
    s = _session()
    s.execute.side_effect = [
        _scalars([rec]),
        _scalars([tank]),
        _scalars([extr]),
        _scalars([filtr]),
    ]
    data = json.loads(
        (await dra.get_dr_extraction_full(year=None, month=None, session=s)).body
    )["data"]
    first = data[0]
    assert first["batch_no"] == "DR-26026"
    assert first["rowspan"] == 1
    assert first["impurities"]["impurity_1"] == 0.1
    assert first["tanks"][0]["tank_no"] == "B401"
    assert first["tanks"][0]["rowspan"] == 1
    assert first["tanks"][0]["extractions"][0]["filtrates"][0]["tank_no"] == "F1"


@pytest.mark.anyio
async def test_get_dr_extraction_years():
    """年份：过滤非数字年份并按升序返回。"""
    s = _session()
    s.execute.return_value = _scalars(["2021", "2020", "abc", "2026"])
    data = json.loads((await dra.get_dr_extraction_years(session=s)).body)["data"]
    assert data == [2020, 2021, 2026]


@pytest.mark.anyio
async def test_list_dr_batches():
    """批次分页列表 + batch_no 模糊过滤。"""
    s = _session()
    s.execute.side_effect = [
        _scalar_one(2),
        _scalars(
            [
                SimpleNamespace(id="b1", batch_no="DR-1", workshop="201-3"),
                SimpleNamespace(id="b2", batch_no="DR-2", workshop="201-3"),
            ]
        ),
    ]
    resp = await dra.list_dr_batches(
        page=1, page_size=10, batch_no="DR", workshop="201-3", session=s
    )
    body = json.loads(resp.body)
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 2


@pytest.mark.anyio
async def test_create_update_delete_dr_batch():
    """创建 / 更新 / 删除发酵批次（含不存在路径）。"""
    s = _session()
    resp = await dra.create_dr_batch(
        {"batch_no": "DR-26027", "workshop": "201-3"}, session=s
    )
    assert json.loads(resp.body)["data"]["batch_no"] == "DR-26027"
    s.add.assert_called_once()
    s.commit.assert_awaited()

    s2 = _session()
    s2.get.return_value = SimpleNamespace(id="rid", is_deleted=False)
    resp2 = await dra.update_dr_batch(
        record_id="rid", data={"batch_no": "DR-26027-new"}, session=s2
    )
    assert json.loads(resp2.body)["message"] == "更新成功"

    s3 = _session()
    s3.get.return_value = None
    resp3 = await dra.update_dr_batch(
        record_id="nope", data={"batch_no": "x"}, session=s3
    )
    assert json.loads(resp3.body)["code"] == 404
    assert json.loads(resp3.body)["message"] == "记录不存在"

    s4 = _session()
    s4.get.return_value = None
    resp4 = await dra.delete_dr_batch(record_id="gone", session=s4)
    assert json.loads(resp4.body)["code"] == 404

    s5 = _session()
    s5.get.return_value = SimpleNamespace(id="rid", is_deleted=False)
    resp5 = await dra.delete_dr_batch(record_id="rid", session=s5)
    assert json.loads(resp5.body)["message"] == "删除成功"
    assert s5.commit.assert_awaited is not None


@pytest.mark.anyio
async def test_dr_tank_crud():
    """发酵罐 list/create/update/delete。"""
    s = _session()
    s.execute.return_value = _scalars(
        [SimpleNamespace(id="t1", tank_no="B401", fermentation_batch_id="b1")]
    )
    data = json.loads((await dra.list_dr_tanks("b1", session=s)).body)["data"]
    assert data[0]["tank_no"] == "B401"

    s2 = _session()
    resp = await dra.create_dr_tank(
        {"tank_no": "B402", "fermentation_batch_id": "b1"}, session=s2
    )
    assert json.loads(resp.body)["data"]["id"]

    s3 = _session()
    s3.get.return_value = SimpleNamespace(id="t1", is_deleted=False)
    resp3 = await dra.update_dr_tank(
        "t1", {"tank_no": "B401"}, session=s3
    )
    assert json.loads(resp3.body)["message"] == "更新成功"

    s4 = _session()
    s4.get.return_value = None
    resp4 = await dra.update_dr_tank("miss", {"tank_no": "x"}, session=s4)
    assert json.loads(resp4.body)["code"] == 404

    s5 = _session()
    s5.get.return_value = None
    resp5 = await dra.delete_dr_tank("gone", session=s5)
    assert json.loads(resp5.body)["code"] == 404

    s6 = _session()
    s6.get.return_value = SimpleNamespace(id="t1", is_deleted=False)
    resp6 = await dra.delete_dr_tank("t1", session=s6)
    assert json.loads(resp6.body)["message"] == "删除成功"


@pytest.mark.anyio
async def test_dr_extraction_crud():
    """萃取列表/create/update/delete。"""
    s = _session()
    s.execute.return_value = _scalars(
        [SimpleNamespace(id="e1", extraction_batch_no="E1", fermentation_tank_id="t1")]
    )
    data = json.loads((await dra.list_dr_extractions("t1", session=s)).body)["data"]
    assert data[0]["extraction_batch_no"] == "E1"

    s2 = _session()
    resp = await dra.create_dr_extraction(
        {"extraction_batch_no": "E2", "fermentation_tank_id": "t1"}, session=s2
    )
    assert json.loads(resp.body)["data"]["id"]

    s3 = _session()
    s3.get.return_value = SimpleNamespace(id="e1", is_deleted=False)
    resp3 = await dra.update_dr_extraction("e1", {"total_qty": 1.0}, session=s3)
    assert json.loads(resp3.body)["message"] == "更新成功"

    s4 = _session()
    s4.get.return_value = None
    resp4 = await dra.update_dr_extraction("miss", {"x": 1}, session=s4)
    assert json.loads(resp4.body)["code"] == 404

    s5 = _session()
    s5.get.return_value = None
    resp5 = await dra.delete_dr_extraction("gone", session=s5)
    assert json.loads(resp5.body)["code"] == 404

    s6 = _session()
    s6.get.return_value = SimpleNamespace(id="e1", is_deleted=False)
    resp6 = await dra.delete_dr_extraction("e1", session=s6)
    assert json.loads(resp6.body)["message"] == "删除成功"


@pytest.mark.anyio
async def test_dr_filtrate_crud():
    """滤液列表/create/update/delete。"""
    s = _session()
    s.execute.return_value = _scalars(
        [SimpleNamespace(id="f1", extraction_id="e1", tank_no="F1")]
    )
    data = json.loads((await dra.list_dr_filtrates("e1", session=s)).body)["data"]
    assert data[0]["tank_no"] == "F1"

    s2 = _session()
    resp = await dra.create_dr_filtrate(
        {"extraction_id": "e1", "volume": 5.0}, session=s2
    )
    assert json.loads(resp.body)["data"]["id"]

    s3 = _session()
    s3.get.return_value = SimpleNamespace(id="f1", is_deleted=False)
    resp3 = await dra.update_dr_filtrate("f1", {"volume": 6.0}, session=s3)
    assert json.loads(resp3.body)["message"] == "更新成功"

    s4 = _session()
    s4.get.return_value = None
    resp4 = await dra.update_dr_filtrate(
        "miss", {"volume": 1.0}, session=s4
    )
    assert json.loads(resp4.body)["code"] == 404

    s5 = _session()
    s5.get.return_value = None
    resp5 = await dra.delete_dr_filtrate("gone", session=s5)
    assert json.loads(resp5.body)["code"] == 404

    s6 = _session()
    s6.get.return_value = SimpleNamespace(id="f1", is_deleted=False)
    resp6 = await dra.delete_dr_filtrate("f1", session=s6)
    assert json.loads(resp6.body)["message"] == "删除成功"


@pytest.mark.anyio
async def test_get_dr_dashboard_default_month():
    """仪表盘：默认当月 + 跨 12 月的结束日期分支。"""
    s = _session()
    count = MagicMock()
    count.scalar_one.return_value = 3
    month_ok = MagicMock()
    month_ok.scalar_one.return_value = 4
    s.execute.side_effect = [count] + [month_ok] * 12
    data = json.loads(
        (await dra.get_dr_dashboard(month=None, workshop="201-3", session=s)).body
    )["data"]
    assert data["monthly_batches"] == 3
    assert len(data["monthly_trend"]) == 12
    assert data["monthly_output_kg"] == 0.0

    s2 = _session()
    count2 = MagicMock()
    count2.scalar_one.return_value = 3
    month2 = MagicMock()
    month2.scalar_one.return_value = 4
    s2.execute.side_effect = [count2] + [month2] * 12
    resp2 = await dra.get_dr_dashboard(
        month="2026-12", workshop="201-3", session=s2
    )
    data2 = json.loads(resp2.body)["data"]
    assert data2["_month"] == "2026-12"


@pytest.mark.anyio
async def test_get_dr_record_years():
    """台账年份：未知表 400、无 production_date 表、有效年份。"""
    s = _session()
    resp = await dra.get_dr_record_years(
        table="dr_unknown", session=s
    )
    body = json.loads(resp.body)
    assert body["code"] == 400
    assert "未知表" in body["message"]

    # 无 production_date 属性 → 早期返回 []
    with patch.dict(dra.DR_TABLES, {"dr_fake_model": SimpleNamespace(is_deleted=True)}):
        s2 = _session()
        resp2 = await dra.get_dr_record_years(table="dr_fake_model", session=s2)
        assert json.loads(resp2.body)["data"] == []

    s3 = _session()
    s3.execute.return_value = _scalars(["2026", "2021", "xx"])
    data = json.loads(
        (await dra.get_dr_record_years(table="dr_chromatography_crystal", session=s3)).body  # noqa: E501
    )["data"]
    assert data == [2021, 2026]


@pytest.mark.anyio
async def test_get_dr_records():
    """通用台账查询：未知表 / 年月筛选 / 排序 / 分页。"""
    s = _session()
    resp = await dra.get_dr_records(table="dr_bad", session=s)
    assert json.loads(resp.body)["code"] == 400

    s2 = _session()
    count_res = MagicMock()
    count_res.scalar_one.return_value = 3
    rows_res = _scalars(
        [
            SimpleNamespace(row_no=1, production_date="2026.08.20", batch_no="X"),
            SimpleNamespace(row_no=2, production_date="2026.09.01"),
        ]
    )
    s2.execute.side_effect = [count_res, rows_res]
    resp2 = await dra.get_dr_records(
        table="dr_chromatography_crystal",
        page=1,
        page_size=20,
        year=2026,
        month=8,
        session=s2,
    )
    body = json.loads(resp2.body)["data"]
    assert body["total"] == 3
    assert body["items"][0]["batch_no"] == "X"

    s3 = _session()
    count3 = MagicMock()
    count3.scalar_one.return_value = 1
    s3.execute.side_effect = [count3, rows_res]
    resp3 = await dra.get_dr_records(
        table="dr_second_refinement",
        page=1,
        page_size=20,
        year=None,
        month=None,
        session=s3,
    )
    assert json.loads(resp3.body)["data"]["total"] == 1


# ═════════════════════════════════════════════════════════
# dr_schedule_api — 排产解析 / 接罐任务同步 / 确认审批
# ═════════════════════════════════════════════════════════


def test_pick_latest_sheet():
    """pick_latest_sheet：取日期最大版本；无日期取第一个。"""
    wb = MagicMock()
    ws1 = SimpleNamespace()
    ws1.title = "排产2026.08.20"
    ws2 = SimpleNamespace()
    ws2.title = "排产2026.08.30"
    wb.worksheets = [ws1, ws2]
    assert drs._pick_latest_sheet(wb) is ws2

    wb2 = MagicMock()
    wb2.worksheets = [SimpleNamespace(title="无日期") , SimpleNamespace(title="A")]
    out = drs._pick_latest_sheet(wb2)
    assert out.title == "无日期"

    wb3 = MagicMock()
    wb3.worksheets = []
    assert drs._pick_latest_sheet(wb3) is None


def test_parse_dump_plans():
    """解析「放罐」行：泵批号 + 下一行罐号 + 纯数字罐号补 B 前缀。"""
    rows = [
        ["2026年8月多拉计划", "", "", "", ""],
        ["放罐", "DR-26030", "中试-1", None, "DR-315"],
        ["", "304", "B205", "", "304"],
    ]
    ws = _FakeSheet(rows)
    plans = drs._parse_dump_plans(ws)
    assert (2026, 8, 1, "DR-26030", "B304") in plans
    assert (2026, 8, 2, "中试-1", "B205") in plans
    assert (2026, 8, 4, "DR-315", "B304") in plans


@pytest.mark.anyio
async def test_sync_receiving_tasks():
    """同步接任务：新批建 / pending 更新 / 非法日期跳过 / 终态不动。"""
    s = _session()

    async def _exec(sql, params=None):
        r = MagicMock()
        s_str = str(sql)
        if "SELECT id, status FROM production.receiving_task" in s_str:
            b = params["b"]
            if b == "DR-NEW":
                r.fetchone.return_value = None
            elif b == "DR-PENDING":
                r.fetchone.return_value = (7, "pending")
            else:  # confirmed 等终态 → 不动
                r.fetchone.return_value = (8, "confirmed")
        return r

    s.execute.side_effect = _exec
    await drs._sync_receiving_tasks(
        s,
        [
            (2026, 8, 25, "DR-NEW", "B1"),
            (2026, 2, 99, "DR-BAD", "B2"),  # ValueError → continue
            (2026, 8, 26, "DR-PENDING", "B2"),
            (2026, 8, 27, "DR-CONFIRMED", "B3"),
        ],
    )
    s.commit.assert_awaited()
    executed = [str(c.args[0]) for c in s.execute.await_args_list]
    assert any("INSERT INTO" in q for q in executed)
    assert any("UPDATE production.receiving_task SET" in q for q in executed)


@pytest.mark.anyio
async def test_receiving_task_map():
    """批号 → 任务状态映射。"""
    s = _session()
    s.execute.return_value = _fetchall(
        [
            ("DR-1", "confirmed", "2026-08-20 09:00:00", "张三", "B304", "", None),
            ("DR-2", "pending", None, None, None, None, None),
        ]
    )
    m = await drs._receiving_task_map(s)
    assert m["DR-1"]["task_status"] == "confirmed"
    assert m["DR-1"]["actual_tank_no"] == "B304"
    assert m["DR-2"]["task_status"] == "pending"


@pytest.mark.anyio
async def test_dump_plans_no_files():
    """无排产文件 → version=None。"""
    fake = MagicMock()
    fake.glob.return_value = []
    with patch.object(drs, "_SCHEDULE_DIR", fake):
        resp = await drs.dr_dump_plans(session=_session())
    data = json.loads(resp.body)["data"]
    assert data["version"] is None
    assert data["items"] == []


@pytest.mark.anyio
async def test_dump_plans_no_plans():
    """有文件但解析无放罐行 → version 返回，items 空。"""
    fake = MagicMock()
    fake.glob.return_value = [_FakeFile("plan.xlsx")]
    s = AsyncMock()
    with patch.object(drs, "_SCHEDULE_DIR", fake), patch(
        "openpyxl.load_workbook",
        return_value=SimpleNamespace(title="wb"),
    ), patch.object(drs, "_pick_latest_sheet", return_value=SimpleNamespace(title="2026.08.20")), patch.object(  # noqa: E501
        drs, "_parse_dump_plans", return_value=[]
    ), patch.object(drs, "_sync_receiving_tasks", new=AsyncMock()):
        resp = await drs.dr_dump_plans(session=s)
    data = json.loads(resp.body)["data"]
    assert data["version"]["file"] == "plan.xlsx"
    assert data["items"] == []


@pytest.mark.anyio
async def test_dump_plans_full():
    """全量放行：DB 批号命中 + 任务状态 + 日期筛选 + summary。"""
    s = _session()

    async def _exec(sql, params=None):
        r = MagicMock()
        sql_str = str(sql)
        if "SELECT DISTINCT batch_no FROM production.dr_fermentation_batches" in sql_str:  # noqa: E501
            r.fetchall.return_value = [("DR-1",)]
        elif "SELECT batch_no, status, " in sql_str:
            r.fetchall.return_value = [
                ("DR-1", "confirmed", "2026-08-20 09:00:00", "张三", "B304", "", None)
            ]
        return r

    s.execute.side_effect = _exec
    fake = MagicMock()
    fake.glob.return_value = [_FakeFile("plan.xlsx")]
    plans = [
        (2020, 6, 1, "中试-OLD", "B2"),  # < from_date 被过滤
        (2026, 3, 1, "DR-1", "B1"),
        (2031, 1, 1, "ZS-1", "B1"),
        (2032, 1, 1, "DR-FUTURE", "B2"),
    ]
    with patch.object(drs, "_SCHEDULE_DIR", fake), patch(
        "openpyxl.load_workbook", return_value=MagicMock()
    ), patch.object(
        drs, "_pick_latest_sheet", return_value=SimpleNamespace(title="2026.08.20")
    ), patch.object(drs, "_parse_dump_plans", return_value=plans), patch.object(
        drs, "_sync_receiving_tasks", new=AsyncMock()
    ):
        resp = await drs.dr_dump_plans(
            session=s, from_date="2021-01-01", to_date="2035-12-31"
        )
    data = json.loads(resp.body)["data"]
    items = data["items"]
    assert len(items) == 3
    assert items[0]["batch_no"] == "DR-1"
    assert items[0]["in_db"] is True
    assert items[0]["task_status"] == "confirmed"
    assert items[0]["status"] == "completed"
    assert items[1]["product_type"] == "中试批"
    assert data["summary"] == {"total": 3, "past": 1, "upcoming": 2}


@pytest.mark.anyio
async def test_dump_plans_no_filter():
    """不传 from/to → 列出全部（无日期过滤）。"""
    fake = MagicMock()
    fake.glob.return_value = [_FakeFile("plan.xlsx")]
    s = _session()
    s.execute.side_effect = [
        _fetchall([("DR-1",)]),
        _fetchall([("DR-1", "pending", None, None, None, None, None)]),
    ]
    with patch.object(drs, "_SCHEDULE_DIR", fake), patch(
        "openpyxl.load_workbook", return_value=MagicMock()
    ), patch.object(
        drs, "_pick_latest_sheet", return_value=SimpleNamespace(title="x")
    ), patch.object(drs, "_parse_dump_plans", return_value=[(2026, 1, 1, "DR-1", "B1")]), patch.object(  # noqa: E501
        drs, "_sync_receiving_tasks", new=AsyncMock()
    ):
        resp = await drs.dr_dump_plans(
            session=s, from_date="", to_date=""
        )
    data = json.loads(resp.body)["data"]
    items = data["items"]
    assert len(items) == 1
    assert items[0]["in_db"] is True
    assert items[0]["task_status"] == "pending"


@pytest.mark.anyio
async def test_receiving_tasks_list():
    """接任务列表：月/状态过滤 + ISO 日期。"""
    s = _session()
    s.execute.return_value = _fetchall(
        [
            (
                "DR-1", "B1", date(2026, 8, 2), "pending", None,
                None, None, None, None, None,
            ),
            (
                "DR-2", "B2", date(2026, 8, 3), "confirmed",
                "2026-08-03 10:00:00", "李四", "A2", "晚点", "王五", "approved",
            ),
        ]
    )
    resp = await drs.dr_receiving_tasks(month="2026-08", status="pending", session=s)
    data = json.loads(resp.body)["data"]
    assert len(data["items"]) == 2
    assert data["items"][0]["plan_date"] == "2026-08-02"
    assert data["items"][1]["approver"] == "王五"


def test_operator_name():
    """确认/审批人名称解析。"""
    assert drs._operator_name(SimpleNamespace(name="张三"), None) == "张三"
    assert drs._operator_name(None, "手动") == "手动"
    assert drs._operator_name(None, None) == "未登录"


@pytest.mark.anyio
async def test_confirm_receiving_not_found():
    """确认：任务不存在 → 404。"""
    s = AsyncMock()
    s.execute.return_value = _fetchone(None)
    with pytest.raises(HTTPException) as ei:
        await drs.confirm_receiving(
            batch_no="DR-1", body=drs.ConfirmBody(), session=s
        )
    assert ei.value.status_code == 404


@pytest.mark.anyio
async def test_confirm_receiving_dup_and_delayed():
    """确认：已确认 / 已延期 → 400。"""
    s = _session()
    s.execute.return_value = _fetchone(("id1", "confirmed", "B1"))
    with pytest.raises(HTTPException) as e1:
        await drs.confirm_receiving(
            batch_no="DR-1", body=drs.ConfirmBody(), session=s
        )
    assert e1.value.status_code == 400

    s2 = _session()
    s2.execute.return_value = _fetchone(("id1", "delayed", "B1"))
    with pytest.raises(HTTPException) as e2:
        await drs.confirm_receiving(
            batch_no="DR-1", body=drs.ConfirmBody(), session=s2
        )
    assert e2.value.status_code == 400


@pytest.mark.anyio
async def test_confirm_receiving_success():
    """确认成功：限实罐/未登录人、commit。"""
    s = _session()

    async def _exec(sql, params=None):
        r = MagicMock()
        if "SELECT id, status, tank_no FROM production.receiving_task" in str(sql):
            r.fetchone.return_value = (5, "pending", "B1")
        return r

    s.execute.side_effect = _exec
    resp = await drs.confirm_receiving(
        batch_no="DR-X",
        body=drs.ConfirmBody(actual_tank_no="B2", note="ok"),
        session=s,
    )
    data = json.loads(resp.body)["data"]
    assert data["task_status"] == "confirmed"
    assert data["confirmed_by"] == "未登录"
    assert data["actual_tank_no"] == "B2"
    s.commit.assert_awaited()
    executed = [str(c.args[0]) for c in s.execute.await_args_list]
    assert any("status = 'confirmed'" in q for q in executed)


@pytest.mark.anyio
async def test_confirm_receiving_qualified_user():
    """开启资质校验且无资质 → 转 pending_approval。"""
    s = _session()
    q_log = []

    async def _exec(sql, params=None):
        r = MagicMock()
        sql_str = str(sql)
        if "SELECT id, status, tank_no FROM production.receiving_task" in sql_str:
            r.fetchone.return_value = (5, "pending", "B0")
        elif "SELECT qualified FROM production.staff_tank_qualification" in sql_str:
            q_log.append(params)
            r.fetchone.return_value = (0,)
        return r

    s.execute.side_effect = _exec
    with patch.object(drs, "_QUALIFICATION_ENFORCED", True):
        resp = await drs.confirm_receiving(
            batch_no="DR-X",
            body=drs.ConfirmBody(),
            session=s,
            current_user=SimpleNamespace(name="组长", employee_no="E9"),
        )
    data = json.loads(resp.body)["data"]
    assert data["task_status"] == "pending_approval"
    assert q_log and q_log[0]["t"] == "B0"


@pytest.mark.anyio
async def test_delay_receiving():
    """延期：空原因 / 不存在 / 状态不允许 / 成功。"""
    s = _session()
    with pytest.raises(HTTPException) as e1:
        await drs.delay_receiving(
            batch_no="DR-1", body=drs.DelayBody(delay_reason="  "), session=s
        )
    assert e1.value.status_code == 400

    s2 = _session()
    s2.execute.return_value = _fetchone(None)
    with pytest.raises(HTTPException) as e2:
        await drs.delay_receiving(
            batch_no="DR-1", body=drs.DelayBody(delay_reason="等料"), session=s2
        )
    assert e2.value.status_code == 404

    s3 = _session()
    s3.execute.return_value = _fetchone(("id1", "confirmed"))
    with pytest.raises(HTTPException) as e3:
        await drs.delay_receiving(
            batch_no="DR-1", body=drs.DelayBody(delay_reason="等料"), session=s3
        )
    assert e3.value.status_code == 400

    s4 = _session()
    s4.execute.return_value = _fetchone(("id1", "pending"))
    resp = await drs.delay_receiving(
        batch_no="DR-1",
        body=drs.DelayBody(delay_reason="等蒸汽", operator="操作员"),
        session=s4,
    )
    data = json.loads(resp.body)["data"]
    assert data["task_status"] == "delayed"
    assert data["delay_reason"] == "等蒸汽"
    s4.commit.assert_awaited()


@pytest.mark.anyio
async def test_approve_receiving():
    """审批：不存在 / 非待审批 / 批准 / 驳回。"""
    s = _session()
    s.execute.return_value = _fetchone(None)
    with pytest.raises(HTTPException) as e1:
        await drs.approve_receiving(
            batch_no="DR-1", body=drs.ApproveBody(), session=s
        )
    assert e1.value.status_code == 404

    s2 = _session()
    s2.execute.return_value = _fetchone(("id1", "confirmed"))
    with pytest.raises(HTTPException) as e2:
        await drs.approve_receiving(
            batch_no="DR-1", body=drs.ApproveBody(approve=True), session=s2
        )
    assert e2.value.status_code == 400

    s3 = _session()
    s3.execute.return_value = _fetchone(("id1", "pending_approval"))
    resp = await drs.approve_receiving(
        batch_no="DR-1", body=drs.ApproveBody(), session=s3
    )
    data3 = json.loads(resp.body)["data"]
    assert data3["task_status"] == "confirmed"
    assert data3["approval_status"] == "approved"
    s3.commit.assert_awaited()

    s4 = _session()
    s4.execute.return_value = _fetchone(("id1", "pending_approval"))
    resp4 = await drs.approve_receiving(
        batch_no="DR-1",
        body=drs.ApproveBody(approve=False, operator="班"),
        session=s4,
    )
    data4 = json.loads(resp4.body)["data"]
    assert data4["task_status"] == "pending"
    assert data4["approval_status"] == "rejected"


@pytest.mark.anyio
async def test_schedule_upload_validations():
    """上传：缺文件名 / 非 xlsx / 空内容 / 超大 / 非有效文件。"""
    with patch.object(drs, "_SCHEDULE_DIR", MagicMock()):
        with pytest.raises(HTTPException) as e1:
            await drs.dr_schedule_upload(_FakeUpload(None, b"x"))
        assert e1.value.status_code == 400

        with pytest.raises(HTTPException) as e2:
            await drs.dr_schedule_upload(_FakeUpload("a.csv", b"x"))
        assert e2.value.status_code == 400

        with pytest.raises(HTTPException) as e3:
            await drs.dr_schedule_upload(_FakeUpload("a.xlsx", b""))
        assert e3.value.status_code == 400

        with pytest.raises(HTTPException) as e4:
            await drs.dr_schedule_upload(
                _FakeUpload("a.xlsx", b"x" * (21 * 1024 * 1024))
            )
        assert e4.value.status_code == 400

        with patch("openpyxl.load_workbook", side_effect=Exception("corrupt")):
            with pytest.raises(HTTPException) as e5:
                await drs.dr_schedule_upload(_FakeUpload("a.xlsx", b"abc"))
            assert e5.value.status_code == 400
            assert "不是有效的 xlsx" in e5.value.detail


@pytest.mark.anyio
async def test_schedule_upload_success():
    """上传成功：写文件 + 解析放罐条数。"""
    fake_dir = MagicMock()
    with patch.object(drs, "_SCHEDULE_DIR", fake_dir), patch(
        "openpyxl.load_workbook", return_value=MagicMock()
    ), patch.object(
        drs, "_pick_latest_sheet", return_value=SimpleNamespace(title="2026.08.20")
    ), patch.object(drs, "_parse_dump_plans", return_value=[(2026, 1, 1, "DR-1", "B1")]):  # noqa: E501
        resp = await drs.dr_schedule_upload(_FakeUpload("plan.xlsx", b"data"))
    body = json.loads(resp.body)
    assert body["data"]["file"] == "plan.xlsx"
    assert body["data"]["total"] == 1
    assert "1 条放罐计划" in body["message"]


# ═════════════════════════════════════════════════════════
# dr_lineage_api — 补链助手 / 兄弟批 / 漏斗 分支
# ═════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_feed_pure_from_upstream():
    """DR-F1/F2/F3 顺链折纯补全 + 无记录回退。"""
    s = _session()
    s.execute.return_value = _fetchone(SimpleNamespace(feed_pure_kg=4.0))
    assert await drl._feed_pure_from_upstream(s, "DR-F1-1") == 4.0

    s.execute.return_value = _fetchone(SimpleNamespace(product_pure_kg=5.0))
    assert await drl._feed_pure_from_upstream(s, "DR-F2-1") == 5.0
    assert await drl._feed_pure_from_upstream(s, "DR-F3-1") == 5.0

    s.execute.return_value = _fetchone(None)
    assert await drl._feed_pure_from_upstream(s, "DR-F1-0") == 0.0
    assert await drl._feed_pure_from_upstream(s, "DR-F2-0") == 0.0
    assert await drl._feed_pure_from_upstream(s, "DR-F3-0") == 0.0
    assert await drl._feed_pure_from_upstream(s, "回收粉") == 0.0


@pytest.mark.anyio
async def test_loss_breakdown_from():
    """精制段损耗去向：一/二/三次 + 四次无字段。"""
    s = _session()
    s.execute.return_value = _fetchone((2.0,))
    assert await drl._loss_breakdown_from(s, "first_refinement", "DR-F1-1") == (2.0, 0.0)  # noqa: E501

    s.execute.return_value = _fetchone(None)
    assert await drl._loss_breakdown_from(s, "first_refinement", "x") == (0.0, 0.0)

    s.execute.return_value = _fetchone(SimpleNamespace(ml=3.0, rp=1.0))
    assert await drl._loss_breakdown_from(s, "second_refinement", "DR-F2-1") == (3.0, 1.0)  # noqa: E501

    s.execute.return_value = _fetchone(SimpleNamespace(ml=None, rp=None))
    assert await drl._loss_breakdown_from(s, "second_refinement", "y") == (0.0, 0.0)

    s.execute.return_value = _fetchone((4.0,))
    assert await drl._loss_breakdown_from(s, "third_refinement", "DR-F3-1") == (4.0, 0.0)  # noqa: E501

    assert await drl._loss_breakdown_from(s, "fourth_refinement", "DR-GB-1") == (0.0, 0.0)  # noqa: E501


@pytest.mark.anyio
async def test_node_info_all_stages():
    """_node_info：各精制段有/无记录、收率/折纯文案。"""
    s = _session()

    s.execute.return_value = _fetchall([])
    assert await drl._node_info(s, "extraction", "DR-E0") == ("", None, None)

    s.execute.return_value = _fetchall(
        [SimpleNamespace(total_qty=10.0, single_batch_yield=0.0)]
    )
    d, yr, q = await drl._node_info(s, "extraction", "DR-E1")
    assert "合计 10.00kg" in d
    assert yr is None and q == 10.0

    s.execute.return_value = _fetchall(
        [SimpleNamespace(product_qty_kg=5.0, chromatography_yield=0.9, crystallization_yield=None)]  # noqa: E501
    )
    d, yr, q = await drl._node_info(s, "chromatography", "DR-C1")
    assert "层析 90.0%" in d
    assert yr == 90.0 and q == 5.0

    s.execute.return_value = _fetchone(None)
    assert await drl._node_info(s, "first_refinement", "F1") == ("", None, None)

    s.execute.return_value = _fetchone(SimpleNamespace(feed_pure_kg=4.0))
    d, yr, q = await drl._node_info(s, "first_refinement", "F1")
    assert d == "折纯 4.00kg" and yr is None and q == 4.0

    s.execute.return_value = _fetchone(None)
    assert await drl._node_info(s, "second_refinement", "F2") == ("", None, None)

    s.execute.return_value = _fetchone(SimpleNamespace(product_pure_kg=6.0, batch_yield=0.95))  # noqa: E501
    d, yr, q = await drl._node_info(s, "second_refinement", "F2")
    assert "收率 95.0%" in d and "折纯 6.00kg" in d

    s.execute.return_value = _fetchone(None)
    assert await drl._node_info(s, "third_refinement", "F3") == ("", None, None)

    s.execute.return_value = _fetchone(SimpleNamespace(product_pure_kg=7.0, yield_rate=0.98))  # noqa: E501
    d, yr, q = await drl._node_info(s, "third_refinement", "F3")
    assert yr == 98.0

    s.execute.return_value = _fetchone(None)
    assert await drl._node_info(s, "fourth_refinement", "GB") == ("", None, None)

    s.execute.return_value = _fetchone(SimpleNamespace(dry_weight_kg=9.0, yield_rate=0.99))  # noqa: E501
    d, yr, q = await drl._node_info(s, "fourth_refinement", "GB")
    assert "干粉 9.00kg" in d and yr == 99.0


@pytest.mark.anyio
async def test_broken_reason():
    """断链原因：回收粉 / 未知工段 / 有记录 / 各段无记录。"""
    s = _session()
    assert (
        await drl._broken_reason(s, "recovery", "回收粉")
        == "回收粉/母液标签，无独立台账"
    )
    assert await drl._broken_reason(s, "unknown", "x") is None

    s.execute.return_value = _fetchone((1,))
    assert await drl._broken_reason(s, "extraction", "DR-E") is None

    s.execute.return_value = _fetchone(None)
    assert await drl._broken_reason(s, "extraction", "E") == "萃取表无记录"
    assert await drl._broken_reason(s, "first_refinement", "F1") == "一次精制表无记录"
    assert await drl._broken_reason(s, "second_refinement", "F2") == "二次精制表无记录"
    assert await drl._broken_reason(s, "third_refinement", "F3") == "三次精制表无记录"
    assert await drl._broken_reason(s, "fourth_refinement", "GB") == "四次精制表无记录"
    assert await drl._broken_reason(s, "chromatography", "C") is None  # reasons 无此段


@pytest.mark.anyio
async def test_upstream_branches():
    """_upstream：萃取无发酵批 / 有发酵批 / 层析 / 一次 / 二三四投料。"""
    s = _session()
    s.execute.side_effect = [_fetchone(None), _fetchone(None)]
    assert await drl._upstream(s, "extraction", "DR-E0") == []

    s2 = _session()
    s2.execute.side_effect = [
        _fetchone(SimpleNamespace(fermentation_batch_id="fb1")),
        _fetchone(None),  # 发酵批次查不到
    ]
    assert await drl._upstream(s2, "extraction", "DR-E1") == []

    s3 = _session()
    s3.execute.side_effect = [
        _fetchone(SimpleNamespace(fermentation_batch_id="fb1")),
        _fetchone(SimpleNamespace(batch_no="DR-26026")),
    ]
    up = await drl._upstream(s3, "extraction", "DR-26026-1")
    assert up == [("fermentation", "DR-26026", None)]

    s4 = _session()
    s4.execute.return_value = _fetchall(
        [SimpleNamespace(extraction_batch_no="DR-E1")]
    )
    up2 = await drl._upstream(s4, "chromatography", "DR-C1")
    assert up2[0][0] == "extraction"

    s5 = _session()
    s5.execute.return_value = _fetchall(
        [SimpleNamespace(chromatography_batch_no="DR-C1")]
    )
    up3 = await drl._upstream(s5, "first_refinement", "DR-F1-1")
    assert up3[0][0] == "chromatography"

    s6 = _session()
    s6.execute.side_effect = [
        _fetchall(
            [
                SimpleNamespace(feed_batch_no="DR-F1-A", feed_pure_kg=0.0),
                SimpleNamespace(feed_batch_no="DR-F1-B + DR-F1-C", feed_pure_kg=2.0),
            ]
        ),
        _fetchone(None),  # _feed_pure_from_upstream 反查 F1-A
    ]
    up4 = await drl._upstream(s6, "second_refinement", "DR-F2-1")
    assert {f[1] for f in up4} == {"DR-F1-A", "DR-F1-B", "DR-F1-C"}
    assert up4[0][2] == 0.0
    assert up4[1][2] == 2.0


@pytest.mark.anyio
async def test_downstream_branches():
    """_downstream：萃取 / 层析 / 精炼 / 四精 без upstream。"""
    s = _session()
    s.execute.return_value = _fetchall(
        [SimpleNamespace(extraction_batch_no="DR-260-1")]
    )
    down = await drl._downstream(s, "fermentation", "DR-26026")
    assert down[0][0] == "extraction"

    s2 = _session()
    s2.execute.return_value = _fetchall(
        [SimpleNamespace(wet_powder_batch_no="DR-24019-1")]
    )
    down2 = await drl._downstream(s2, "chromatography", "DR-C1")
    assert down2[0] == ("first_refinement", "DR-F1-24019-1", None)

    s3 = _session()
    s3.execute.return_value = _fetchall(
        [SimpleNamespace(refinement_batch_no="DR-F2-1")]
    )
    down3 = await drl._downstream(s3, "first_refinement", "DR-F1-1")
    assert down3[0][0] == "second_refinement"

    # 四次精制不在 down_map → 默认 []（无线化）
    assert await drl._downstream(s3, "fourth_refinement", "DR-GB-1") == []


@pytest.mark.anyio
async def test_siblings_extraction_hint():
    """兄弟批：撞名优先主链发酵批。"""
    s = _session()

    async def _exec(sql, params=None):
        sql_str = str(sql)
        r = MagicMock()
        if "SELECT DISTINCT t.fermentation_batch_id" in sql_str:
            r.fetchall.return_value = [
                SimpleNamespace(fermentation_batch_id="f1"),
                SimpleNamespace(fermentation_batch_id="f2"),
            ]
        elif "SELECT id::text AS id FROM production.dr_fermentation_batches" in sql_str:
            r.fetchone.return_value = SimpleNamespace(id="f1")
        elif "SELECT DISTINCT e.extraction_batch_no" in sql_str and "FROM production.dr_extractions e" in sql_str:  # noqa: E501
            r.fetchall.return_value = [
                SimpleNamespace(extraction_batch_no="DR-E1"),
                SimpleNamespace(extraction_batch_no="DR-E2"),
            ]
        elif "SELECT batch_no FROM production.dr_fermentation_batches" in sql_str:
            r.fetchone.return_value = SimpleNamespace(batch_no="DR-26026")
        return r

    s.execute.side_effect = _exec
    gk, members = await drl._siblings(
        s, "extraction", "DR-26026-1", hint_fbatch="DR-26026"
    )
    assert gk == "DR-26026"
    assert ("extraction", "DR-E1") in members
    assert ("extraction", "DR-E2") in members


@pytest.mark.anyio
async def test_siblings_empty_and_single():
    """兄弟组：无发酵罐 / 单成员 → (None, [])。"""
    s = _session()
    s.execute.side_effect = [
        _fetchall([]),
    ]
    assert await drl._siblings(s, "extraction", "DR-E") == (None, [])


@pytest.mark.anyio
async def test_siblings_chrom_and_f1():
    """层析/一次精炼兄弟组。"""
    s = _session()
    s.execute.side_effect = [
        _fetchall(
            [
                SimpleNamespace(extraction_batch_no="DR-E1"),
                SimpleNamespace(extraction_batch_no="DR-E2"),
            ]
        ),
        _fetchall(
            [
                SimpleNamespace(chromatography_batch_no="DR-C1"),
                SimpleNamespace(chromatography_batch_no="DR-C2"),
            ]
        ),
        _fetchall(
            [
                SimpleNamespace(chromatography_batch_no="DR-C3"),
                SimpleNamespace(chromatography_batch_no="DR-C4"),
            ]
        ),
    ]
    gk, members = await drl._siblings(s, "chromatography", "DR-C1")
    assert gk == "DR-E1、DR-E2"
    assert len(members) == 4

    s2 = _session()
    s2.execute.side_effect = [
        _fetchall([SimpleNamespace(chromatography_batch_no="DR-CA")]),
        _fetchall(
            [
                SimpleNamespace(wet_powder_batch_no="DR-24019-1"),
                SimpleNamespace(wet_powder_batch_no="DR-24019-2"),
            ]
        ),
    ]
    gk2, members2 = await drl._siblings(s2, "first_refinement", "DR-F1-24019-1")
    assert gk2 == "DR-CA"
    assert ("first_refinement", "DR-F1-24019-1") in members2


@pytest.mark.anyio
async def test_siblings_none_for_other_stage():
    assert await drl._siblings(_session(), "fourth_refinement", "GB") == (None, [])


@pytest.mark.anyio
async def test_trace_not_found():
    """追溯：批号未解析 → 404。"""
    with patch.object(drl, "_resolve", new=AsyncMock(return_value=(None, None))):
        with pytest.raises(HTTPException) as e:
            await drl.dr_lineage_trace(batch_no="DR-X", stage="", session=_session())
    assert e.value.status_code == 404


@pytest.mark.anyio
async def test_trace_sibling_loss_breakdown():
    """追溯完整策略：兄弟批展开 + 断链回收粉 + 损耗拆解。"""
    s = _session()
    misi = AsyncMock(return_value=("含收率 90.0%", 90.0, 9.0))
    broken_reason = AsyncMock(return_value=None)

    async def _up(se, st, bn):
        if st == "third_refinement" and bn == "DR-F3-1":
            return [("second_refinement", "DR-F2-1", 10.0), ("recovery", "回收粉", 0.0)]
        return []

    async def _dn(se, st, bn):
        if st in ("third_refinement",):
            return [("fourth_refinement", "DR-GB-1", None)]
        return []

    async def _sib(se, st, bn, hint_fbatch=""):
        return ("DR-F2-1", [("third_refinement", "DR-F3-1"), ("third_refinement", "DR-F3-2")])  # noqa: E501

    async def _lb(se, st, bn):
        return (2.0, 1.0)

    with patch.object(drl, "_resolve", new=AsyncMock(return_value=("third_refinement", "DR-F3-1"))), patch.object(  # noqa: E501
        drl, "_node_info", misi
    ), patch.object(drl, "_broken_reason", broken_reason), patch.object(
        drl, "_upstream", _up
    ), patch.object(drl, "_downstream", _dn), patch.object(
        drl, "_siblings", _sib
    ), patch.object(drl, "_loss_breakdown_from", _lb):
        resp = await drl.dr_lineage_trace(
            batch_no="DR-F3-1", stage="third_refinement", session=s
        )
    data = json.loads(resp.body)["data"]
    assert data["target_batch"] == "DR-F3-1"
    assert data["target_stage"] == "third_refinement"
    third = next(sg for sg in data["stages"] if sg["stage"] == "third_refinement")
    target_node = next(n for n in third["nodes"] if n["batch_no"] == "DR-F3-1")
    assert target_node["loss_kg"] == 1.0
    assert target_node["loss_rate"] == 10.0
    assert target_node["loss_breakdown"]["mother_liquor_kg"] == 2.0
    assert target_node["loss_breakdown"]["recovery_powder_kg"] == 1.0
    assert target_node["is_sibling"] is False
    recovery_sg = next(sg for sg in data["stages"] if sg["stage"] == "recovery")
    assert recovery_sg["nodes"][0]["batch_no"] == "回收粉"
    assert any(bl["stage"] == "recovery" for bl in data["broken_links"])


@pytest.mark.anyio
async def test_trace_target_and_node_broken():
    """追溯：目标断链 + 投料节点断链登记 broken_links。"""
    s = _session()
    misi = AsyncMock(return_value=("", None, None))
    broken_reason = AsyncMock(
        side_effect=lambda se, st, bn: (
            "二次精制表无记录"
            if st == "second_refinement" and bn == "DR-F2-T"
            else "一次精制表无记录"
            if st == "first_refinement" and bn == "DR-F1-9"
            else None
        )
    )

    async def _up(se, st, bn):
        if st == "second_refinement" and bn == "DR-F2-T":
            return [("first_refinement", "DR-F1-9", 1.0)]
        return []

    async def _dn(se, st, bn):
        if st == "second_refinement":
            return [("third_refinement", "DR-F3-1", None)]
        return []

    with (
        patch.object(drl, "_resolve", new=AsyncMock(return_value=("second_refinement", "DR-F2-T"))),  # noqa: E501
        patch.object(drl, "_node_info", misi),
        patch.object(drl, "_broken_reason", broken_reason),
        patch.object(drl, "_upstream", _up),
        patch.object(drl, "_downstream", _dn),
        patch.object(drl, "_siblings", new=AsyncMock(return_value=(None, []))),
        patch.object(drl, "_loss_breakdown_from", new=AsyncMock(return_value=(0.0, 0.0))),  # noqa: E501
    ):
        resp = await drl.dr_lineage_trace(batch_no="DR-F2-T", stage="second_refinement", session=s)  # noqa: E501
    data = json.loads(resp.body)["data"]
    broken = {b["batch_no"]: b["reason"] for b in data["broken_links"]}
    assert broken["DR-F2-T"] == "二次精制表无记录"
    f1_nodes = [
        n
        for sg in data["stages"]
        if sg["stage"] == "first_refinement"
        for n in sg["nodes"]
        if n["batch_no"] == "DR-F1-9"
    ]
    assert len(f1_nodes) == 1
    assert f1_nodes[0]["broken"] is True
    assert f1_nodes[0]["broken_reason"] == "一次精制表无记录"
    assert broken["DR-F1-9"] == "一次精制表无记录"


@pytest.mark.anyio
async def test_wet_powder_roots():
    """层析湿粉起点：直接/向上/向下找层析。"""
    s = _session()
    assert await drl._wet_powder_roots(s, "chromatography", "DR-C") == {"DR-C"}

    async def _up(se, st, bn):
        if st == "first_refinement":
            return [("chromatography", "DR-C1", None)]
        return []

    with patch.object(drl, "_upstream", new=_up):
        assert await drl._wet_powder_roots(s, "first_refinement", "DR-F1-1") == {"DR-C1"}  # noqa: E501

    # 目标在层析之前（发酵）→ 向下展开
    async def _dn2(se, st, bn):
        if bn == "DR-26026":
            return [("extraction", "DR-E1", None), ("chromatography", "DR-C2", None)]
        if bn == "DR-E1":
            return [("chromatography", "DR-E2", None)]
        return []

    down_s = _session()
    with patch.object(drl, "_downstream", new=_dn2):
        roots = await drl._wet_powder_roots(down_s, "fermentation", "DR-26026")
    assert roots == {"DR-C2", "DR-E2"}


@pytest.mark.anyio
async def test_wet_powder_roots_seen_skip():
    """向上回溯遇已访问节点跳过。"""
    s = _session()

    async def _up(se, st, bn):
        if st == "first_refinement":
            return [("first_refinement", "DR-F1-loop", None), ("chromatography", "DR-C", None)]  # noqa: E501
        if st == "fermentation":
            return [("fermentation", "loop", None)]
        return []

    with patch.object(drl, "_upstream", new=_up):
        roots = await drl._wet_powder_roots(s, "first_refinement", "DR-F1-1")
    assert roots == {"DR-C"}


@pytest.mark.anyio
async def test_chain_layers():
    """从层析起点逐层展开 + 访问去重。"""
    s = _session()

    async def _dn(se, st, bn):
        if st == "chromatography" and bn in {"DR-C1"}:
            return [("first_refinement", "DR-F1-1", None)]
        if st == "first_refinement" and bn == "DR-F1-1":
            return [
                ("first_refinement", "DR-F1-1", None),  # 已在 seen → 跳过
                ("second_refinement", "DR-F2-1", None),
            ]
        if st == "second_refinement":
            return [("third_refinement", "DR-F3-1", None)]
        return []

    with patch.object(drl, "_downstream", new=_dn):
        layers = await drl._chain_layers(s, {"DR-C1"})
    assert layers["chromatography"] == {"DR-C1"}
    assert layers["first_refinement"] == {"DR-F1-1"}
    assert layers["second_refinement"] == {"DR-F2-1"}
    assert layers["third_refinement"] == {"DR-F3-1"}


@pytest.mark.anyio
async def test_layer_output():
    """产出量：空集合 / 无列工段 / 有效聚合。"""
    s = _session()
    assert await drl._layer_output(s, "second_refinement", set()) == 0.0
    assert await drl._layer_output(s, "fermentation", {"DR-F"}) == 0.0
    s.execute.return_value = _scalar(5.0)
    assert await drl._layer_output(s, "chromatography", {"C1"}) == 5.0


@pytest.mark.anyio
async def test_layer_input():
    """投入量：只累计精制段折纯。"""
    s = _session()
    assert await drl._layer_input(s, "second_refinement", set()) == 0.0

    async def _up(se, st, bn):
        return [
            ("first_refinement", "DR-F1-A", 3.0),
            ("second_refinement", "DR-F1-B", 2.0),
            ("third_refinement", "DR-F1-C", 1.5),
            ("recovery", "回收粉", 0.0),
        ]

    with patch.object(drl, "_upstream", new=_up):
        total = await drl._layer_input(s, "second_refinement", {"A", "B"})
    # 两个批次都展开同样的投料明细，总折纯 = 2 * (3+2+1.5)
    assert total == 13.0


@pytest.mark.anyio
async def test_loss_funnel_endpoint():
    """漏斗：未找到 / 无起点 / 全链 + 超产 / 干粉口径备注。"""
    with patch.object(
        drl, "_resolve", new=AsyncMock(return_value=(None, None))
    ):
        with pytest.raises(HTTPException) as e:
            await drl.dr_loss_funnel(batch_no="DR-X", stage="", session=_session())
        assert e.value.status_code == 404

    with patch.object(drl, "_resolve", new=AsyncMock(return_value=("chromatography", "DR-C"))), patch.object(  # noqa: E501
        drl, "_wet_powder_roots", new=AsyncMock(return_value=set())
    ):
        resp = await drl.dr_loss_funnel(batch_no="DR-C", stage="", session=_session())
    data = json.loads(resp.body)["data"]
    assert data["layers"] == []
    assert data["notes"] == ["未找到层析湿粉起点（数据未闭合或非 DR 批次）"]

    # 全链：目标=层析，逐段对账
    out_map = {
        "chromatography": 10.0,
        "first_refinement": 1000.0,
        "second_refinement": 100.0,
        "third_refinement": 110.0,
        "fourth_refinement": 120.0,
    }
    layer_map = {
        "chromatography": {"DR-C1"},
        "first_refinement": {"DR-F1-1"},
        "second_refinement": {"DR-F2-1"},
        "third_refinement": {"DR-F3-1"},
        "fourth_refinement": {"DR-GB-1"},
    }

    async def _out(se, st, batches):
        return out_map[st]

    async def _inp(se, st, batches):
        return {"second_refinement": 100.0, "third_refinement": 50.0, "fourth_refinement": 120.0}.get(st, 0.0)  # noqa: E501

    with patch.object(drl, "_resolve", new=AsyncMock(return_value=("fermentation", "DR-26026"))), patch.object(  # noqa: E501
        drl, "_wet_powder_roots", new=AsyncMock(return_value={"DR-C1"})
    ), patch.object(drl, "_chain_layers", new=AsyncMock(return_value=layer_map)), patch.object(  # noqa: E501
        drl, "_layer_output", new=_out
    ), patch.object(drl, "_layer_input", new=_inp):
        resp2 = await drl.dr_loss_funnel(batch_no="DR-26026", stage="", session=_session())  # noqa: E501
    data2 = json.loads(resp2.body)["data"]
    assert len(data2["layers"]) == 5
    assert data2["layers"][4]["note"].startswith("干粉口径")
    assert data2["layers"][2]["segment_yield"] == 100.0
    assert "产出大于投入" in data2["layers"][3]["note"]
    assert any("中间批次起点" in n for n in data2["notes"])  # 全程收率>100
