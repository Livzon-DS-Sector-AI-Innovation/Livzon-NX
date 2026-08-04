from __future__ import annotations

import types
import uuid
from datetime import UTC, date, datetime
from enum import Enum
from types import SimpleNamespace
from typing import Any, Literal, Union, get_args, get_origin
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.modules.agent.tools import tool_registry
from app.modules.energy import agent_tools as energy_tools
from app.modules.procurement import agent_tools as procurement_tools
from app.modules.quality import agent_tools as quality_tools
from app.modules.warehouse import agent_tools as warehouse_tools
from app.modules.warehouse import ws_client as warehouse_ws_client
from app.platform.identity import agent_tools as identity_tools


class _EmptyResult(BaseModel):
    pass


class _EmptyInput(BaseModel):
    pass


class _ServiceDouble:
    """Return service-shaped empty values while recording every adapter call."""

    def __init__(self, *, tuple_sizes: dict[str, int] | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.tuple_sizes = tuple_sizes or {}

    def __getattr__(self, name: str) -> Any:
        async def _call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            tuple_size = self.tuple_sizes.get(name)
            if tuple_size is not None:
                if tuple_size == 2:
                    return [], 0
                if tuple_size == 3:
                    return [], 0, []
            if name.startswith(("list_", "get_parameters")):
                return []
            if name == "get_mapping":
                return None
            return _EmptyResult()

        return _call


def _required_value(annotation: Any, field_name: str) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in (Union, types.UnionType):
        concrete = [item for item in args if item is not type(None)]
        return _required_value(concrete[0], field_name) if concrete else None
    if origin is Literal:
        return args[0]
    if origin in (list, set, tuple):
        return origin()
    if origin is dict:
        return {}
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return next(iter(annotation))
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _build_input(annotation)
    if annotation is uuid.UUID:
        return uuid.uuid4()
    if annotation is datetime:
        return datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    if annotation is date:
        return date(2026, 7, 1)
    if annotation is bool:
        return True
    if annotation is int:
        return 1
    if annotation is float:
        return 1.0
    if annotation is bytes:
        return b"test"
    if annotation is str:
        if "period_month" in field_name:
            return "2026-07"
        if "email" in field_name:
            return "tester@example.com"
        if "url" in field_name:
            return "https://example.com/test"
        return f"test-{field_name.replace('_', '-')}"
    return "test-value"


def _build_input(model: type[BaseModel]) -> BaseModel:
    values: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        if field.is_required():
            values[name] = _required_value(field.annotation, name)
    return model.model_construct(**values)


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        db=object(),
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user=SimpleNamespace(id=uuid.uuid4(), name="测试用户"),
        reason="coverage adapter contract",
        raw_request=SimpleNamespace(trace_id=uuid.uuid4()),
    )


def _specs(prefix: str, excluded: set[str] | None = None) -> list[Any]:
    excluded = excluded or set()
    return [
        spec
        for spec in tool_registry.list()
        if spec.name.startswith(f"{prefix}.") and spec.name not in excluded
    ]


@pytest.mark.anyio
async def test_quality_agent_tool_adapters_forward_validated_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tuple_sizes = {
        "get_products": 2,
        "get_batches": 2,
        "get_batches_wide": 2,
        "list_resource_records": 2,
        "list_oos_oot_records": 2,
    }
    doubles: list[_ServiceDouble] = []
    for dependency_name in (
        "change_action_plan",
        "cpv_batch",
        "cpv_parameter",
        "cpv_product",
        "cpv_statistics",
        "external_quality",
        "feishu_capa",
        "inspection",
        "oos_oot",
        "quality_feishu_pages",
        "quality_feishu_sync",
        "quality_management",
        "validation",
    ):
        double = _ServiceDouble(tuple_sizes=tuple_sizes)
        doubles.append(double)
        monkeypatch.setattr(quality_tools, dependency_name, double)

    # These adapters validate a returned ORM row against a detailed response
    # schema. They are covered by their existing focused integration tests.
    excluded = {
        "quality.create_cpv_parameter",
        "quality.create_cpv_product",
        "quality.get_cpv_product",
        "quality.get_inspection_record",
        "quality.get_oos_oot_record",
        "quality.update_cpv_parameter",
        "quality.update_cpv_product",
    }

    invoked: list[str] = []
    for spec in _specs("quality", excluded):
        result = await spec.handler(_context(), _build_input(spec.input_model))
        assert result is not None
        invoked.append(spec.name)

    assert len(invoked) >= 65
    assert sum(len(double.calls) for double in doubles) >= len(invoked)


@pytest.mark.anyio
async def test_energy_agent_tool_adapters_cover_paging_and_sync_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    double = _ServiceDouble(
        tuple_sizes={
            "list_sync_runs": 2,
            "list_snapshot_rows": 3,
        }
    )
    monkeypatch.setattr(energy_tools, "_service", lambda _context: double)

    excluded = {
        "energy.delete_source_sheets",
        "energy.get_feishu_config",
        "energy.get_overview",
        "energy.list_snapshot_rows",
        "energy.test_feishu_connectivity",
        "energy.trigger_sync",
    }
    invoked = []
    for spec in _specs("energy", excluded):
        tool_input = _build_input(spec.input_model)
        if spec.name == "energy.update_feishu_source_root":
            tool_input = spec.input_model.model_construct(
                root_id=uuid.uuid4(),
                name="更新后的入口",
            )
        result = await spec.handler(_context(), tool_input)
        if spec.name == "energy.get_sheet_mapping":
            assert result is None
        else:
            assert result is not None
        invoked.append(spec.name)

    assert len(invoked) >= 9
    assert len(double.calls) >= len(invoked)


@pytest.mark.anyio
async def test_warehouse_agent_tool_adapters_cover_inventory_and_feishu_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    double = _ServiceDouble()
    monkeypatch.setattr(warehouse_tools, "_warehouse_service", lambda _context: double)
    monkeypatch.setattr(
        warehouse_ws_client,
        "get_ws_status",
        AsyncMock(return_value=_EmptyResult()),
    )
    monkeypatch.setattr(
        warehouse_ws_client,
        "restart_ws_from_db",
        AsyncMock(return_value=_EmptyResult()),
    )

    invoked = []
    for spec in _specs("warehouse"):
        result = await spec.handler(_context(), _build_input(spec.input_model))
        assert result is not None
        invoked.append(spec.name)

    assert len(invoked) >= 8
    assert len(double.calls) == 6


@pytest.mark.anyio
async def test_procurement_read_agent_tool_adapters_cover_all_list_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = {
        "list_invoice_recognition_records": AsyncMock(return_value=([], 0)),
        "list_suppliers": AsyncMock(return_value=([], 0, [])),
        "list_purchase_requests": AsyncMock(return_value=([], 0)),
        "list_purchase_order_lines": AsyncMock(return_value=([], 0)),
        "get_purchase_request": AsyncMock(return_value={}),
        "export_purchase_order_lines_xlsx": AsyncMock(return_value=b"xlsx"),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(procurement_tools, name, mock)

    excluded = {
        "procurement.approve_purchase_request",
        "procurement.create_purchase_request",
        "procurement.generate_contract",
        "procurement.get_purchase_request",
        "procurement.get_contract_template",
        "procurement.reject_purchase_request",
        "procurement.submit_purchase_request",
        "procurement.update_purchase_request",
    }
    invoked = []
    for spec in _specs("procurement", excluded):
        result = await spec.handler(_context(), _build_input(spec.input_model))
        assert result is not None
        invoked.append(spec.name)

    assert len(invoked) >= 6
    assert any(mock.await_count for mock in mocks.values())


def test_identity_delivery_input_requires_local_users_and_idempotency() -> None:
    user_id = uuid.uuid4()
    delivery = identity_tools.FeishuDeliveryInput.model_validate(
        {
            "recipient_user_ids": [str(user_id)],
            "title": "CAPA 提醒",
            "markdown": "请完成整改",
            "actions": [{"label": "查看详情", "url": "/quality/capa/1"}],
            "idempotency_key": "capa-reminder-1",
        }
    )

    assert delivery.recipient_user_ids == [user_id]
    assert delivery.actions[0]["label"] == "查看详情"


@pytest.mark.anyio
async def test_identity_agent_tool_adapters_cover_tree_search_and_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    departments = [
        SimpleNamespace(
            id=root_id,
            feishu_department_id="od_root",
            parent_feishu_department_id=None,
            name="生产部",
            member_count=2,
            leader_user_id=None,
            order=1,
        ),
        SimpleNamespace(
            id=child_id,
            feishu_department_id="od_child",
            parent_feishu_department_id="od_root",
            name="一车间",
            member_count=1,
            leader_user_id=None,
            order=1,
        ),
    ]

    class _DepartmentRepo:
        async def list_all(self, _db: Any) -> list[Any]:
            return departments

    class _UserRepo:
        async def list_all(self, *args: Any, **kwargs: Any) -> tuple[list[Any], int]:
            return [], 0

        async def get_by_id(self, _db: Any, requested_user_id: uuid.UUID) -> Any:
            assert requested_user_id == user_id
            return SimpleNamespace(
                id=user_id,
                is_deleted=False,
                status="active",
                feishu_open_id="ou_001",
            )

    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"id": "delivery-1", "status": "queued"},
    )
    post = AsyncMock(return_value=response)

    class _HttpClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Any:
            return SimpleNamespace(post=post)

        async def __aexit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr(identity_tools, "DepartmentRepository", _DepartmentRepo)
    monkeypatch.setattr(identity_tools, "UserRepository", _UserRepo)
    monkeypatch.setattr(
        identity_tools,
        "diagnose_livzon_feishu_config",
        AsyncMock(return_value=_EmptyResult()),
    )
    monkeypatch.setattr(
        identity_tools,
        "get_settings",
        lambda: SimpleNamespace(
            HERMES_INTERNAL_URL="http://hermes:8100",
            HERMES_INTERNAL_TOKEN="test-token",
        ),
    )
    monkeypatch.setattr(identity_tools.httpx, "AsyncClient", _HttpClient)

    context = _context()
    tree = await identity_tools.get_department_tree(context, _EmptyInput())
    assert tree["departments"][0]["children"][0]["name"] == "一车间"

    personnel = await identity_tools.search_personnel(
        context,
        identity_tools.PersonnelSearchInput(),
    )
    assert personnel["total"] == 0

    diagnosis = await identity_tools.check_feishu_permissions(
        context,
        _EmptyInput(),
    )
    assert diagnosis == {}

    delivery = identity_tools.FeishuDeliveryInput(
        recipient_user_ids=[user_id],
        title="卡片标题",
        markdown="卡片正文",
        idempotency_key="adapter-delivery",
    )
    assert await identity_tools.deliver_feishu_message(context, delivery) == {
        "results": [
            {
                "recipient_user_id": str(user_id),
                "status": "queued",
                "delivery_id": "delivery-1",
            }
        ]
    }
    request = post.await_args.kwargs["json"]
    assert request["chat_id"] == "ou_001"
    assert "card" in request
    assert "content" not in request
    assert request["metadata"]["recipient_user_id"] == str(user_id)

    text_delivery = identity_tools.FeishuDeliveryInput(
        recipient_user_ids=[user_id],
        message_form="text",
        title="文本标题",
        markdown="纯文本正文",
        idempotency_key="adapter-text-delivery",
    )
    await identity_tools.deliver_feishu_message(context, text_delivery)
    text_request = post.await_args.kwargs["json"]
    assert text_request["content"] == "纯文本正文"
    assert "card" not in text_request
