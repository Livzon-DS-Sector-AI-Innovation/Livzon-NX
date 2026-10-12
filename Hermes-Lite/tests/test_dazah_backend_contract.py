from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from tools import dazah_platform


def _bind_context() -> object:
    return dazah_platform.dazah_request_context.set(
        {
            "tenant_id": "tenant-contract",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "channel": "internal",
            "trace_id": "00000000-0000-0000-0000-000000000002",
        }
    )


def test_backend_openapi_exposes_progressive_tool_contract() -> None:
    openapi_path = Path(__file__).parents[2] / "dazah-backend" / "openapi.json"
    document = json.loads(openapi_path.read_text(encoding="utf-8"))
    paths = document["paths"]
    assert "post" in paths["/api/v1/agent/tools/search"]
    assert "get" in paths["/api/v1/agent/tools/{operation}"]
    assert "post" in paths["/api/v1/agent/tools/execute"]


def test_backend_openapi_exposes_page_permission_execution_contract() -> None:
    openapi_path = Path(__file__).parents[2] / "dazah-backend" / "openapi.json"
    document = json.loads(openapi_path.read_text(encoding="utf-8"))
    paths = document["paths"]

    assert "/api/v1/identity/admin/page-permissions/modules" in paths
    assert "/api/v1/warehouse/page-data/{page_key}" in paths

    execute_schema = document["components"]["schemas"]["AgentToolExecuteRequest"]
    assert execute_schema["required"] == ["operation", "subject"]
    assert execute_schema["properties"]["subject"]["$ref"].endswith(
        "AgentTrustedSubject"
    )
    assert execute_schema["properties"]["execution_context"]["type"] == "object"


def test_backend_openapi_exposes_runtime_overview_contract() -> None:
    openapi_path = Path(__file__).parents[2] / "dazah-backend" / "openapi.json"
    document = json.loads(openapi_path.read_text(encoding="utf-8"))

    operation = document["paths"][
        "/api/v1/agent/control/runtime-overview"
    ]["get"]

    assert operation["operationId"].startswith(
        "get_control_plane_runtime_overview_"
    )
    assert "200" in operation["responses"]
    assert any(
        parameter["name"] == "auth_token" and parameter["in"] == "cookie"
        for parameter in operation["parameters"]
    )


def test_backend_openapi_exposes_feishu_gateway_restart_contract() -> None:
    openapi_path = Path(__file__).parents[2] / "dazah-backend" / "openapi.json"
    document = json.loads(openapi_path.read_text(encoding="utf-8"))

    operation = document["paths"][
        "/api/v1/identity/feishu-config/gateway/restart"
    ]["post"]

    assert operation["operationId"].startswith("restart_livzon_feishu_gateway_")
    response_schema = operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert response_schema["$ref"].endswith("FeishuGatewayRestartApiResponse")


@pytest.mark.parametrize("operation", [
    "quality.list_deviations", "production.list_batches", "warehouse.list_page_records",
    "procurement.list_material_catalog", "hr.list_employees",
    "hr.list_departments", "hr.list_contacts", "hr.list_candidates",
    "hr.list_onboarding", "hr.list_offboarding", "hr.list_position_transfers",
    "hr.list_contracts", "hr.list_contract_approval_results",
    "hr.list_new_employee_training", "hr.list_employee_training_summary",
    "hr.list_trainers", "hr.list_position_training", "hr.list_training_plan_tracking",
    "registration.list_project_ledger", "quality.list_lab_instruments",
    "production.list_sales_plan_details", "production.list_nonconforming_events",
    "production.list_shift_logs", "production.list_shift_handovers",
    "production.summarize_ipc_samples",
    "warehouse.get_inventory_summary", "warehouse.get_trend_summary",
    "warehouse.get_hardware_cost_summary",
    "registration.list_authorization_letters", "registration.list_regulatory_documents",
    "registration.list_inspection_contacts", "registration.list_knowledge_articles",
    "quality.list_documents", "quality.list_deviation_reports",
    "quality.list_deviation_investigations", "quality.list_historical_deviations",
    "quality.list_deviation_workbench_reports", "quality.list_lab_item_inbounds",
    "quality.list_lab_item_outbounds", "quality.list_oos_oot_reports",
    "quality.list_oos_oot_investigations", "quality.list_oot_ledger",
    "quality.list_oot_limit_products", "quality.list_product_departments",
    "quality.list_finished_product_anomalies", "quality.list_qc_validations",
    "quality.list_validation_reviews",
])
def test_describe_uses_operation_and_trusted_subject(monkeypatch, operation) -> None:
    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"data": {"operation": operation}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, url, params, headers):
            recorded.update(url=url, params=params, headers=headers)
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "contract-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)
    token = _bind_context()
    try:
        payload = asyncio.run(
            dazah_platform.dazah_tool(
                "describe",
                operation=operation,
            )
        )
    finally:
        dazah_platform.dazah_request_context.reset(token)

    assert json.loads(payload)["data"]["operation"] == operation
    assert str(recorded["url"]).endswith(
        f"/agent/tools/{operation}"
    )
    assert recorded["params"] == {
        "subject_user_id": "00000000-0000-0000-0000-000000000001",
        "subject_tenant_id": "tenant-contract",
        "trace_id": "00000000-0000-0000-0000-000000000002",
    }


@pytest.mark.parametrize("entries", [
    [],
    [{"operation": "agent.get_my_access_scope"}, {"operation": "quality.list_deviations"}],
])
def test_search_forwards_natural_language_and_preserves_backend_ranking(
    monkeypatch, entries: list[dict[str, str]]
) -> None:
    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"data": entries}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, json, headers):
            recorded.update(url=url, json=json)
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "contract-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)
    token = _bind_context()
    try:
        payload = asyncio.run(
            dazah_platform.dazah_tool("search", query="平台有哪些模块", limit=2)
        )
    finally:
        dazah_platform.dazah_request_context.reset(token)

    assert str(recorded["url"]).endswith("/agent/tools/search")
    request_json = recorded["json"]
    assert request_json["query"] == "平台有哪些模块"
    assert request_json["limit"] == 2
    assert request_json["trace_id"] == "00000000-0000-0000-0000-000000000002"
    assert request_json["subject"]["user_id"] == "00000000-0000-0000-0000-000000000001"
    assert json.loads(payload)["data"] == entries


def test_catalog_is_refetched_after_effective_page_access_is_revoked(monkeypatch) -> None:
    responses = iter([
        [{"operation": "quality.list_deviations", "module": "quality"}],
        [],
    ])
    subjects: list[dict[str, object]] = []

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"data": next(responses)}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, json, headers):
            assert str(url).endswith("/agent/tools/search")
            subjects.append(json["subject"])
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "contract-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)
    token = _bind_context()
    try:
        granted = asyncio.run(dazah_platform.dazah_tool("search", query="偏差"))
        revoked = asyncio.run(dazah_platform.dazah_tool("search", query="偏差"))
    finally:
        dazah_platform.dazah_request_context.reset(token)

    assert json.loads(granted)["data"] == [
        {"operation": "quality.list_deviations", "module": "quality"}
    ]
    assert json.loads(revoked)["data"] == []
    assert len(subjects) == 2
    assert subjects[0] == subjects[1]
    assert subjects[0]["user_id"] == "00000000-0000-0000-0000-000000000001"


def test_quality_operation_is_forwarded_to_backend_catalog(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "ok": True,
                    "operation": "quality.list_cpv_products",
                }
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, json, headers):
            recorded.update(url=url, json=json, headers=headers)
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "contract-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)
    token = _bind_context()
    try:
        payload = asyncio.run(
            dazah_platform.dazah_tool(
                "execute",
                operation="quality.list_cpv_products",
                params={"page": 1},
            )
        )
    finally:
        dazah_platform.dazah_request_context.reset(token)

    assert json.loads(payload)["data"]["operation"] == "quality.list_cpv_products"
    assert str(recorded["url"]).endswith("/agent/tools/execute")
    request_json = recorded["json"]
    assert request_json["operation"] == "quality.list_cpv_products"
    assert request_json["params"] == {"page": 1}


def test_automation_paged_audit_result_preserves_total(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "ok": True,
                    "operation": "agent.list_automations",
                    "data": {"items": [{"id": "automation-501"}], "page": 26, "total": 501},
                }
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, json, headers):
            recorded.update(url=url, json=json)
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "contract-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)
    token = _bind_context()
    try:
        payload = asyncio.run(
            dazah_platform.dazah_tool(
                "execute", operation="agent.list_automations", params={"page": 26}
            )
        )
    finally:
        dazah_platform.dazah_request_context.reset(token)

    assert recorded["json"]["params"] == {"page": 26}
    result = json.loads(payload)["data"]
    assert result["operation"] == "agent.list_automations"
    assert result["data"]["total"] == 501
    assert result["data"]["items"][0]["id"] == "automation-501"


def test_timeout_and_unavailable_backend_are_typed_errors(monkeypatch) -> None:
    class FailingAsyncClient:
        failure: type[httpx.HTTPError] = httpx.ReadTimeout

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, json, headers):
            request = httpx.Request("POST", url)
            raise self.failure("contract failure", request=request)

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "contract-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FailingAsyncClient)
    token = _bind_context()
    try:
        for failure in (httpx.ReadTimeout, httpx.ConnectError):
            FailingAsyncClient.failure = failure
            result = asyncio.run(
                dazah_platform.dazah_tool("search", query="偏差")
            )
            assert json.loads(result)["error"] == failure.__name__
    finally:
        dazah_platform.dazah_request_context.reset(token)


def test_tool_schema_has_only_progressive_actions() -> None:
    action = dazah_platform.DAZAH_TOOL_SCHEMA["parameters"]["properties"]["action"]
    assert action["enum"] == ["search", "describe", "execute"]
    assert dazah_platform.DAZAH_TOOL_SCHEMA["parameters"]["required"] == ["action"]


def test_backend_openapi_keeps_deviation_statistics_tool_contract() -> None:
    """偏差统计目录契约：dazah_tool describe/execute 依赖后端 OpenAPI 形状。

    人机料法环口径字段（majorCount / rootCauseDistribution 等）与旧版
    statusDistribution/stepBreakdown 的移除都必须在此显式钉住，避免后端
    统计口径回退时 Hermes 侧无感知。
    """

    openapi_path = Path(__file__).parents[2] / "dazah-backend" / "openapi.json"
    document = json.loads(openapi_path.read_text(encoding="utf-8"))

    operation = document["paths"]["/api/v1/quality/statistics/deviations"]["get"]
    assert operation["operationId"].startswith("get_deviation_statistics")
    assert "200" in operation["responses"]

    schemas = document["components"]["schemas"]
    properties = schemas["DeviationStatistics"]["properties"]
    assert set(properties) == {
        "total",
        "closedCount",
        "majorCount",
        "levelDistribution",
        "departmentDistribution",
        "rootCauseDistribution",
        "monthlyTrend",
    }
    assert properties["rootCauseDistribution"]["items"]["$ref"].endswith(
        "StatDistributionItem"
    )
    item_properties = schemas["StatDistributionItem"]["properties"]
    assert set(item_properties) == {"name", "count"}
    trend_properties = schemas["MonthlyTrendPoint"]["properties"]
    assert set(trend_properties) == {"month", "count"}


@pytest.mark.parametrize(
    ("operation", "status_code"),
    [("analytics.aggregate", 200), ("analytics.aggregate", 403),
     ("identity.check_feishu_permissions", 400)],
)
def test_tools_preserve_backend_permission_and_exclusion_decision(monkeypatch, operation, status_code):
    recorded = []

    class FakeResponse:
        text = "supplier page query permission denied"

        def json(self):
            return {"data": {"ok": True, "operation": "analytics.aggregate", "data": {"rows": [{"count": 3}]}}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json, headers):
            recorded.append((url, json))
            response = FakeResponse()
            response.status_code = status_code
            return response

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "contract-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)
    token = _bind_context()
    try:
        payload = json.loads(
            asyncio.run(
                dazah_platform.dazah_tool(
                    "execute",
                    operation=operation,
                    params={"dataset": "procurement.suppliers"},
                )
            )
        )
    finally:
        dazah_platform.dazah_request_context.reset(token)
    assert len(recorded) == 1
    assert recorded[0][0].endswith("/agent/tools/execute")
    assert recorded[0][1]["subject"]["user_id"] == "00000000-0000-0000-0000-000000000001"
    assert recorded[0][1]["params"] == {"dataset": "procurement.suppliers"}
    assert recorded[0][1]["operation"] == operation
    if status_code in (400, 403):
        assert payload["ok"] is False
        assert payload["status_code"] == status_code
        assert "rows" not in payload
    else:
        assert payload["data"]["data"]["rows"] == [{"count": 3}]
