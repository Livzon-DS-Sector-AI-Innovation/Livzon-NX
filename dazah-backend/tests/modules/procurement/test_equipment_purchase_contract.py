"""设备↔采购备件采购契约封装测试（方案C）。

覆盖 create_equipment_purchase_request 的 items 解析：
- 物料说明缺省时用「名称 规格」补齐（真实事故：采购侧校验必填被拒）；
- 数量/单价 Decimal 转换与透传；调用采购 service 创建草稿单。
"""

from decimal import Decimal

import pytest

import app.modules.procurement.service as procurement_service
from app.modules.procurement.public_api import create_equipment_purchase_request


@pytest.mark.asyncio
async def test_contract_fills_material_description_from_name_and_spec(
    monkeypatch,
) -> None:
    captured: dict = {}

    class _FakeResp:
        id = "0b17f4e0-0000-4000-8000-000000000001"
        total_amount = Decimal("1350.00")
        status = "draft"

    async def _fake_create(db, payload) -> _FakeResp:
        captured["payload"] = payload
        return _FakeResp()

    monkeypatch.setattr(
        procurement_service, "create_purchase_request", _fake_create
    )

    result = await create_equipment_purchase_request(
        None,
        items=[
            {
                "product_name": "机械密封",
                "specification": "B401",
                "material_code": "SP-001",
                "quantity": 9,
                "unit": "套",
                "unit_price": 150,
                "remarks": "安全线预警",
            }
        ],
    )

    assert result == {
        "request_id": str(_FakeResp.id),
        "total_amount": 1350.0,
        "status": "draft",
    }
    item = captured["payload"].items[0]
    # 关键回归：物料说明必须被补齐（采购侧必填校验）
    assert item.material_description == "机械密封 B401"
    assert item.quantity == Decimal("9")
    assert item.unit_price == Decimal("150")
    assert captured["payload"].category.value == "hardware"


@pytest.mark.asyncio
async def test_contract_keeps_explicit_material_description(
    monkeypatch,
) -> None:
    captured: dict = {}

    class _FakeResp:
        id = "0b17f4e0-0000-4000-8000-000000000002"
        total_amount = Decimal("0")
        status = "draft"

    async def _fake_create(db, payload) -> _FakeResp:
        captured["payload"] = payload
        return _FakeResp()

    monkeypatch.setattr(
        procurement_service, "create_purchase_request", _fake_create
    )

    await create_equipment_purchase_request(
        None,
        items=[
            {
                "product_name": "轴承",
                "material_description": "定制深沟球轴承 6204",
                "quantity": 2,
                "unit_price": 80,
            }
        ],
    )
    item = captured["payload"].items[0]
    assert item.material_description == "定制深沟球轴承 6204"
