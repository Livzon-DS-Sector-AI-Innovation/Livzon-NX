import pytest

from services import dazah_agent_service as service
from services.dazah_agent_service import (
    AutomationSheetReadRequest,
    _parse_json_object,
    _validate_json_schema,
)
from services.feishu_runtime import CliResult


def test_automation_analysis_parses_fenced_json_and_validates_schema() -> None:
    output = _parse_json_object('```json\n{"summary":"正常","count":2}\n```')

    _validate_json_schema(
        output,
        {
            "type": "object",
            "required": ["summary", "count"],
            "properties": {
                "summary": {"type": "string"},
                "count": {"type": "integer"},
            },
        },
    )


def test_automation_analysis_rejects_invalid_output() -> None:
    with pytest.raises(ValueError, match="required"):
        _validate_json_schema(
            {"summary": "正常"},
            {"type": "object", "required": ["summary", "count"]},
        )


def test_automation_analysis_rejects_unknown_or_out_of_range_values() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {"type": "string", "enum": ["normal", "warning"]},
            "count": {"type": "integer", "maximum": 10},
        },
    }

    with pytest.raises(ValueError, match="unknown fields"):
        _validate_json_schema({"status": "normal", "extra": True}, schema)
    with pytest.raises(ValueError, match="maximum"):
        _validate_json_schema({"status": "normal", "count": 11}, schema)


@pytest.mark.asyncio
async def test_sheet_range_read_uses_bound_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    async def fake_run_cli(args: list[str]) -> CliResult:
        captured.extend(args)
        return CliResult(0, '{"values":[["姓名","张三"]]}', "", 1)

    monkeypatch.setenv("HERMES_INTERNAL_TOKEN", "test-token")
    monkeypatch.setattr(service, "run_cli", fake_run_cli)

    result = await service.read_automation_sheet_cells(
        AutomationSheetReadRequest(
            base_token="sheet-token",
            table_id="sheet-id",
            range="A1:B10",
        ),
        authorization="Bearer test-token",
    )

    assert result == {"cells": {"values": [["姓名", "张三"]]}}
    assert captured == [
        "sheets",
        "+cells-get",
        "--spreadsheet-token",
        "sheet-token",
        "--sheet-id",
        "sheet-id",
        "--range",
        "A1:B10",
        "--format",
        "json",
        "--as",
        "bot",
    ]
