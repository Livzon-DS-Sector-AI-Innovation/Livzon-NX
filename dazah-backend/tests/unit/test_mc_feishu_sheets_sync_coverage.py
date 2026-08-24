"""MC 飞书电子表格同步 — 分支覆盖补充测试。

目标文件: app/modules/production/mc_feishu_sheets_sync.py
覆盖 CI 门禁中仍未触达的可执行行（增量补充，不修改业务源码）：
  * _get_mc_spreadsheet_config 无配置报错
  * _read_sheet_range HTTP 非200 与 业务错误分支
  * _sync_crude 新批次 / 子罐2 暂存数据 / 收率继承 / 追加步骤 / 行解析错误回滚
  * _sync_extraction / _sync_refinement / _sync_blending / _sync_qc 的更新与跳过分支
  * _sync_ba 交叉表解析分支
  * run_mc_sync 的 handler 成功/失败、lineage、异常自动检测成功与失败
  * _mc_scheduled_sync_job 成功与异常路径

feishu 客户端与 DB 会话均使用 mock，不触网、不碰真实数据库。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.modules.production import mc_feishu_sheets_sync as sync


class _Selection:
    """模拟 sqlalchemy Result：scalars().first() 与 scalar_one_or_none 同步返回。"""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def first(self):
        return self._value


class _BranchDB:
    """按 SQL 文本逐条匹配的分派会话 mock，记录 add 传入的 ORM 对象。"""

    def __init__(self, matchers=None, raise_on=None):
        self._matchers = list(matchers or ())
        self._raise_on = raise_on
        self.added = []
        self.flushed = 0
        self.committed = 0
        self.rolled_back = 0

    async def execute(self, stmt, *args, **kwargs):
        sql = str(stmt)
        if self._raise_on and self._raise_on in sql:
            raise RuntimeError("db boom")
        for needle, value in self._matchers:
            if needle in sql:
                return _Selection(value)
        return _Selection(None)

    def add(self, obj):
        obj.id = getattr(obj, "id", None) or f"id-{len(self.added) + 1}"
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1


def _row(*values: object, length: int = 36) -> list[str]:
    """按列索引填充一行，None / 缺省为空串。"""
    cells = [""] * length
    for idx, value in enumerate(values[:length]):
        if value is not None:
            cells[idx] = str(value)
    return cells


# ═══════════ _get_mc_spreadsheet_config ═══════════


@pytest.mark.anyio
async def test_get_mc_spreadsheet_config_no_config_raises() -> None:
    """查无"霉酚酸/production_plan"配置 → 抛 RuntimeError。"""
    session = AsyncMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = None
    result.scalars.return_value = scalars
    session.execute.return_value = result

    with pytest.raises(RuntimeError, match="未找到 MC 飞书配置"):
        await sync._get_mc_spreadsheet_config(session)


@pytest.mark.anyio
async def test_get_mc_spreadsheet_config_with_config() -> None:
    """存在配置 → 用 decrypt_secret 解密后返回抓手参数。"""
    cfg = SimpleNamespace(
        bitable_app_token="spt-1",
        app_id="app-1",
        encrypted_app_secret="enc-1",
    )
    session = AsyncMock()
    session.execute.return_value = _Selection(cfg)
    with patch.object(sync, "decrypt_secret", return_value="plain-secret") as mock_d:
        out = await sync._get_mc_spreadsheet_config(session)
    mock_d.assert_called_once_with("enc-1")
    assert out == {
        "spreadsheet_token": "spt-1",
        "app_id": "app-1",
        "app_secret": "plain-secret",
    }


# ═══════════ _read_sheet_range ═══════════


def _install_httpx(handler):
    real_async_client = httpx.AsyncClient

    def fake_async_client(*, base_url=None, timeout=30):
        return real_async_client(
            transport=httpx.MockTransport(handler), timeout=timeout, base_url=base_url
        )

    return patch.object(sync.httpx, "AsyncClient", fake_async_client)


@pytest.mark.anyio
async def test_read_sheet_range_http_error() -> None:
    """Sheets API 返回非 200 → RuntimeError 且带状态码。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "tok-500"})
        return httpx.Response(500, text="spreadsheet boom")

    with _install_httpx(handler):
        with pytest.raises(RuntimeError, match="500"):
            await sync._read_sheet_range("s1", "A4:AI5000", "spt", "app-500", "sec-500")


@pytest.mark.anyio
async def test_read_sheet_range_business_error() -> None:
    """HTTP 200 但 code != 0 → RuntimeError 且带 code。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "tok-code"})
        return httpx.Response(200, json={"code": 2, "msg": "bad sheet"})

    with _install_httpx(handler):
        with pytest.raises(RuntimeError, match="2"):
            await sync._read_sheet_range("s1", "A1:C9", "spt", "code-app", "sec")


@pytest.mark.anyio
async def test_read_sheet_range_success() -> None:
    """正常读取 → 单元格转字符串，None 变空串。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "tok-ok"})
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": {
                    "valueRange": {
                        "values": [[1.5, None, "甲"], ["乙", "丙", "丁"]],
                    }
                },
            },
        )

    with _install_httpx(handler):
        rows = await sync._read_sheet_range("s1", "A1:C500", "spt", "app-ok", "sec")
    assert rows[0] == ["1.5", "", "甲"]
    assert rows[1] == ["乙", "丙", "丁"]


# ═══════════ _sync_crude ═══════════


@pytest.mark.anyio
async def test_sync_crude_full_path_with_skip() -> None:
    """新批次子罐1 创建、追加步骤、跳过分隔/空行/无提炼批号行。"""
    rows = [
        _row("", "", ""),
        _row("", "", "", "66"),
        _row("03月份", ""),
        _row(
            "2026-03-01", "FL-1", "RB-1", "50", "180", "60", "85", "120", "RB-1-1",
            "5", "180", "300", "8.5", "1.2", "90", "10", "100", "30", "250",
            "12", "7.0", "35", "28", "260", "0.95", "0.9", "300", "12", "82",
            "2", "280", "91", "315", "0.9", "",
        ),
        _row(
            "", "", "", "", "", "", "", "", "", "4", "160", "280", "8.0",
            "1.0", "85", "9", "90", "28", "240", "11", "6.8", "33", "26",
            "250", "0.94", "0.88", "",
        ),
    ]
    session = _BranchDB()
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_crude(session, "tok", "app", "sec")
    assert stats["created_fl"] == 1
    assert stats["created_rb"] == 1
    assert stats["created_st"] == 1
    assert stats["created_sodium"] == 2
    assert stats["created_acid"] == 2
    assert stats["skipped"] == 3
    assert stats["errors"] == 0


@pytest.mark.anyio
async def test_sync_crude_st2_pending_and_yield_inherit() -> None:
    """子罐2 创建时使用暂存发酵液数据并继承子罐1 收率。"""
    rows = [
        _row(
            "2026-03-05", "FL-9", "RB-9", "50", "180", "300", "8.5", "85", "RB-9-1",
            "5", "180", "300", "8.5", "1.2", "90", "10", "100", "30", "250",
            "12", "7.0", "35", "28", "260", "0.95", "0.9", "300", "11", "82",
            "2", "280", "91", "315", "0.9", "",
        ),
        # 暂存子罐2 发酵液数据（D/E/F 列）
        _row("", "", "", "47", "175", "135"),
        _row(
            "", "", "", "", "", "", "", "", "RB-9-2", "4", "170", "85", "7.5", "1.0",
            "88", "9", "90", "27", "230", "11", "6.5", "33", "26", "245", "0.93",
            "0.87", "290", "11", "80", "2", "88", "", "300", "0.88", "",
        ),
    ]
    db = _BranchDB(
        matchers=[("tank_no = :tank_no_1", SimpleNamespace(id="t1", yield_rate=91.0))]
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_crude(
            session=db, spreadsheet_token="tok", app_id="app", app_secret="sec"
        )
    assert stats["created_st"] == 2
    from app.modules.production.mc_crude_extract_models import SubTankRecord

    t2 = next(
        obj for obj in db.added if isinstance(obj, SubTankRecord) and obj.tank_no == 2
    )
    assert t2.fl_volume == 47.0
    assert t2.yield_rate == 91.0


@pytest.mark.anyio
async def test_sync_crude_existing_subtank_skips_create() -> None:
    """子罐记录已存在 → 复用 id 且不重复创建。"""
    existing = SimpleNamespace(id="st-exist")
    rows = [
        _row(
            "2026-03-02", "FL-77", "RB-77", "50", "", "", "", "", "RB-77-1", "5",
            "6", "7", "8", "1", "2", "3", "4", "5", "6", "7", "", "", "",
            "", "", "", "", "", "", "", "", "", "", "", "",
        ),
        _row(
            "", "", "", "", "", "", "", "", "", "5", "2", "3", "4", "1", "2", "3",
            "6", "7", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
            "", "", "", "",
        ),
    ]
    db = _BranchDB(matchers=[("sub_tank_records.batch_no = :batch_no_1", existing)])
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_crude(db, "tok", "app", "sec")
    assert stats["created_st"] == 0
    assert stats["created_sodium"] >= 1
    assert stats["created_acid"] >= 1
    sub = next(
        obj for obj in db.added if getattr(obj, "sub_tank_id", None) == "RB-77-1"
    )
    assert sub.seq_no == 1


@pytest.mark.anyio
async def test_sync_crude_row_error_rolls_back() -> None:
    """行解析/写入异常 → 计入 errors 并回滚。"""
    rows = [
        _row(
            "2026-03-03", "FL-3", "RB-3", "50", "180", "60", "85", "70", "RB-3-1",
            "5", "180", "300", "8.5", "1.2", "90", "10", "100", "30", "250",
            "12", "7.0", "35", "28", "260", "0.95", "0.9", "300", "12", "82",
            "2", "280", "91", "315", "0.9", "",
        ),
    ]
    db = _BranchDB()
    db.flush = AsyncMock(side_effect=RuntimeError("flush boom"))
    db.rollback = AsyncMock(side_effect=RuntimeError("rollback boom"))
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_crude(db, "batch", "app", "sec")
    assert stats["errors"] >= 1


@pytest.mark.anyio
async def test_sync_crude_append_steps_partial() -> None:
    """追加步骤中仅钠化或仅酸化数据缺失时，另一侧仍正确建行。"""
    rows = [
        _row(
            "2026-03-04", "FL-4", "RB-4", "45", "170", "", "", "", "RB-4-1",
            "5", "6",
        ),
        # 无 batch_no，J-P 空、Q-W 有值（仅酸化步骤）
        _row(
            "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
            "12", "70", "240", "11", "6.8", "33", "26", "250", "0.94", "0.88",
        ),
    ]
    session = _BranchDB()
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_crude(session, "tok", "app", "sec")
    # 第一批创建了钠化；第二批只命中酸化创建
    assert stats["created_sodium"] == 1
    assert stats["created_acid"] == 1
    assert stats["created_st"] == 1
    assert stats["skipped"] == 0


@pytest.mark.anyio
async def test_sync_crude_existing_steps_return_early() -> None:
    """钠化/酸化步骤已存在时计数不增长。"""
    existing_step = SimpleNamespace(id="step-exists")
    rows = [
        _row(
            "2026-03-06", "FL-6", "RB-6", "40", "", "", "", "", "RB-6-1",
            "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15",
            "90", "100", "110", "120",
        ),
    ]
    db = _BranchDB(
        matchers=[
            ("sub_tank_sodium_steps", existing_step),
            ("sub_tank_acid_steps", existing_step),
        ]
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_crude(db, "tok", "app", "sec")
    assert stats["created_sodium"] == 0
    assert stats["created_acid"] == 0


# ═══════════ _sync_extraction ═══════════


@pytest.mark.anyio
async def test_sync_extraction_update_and_skip() -> None:
    rows = [
        [
            "2026-03-11", "", "MC-C0", "7", "", "", "", "", "", "", "",
            "", "", "", "", "", "", "", "", "", "", "",
        ],
        [
            "", "", "", "", "", "", "", "", "", "", "",
            "", "", "", "", "", "", "", "", "", "", "",
        ],
        [
            "2026-03-11", "MC-111", "MC-C111", "8", "90", "100", "70",
            "80", "85", "700", "3", "82", "10", "5", "85", "2",
            "50", "0.9", "1.0", "460", "2", "0.8",
        ],
        [
            "", "", "MC-C112", "5", "30", "40", "",
            "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
        ],
    ]
    db = _BranchDB(
        matchers=[
            ("extraction_records", SimpleNamespace(id="er-1")),
            ("extraction_inputs", SimpleNamespace(id="ei-1")),
        ]
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_extraction(db, "tok", "app", "sec")
    assert stats["updated_records"] == 1
    assert stats["updated_inputs"] == 2
    assert stats["skipped"] == 2
    assert stats["created_records"] == 0


@pytest.mark.anyio
async def test_sync_extraction_error() -> None:
    rows = [
        [
            "2026-03-12", "MC-112", "MC-C2", "8", "90", "80", "60", "50",
            "40", "300", "1", "80", "5", "4", "60", "1", "30",
            "0.5", "0.8", "200", "1.5", "0.6",
        ],
    ]
    db = _BranchDB(
        matchers=[("extraction_records", SimpleNamespace(id="er-1"))],
        raise_on="extraction_records",
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_extraction(db, "tok", "app", "sec")
    assert stats["errors"] == 1


# ═══════════ _sync_refinement ═══════════

@pytest.mark.anyio
async def test_sync_refinement_update_and_skip() -> None:
    rows = [
        [
            "2026-03-08", "", "WET-9", "6", "", "", "", "", "", "", "",
            "", "", "", "", "", "", "", "", "", "", "",
        ],
        [
            "", "", "", "", "", "", "", "", "", "", "",
            "", "", "", "", "", "", "", "", "", "",
        ],
        [
            "2026-03-08", "MC-F2-88", "WET-88", "22", "12", "1", "84", "20",
            "16", "130", "1#结晶罐", "1.1", "3#结晶罐", "9.5", "8", "78",
            "0.95", "0.9", "300", "2.0", "1.5",
        ],
        [
            "", "", "WET-89", "9", "9", "0.5", "80", "8", "4", "45",
            "T8", "0.5", "C8", "2", "1", "60", "0.9", "0.8", "120",
            "1", "0.6",
        ],
    ]
    db = _BranchDB(
        matchers=[
            ("mc_refinement_records", SimpleNamespace(id="rr-1")),
            ("mc_refinement_inputs", SimpleNamespace(id="ri-1")),
        ]
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_refinement(db, "tok", "app", "sec")
    assert stats["updated_records"] == 1
    assert stats["updated_inputs"] == 2
    assert stats["skipped"] == 2


# ═══════════ _sync_blending ═══════════

@pytest.mark.anyio
async def test_sync_blending_create_path() -> None:
    rows = [
        [
            "MC-200", "MC-F2-501", "60", "58", "25kg/桶", "0.5", "0.6",
            "0.7", "0.8", "0.9", "3.5", "95", "0.1", "0.2", "0.3",
            "0.4", "0.5", "1.5", "97",
        ],
        [
            "", "MC-F2-502", "40", "38", "25kg", "0.2", "0.3", "0.4",
            "0.5", "0.6", "4", "94", "", "", "", "", "", "", "",
        ],
    ]
    db = _BranchDB()
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_blending(db, "tok", "app", "sec")
    assert stats["created_records"] == 1
    assert stats["created_inputs"] == 2
    assert stats["skipped"] == 0


@pytest.mark.anyio
async def test_sync_blending_update_path() -> None:
    rows = [
        [
            "MC-200", "MC-F2-501", "60", "58", "25kg/桶", "0.5", "0.6",
            "0.7", "0.8", "0.9", "3.5", "95", "0.1", "0.2", "0.3",
            "0.4", "0.5", "1.5", "97",
        ],
        [
            "", "MC-F2-502", "40", "38", "25kg", "0.2", "0.3", "0.4",
            "0.5", "0.6", "4", "94", "", "", "", "", "", "", "",
        ],
    ]
    db = _BranchDB(
        matchers=[
            ("blending_records", SimpleNamespace(id="br-1")),
            ("blending_inputs", SimpleNamespace(id="bi-1")),
        ]
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_blending(db, "tok", "app", "sec")
    assert stats["updated_records"] == 1
    assert stats["updated_inputs"] == 2


# ═══════════ _sync_qc ═══════════

@pytest.mark.anyio
async def test_sync_qc_create_and_skip() -> None:
    rows = [
        ["", "", "", "", "", "", "", "", "", "", ""],
        [
            "2026-03-01", "", "MC-F2-X", "5", "", "", "", "", "", "", "",
        ],
        [
            "2026-03-01", "QC-311", "MC-F2-1", "50", "25kg", "120", "4",
            "企标A", "前端", "180", "累计",
        ],
        ["", "", "MC-F2-2", "12", "", "", "", "", "", "", ""],
    ]
    db = _BranchDB()
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_qc(db, "tok", "app", "sec")
    assert stats["created_records"] == 1
    assert stats["created_inputs"] == 2
    assert stats["skipped"] == 2


@pytest.mark.anyio
async def test_sync_qc_update_path() -> None:
    rows = [
        [
            "2026-03-02", "QC-333", "MC-F2-3", "50", "25kg", "110", "4",
            "S1", "F1", "2", "1",
        ],
    ]
    db = _BranchDB(
        matchers=[
            ("qc_inspections", SimpleNamespace(id="qc-1")),
            ("qc_inspection_inputs", SimpleNamespace(id="qc-i-1")),
        ]
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_qc(db, "tok", "app", "sec")
    assert stats["updated_records"] == 1
    assert stats["updated_inputs"] == 1


@pytest.mark.anyio
async def test_sync_qc_error() -> None:
    rows = [
        ["2026-03-03", "QC-444", "MC-F2-4", "60", "", "", "", "", "", "", ""],
    ]
    db = _BranchDB(
        matchers=[("qc_inspections", SimpleNamespace(id="qc-1"))],
        raise_on="qc_inspections",
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_qc(db, "tok", "app", "sec")
    assert stats["errors"] == 1


@pytest.mark.anyio
async def test_sync_refinement_row_error() -> None:
    """二精制同步查询异常 → 计入 errors。"""
    rows = [
        ["2026-03-09", "MC-F2-90", "WET-90", "22", "12", "1", "84", "20"],
    ]
    db = _BranchDB(
        matchers=[("mc_refinement_records", SimpleNamespace(id="rr-2"))],
        raise_on="mc_refinement_records",
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_refinement(db, "tok", "app", "sec")
    assert stats["errors"] == 1


@pytest.mark.anyio
async def test_sync_blending_skip_and_row_error() -> None:
    """混粉：无混合批号跳过 + 主表查询异常计入 errors。"""
    rows = [
        ["", "", "", "", ""],
        ["", "", "MC-C60", "9", "20kg/桶", "", "", "80", "", "", "", "", ""],
        [
            "MC-300", "MC-F2-9", "50", "48", "20kg/桶", "0.5", "0.6",
            "0.7", "0.8", "0.9", "1", "98", "0.2", "0.3", "0.4", "0.5",
        ],
    ]
    db = _BranchDB(raise_on="blending_records")
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_blending(db, "tok", "app", "sec")
    assert stats["skipped"] == 2
    assert stats["errors"] == 1


# ═══════════ _sync_ba ═══════════

@pytest.mark.anyio
async def test_sync_ba_header_only_error() -> None:
    rows = [["消耗记录", "日期"]]
    db = _BranchDB()
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_ba(db, "tok", "app", "sec")
    assert stats["errors"] == 1


@pytest.mark.anyio
async def test_sync_ba_cross_table_create() -> None:
    rows = [
        ["消耗记录", "日期", "2026.03.01", "2026.03.02", "坏日期"],
        ["", "1#萃取罐", "21.1", "33.4"],
        ["", "入库A", "5.5", ""],
        ["", "合计(m³)", "99", ""],
        ["", "成品入库", "88", ""],
        ["", "2#罐", "", "4.2"],
        ["", "", "9", ""],
    ]
    db = _BranchDB()
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_ba(db, "tok", "app", "sec")
    assert stats["created_records"] == 4
    assert stats["errors"] == 0


@pytest.mark.anyio
async def test_sync_ba_cross_table_update() -> None:
    rows = [
        ["消耗记录", "日期", "2026.03.01", "2026.03.02", "坏日期"],
        ["", "1#萃取罐", "21.1", "33.4"],
        ["", "入库A", "5.5", ""],
        ["", "合计(m³)", "99", ""],
        ["", "成品入库", "88", ""],
        ["", "2#萃取罐", "", "4.2"],
        ["", "", "9", ""],
    ]
    db = _BranchDB(
        matchers=[("butyl_acetate_records", SimpleNamespace(id="ba-1"))],
    )
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_ba(db, "tok", "app", "sec")
    assert stats["updated_records"] == 4
    assert stats["created_records"] == 0


@pytest.mark.anyio
async def test_sync_ba_row_error() -> None:
    rows = [
        ["消耗记录", "日期", "2026.03.01"],
        ["", "1#罐", "8.8"],
        ["", "入库B", "6.6"],
    ]
    db = _BranchDB(raise_on="butyl_acetate_records")
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_ba(db, "tok", "app", "sec")
    assert stats["errors"] >= 1


# ═══════════ run_mc_sync ═══════════

@pytest.mark.anyio
async def test_run_mc_sync_handler_success_with_anomalies() -> None:
    session = AsyncMock()
    cfg = {"spreadsheet_token": "tok", "app_id": "app", "app_secret": "sec"}
    with (
        patch.object(
            sync, "_get_mc_spreadsheet_config", new=AsyncMock(return_value=cfg)
        ),
        patch.object(
            sync, "SYNC_HANDLERS", {"crude": AsyncMock(return_value={"created_fl": 3})}
        ),
        patch.object(sync, "_sync_lineage", new=AsyncMock(return_value=2)),
        patch(
            "app.modules.production.mc_yield_anomaly_detector.run_anomaly_detection",
            new=AsyncMock(
                return_value={
                    "scanned": 9, "detected": 2, "high": 1, "medium": 1,
                    "details": [],
                }
            ),
        ),
    ):
        out = await sync.run_mc_sync(["crude"], session)
    assert out["crude"] == {"created_fl": 3}
    assert out["lineage"] == {"updated": 2}
    assert out["anomaly_detection"]["detected"] == 2


@pytest.mark.anyio
async def test_run_mc_sync_handler_error_is_captured() -> None:
    session = AsyncMock()
    cfg = {"spreadsheet_token": "tok", "app_id": "app", "app_secret": "sec"}
    with (
        patch.object(
            sync, "_get_mc_spreadsheet_config", new=AsyncMock(return_value=cfg)
        ),
        patch.object(
            sync,
            "SYNC_HANDLERS",
            {"extraction": AsyncMock(side_effect=RuntimeError("boom-x"))},
        ),
        patch.object(sync, "_sync_lineage", new=AsyncMock(return_value=0)),
        patch(
            "app.modules.production.mc_yield_anomaly_detector.run_anomaly_detection",
            new=AsyncMock(return_value={}),
        ),
    ):
        out = await sync.run_mc_sync(["extraction"], session)
    assert out["extraction"] == {"error": "boom-x"}


@pytest.mark.anyio
async def test_run_mc_sync_anomaly_failure_is_captured() -> None:
    session = AsyncMock()
    cfg = {"spreadsheet_token": "tok", "app_id": "app", "app_secret": "sec"}
    with (
        patch.object(
            sync, "_get_mc_spreadsheet_config", new=AsyncMock(return_value=cfg)
        ),
        patch.object(sync, "SYNC_HANDLERS", {"crude": AsyncMock(return_value={})}),
        patch.object(sync, "_sync_lineage", new=AsyncMock(return_value=0)),
        patch(
            "app.modules.production.mc_yield_anomaly_detector.run_anomaly_detection",
            new=AsyncMock(side_effect=RuntimeError("anom-fail")),
        ),
    ):
        out = await sync.run_mc_sync(["crude"], session)
    assert out["anomaly_detection"] == {"error": "anom-fail"}


@pytest.mark.anyio
async def test_run_mc_sync_lineage_error_is_captured() -> None:
    """血链表更新失败 → lineage 错误被捕获而非扩散。"""
    session = AsyncMock()
    cfg = {"spreadsheet_token": "tok", "app_id": "app", "app_secret": "sec"}
    with (
        patch.object(
            sync, "_get_mc_spreadsheet_config", new=AsyncMock(return_value=cfg)
        ),
        patch.object(sync, "SYNC_HANDLERS", {"crude": AsyncMock(return_value={})}),
        patch.object(
            sync,
            "_sync_lineage",
            new=AsyncMock(side_effect=RuntimeError("lineage-fail")),
        ),
        patch(
            "app.modules.production.mc_yield_anomaly_detector.run_anomaly_detection",
            new=AsyncMock(return_value={}),
        ),
    ):
        out = await sync.run_mc_sync(["crude"], session)
    assert out["crude"] == {}
    assert out["lineage"] == {"error": "lineage-fail"}


# ═══════════ _mc_scheduled_sync_job ═══════════

@pytest.mark.anyio
async def test_scheduled_job_success_path() -> None:
    run_mock = AsyncMock(
        return_value={
            "crude": {"created_fl": 2, "created_st": 1},
            "bad": {"error": "boom"},
            "lineage": {"updated": 1},
        }
    )

    class SessionContext:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *_args):
            return False

    with (
        patch.object(sync, "run_mc_sync", run_mock),
        patch("app.core.database.async_session_factory", SessionContext),
    ):
        await sync._mc_scheduled_sync_job()
    run_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_scheduled_job_exception_path() -> None:
    class SessionContext:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *_args):
            return False

    with patch.object(
        sync, "run_mc_sync", AsyncMock(side_effect=RuntimeError("sync-boom"))
    ), patch("app.core.database.async_session_factory", SessionContext):
        # 异常应被吞掉，不扩散到调用方
        await sync._mc_scheduled_sync_job()
