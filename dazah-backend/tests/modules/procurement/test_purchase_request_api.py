from datetime import date
from decimal import Decimal
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
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

SimpleNamespace: Any = _SimpleNamespace


@pytest.fixture
async def authenticated_client(client: AsyncClient) -> Any:
    async def _override_current_user() -> Any:
        return SimpleNamespace(role="admin", status="active", name="何学斌")

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

    async def create(_db: Any, payload: Any) -> Any:
        assert payload.category == PurchaseRequestCategory.fire
        assert payload.attachment_note == "消防器材技术参数附件"
        assert payload.items[0].material_code == "FIRE-001"
        return expected

    monkeypatch.setattr(procurement_api, "create_purchase_request", create)
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-fire"},
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
    async def create(_db: Any, _payload: Any) -> Any:
        raise ValueError("第1条明细缺少物料编码")

    monkeypatch.setattr(procurement_api, "create_purchase_request", create)
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-fire"},
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

    async def create(_db: Any, payload: Any) -> Any:
        assert payload.category == PurchaseRequestCategory.urgent
        assert [item.item_category for item in payload.items] == [
            PurchaseRequestCategory.hardware,
            PurchaseRequestCategory.office,
        ]
        return expected

    monkeypatch.setattr(procurement_api, "create_purchase_request", create)
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-urgent"},
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
    async def create(_db: Any, _payload: Any) -> Any:
        raise ValueError("第1条明细缺少申请类型")

    monkeypatch.setattr(procurement_api, "create_purchase_request", create)
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-urgent"},
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
        headers={"X-Dazah-Page-Key": "purchasing:request:request-urgent"},
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

    async def approve(
        _db: Any, request_id: Any, payload: PurchaseApprovalRequest
    ) -> Any:
        assert request_id
        assert payload.approval_role == PurchaseApprovalRole.equipment_power
        assert payload.approver_name == "何学斌"
        assert payload.result == PurchaseApprovalResult.approved
        return expected

    monkeypatch.setattr(procurement_api, "approve_purchase_request", approve)
    response = await authenticated_client.post(
        f"/api/v1/procurement/purchase-requests/{uuid4()}/approve",
        headers={
            "X-Dazah-Page-Key": (
                "purchasing:approval:approval-electrical:"
                "approval-electrical-equipment-power"
            )
        },
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
    async def approve(_db: Any, _request_id: Any, _payload: Any) -> Any:
        raise ValueError("该采购类型不包含此审批步骤")

    monkeypatch.setattr(procurement_api, "approve_purchase_request", approve)
    response = await authenticated_client.post(
        f"/api/v1/procurement/purchase-requests/{uuid4()}/approve",
        headers={
            "X-Dazah-Page-Key": (
                "purchasing:approval:approval-urgent:"
                "approval-urgent-general-manager"
            )
        },
        json={
            "approval_role": "general_manager",
            "approver_name": "总经理",
            "opinion": "同意",
            "result": "approved",
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == "该采购类型不包含此审批步骤"


@pytest.mark.anyio
async def test_import_purchase_requests_api_accepts_table_file(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.procurement.schemas import (
        PurchaseRequestImportResult,
        PurchaseRequestImportSummary,
    )

    async def import_table(_db: Any, _file_bytes: Any, *, file_name: Any) -> Any:
        assert file_name == "采购申请.xlsx"
        return PurchaseRequestImportResult(
            file_name=file_name,
            total_sheets=2,
            imported_requests=[
                PurchaseRequestImportSummary(
                    request_id=uuid4(),
                    sheet_name="五金材料",
                    category=PurchaseRequestCategory.hardware,
                    category_label="五金材料",
                    request_department="102一车间",
                    request_date=date(2026, 8, 14),
                    items_count=2,
                )
            ],
            failed_rows=[],
        )

    monkeypatch.setattr(
        procurement_api,
        "import_purchase_request_table_file",
        import_table,
    )
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests/import",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-hardware"},
        files={
            "file": (
                "采购申请.xlsx",
                b"xlsx-bytes",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total_sheets"] == 2
    assert body["data"]["imported_requests"][0]["category"] == "hardware"
    assert body["data"]["imported_requests"][0]["items_count"] == 2
    assert body["data"]["failed_rows"] == []


@pytest.mark.anyio
async def test_import_purchase_requests_api_rejects_unsupported_extension(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests/import",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-hardware"},
        files={"file": ("采购申请.docx", b"docx-bytes", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "请上传 xlsx、xls 或 csv 文件" in response.json()["message"]


@pytest.mark.anyio
async def test_import_purchase_requests_api_maps_service_error_to_400(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def import_table(_db: Any, _file_bytes: Any, *, file_name: Any) -> Any:
        raise ValueError("上传文件为空")

    monkeypatch.setattr(
        procurement_api,
        "import_purchase_request_table_file",
        import_table,
    )
    response = await authenticated_client.post(
        "/api/v1/procurement/purchase-requests/import",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-hardware"},
        files={"file": ("采购申请.xlsx", b"", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "上传文件为空"


@pytest.mark.anyio
async def test_delete_purchase_request_api_deletes_draft(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()

    async def delete_request(_db: Any, delete_id: Any) -> Any:
        assert delete_id == request_id
        return True

    monkeypatch.setattr(procurement_api, "delete_purchase_request", delete_request)
    response = await authenticated_client.delete(
        f"/api/v1/procurement/purchase-requests/{request_id}",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-fire"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "采购申请已删除"
    assert body["data"]["success_count"] == 1
    assert body["data"]["fail_count"] == 0


@pytest.mark.anyio
async def test_delete_purchase_request_api_maps_status_error_to_400(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def delete_request(_db: Any, _delete_id: Any) -> Any:
        raise ValueError("仅草稿状态的采购申请可以删除")

    monkeypatch.setattr(procurement_api, "delete_purchase_request", delete_request)
    response = await authenticated_client.delete(
        f"/api/v1/procurement/purchase-requests/{uuid4()}",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-fire"},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "仅草稿状态的采购申请可以删除"


@pytest.mark.anyio
async def test_submit_purchase_request_api_maps_total_amount_error_to_400(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def submit(_db: Any, _request_id: Any) -> Any:
        raise ValueError(
            "第1条明细总额（0.00）与数量×单价（50.00）不一致，请修改后重新提交"
        )

    monkeypatch.setattr(procurement_api, "submit_purchase_request", submit)
    response = await authenticated_client.post(
        f"/api/v1/procurement/purchase-requests/{uuid4()}/submit",
        headers={"X-Dazah-Page-Key": "purchasing:request:request-fire"},
    )

    assert response.status_code == 400
    assert "总额（0.00）与数量×单价（50.00）不一致" in response.json()["message"]
