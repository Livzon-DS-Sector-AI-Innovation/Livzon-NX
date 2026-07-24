from __future__ import annotations

import ast
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import EmptyToolInput, ToolContext, tool_registry
from app.modules.energy import agent_tools
from app.modules.energy.schemas import (
    EnergyFeishuConfigResponse,
    EnergyOverviewResponse,
)


def _context() -> ToolContext:
    return ToolContext(
        db=object(),  # type: ignore[arg-type]
        session_id=None,
        user_id=None,
        user=None,
        reason=None,
        raw_request=SimpleNamespace(),  # type: ignore[arg-type]
    )


def _hermes_allowed_operations() -> list[str]:
    source = (
        Path(__file__).resolve().parents[4]
        / "Hermes-Lite"
        / "tools"
        / "dazah_platform.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name)
                and target.id == "ALLOWED_OPERATIONS"
                for target in node.targets
            ):
                return ast.literal_eval(node.value)
    raise AssertionError("ALLOWED_OPERATIONS not found")


def test_energy_tools_are_registered_with_expected_policy() -> None:
    ensure_agent_tools_registered()

    config = tool_registry.require("energy.get_feishu_config")
    sync = tool_registry.require("energy.trigger_sync")
    connectivity = tool_registry.require("energy.test_feishu_connectivity")
    create_root = tool_registry.require("energy.create_feishu_source_root")
    update_root = tool_registry.require("energy.update_feishu_source_root")
    delete_root = tool_registry.require("energy.delete_feishu_source_root")
    delete_sheets = tool_registry.require("energy.delete_source_sheets")

    assert config.write is False
    assert config.required_roles == ("admin",)
    assert config.sensitivity == "sensitive"
    assert sync.write is True
    assert sync.risk_level == "medium"
    assert sync.required_roles == ("admin",)
    assert connectivity.workflow_allowed is False
    assert create_root.write is True
    assert create_root.required_roles == ("admin",)
    assert create_root.workflow_allowed is False
    assert update_root.write is True
    assert update_root.workflow_allowed is False
    assert delete_root.write is True
    assert delete_root.risk_level == "high"
    assert delete_root.workflow_allowed is False
    assert delete_sheets.write is True
    assert delete_sheets.risk_level == "high"
    assert delete_sheets.required_roles == ("admin",)
    assert delete_sheets.workflow_allowed is False


def test_all_energy_tools_are_allowed_by_hermes() -> None:
    ensure_agent_tools_registered()
    hermes_operations = set(_hermes_allowed_operations())
    backend_operations = {
        spec.name for spec in tool_registry.list() if spec.name.startswith("energy.")
    }

    assert backend_operations
    assert backend_operations <= hermes_operations


def test_energy_overview_input_validates_mixed_timezone_range() -> None:
    with pytest.raises(ValidationError, match="end_time 不能早于 start_time"):
        agent_tools.EnergyOverviewInput(
            start_time=datetime(2026, 7, 23, 8),
            end_time=datetime(2026, 7, 22, 23, tzinfo=UTC),
        )


@pytest.mark.anyio
async def test_get_feishu_config_returns_only_masked_secret_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeService:
        async def get_config(self) -> EnergyFeishuConfigResponse:
            return EnergyFeishuConfigResponse(
                id=uuid4(),
                config_name="能源配置",
                app_id="cli_app",
                app_secret_configured=True,
                app_secret_masked="sec***ret",
                root_wiki_url="https://example.feishu.cn/wiki/root",
                root_wiki_token="root",
                timezone="Asia/Shanghai",
                daily_sync_time="02:00",
                is_active=True,
                last_successful_sync_date=date(2026, 7, 23),
                sync_status="success",
                sync_error=None,
                remark=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

    monkeypatch.setattr(agent_tools, "_service", lambda _context: FakeService())

    result = await agent_tools.get_feishu_config(
        _context(), EmptyToolInput()
    )

    assert result["app_secret_configured"] is True
    assert result["app_secret_masked"] == "sec***ret"
    assert "app_secret" not in result


@pytest.mark.anyio
async def test_energy_source_root_handlers_call_service_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_id = uuid4()
    calls = []
    response = SimpleNamespace(
        model_dump=lambda **_kwargs: {
            "id": str(root_id),
            "name": "能源 Base",
        }
    )

    class FakeService:
        async def create_source_root(self, payload):
            calls.append(("create", payload))
            return response

        async def update_source_root(self, requested_root_id, payload):
            calls.append(("update", requested_root_id, payload))
            return response

        async def delete_source_root(self, requested_root_id):
            calls.append(("delete", requested_root_id))

        async def delete_sources(self, sheet_ids):
            calls.append(("delete_sheets", sheet_ids))
            return {
                "deleted_count": 1,
                "snapshot_count": 2,
                "snapshot_row_count": 10,
                "mapping_count": 1,
                "fact_count": 4,
                "binding_count": 1,
                "document_count": 1,
            }

    monkeypatch.setattr(agent_tools, "_service", lambda _context: FakeService())

    await agent_tools.create_feishu_source_root(
        _context(),
        agent_tools.EnergySourceRootCreateInput(
            name="能源 Base",
            source_type="base",
            source_url="https://example.feishu.cn/base/bascnExample",
        ),
    )
    await agent_tools.update_feishu_source_root(
        _context(),
        agent_tools.EnergySourceRootUpdateInput(
            root_id=root_id,
            name="能源 Base（更新）",
        ),
    )
    deleted = await agent_tools.delete_feishu_source_root(
        _context(),
        agent_tools.EnergySourceRootDeleteInput(root_id=root_id),
    )
    deleted_sheets = await agent_tools.delete_source_sheets(
        _context(),
        agent_tools.EnergySourceBatchRequest(sheet_ids=[root_id]),
    )

    assert [item[0] for item in calls] == [
        "create",
        "update",
        "delete",
        "delete_sheets",
    ]
    assert calls[1][1] == root_id
    assert deleted == {"id": str(root_id), "deleted": True}
    assert deleted_sheets["snapshot_row_count"] == 10


@pytest.mark.anyio
async def test_list_source_sheets_includes_document_and_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet_id = uuid4()
    sheet = SimpleNamespace(
        id=sheet_id,
        document_id=uuid4(),
        external_sheet_id="sheet-a",
        title="电力日报",
        sheet_index=0,
        header_row=1,
        headers=["日期", "用量"],
        schema_hash="hash",
        mapping_status="mapped",
        latest_snapshot_id=uuid4(),
        last_synced_at=datetime.now(UTC),
    )
    document = SimpleNamespace(
        title="7月能源日报",
        period_month=date(2026, 7, 1),
    )

    class FakeService:
        async def list_sources(self, **_kwargs):
            return [(sheet, document)]

        async def get_mapping(self, requested_sheet_id):
            assert requested_sheet_id == sheet_id
            return SimpleNamespace(source_role="workshop_detail")

    monkeypatch.setattr(agent_tools, "_service", lambda _context: FakeService())

    result = await agent_tools.list_source_sheets(
        _context(), agent_tools.EnergySourceFilterInput()
    )

    assert result[0]["document_title"] == "7月能源日报"
    assert result[0]["period_month"] == "2026-07-01"
    assert result[0]["source_role"] == "workshop_detail"


@pytest.mark.anyio
async def test_get_overview_passes_all_filters_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class FakeService:
        async def get_overview(self, **kwargs):
            calls.append(kwargs)
            return EnergyOverviewResponse(
                source_scope="detail",
                metrics=[],
                trend=[],
                distribution=[],
                latest_metrics=[],
                invalid_count=0,
            )

    monkeypatch.setattr(agent_tools, "_service", lambda _context: FakeService())
    start = datetime(2026, 7, 1, tzinfo=UTC)
    end = datetime(2026, 7, 23, tzinfo=UTC)

    result = await agent_tools.get_overview(
        _context(),
        agent_tools.EnergyOverviewInput(
            start_time=start,
            end_time=end,
            energy_type="electricity",
            group_by="workshop",
            workshop="一车间",
            source_sheet_title="电力日报",
        ),
    )

    assert result["source_scope"] == "detail"
    assert calls == [
        {
            "start": start,
            "end": end,
            "energy_type": "electricity",
            "group_by": "workshop",
            "source_scope": "detail",
            "workshop": "一车间",
            "source_sheet_title": "电力日报",
        }
    ]
