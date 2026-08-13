from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.main import app
from app.modules.procurement import api as procurement_api
from app.modules.procurement.schemas import (
    PurchaseApprovalRequest,
    PurchaseApprovalResult,
    PurchaseApprovalRole,
    PurchaseRequestCategory,
    PurchaseRequestItemResponse,
    PurchaseRequestResponse,
    PurchaseRequestStatus,
)
from app.platform.identity.deps import get_current_user


@pytest.fixture
async def authenticated_client(client: AsyncClient):
    async def _override_current_user():
        return SimpleNamespace(role="admin", status="active")

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _response() -> PurchaseRequestResponse:
    return PurchaseRequestResponse(
        id=uuid4(),
        category=PurchaseRequestCategory.fire,
        request_department="安全环保部",
        request_date=date(2026, 8, 12),
        attachment_note="消防器材技术参数附件",
        status=PurchaseRequestStatus.draft,
        total_amount=Decimal("100.00"),
        items=[
            PurchaseRequestItemResponse(
                id=uuid4(),
                sequence=1,
                product_name="",
                specification="",
                material_code="FIRE-001",
                material_description="灭火器",
                rule_model="4kg",
                purpose="消防设施补充",
                material="",
                brand="",
                quantity=Decimal("2"),
                unit="具",
                unit_price=Decimal("50"),
                total_amount=Decimal("100.00"),
                remarks="",
            )
        ],
        approvals=[],
    )


@pytest.mark.anyio
async def test_create_purchase_request_api_accepts_new_fields_and_attachment_note(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _response()

    async def create(_db, payload):
        assert payload.category == PurchaseRequestCategory.fire
        assert payload.attachment_note == "消防器材技术参数附件"
        assert payload.items[0].material_code == "FIRE-001"
        return expected

    monkeypatch.setattr(procurement_api, "create_purchase_request", create)
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests",
        json={
            "category": "fire",
            "request_department": "安全环保部",
            "request_date": "2026-08-12",
            "attachment_note": "消防器材技术参数附件",
            "items": [
                {
                    "material_code": "FIRE-001",
                    "material_description": "灭火器",
                    "rule_model": "4kg",
                    "purpose": "消防设施补充",
                    "material": "",
                    "brand": "",
                    "quantity": 2,
                    "unit": "具",
                    "unit_price": 50,
                    "remarks": "",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["attachment_note"] == "消防器材技术参数附件"
    assert body["data"]["items"][0]["material_code"] == "FIRE-001"


@pytest.mark.anyio
async def test_create_purchase_request_api_maps_material_validation_to_400(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def create(_db, _payload):
        raise ValueError("第1条明细缺少物料编码")

    monkeypatch.setattr(procurement_api, "create_purchase_request", create)
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests",
        json={
            "category": "fire",
            "request_department": "安全环保部",
            "request_date": "2026-08-12",
            "items": [
                {
                    "material_description": "灭火器",
                    "quantity": 2,
                    "unit_price": 50,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == "第1条明细缺少物料编码"


@pytest.mark.anyio
async def test_create_urgent_purchase_request_api_accepts_mixed_item_categories(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _response()
    expected.category = PurchaseRequestCategory.urgent

    async def create(_db, payload):
        assert payload.category == PurchaseRequestCategory.urgent
        assert [item.item_category for item in payload.items] == [
            PurchaseRequestCategory.hardware,
            PurchaseRequestCategory.office,
        ]
        return expected

    monkeypatch.setattr(procurement_api, "create_purchase_request", create)
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests",
        json={
            "category": "urgent",
            "request_department": "采购部",
            "request_date": "2026-08-12",
            "attachment_note": "加急技术附件",
            "items": [
                {
                    "item_category": "hardware",
                    "material_code": "HW-001",
                    "material_description": "螺栓",
                    "quantity": 2,
                    "unit_price": 10,
                },
                {
                    "item_category": "office",
                    "product_name": "标签纸",
                    "specification": "A4",
                    "quantity": 1,
                    "unit_price": 5,
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["category"] == "urgent"


@pytest.mark.anyio
async def test_create_urgent_purchase_request_api_maps_missing_item_category_to_400(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def create(_db, _payload):
        raise ValueError("第1条明细缺少申请类型")

    monkeypatch.setattr(procurement_api, "create_purchase_request", create)
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests",
        json={
            "category": "urgent",
            "request_department": "采购部",
            "request_date": "2026-08-12",
            "items": [
                {
                    "material_code": "HW-001",
                    "material_description": "螺栓",
                    "quantity": 2,
                    "unit_price": 10,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == "第1条明细缺少申请类型"


@pytest.mark.anyio
async def test_create_urgent_purchase_request_api_uses_test_database(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests",
        json={
            "category": "urgent",
            "request_department": "接口测试部",
            "request_date": "2026-08-12",
            "attachment_note": "测试附件说明",
            "items": [
                {
                    "item_category": "fire",
                    "material_code": "API-FIRE-001",
                    "material_description": "接口测试灭火器",
                    "quantity": 1,
                    "unit": "具",
                    "unit_price": 12.5,
                },
                {
                    "item_category": "office",
                    "product_name": "接口测试标签纸",
                    "specification": "A4",
                    "quantity": 2,
                    "unit": "包",
                    "unit_price": 3,
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["category"] == "urgent"
    assert body["attachment_note"] == "测试附件说明"
    assert [item["item_category"] for item in body["items"]] == [
        "fire",
        "office",
    ]


@pytest.mark.anyio
async def test_approve_purchase_request_api_accepts_new_approval_role(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _response()
    expected.category = PurchaseRequestCategory.electrical
    expected.status = PurchaseRequestStatus.pending_equipment_power

    async def approve(_db, request_id, payload: PurchaseApprovalRequest):
        assert request_id
        assert payload.approval_role == PurchaseApprovalRole.equipment_power
        assert payload.approver_name == "何学斌"
        assert payload.result == PurchaseApprovalResult.approved
        return expected

    monkeypatch.setattr(procurement_api, "approve_purchase_request", approve)
    response = await authenticated_client.post(
        f"/api/v1/procurement/purchase-requests/{uuid4()}/approve",
        json={
            "approval_role": "equipment_power",
            "approver_name": "何学斌",
            "opinion": "同意",
            "result": "approved",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending_equipment_power"


@pytest.mark.anyio
async def test_approve_purchase_request_api_returns_400_for_invalid_workflow_step(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def approve(_db, _request_id, _payload):
        raise ValueError("该采购类型不包含此审批步骤")

    monkeypatch.setattr(procurement_api, "approve_purchase_request", approve)
    response = await authenticated_client.post(
        f"/api/v1/procurement/purchase-requests/{uuid4()}/approve",
        json={
            "approval_role": "general_manager",
            "approver_name": "总经理",
            "opinion": "同意",
            "result": "approved",
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == "该采购类型不包含此审批步骤"
