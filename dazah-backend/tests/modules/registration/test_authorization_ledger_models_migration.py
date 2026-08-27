from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.registration.models import (
    AuthorizationLedgerMain,
    AuthorizationLedgerUpdate,
)
from app.modules.registration.schemas import AuthorizationLedgerMainRead


@pytest.mark.asyncio
async def test_create_authorization_ledger_main_read_returns_updates(
    db_session: AsyncSession,
) -> None:
    main = AuthorizationLedgerMain(
        product_name="多拉菌素",
        market_name="欧盟",
        source_sequence="1",
        authorization_file_name="多拉菌素欧盟授权书",
        quality_standard="EP",
        company_name="客户公司",
        country="爱尔兰",
        customer_code="KH-001",
        purpose="注册",
        status="有效",
        updates=[
            AuthorizationLedgerUpdate(
                sort_order=1,
                authorization_date="2026.01.01",
                handler="王五",
                remarks="首次授权",
            ),
            AuthorizationLedgerUpdate(
                sort_order=2,
                authorization_date="2026.02.03",
                handler="张三",
                remarks="补充更新",
            ),
        ],
    )

    db_session.add(main)
    await db_session.flush()

    result = await db_session.execute(
        select(AuthorizationLedgerMain)
        .options(selectinload(AuthorizationLedgerMain.updates))
        .where(AuthorizationLedgerMain.id == main.id)
    )
    persisted = result.scalar_one()

    payload = AuthorizationLedgerMainRead.model_validate(persisted)

    assert payload.product_name == "多拉菌素"
    assert payload.authorization_file_name == "多拉菌素欧盟授权书"
    assert len(payload.updates) == 2
    assert [item.sort_order for item in payload.updates] == [1, 2]
    assert payload.updates[0].authorization_date == "2026.01.01"
    assert payload.updates[1].handler == "张三"
    assert payload.updates[1].ledger_main_id == payload.id
