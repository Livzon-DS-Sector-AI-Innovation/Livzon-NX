"""Public procurement analytics and events consumed by other modules."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.event_service import DomainEventEnvelope
from app.modules.agent.models import AgentDomainEvent
from app.modules.agent.public_api import publish_domain_event
from app.modules.procurement.analytics_service import (
    AnalyticsAggregateInput as AnalyticsAggregateInput,
)
from app.modules.procurement.analytics_service import (
    AnalyticsFilterInput as AnalyticsFilterInput,
)
from app.modules.procurement.analytics_service import (
    AnalyticsMetricInput as AnalyticsMetricInput,
)
from app.modules.procurement.analytics_service import (
    AnalyticsOrderInput as AnalyticsOrderInput,
)
from app.modules.procurement.analytics_service import (
    aggregate_analytics,
)


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


async def aggregate_supplier_analytics(
    db: AsyncSession, data: AnalyticsAggregateInput
) -> dict[str, Any]:
    """Aggregate supplier master data under the executor's trusted page context."""
    return await aggregate_analytics(db, data)


async def create_equipment_purchase_request(
    db: AsyncSession,
    *,
    items: list[dict[str, Any]],
    request_department: str = "设备动力部",
    attachment_note: str = "设备模块备件安全线预警自动生成",
) -> dict[str, Any]:
    """设备模块备件采购入口：按明细创建「五金」类草稿采购申请单。

    契约说明（设备 → 采购）：
    - 只创建草稿单，审批、供应商、下单全流程留在采购模块；
    - items 字段：product_name/specification/material_code/quantity/
      unit/unit_price/remarks（缺省字段按采购 Schema 默认值补齐）；
    - 返回 {request_id, total_amount, status}，调用方负责回填追溯。
    """
    from datetime import date as _date
    from decimal import Decimal as _Decimal

    from app.modules.procurement.schemas import (
        PurchaseRequestCategory,
        PurchaseRequestCreate,
        PurchaseRequestItemInput,
    )
    from app.modules.procurement.service import create_purchase_request

    parsed = [
        PurchaseRequestItemInput(
            product_name=str(i.get("product_name", "")),
            specification=str(i.get("specification", "")),
            material_code=str(i.get("material_code", "")),
            # 采购侧校验物料说明必填：缺省时用「名称 规格」补齐，避免明细被拒
            material_description=str(
                i.get("material_description")
                or " ".join(
                    x for x in (i.get("product_name"), i.get("specification")) if x
                )
            ),
            quantity=_Decimal(str(i.get("quantity", 0))),
            unit=str(i.get("unit", "")),
            unit_price=_Decimal(str(i.get("unit_price", 0))),
            remarks=str(i.get("remarks", "")),
        )
        for i in items
    ]
    response = await create_purchase_request(
        db,
        PurchaseRequestCreate(
            category=PurchaseRequestCategory.hardware,
            request_department=request_department,
            request_date=_date.today(),
            attachment_note=attachment_note,
            items=parsed,
        ),
    )
    return {
        "request_id": str(response.id),
        "total_amount": float(response.total_amount),
        "status": response.status,
    }
