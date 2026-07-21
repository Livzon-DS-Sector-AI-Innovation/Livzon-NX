from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.deviations import Deviation
from app.modules.quality.repository.quality_management import get_deviations


@pytest.fixture(autouse=True)
async def _clean_deviations(db_session: AsyncSession):
    await db_session.execute(Deviation.__table__.delete())
    await db_session.commit()
    yield
    await db_session.execute(Deviation.__table__.delete())
    await db_session.commit()


@pytest.mark.anyio
async def test_get_deviations_supports_extended_filters_and_escaped_like(
    db_session: AsyncSession,
) -> None:
    keep = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-2026-001",
        title="100%_批过滤验证",
        description="描述包含 100%_批 特殊字符",
        department="质量部",
        status="pending_investigation",
        level="major",
        affected_items="原料 100%_批",
        batch_number="LOT-100%_批",
        has_occurred_before=True,
        investigation_completed_at=datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc),
        root_cause_analysis="根因_100%",
        corrective_actions="纠正%方案",
    )
    skip = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-2026-002",
        title="普通偏差",
        description="不应被命中",
        department="生产部",
        status="closed",
        level="minor",
        affected_items="原料B",
        batch_number="LOT-002",
        has_occurred_before=False,
        investigation_completed_at=datetime(2026, 7, 4, 9, 0, tzinfo=timezone.utc),
        root_cause_analysis="其他根因",
        corrective_actions="其他措施",
    )
    db_session.add_all([keep, skip])
    await db_session.commit()

    items, total = await get_deviations(
        db_session,
        status="pending_investigation",
        level="major",
        department="质量部",
        keyword="100%_批",
        page=1,
        page_size=20,
        deviation_code="2026-001",
        product_keyword="100%_批",
        has_occurred_before=True,
        is_closed=False,
        investigation_completed_from=datetime(
            2026, 7, 2, 0, 0, tzinfo=timezone.utc
        ),
        investigation_completed_to=datetime(
            2026, 7, 3, 0, 0, tzinfo=timezone.utc
        ),
        root_cause_keyword="根因_100%",
        corrective_actions_keyword="纠正%方案",
    )

    assert total == 1
    assert [item.id for item in items] == [keep.id]
