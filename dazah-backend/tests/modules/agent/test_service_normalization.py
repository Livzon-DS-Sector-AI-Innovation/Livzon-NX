import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.modules.agent.service import AgentService
from app.modules.procurement.agent_tools import (
    PurchaseRequestCreateInput,
    PurchaseRequestUpdateInput,
)

SimpleNamespace: Any = _SimpleNamespace


@pytest.fixture
def service() -> AgentService:
    return AgentService(
        settings=SimpleNamespace(API_V1_PREFIX="/api/v1/"),
        access_scope_service=SimpleNamespace(),
    )


def test_payload_and_path_helpers(service: AgentService) -> None:
    assert service._unwrap_payload(None, {"name": "params"}) == {"name": "params"}
    assert service._unwrap_payload(
        {"payload": {"name": "nested"}, "keep": True},
        {},
    ) == {"payload": {"name": "nested"}, "keep": True, "name": "nested"}
    assert service._unwrap_payload({"payload": "not-a-mapping"}, {}) == {
        "payload": "not-a-mapping"
    }

    assert service._format_path("/items/{item_id}", {"item_id": 7}) == (
        "/api/v1/items/7"
    )
    with pytest.raises(HTTPException, match="Missing required"):
        service._format_path("/items/{item_id}", {})

    assert service._path_param_names("/a/{first}/b/{ second }") == [
        "first",
        "second",
    ]
    assert service._path_param_names("/a/{}/b") == []


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("attachment", None),
        ("attachment; filename=", None),
        ("attachment; filename=report.xlsx", "report.xlsx"),
        ('attachment; filename="report.xlsx"; size=1', "report.xlsx"),
        ("attachment; filename*=UTF-8''%E6%8A%A5%E5%91%8A.xlsx", "报告.xlsx"),
    ],
)
def test_download_filename(
    header: str | None,
    expected: str | None,
) -> None:
    assert AgentService._download_filename(header) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ({"items": [{"name": "A"}]}, [{"name": "A"}]),
        ({"items": [], "item": {"name": "B"}}, [{"name": "B"}]),
        ({"name": "C", "unrelated": 1}, [{"name": "C"}]),
        ({"unrelated": 1}, []),
    ],
)
def test_extract_items_source(
    service: AgentService,
    source: dict[str, Any],
    expected: list[Any],
) -> None:
    assert service._extract_items_source(source) == expected


@pytest.mark.parametrize(
    ("category", "text", "title", "unit", "item_name"),
    [
        (
            "consumables",
            "办公用品示例",
            "办公用品耗材采购合同",
            "个",
            "办公用品耗材",
        ),
        ("hardware", "", "五金备件采购合同", "个", "五金备件"),
        ("raw-materials", "", "原材料采购合同", "吨", "原材料"),
        ("fixed-assets", "", "固定资产采购合同", "台", "固定资产设备"),
        ("unknown", "", "采购合同", "个", "采购物品"),
    ],
)
def test_contract_defaults(
    category: str,
    text: str,
    title: str,
    unit: str,
    item_name: str,
) -> None:
    assert AgentService._default_contract_title(category, text) == title
    assert AgentService._default_contract_unit(category) == unit
    assert AgentService._sample_contract_item_name(category, text) == item_name
    assert AgentService._default_contract_number(category).startswith(
        f"AI-{category.replace('-', '').upper()}-"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("固定资产设备", "fixed-assets"),
        ("办公用品耗材", "consumables"),
        ("五金备件", "hardware"),
        ("原材料", "raw-materials"),
        ("custom", "custom"),
    ],
)
def test_normalize_contract_category(value: object, expected: object) -> None:
    assert AgentService._normalize_contract_category(value) == expected


def test_normalize_contract_item_supports_aliases_and_defaults() -> None:
    assert AgentService._normalize_contract_item(
        {
            "code": "M-1",
            "product_name": "物料",
            "spec": "S",
            "factory": "F",
            "request_department": "D",
            "qty": 2,
            "price": 3,
            "remark": "R",
        }
    ) == {
        "item_code": "M-1",
        "name": "物料",
        "specification": "S",
        "quality_standard": "",
        "manufacturer": "F",
        "department": "D",
        "quantity": 2,
        "unit": "",
        "unit_price": 3,
        "amount": None,
        "remarks": "R",
    }
    assert AgentService._normalize_contract_item({"title": "备用"})["name"] == "备用"


def test_normalize_contract_body_builds_sample_and_preserves_explicit_values(
    service: AgentService,
) -> None:
    sample = service._normalize_contract_body(
        {
            "contract_category": "五金",
            "department": "设备部",
        },
        {},
        "请生成示例合同",
    )
    assert sample["category"] == "hardware"
    assert sample["items"][0] == {
        "item_code": "",
        "name": "五金备件",
        "specification": "",
        "quality_standard": "",
        "manufacturer": "",
        "department": "设备部",
        "quantity": 1,
        "unit": "个",
        "unit_price": 0,
        "amount": None,
        "remarks": "示例",
    }
    assert sample["tax_rate"] == 13
    assert sample["seller"] == {}

    explicit = service._normalize_contract_body(
        {
            "type": "raw_materials",
            "contract_title": "自定义合同",
            "contract_no": "C-1",
            "date": "2026-07-30",
            "tax_rate": 9,
            "seller": {"name": "供应商"},
            "item": {"item_name": "原料", "quantity": 4, "unit_price": 5},
        },
        {},
        None,
    )
    assert explicit["title"] == "自定义合同"
    assert explicit["contract_number"] == "C-1"
    assert explicit["contract_date"] == "2026-07-30"
    assert explicit["tax_rate"] == 9
    assert explicit["seller"] == {"name": "供应商"}
    assert explicit["items"][0]["name"] == "原料"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("电脑", "computer"),
        ("五金材料", "hardware"),
        ("办公用品", "office"),
        ("原辅料", "raw-auxiliary"),
        ("化学试剂", "chemical-glass"),
        ("电器", "electrical"),
        ("广告", "advertising-printing"),
        ("消防器材", "fire"),
        ("印刷品", "advertising-printing"),
        ("广告/印刷", "advertising-printing"),
        ("包装材料", "packaging"),
        ("劳保特防", "labor-special"),
        ("劳保杂品", "labor-miscellaneous"),
        ("劳保用品", "劳保用品"),
        ("custom", "custom"),
    ],
)
def test_normalize_purchase_category(value: object, expected: object) -> None:
    assert AgentService._normalize_purchase_category(value) == expected


def test_normalize_purchase_request_body_supports_single_and_multiple_items(
    service: AgentService,
) -> None:
    single = service._normalize_purchase_request_body(
        {
            "category": "电脑",
            "dept": "信息部",
            "apply_date": "2026-07-30",
            "attachment_description": "产品技术参数表一份",
            "name": "笔记本",
            "spec": "16G",
            "note": "开发",
            "quantity": 1,
            "price": 100,
            "remark": "急用",
        },
        {},
    )
    assert single["category"] == "computer"
    assert single["request_department"] == "信息部"
    assert single["request_date"] == "2026-07-30"
    assert single["attachment_note"] == "产品技术参数表一份"
    assert single["items"][0] == {
        "product_name": "笔记本",
        "specification": "16G",
        "material_code": "",
        "material_description": "",
        "rule_model": "",
        "purpose": "开发",
        "material": "",
        "brand": "",
        "quantity": 1,
        "unit": "",
        "unit_price": 100,
        "remarks": "急用",
    }

    multiple = service._normalize_purchase_request_body(
        None,
        {
            "request_department": "采购部",
            "date": "2026-07-31",
            "items": [{"item_name": "A"}, "ignored"],
        },
    )
    assert multiple["request_department"] == "采购部"
    assert multiple["request_date"] == "2026-07-31"
    assert [item["product_name"] for item in multiple["items"]] == ["A"]

    empty = service._normalize_purchase_request_body({}, {})
    assert empty["items"] == []


def test_normalize_purchase_request_material_fields(service: AgentService) -> None:
    normalized = service._normalize_purchase_request_body(
        {
            "category": "消防器材",
            "request_department": "安全环保部",
            "attachment_note": "消防技术附件",
            "items": [
                {
                    "code": "FIRE-001",
                    "description": "灭火器",
                    "rule": "4kg",
                    "use": "消防设施补充",
                    "quantity": 2,
                    "price": 50,
                }
            ],
        },
        {},
    )

    assert normalized["category"] == "fire"
    assert normalized["attachment_note"] == "消防技术附件"
    assert normalized["items"] == [
        {
            "product_name": None,
            "specification": "",
            "material_code": "FIRE-001",
            "material_description": "灭火器",
            "rule_model": "4kg",
            "purpose": "消防设施补充",
            "material": "",
            "brand": "",
            "quantity": 2,
            "unit": "",
            "unit_price": 50,
            "remarks": "",
        }
    ]


def test_purchase_tool_schema_exposes_new_request_fields() -> None:
    payload = PurchaseRequestCreateInput.model_validate(
        {
            "category": "fire",
            "request_department": "安全环保部",
            "request_date": "2026-08-12",
            "attachment_note": "消防技术附件",
            "items": [
                {
                    "material_code": "FIRE-001",
                    "material_description": "灭火器",
                    "rule_model": "4kg",
                    "quantity": 1,
                    "unit_price": 50,
                }
            ],
        }
    )
    update = PurchaseRequestUpdateInput.model_validate(
        {"request_id": str(uuid.uuid4()), "attachment_note": "补充说明"}
    )

    assert payload.attachment_note == "消防技术附件"
    assert payload.items[0].material_code == "FIRE-001"
    assert payload.items[0].material_description == "灭火器"
    assert payload.items[0].rule_model == "4kg"
    assert update.attachment_note == "补充说明"


def test_normalize_urgent_purchase_request_item_categories(
    service: AgentService,
) -> None:
    normalized = service._normalize_purchase_request_body(
        {
            "category": "加急单",
            "request_department": "采购部",
            "items": [
                {
                    "category": "消防",
                    "code": "FIRE-001",
                    "description": "灭火器",
                    "quantity": 1,
                    "price": 50,
                },
                {
                    "item_category": "办公用品",
                    "name": "标签纸",
                    "quantity": 2,
                    "price": 5,
                },
            ],
        },
        {},
    )

    assert normalized["category"] == "urgent"
    assert [item["item_category"] for item in normalized["items"]] == [
        "fire",
        "office",
    ]


def test_misc_normalizers_and_local_db_guard() -> None:
    assert AgentService._normalize_string_list([" alpha ", "", "alpha", 2, None]) == [
        "alpha",
        "2",
        "None",
    ]
    assert AgentService._normalize_string_list([]) == []
    assert AgentService._normalize_match_text(" A B ") == "ab"
    assert AgentService._is_sample_contract_request("demo contract")
    assert not AgentService._is_sample_contract_request("production contract")

    AgentService._require_local_db(SimpleNamespace())
    with pytest.raises(HTTPException, match="database session"):
        AgentService._require_local_db(None)


def test_request_validation_reports_missing_and_invalid_business_fields(
    service: AgentService,
) -> None:
    assert "合同分类" in service._tool_request_validation_error(  # type: ignore[operator]
        SimpleNamespace(operation="procurement.generate_contract", body={})
    )
    assert "合同明细" in service._tool_request_validation_error(  # type: ignore[operator]
        SimpleNamespace(
            operation="procurement.generate_contract",
            body={"category": "hardware"},
        )
    )
    assert "物品名称" in service._tool_request_validation_error(  # type: ignore[operator]
        SimpleNamespace(
            operation="procurement.generate_contract",
            body={"category": "hardware", "items": [{}]},
        )
    )
    assert (
        service._tool_request_validation_error(
            SimpleNamespace(
                operation="procurement.generate_contract",
                body={"category": "hardware", "items": [{"name": "螺栓"}]},
            )
        )
        is None
    )
    assert (
        service._tool_request_validation_error(
            SimpleNamespace(operation="agent.get_current_time", body=None)
        )
        is None
    )
    assert "必要字段" in service._workflow_request_validation_error({})  # type: ignore[operator]
    assert "格式不正确" in service._workflow_request_validation_error(  # type: ignore[operator]
        {"name": 123, "steps": "invalid"}
    )


def test_workflow_body_and_policy_normalization_cover_optional_inputs(
    service: AgentService,
) -> None:
    normalized = service._normalize_workflow_body(
        {"workflow": {"title": "巡检流程"}},
        {},
        "创建巡检工作流",
    )
    assert normalized["name"] == "巡检流程"
    assert normalized["source_request"] == "创建巡检工作流"
    assert service._normalize_workflow_body(
        {"name": "保留", "source_request": "已有"},
        {},
        "不覆盖",
    ) == {"name": "保留", "source_request": "已有"}

    assert not service._is_human_decision_required_message("")
    assert not service._is_human_decision_required_message("请查看采购申请")
    assert not service._is_human_decision_required_message("普通业务消息")


def test_extract_confirmation_ids_handles_all_supported_envelopes(
    service: AgentService,
) -> None:
    first = str(uuid.uuid4())
    second = str(uuid.uuid4())
    third = str(uuid.uuid4())
    fourth = str(uuid.uuid4())
    payload = {
        "id": first,
        "confirmation_id": second,
        "confirmation": {"id": third},
        "pending_confirmation": {"id": fourth},
        "nested": [{"confirmation_id": first}, 123],
    }
    encoded = json.dumps(payload)

    extracted = service._extract_confirmation_ids(encoded)

    assert {first, second, third, fourth}.issubset(extracted)
    assert service._extract_confirmation_ids(f"invalid json {first}") == [first]
    assert service._extract_confirmation_ids(None) == []
    assert set(service._extract_confirmation_ids([{"id": second}])) == {second}


@pytest.mark.anyio
async def test_resolve_user_and_pending_confirmations_filters_invalid_entries() -> None:
    now = datetime.now(UTC)
    session_user_id = uuid.uuid4()
    pending: Any = SimpleNamespace(
        id=uuid.uuid4(),
        status="pending",
        expires_at=now + timedelta(minutes=5),
    )
    expired: Any = SimpleNamespace(
        id=uuid.uuid4(),
        status="pending",
        expires_at=now - timedelta(minutes=5),
    )
    completed: Any = SimpleNamespace(
        id=uuid.uuid4(),
        status="completed",
        expires_at=now + timedelta(minutes=5),
    )

    class Repo:
        async def get_session(self: Any, db: Any, session_id: Any) -> Any:
            return SimpleNamespace(user_id=session_user_id)

        async def list_pending_confirmations(self: Any, db: Any, **kwargs: Any) -> Any:
            return [None, pending, pending, expired, completed]

        async def get_confirmation(self: Any, db: Any, confirmation_id: Any) -> Any:
            if confirmation_id == pending.id:
                return pending
            return None

    service = AgentService(
        settings=SimpleNamespace(API_V1_PREFIX="/api/v1"),
        repo=Repo(),  # type: ignore[arg-type]
        access_scope_service=SimpleNamespace(),
    )
    assert (
        await service._resolve_user_id(None, None, session_user_id) == session_user_id  # type: ignore[arg-type]
    )
    assert (
        await service._resolve_user_id(None, uuid.uuid4(), "invalid")  # type: ignore[arg-type]
        == session_user_id
    )
    assert await service._resolve_user_id(None, None, None) is None  # type: ignore[arg-type]

    result = await service._resolve_pending_confirmations(
        None,  # type: ignore[arg-type]
        {"confirmation_id": str(pending.id), "invalid": "not-a-uuid"},
    )
    assert result == [pending]
