from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, ExecutionContext
from sqlalchemy.engine.interfaces import DBAPICursor
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.energy.ledger_models import EnergyAdjustment
from app.modules.energy.ledger_schemas import (
    MeterDefinition,
    MeterWrite,
    RuleDefinition,
    RuleTerm,
    RuleWrite,
)
from app.modules.energy.ledger_service import EnergyLedgerService
from app.platform.identity.models import User


@pytest.mark.asyncio
async def test_rebuild_batches_adjustments_and_propagates_latest_zero(
    db_session: AsyncSession,
) -> None:
    """Monthly imports must not query adjustments once per result cell."""
    day = date(2040, 7, 1)
    actor = User(
        id=uuid4(),
        username=uuid4().hex,
        name="数据库测试",
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(actor)
    await db_session.flush()
    service = EnergyLedgerService(db_session, actor)
    meters = []
    for index in range(12):
        meters.append(
            await service.save_meter(
                MeterWrite(
                    definition=MeterDefinition(
                        code="batch_" + uuid4().hex,
                        name=f"电表{index}",
                        category="electricity",
                        area="测试",
                        department="测试",
                        unit="kWh",
                        reading_type="direct",
                        quantity_kind="electricity",
                        active_from=day,
                        enabled=True,
                    )
                )
            )
        )
    metric = "point:" + meters[0].definition.code
    rule = await service.save_rule(
        RuleWrite(
            definition=RuleDefinition(
                code="batch_sum_" + uuid4().hex,
                name="下游汇总",
                category="electricity",
                unit="kWh",
                department="测试",
                active_from=day,
                enabled=True,
                quantity_kind="electricity",
                terms=[RuleTerm(metric_key=metric)],
            )
        )
    )
    now = datetime.now(UTC)
    # Deliberately insert the newest correction before the older correction.
    for value, timestamp, deleted in [
        (0, now - timedelta(seconds=1), False),
        (5, now - timedelta(seconds=2), False),
        (99, now, True),
    ]:
        db_session.add(
            EnergyAdjustment(
                id=uuid4(),
                metric_key=metric,
                usage_date=day,
                mode="override",
                value=Decimal(value),
                reason="核对",
                created_by=actor.id,
                created_at=timestamp,
                is_deleted=deleted,
            )
        )
    await db_session.flush()
    connection = await db_session.connection()
    adjustment_queries: list[str] = []

    def capture(
        _connection: Connection,
        _cursor: DBAPICursor,
        statement: str,
        _parameters: object,
        _context: ExecutionContext,
        _many: bool,
    ) -> None:
        if "FROM energy.usage_adjustments" in statement:
            adjustment_queries.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", capture)
    try:
        await service.rebuild({day})
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", capture)
    assert 1 <= len(adjustment_queries) <= 2
    report = await service.report(day, day, report_scope="all", include_all=True)
    by_key = {row.metric_key: row for row in report.rows}
    assert by_key[metric].effective_value == 0
    assert by_key[metric].status == "adjusted"
    assert by_key["rule:" + rule.definition.code].effective_value == 0
    assert by_key["point:" + meters[1].definition.code].effective_value is None
