from tools import dazah_platform


def test_hermes_keeps_progressive_backend_tool_contract() -> None:
    schema = dazah_platform.DAZAH_TOOL_SCHEMA
    action = schema["parameters"]["properties"]["action"]

    assert action["enum"] == ["search", "describe", "execute"]
    assert schema["parameters"]["required"] == ["action"]


def test_hermes_schema_requires_backend_discovery_before_execution() -> None:
    description = dazah_platform.DAZAH_TOOL_SCHEMA["description"]

    assert "Start with action=search" in description
    assert "then action=describe" in description
    assert "then action=execute" in description
    assert "permissions and confirmations are enforced by the backend" in description


def test_hermes_does_not_duplicate_backend_page_permission_catalog() -> None:
    properties = dazah_platform.DAZAH_TOOL_SCHEMA["parameters"]["properties"]

    assert "operation" in properties
    assert "page_key" not in properties
