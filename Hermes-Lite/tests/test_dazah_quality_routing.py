from pathlib import Path


SERVICE_SOURCE = Path(__file__).resolve().parents[1] / "services" / "dazah_agent_service.py"
PLATFORM_TOOL_SOURCE = Path(__file__).resolve().parents[1] / "tools" / "dazah_platform.py"


def test_dazah_prompt_routes_quality_requests_to_quality_tools() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")

    assert "服务能源、仓储、采购、质量管理和 Livzon 助手通讯录查询" in source
    assert "必须优先调用 dazah_tool 的 quality.* operation" in source
    assert "quality.list_deviation_report_records" in source


def test_skill_resolver_default_scope_includes_quality() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")

    assert (
        'default_scope = ["identity", "energy", "warehouse", "procurement", "quality"]'
        in source
    )
    assert '"business_scope": _business_scope(payload.context)' in source


def test_quality_requests_do_not_bypass_agent_orchestration() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    platform_source = PLATFORM_TOOL_SOURCE.read_text(encoding="utf-8")

    assert '"quality.list_deviation_report_records"' in platform_source
    assert "def _try_direct_quality_response" not in source
    assert "_try_direct_quality_response(payload)" not in source


def test_energy_feishu_config_writes_route_through_confirmed_tools() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    platform_source = PLATFORM_TOOL_SOURCE.read_text(encoding="utf-8")

    for operation in (
        "energy.create_feishu_source_root",
        "energy.update_feishu_source_root",
        "energy.delete_feishu_source_root",
        "energy.delete_source_sheets",
    ):
        assert operation in source
        assert f'"{operation}"' in platform_source
    assert "三类写操作都只能生成待确认项" in source
    assert "不得声称会修改或删除飞书原表内容" in source
