"""Tests for regulatory tracker scheduled generators."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker.scheduled import (
    RegulatoryTrackerDailyAnalysisGenerator,
    RegulatoryTrackerDailyNotifyGenerator,
    RegulatoryTrackerNightlySyncGenerator,
)


def _enabled_setting(*, recent_days: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        is_enabled=True,
        recent_days=recent_days,
        recipient_open_id="ou_test_qa",
        recipient_name="武巧玲",
        recipient_department="QA",
    )


# ── 00:10 夜间抓取 ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_nightly_sync_find_due_always_fires(db_session: AsyncSession) -> None:
    generator = RegulatoryTrackerNightlySyncGenerator()
    # 抓取是数据底座：即使未配置通知也必须执行
    assert await generator.find_due(db_session) == [True]


@pytest.mark.anyio
async def test_nightly_sync_execute_one_calls_run_all_sites_without_analysis(
    db_session: AsyncSession,
) -> None:
    generator = RegulatoryTrackerNightlySyncGenerator()
    with patch(
        "app.modules.regulatory_tracker.scheduled.run_all_sites",
        new=AsyncMock(
            return_value={"totals": {"checked": 3, "inserted": 1, "updated": 1}}
        ),
    ) as mocked:
        await generator.execute_one(db_session, True)

    mocked.assert_awaited_once()
    assert mocked.await_args.kwargs["analyze"] is False
    assert mocked.await_args.kwargs["recent_days"] == 2


# ── 02:00 AI 分析 ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_daily_analysis_find_due_and_limit(db_session: AsyncSession) -> None:
    generator = RegulatoryTrackerDailyAnalysisGenerator()
    assert await generator.find_due(db_session) == [True]

    with patch(
        "app.modules.regulatory_tracker.scheduled.analyze_new_documents",
        new=AsyncMock(return_value={"analyzed": 2, "failed": 0, "skipped": 0}),
    ) as mocked:
        await generator.execute_one(db_session, True)

    mocked.assert_awaited_once()
    assert mocked.await_args.kwargs["limit"] == 50


# ── 10:00 定时推送 ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_daily_notify_find_due_skips_without_setting(
    db_session: AsyncSession,
) -> None:
    generator = RegulatoryTrackerDailyNotifyGenerator()
    with patch(
        "app.modules.regulatory_tracker.scheduled.repo.get_notification_setting",
        new=AsyncMock(return_value=None),
    ):
        assert await generator.find_due(db_session) == []


@pytest.mark.anyio
async def test_daily_notify_find_due_skips_when_disabled(
    db_session: AsyncSession,
) -> None:
    generator = RegulatoryTrackerDailyNotifyGenerator()
    with patch(
        "app.modules.regulatory_tracker.scheduled.repo.get_notification_setting",
        new=AsyncMock(
            return_value=SimpleNamespace(
                is_enabled=False,
                recent_days=7,
                recipient_open_id=None,
                recipient_name=None,
                recipient_department=None,
            )
        ),
    ):
        assert await generator.find_due(db_session) == []


@pytest.mark.anyio
async def test_daily_notify_find_due_skips_without_recipient(
    db_session: AsyncSession,
) -> None:
    generator = RegulatoryTrackerDailyNotifyGenerator()
    disabled_recipient = _enabled_setting()
    disabled_recipient.recipient_open_id = None
    with patch(
        "app.modules.regulatory_tracker.scheduled.repo.get_notification_setting",
        new=AsyncMock(return_value=disabled_recipient),
    ):
        assert await generator.find_due(db_session) == []


@pytest.mark.anyio
async def test_daily_notify_find_due_returns_setting_when_enabled(
    db_session: AsyncSession,
) -> None:
    generator = RegulatoryTrackerDailyNotifyGenerator()
    with patch(
        "app.modules.regulatory_tracker.scheduled.repo.get_notification_setting",
        new=AsyncMock(return_value=_enabled_setting(recent_days=1)),
    ):
        items = await generator.find_due(db_session)
    assert len(items) == 1
    assert items[0].recipient_name == "武巧玲"


@pytest.mark.anyio
async def test_daily_notify_execute_one_pushes_recent_accepted_documents(
    db_session: AsyncSession,
) -> None:
    generator = RegulatoryTrackerDailyNotifyGenerator()
    item = _enabled_setting(recent_days=1)

    with (
        patch(
            "app.modules.regulatory_tracker.scheduled.RegulatoryTrackerNotificationService"
        ) as mocked_service_cls,
        patch(
            "app.modules.regulatory_tracker.scheduled.repo.list_recent_accepted_document_ids",
            new=AsyncMock(return_value=["11111111-1111-1111-1111-111111111111"]),
        ) as mocked_query,
    ):
        mocked_svc = AsyncMock()
        mocked_svc.send_update_notifications.return_value = {
            "sent": 1,
            "skipped": 0,
            "failed": 0,
        }
        mocked_service_cls.return_value = mocked_svc
        await generator.execute_one(db_session, item)

    expected_threshold = date.today() - timedelta(days=0)
    assert mocked_query.await_args.kwargs["threshold"] == expected_threshold
    mocked_svc.send_update_notifications.assert_awaited_once()
    assert mocked_svc.send_update_notifications.await_args.kwargs["document_ids"] == [
        "11111111-1111-1111-1111-111111111111"
    ]
    assert (
        mocked_svc.send_update_notifications.await_args.kwargs["trigger_type"]
        == "daily_auto_sync"
    )
