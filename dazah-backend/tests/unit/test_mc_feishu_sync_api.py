"""MC 飞书同步 API 触发/状态 端点测试。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.production import mc_feishu_sync_api as api


@pytest.mark.anyio
async def test_trigger_mc_sync_valid() -> Any:
    """触发同步：有效模块 → 调用 run_mc_sync + 汇总创建/更新数。"""
    s = AsyncMock()
    with patch(
        "app.modules.production.mc_feishu_sync_api.run_mc_sync",
        new=AsyncMock(return_value={
            "crude": {"created_fl": 3, "created_sodium": 1},
            "extraction": {"created_records": 2, "updated_records": 1},
            "bad_mod": {},
        }),
    ):
        resp = await api.trigger_mc_sync(
            body=api.SyncTriggerRequest(
                modules=["crude", "extraction", "nope"],
            ),
            session=s,
        )
    data = json.loads(resp.body)["data"]
    assert data["invalid"] == ["nope"]
    assert data["total_created"] == 6  # crude(3+1) + extraction(2)
    assert data["total_updated"] == 1
    assert data["synced_at"]
    assert json.loads(resp.body)["message"].startswith("同步完成")


@pytest.mark.anyio
async def test_trigger_mc_sync_no_valid() -> Any:
    """无有效模块 → 400。"""
    s = AsyncMock()
    resp = await api.trigger_mc_sync(
        body=api.SyncTriggerRequest(modules=["xyz"]),
        session=s,
    )
    assert json.loads(resp.body)["code"] == 400


async def test_get_mc_sync_status() -> Any:
    """同步状态：返回各模块的 last_sync 与标签。"""
    api._last_sync["crude"] = "2026-08-21T00:00:00+00:00"
    resp = await api.get_mc_sync_status()
    data = json.loads(resp.body)["data"]
    assert data["spreadsheet"] == "2026年生产台账-mc"
    assert data["modules"]["crude"]["label"] == "粗提"
    assert data["modules"]["crude"]["last_sync"] == "2026-08-21T00:00:00+00:00"
    assert data["modules"]["ba"]["label"] == "丁酯盘点"


# ═══════════ mc_feishu_sheets_sync 调度器/配置纯净函数 ═══════════


@pytest.mark.anyio
async def test_start_stop_mc_sync_scheduler() -> Any:
    """启动/停止 MC 飞书同步定时任务（幂等）。"""
    from app.modules.production import mc_feishu_sheets_sync as mcsync

    mcsync._mc_sync_scheduler = None
    mcsync.start_mc_sync_scheduler()
    assert mcsync._mc_sync_scheduler is not None
    mcsync.stop_mc_sync_scheduler()
    assert mcsync._mc_sync_scheduler is None


@pytest.mark.anyio
async def test_mc_sync_scheduler_double_start() -> Any:
    """重复启动不重复创建。"""
    from unittest.mock import MagicMock

    from app.modules.production import mc_feishu_sheets_sync as mcsync

    mcsync._mc_sync_scheduler = MagicMock()
    mcsync.start_mc_sync_scheduler()  # 已存在 → 直接返回，不重启
    mcsync._mc_sync_scheduler.add_job.assert_not_called()
    assert mcsync._mc_sync_scheduler is not None
    mcsync.stop_mc_sync_scheduler()
    assert mcsync._mc_sync_scheduler is None


# ═══════════ mc_feishu_sheets_sync _sync_lineage ═══════════


@pytest.mark.anyio
async def test_sync_lineage_all_segments() -> Any:
    """6 段血链表 INSERT 全部执·行并累计 rowcount。"""
    from unittest.mock import MagicMock

    from app.modules.production import mc_feishu_sheets_sync as mcsync

    s = AsyncMock()
    result = MagicMock(rowcount=2)
    s.execute.return_value = result
    count = await mcsync._sync_lineage(session=s)
    assert count == 14  # 7 条 SQL 段 × 各插入 2 行
    assert s.execute.call_count == 7


@pytest.mark.anyio
async def test_sync_lineage_zero_rows() -> Any:
    """无插入 → 返回 0。"""
    from unittest.mock import MagicMock

    from app.modules.production import mc_feishu_sheets_sync as mcsync

    s = AsyncMock()
    result = MagicMock(rowcount=0)
    s.execute = AsyncMock(return_value=result)
    count = await mcsync._sync_lineage(session=s)
    assert count == 0


# ═══════════ mc_feishu_sheets_sync._sync_crude 主路径 ═══════════


@pytest.mark.anyio
async def test_mc_sync_crude_full_path() -> Any:
    """覆盖 _sync_crude 的新批次、子罐2、追加步骤等主路径。"""
    from app.modules.production import mc_feishu_sheets_sync as sync

    rows = [
        # 新批次子罐1（I列 MC-101-1），J-P 钠化、Q-W 酸化均有值
        [
            "2026-03-01", "MC-F-1", "MC-RB-1", "50", "", "", "", "",
            "MC-101-1", "5", "180", "300", "8.5", "1.2", "90", "10",
            "100", "30", "250", "12", "7.0", "35", "28", "260", "0.95", "0.90",
        ],
        # 子罐2（I列 MC-101-2）
        [
            "", "", "", "", "", "", "", "",
            "MC-101-2", "5", "180", "300", "8.5", "1.2", "90", "10",
            "100", "30", "250", "12", "7.0", "35", "28", "260", "0.95", "0.90",
        ],
        # 追加步骤（I列为空，J-P/Q-W 有数据）
        [
            "", "", "", "", "", "", "", "",
            "", "4", "160", "280", "8.0", "1.0", "85", "9",
            "90", "28", "240", "11", "6.8", "33", "26", "250", "0.94", "0.88",
        ],
        # 月份分隔行 → 跳过
        ["03月份", ""],
        # 空行 → 跳过
        ["", ""],
    ]
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None  # 记录不存在 → 创建路径
    session.execute.return_value = result
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    with patch.object(sync, "_read_sheet_range", new=AsyncMock(return_value=rows)):
        stats = await sync._sync_crude(session, "tok", "app", "sec")
    assert stats["created_fl"] >= 1
    assert stats["created_st"] >= 1
    assert stats["skipped"] >= 1
    assert stats["created_sodium"] >= 1
    assert stats["created_acid"] >= 1
