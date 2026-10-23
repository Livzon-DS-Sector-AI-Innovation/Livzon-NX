"""Persist workbook metadata in tests without retired management APIs."""

from uuid import uuid4

from app.modules.energy.ledger_models import EnergyCalculationRule, EnergyMeterPoint
from app.modules.energy.ledger_schemas import (
    MeterResponse,
    MeterWrite,
    RuleResponse,
    RuleWrite,
)
from app.modules.energy.ledger_service import EnergyLedgerService


async def seed_meter(
    service: EnergyLedgerService, payload: MeterWrite
) -> MeterResponse:
    item = EnergyMeterPoint(
        id=uuid4(),
        code=payload.definition.code,
        version=1,
        definition=payload.definition.model_dump(mode="json"),
    )
    service.db.add(item)
    await service.db.flush()
    return MeterResponse(id=item.id, version=1, definition=payload.definition)


async def seed_rule(service: EnergyLedgerService, payload: RuleWrite) -> RuleResponse:
    item = EnergyCalculationRule(
        id=uuid4(),
        code=payload.definition.code,
        version=1,
        definition=payload.definition.model_dump(mode="json"),
    )
    service.db.add(item)
    await service.db.flush()
    return RuleResponse(id=item.id, version=1, definition=payload.definition)
