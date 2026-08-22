"""MC 飞书同步 API 触发/状态 端点测试。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.production import mc_feishu_sync_api as api


@pytest.mark.anyio
async def test_trigger_mc_sync_valid():
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
async def test_trigger_mc_sync_no_valid():
    """无有效模块 → 400。"""
    s = AsyncMock()
    resp = await api.trigger_mc_sync(
        body=api.SyncTriggerRequest(modules=["xyz"]),
        session=s,
    )
    assert json.loads(resp.body)["code"] == 400


async def test_get_mc_sync_status():
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
async def test_start_stop_mc_sync_scheduler():
    """启动/停止 MC 飞书同步定时任务（幂等）。"""
    from app.modules.production import mc_feishu_sheets_sync as mcsync

    mcsync._mc_sync_scheduler = None
    mcsync.start_mc_sync_scheduler()
    assert mcsync._mc_sync_scheduler is not None
    mcsync.stop_mc_sync_scheduler()
    assert mcsync._mc_sync_scheduler is None


@pytest.mark.anyio
async def test_mc_sync_scheduler_double_start():
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
async def test_sync_lineage_all_segments():
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
async def test_sync_lineage_zero_rows():
    """无插入 → 返回 0。"""
    from unittest.mock import MagicMock

    from app.modules.production import mc_feishu_sheets_sync as mcsync

    s = AsyncMock()
    result = MagicMock(rowcount=0)
    s.execute = AsyncMock(return_value=result)
    count = await mcsync._sync_lineage(session=s)
    assert count == 0
