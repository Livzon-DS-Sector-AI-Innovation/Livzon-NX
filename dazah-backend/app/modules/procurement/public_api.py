"""Stable procurement events consumed by other platform modules."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.event_service import DomainEventEnvelope
from app.modules.agent.models import AgentDomainEvent
from app.modules.agent.public_api import publish_domain_event


async def publish_purchase_arrival(
    db: AsyncSession,
    *,
    arrival_id: str,
    purchase_request_id: UUID,
    warehouse_code: str,
    material_code: str,
    material_name: str,
    received_quantity: Decimal,
    correlation_id: UUID,
) -> AgentDomainEvent:
    """Publish a minimal arrival fact; warehouse details stay out of the event."""
    return await publish_domain_event(
        db,
        envelope=DomainEventEnvelope(
            source_module="procurement",
            event_type="procurement.purchase_arrival.v1",
            event_version="v1",
            subject_type="purchase_arrival",
            subject_id=arrival_id,
            idempotency_key=f"procurement.purchase_arrival:{arrival_id}",
            correlation_id=correlation_id,
            payload={
                "purchase_request_id": str(purchase_request_id),
                "warehouse_code": warehouse_code,
                "material_code": material_code,
                "material_name": material_name,
                "received_quantity": str(received_quantity),
            },
        ),
    )
