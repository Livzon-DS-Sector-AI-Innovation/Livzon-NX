import base64
from typing import Any
from urllib.parse import quote
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.agent.tools import ToolContext, agent_tool
from app.modules.procurement.contract_generator import (
    TEMPLATE_DIR,
    TEMPLATE_FILES,
    generate_contract,
    get_contract_template_metadata,
)
from app.modules.procurement.schemas import (
    ContractCategory,
    ContractGenerateRequest,
    InvoiceRecognitionRecordResponse,
    PurchaseApprovalRequest,
    PurchaseApprovalResult,
    PurchaseApprovalRole,
    PurchaseApprovalView,
    PurchaseOrderLineResponse,
    PurchaseRequestCreate,
    PurchaseRequestResponse,
    PurchaseRequestUpdate,
    SupplierResponse,
)
from app.modules.procurement.service import (
    approve_purchase_request,
    export_purchase_order_lines_xlsx,
    get_purchase_request,
    list_invoice_recognition_records,
    list_purchase_order_lines,
    list_purchase_requests,
    list_suppliers,
    reject_purchase_request,
    submit_purchase_request,
)
from app.modules.procurement.service import (
    create_purchase_request as create_purchase_request_service,
)
from app.modules.procurement.service import (
    update_purchase_request as update_purchase_request_service,
)


class PageInput(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class InvoiceRecordsInput(PageInput):
    keyword: str | None = None
    seller_name: str | None = None
    invoice_number: str | None = None


class SupplierListInput(PageInput):
    keyword: str | None = None
    supplier_name: str | None = None
    material_name: str | None = None
    purchase_category: str | None = None


class PurchaseRequestListInput(PageInput):
    category: str | None = None
    status: str | None = None
    approval_role: PurchaseApprovalRole | None = None
    approval_view: PurchaseApprovalView = PurchaseApprovalView.pending
    keyword: str | None = None


class PurchaseRequestIdInput(BaseModel):
    request_id: UUID


class PurchaseRequestCreateInput(PurchaseRequestCreate):
    pass


class PurchaseRequestUpdateInput(PurchaseRequestUpdate):
    request_id: UUID


class PurchaseApprovalInput(PurchaseApprovalRequest):
    request_id: UUID


class PurchaseOrderInput(PageInput):
    category: str | None = None
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)


class PurchaseOrderExportInput(BaseModel):
    category: str | None = None
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)


class ContractTemplateInput(BaseModel):
    category: ContractCategory


def _purchase_request(value: PurchaseRequestResponse) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _purchase_order(value: PurchaseOrderLineResponse) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _artifact_response(
    *,
    filename: str,
    content_type: str,
    content: bytes,
    operation: str,
) -> dict[str, Any]:
    disposition = f"attachment; filename*=utf-8''{quote(filename, safe='')}"
    return {
        "content_type": content_type,
        "content_disposition": disposition,
        "size": len(content),
        "operation": operation,
        "artifact": {
            "kind": "file",
            "filename": filename,
            "content_type": content_type,
            "base64": base64.b64encode(content).decode("ascii"),
            "size": len(content),
        },
    }


def _contract_template_info(category: ContractCategory) -> dict[str, Any]:
    metadata = get_contract_template_metadata(category)
    template_file = TEMPLATE_FILES[category]
    template_path = TEMPLATE_DIR / template_file
    fields = [field.model_dump(mode="json") for field in metadata.fields]
    required_fields = [field["name"] for field in fields if field.get("required")]
    return {
        "category": metadata.category.value,
        "label": metadata.label,
        "template": {
            "file": template_file,
            "exists": template_path.exists(),
            "size": template_path.stat().st_size if template_path.exists() else 0,
        },
        "fields": fields,
        "required_fields": required_fields,
        "item_required_fields": ["name", "quantity", "unit_price"],
        "generate_required_fields": [
            "title",
            "category",
            "contract_number",
            "contract_date",
            "items",
        ],
        "notes": (
            "生成合同时必须提供 title 合同标题并至少提供一条 items 明细；"
            "items 每条至少需要 "
            "name、quantity、unit_price。seller 字段可逐项补充，未提供时为空。"
        ),
    }


@agent_tool(
    name="procurement.list_invoice_records",
    summary="查询发票识别记录",
    input_model=InvoiceRecordsInput,
    method="GET",
    path="/procurement/invoices/recognition-records",
)
async def list_invoice_records(
    context: ToolContext, data: InvoiceRecordsInput
) -> dict[str, Any]:
    records, total = await list_invoice_recognition_records(
        context.db,
        keyword=data.keyword,
        seller_name=data.seller_name,
        invoice_number=data.invoice_number,
        page=data.page,
        page_size=data.page_size,
    )
    return {
        "data": [
            InvoiceRecognitionRecordResponse.model_validate(record).model_dump(
                mode="json"
            )
            for record in records
        ],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="procurement.list_suppliers",
    summary="查询供应商清单",
    input_model=SupplierListInput,
    method="GET",
    path="/procurement/suppliers",
    input_schema={
        "params": {
            "keyword": "跨供应商、物料、厂家、品类和原始字段关键词",
            "supplier_name": "供应商名称模糊查询",
            "material_name": "物料名称模糊查询",
            "purchase_category": "采购品类名称精确查询",
            "page": "页码，默认 1",
            "page_size": "每页条数，默认 20，最大 100",
        }
    },
    output_hint="返回供应商代码、供应商名称、物料、厂家、品类和导入原始字段。",
)
async def list_supplier_records(
    context: ToolContext, data: SupplierListInput
) -> dict[str, Any]:
    suppliers, total, columns = await list_suppliers(
        context.db,
        keyword=data.keyword,
        supplier_name=data.supplier_name,
        material_name=data.material_name,
        purchase_category=data.purchase_category,
        page=data.page,
        page_size=data.page_size,
    )
    return {
        "data": [
            SupplierResponse.model_validate(supplier).model_dump(mode="json")
            for supplier in suppliers
        ],
        "meta": {
            "page": data.page,
            "page_size": data.page_size,
            "total": total,
            "columns": columns,
        },
    }


@agent_tool(
    name="procurement.list_purchase_requests",
    summary="查询采购申请",
    input_model=PurchaseRequestListInput,
    method="GET",
    path="/procurement/purchase-requests",
)
async def list_purchase_request_records(
    context: ToolContext, data: PurchaseRequestListInput
) -> dict[str, Any]:
    requests, total = await list_purchase_requests(
        context.db,
        category=data.category,
        status=data.status,
        approval_role=data.approval_role,
        approval_view=data.approval_view,
        keyword=data.keyword,
        page=data.page,
        page_size=data.page_size,
    )
    return {
        "data": [_purchase_request(request) for request in requests],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="procurement.get_purchase_request",
    summary="查看采购申请详情",
    input_model=PurchaseRequestIdInput,
    method="GET",
    path="/procurement/purchase-requests/{request_id}",
)
async def get_purchase_request_record(
    context: ToolContext, data: PurchaseRequestIdInput
) -> dict[str, Any]:
    return _purchase_request(await get_purchase_request(context.db, data.request_id))


@agent_tool(
    name="procurement.create_purchase_request",
    summary="创建采购申请",
    input_model=PurchaseRequestCreateInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/procurement/purchase-requests",
)
async def create_purchase_request(
    context: ToolContext, data: PurchaseRequestCreateInput
) -> dict[str, Any]:
    return _purchase_request(await create_purchase_request_service(context.db, data))


@agent_tool(
    name="procurement.update_purchase_request",
    summary="更新采购申请",
    input_model=PurchaseRequestUpdateInput,
    write=True,
    risk_level="medium",
    method="PUT",
    path="/procurement/purchase-requests/{request_id}",
)
async def update_purchase_request(
    context: ToolContext, data: PurchaseRequestUpdateInput
) -> dict[str, Any]:
    payload = PurchaseRequestUpdate.model_validate(
        data.model_dump(exclude={"request_id"})
    )
    return _purchase_request(
        await update_purchase_request_service(context.db, data.request_id, payload)
    )


@agent_tool(
    name="procurement.submit_purchase_request",
    summary="提交采购申请",
    input_model=PurchaseRequestIdInput,
    write=True,
    risk_level="medium",
    method="POST",
    path="/procurement/purchase-requests/{request_id}/submit",
)
async def submit_purchase_request_record(
    context: ToolContext, data: PurchaseRequestIdInput
) -> dict[str, Any]:
    return _purchase_request(await submit_purchase_request(context.db, data.request_id))


@agent_tool(
    name="procurement.approve_purchase_request",
    summary="审批通过采购申请",
    input_model=PurchaseApprovalInput,
    write=True,
    risk_level="high",
    workflow_allowed=False,
    human_decision_required=True,
    method="POST",
    path="/procurement/purchase-requests/{request_id}/approve",
)
async def approve_purchase_request_record(
    context: ToolContext, data: PurchaseApprovalInput
) -> dict[str, Any]:
    payload = PurchaseApprovalRequest(
        approval_role=data.approval_role,
        approver_name=data.approver_name,
        opinion=data.opinion,
        result=PurchaseApprovalResult.approved,
    )
    return _purchase_request(
        await approve_purchase_request(context.db, data.request_id, payload)
    )


@agent_tool(
    name="procurement.reject_purchase_request",
    summary="驳回采购申请",
    input_model=PurchaseApprovalInput,
    write=True,
    risk_level="high",
    workflow_allowed=False,
    human_decision_required=True,
    method="POST",
    path="/procurement/purchase-requests/{request_id}/reject",
)
async def reject_purchase_request_record(
    context: ToolContext, data: PurchaseApprovalInput
) -> dict[str, Any]:
    payload = PurchaseApprovalRequest(
        approval_role=data.approval_role,
        approver_name=data.approver_name,
        opinion=data.opinion,
        result=PurchaseApprovalResult.rejected,
    )
    return _purchase_request(
        await reject_purchase_request(context.db, data.request_id, payload)
    )


@agent_tool(
    name="procurement.list_purchase_orders",
    summary="查询采购订单",
    input_model=PurchaseOrderInput,
    method="GET",
    path="/procurement/purchase-orders",
)
async def list_purchase_order_records(
    context: ToolContext, data: PurchaseOrderInput
) -> dict[str, Any]:
    lines, total = await list_purchase_order_lines(
        context.db,
        category=data.category,
        year=data.year,
        month=data.month,
        page=data.page,
        page_size=data.page_size,
    )
    return {
        "data": [_purchase_order(line) for line in lines],
        "meta": {"page": data.page, "page_size": data.page_size, "total": total},
    }


@agent_tool(
    name="procurement.export_purchase_orders",
    summary="导出采购订单",
    input_model=PurchaseOrderExportInput,
    method="GET",
    path="/procurement/purchase-orders/export",
)
async def export_purchase_orders(
    context: ToolContext, data: PurchaseOrderExportInput
) -> dict[str, Any]:
    content = await export_purchase_order_lines_xlsx(
        context.db,
        category=data.category,
        year=data.year,
        month=data.month,
    )
    filename = f"采购订单_{data.year}-{data.month:02d}.xlsx"
    return _artifact_response(
        filename=filename,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        content=content,
        operation="procurement.export_purchase_orders",
    )


@agent_tool(
    name="procurement.list_contract_templates",
    summary="查询四类合同模板字段",
    method="GET",
    path="/procurement/contracts/templates",
)
async def list_contract_templates(context: ToolContext, _: BaseModel) -> dict[str, Any]:
    return {
        "templates": [
            _contract_template_info(category) for category in ContractCategory
        ],
        "generate_operation": "procurement.generate_contract",
        "template_lookup_operation": "procurement.get_contract_template",
    }


@agent_tool(
    name="procurement.get_contract_template",
    summary="查询合同模板",
    input_model=ContractTemplateInput,
    method="GET",
    path="/procurement/contracts/templates/{category}",
)
async def get_contract_template(
    context: ToolContext, data: ContractTemplateInput
) -> dict[str, Any]:
    return _contract_template_info(data.category)


@agent_tool(
    name="procurement.generate_contract",
    summary="生成采购合同",
    input_model=ContractGenerateRequest,
    write=True,
    risk_level="medium",
    method="POST",
    path="/procurement/contracts/generate",
)
async def generate_purchase_contract(
    context: ToolContext, data: ContractGenerateRequest
) -> dict[str, Any]:
    buffer, filename, media_type = generate_contract(data)
    return _artifact_response(
        filename=filename,
        content_type=media_type,
        content=buffer.getvalue(),
        operation="procurement.generate_contract",
    )
