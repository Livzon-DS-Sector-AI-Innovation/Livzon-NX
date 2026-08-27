from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.registration.models import (
    AuthorizationLedgerEntry,
    AuthorizationLedgerMain,
    AuthorizationLedgerUpdate,
)
from app.modules.registration.service import AuthorizationLetterService


async def _list_active_mains(db_session: AsyncSession) -> list[AuthorizationLedgerMain]:
    result = await db_session.execute(
        select(AuthorizationLedgerMain)
        .options(selectinload(AuthorizationLedgerMain.updates))
        .where(AuthorizationLedgerMain.is_deleted.is_(False))
    )
    return list(result.scalars().unique().all())


@pytest.mark.asyncio
async def test_backfill_grouped_ledger_from_legacy_is_idempotent(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
    suffix = uuid4().hex[:6].upper()
    legacy_product_name = f"回填验证-{suffix}"
    legacy_market_name = f"测试市场-{suffix}"

    legacy_entries = [
        AuthorizationLedgerEntry(
            product_name=legacy_product_name,
            market_name=legacy_market_name,
            source_sequence="1",
            authorization_file_name="LOA for Zenex Animal Health India Private Limited",
            quality_standard="USP",
            company_name="Zenex Animal Health India Private Limited",
            country="India",
            customer_code="KH-001",
            purpose="注册",
            authorization_date="2024.02.19",
            handler="刘乐",
            status="已递交",
            remarks="首次授权",
            created_at=now,
            updated_at=now,
        ),
        AuthorizationLedgerEntry(
            product_name=legacy_product_name,
            market_name=legacy_market_name,
            source_sequence="1",
            authorization_file_name="LOA for Zenex Animal Health India Private Limited",
            quality_standard="USP",
            company_name="Zenex Animal Health India Private Limited",
            country="India",
            customer_code="KH-001",
            purpose="注册",
            authorization_date="2024.11.22",
            handler="刘乐",
            status="已递交",
            remarks="更新博茨瓦纳的 LOA",
            created_at=now.replace(month=11, day=22),
            updated_at=now.replace(month=11, day=22),
        ),
    ]

    stale_main = AuthorizationLedgerMain(
        product_name=f"脏数据-{suffix}",
        market_name="欧盟",
        source_sequence="1",
        authorization_file_name="LOA for C&H Generics Limited",
        quality_standard="EP",
        company_name="C&H Generics Limited",
        country="Ireland",
        customer_code="KH-TEST",
        purpose="注册",
        status="已递交",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([*legacy_entries, stale_main])
    await db_session.flush()

    db_session.add_all(
        [
            AuthorizationLedgerUpdate(
                ledger_main_id=stale_main.id,
                sort_order=1,
                authorization_date="2026.01.01",
                handler="张三",
                remarks="测试主记录",
                created_at=now,
                updated_at=now,
            ),
            AuthorizationLedgerUpdate(
                ledger_main_id=stale_main.id,
                sort_order=2,
                authorization_date="2026.02.03",
                handler="李四",
                remarks="补充更新",
                created_at=now.replace(month=2, day=3),
                updated_at=now.replace(month=2, day=3),
            ),
        ]
    )
    await db_session.commit()

    service = AuthorizationLetterService(db_session)
    first_stats = await service.backfill_grouped_ledger_from_legacy()

    assert first_stats["legacy_entry_count"] >= 2
    assert first_stats["legacy_group_count"] >= 1
    assert first_stats["soft_deleted_main_count"] >= 1
    assert first_stats["soft_deleted_update_count"] >= 2
    assert first_stats["created_main_count"] >= 1
    assert first_stats["created_update_count"] >= 2

    active_mains = [
        item
        for item in await _list_active_mains(db_session)
        if item.product_name == legacy_product_name
    ]
    assert len(active_mains) == 1
    assert active_mains[0].product_name == legacy_product_name
    assert active_mains[0].market_name == legacy_market_name
    assert [item.sort_order for item in active_mains[0].updates] == [1, 2]
    assert [item.authorization_date for item in active_mains[0].updates] == [
        "2024.02.19",
        "2024.11.22",
    ]
    assert [item.remarks for item in active_mains[0].updates] == [
        "首次授权",
        "更新博茨瓦纳的 LOA",
    ]

    stale_main_result = await db_session.execute(
        select(AuthorizationLedgerMain).where(
            AuthorizationLedgerMain.id == stale_main.id
        )
    )
    persisted_stale_main = stale_main_result.scalar_one()
    assert persisted_stale_main.is_deleted is True

    second_stats = await service.backfill_grouped_ledger_from_legacy()
    assert second_stats["legacy_entry_count"] >= 2
    assert second_stats["legacy_group_count"] >= 1
    assert second_stats["created_main_count"] == 0
    assert second_stats["created_update_count"] == 0
    assert second_stats["reused_main_count"] >= 1

    active_mains_after_second_run = [
        item
        for item in await _list_active_mains(db_session)
        if item.product_name == legacy_product_name
    ]
    assert len(active_mains_after_second_run) == 1
    assert [item.sort_order for item in active_mains_after_second_run[0].updates] == [
        1,
        2,
    ]
