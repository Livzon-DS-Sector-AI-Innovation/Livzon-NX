from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.modules.registration.schemas import ProjectOverview
from app.modules.registration.service.project import ProjectOverviewService


@pytest.mark.asyncio
async def test_project_overview_returns_aggregated_modules(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_overview(self: ProjectOverviewService) -> ProjectOverview:
        del self
        return ProjectOverview.model_validate(
            {
                "module_name": "申报项目",
                "path": "/registration/project",
                "modules": [
                    {
                        "key": "project-ledger",
                        "name": "申报台账",
                        "description": "测试台账",
                        "path": "/registration/project-ledger",
                        "workbook_name": "台账.xlsx",
                        "total_records": 0,
                        "sheet_count": 4,
                        "child_pages": [
                            {
                                "key": "sheet-1",
                                "name": "子页",
                                "path": "/registration/project-ledger/sheet-1",
                            }
                        ]
                        * 4,
                        "api_endpoints": [
                            {
                                "key": "overview",
                                "name": "总览",
                                "method": "GET",
                                "path": "/api/v1/registration/project-ledger/overview",
                            }
                        ],
                    },
                    {
                        "key": "declaration-progress",
                        "name": "申报进度",
                        "description": "测试进度",
                        "path": "/registration/declaration-progress",
                        "workbook_name": "进度.xlsx",
                        "total_records": 0,
                        "sheet_count": 7,
                    },
                ],
            }
        )

    monkeypatch.setattr(ProjectOverviewService, "get_overview", fake_overview)
    response = await client.get("/api/v1/registration/project/overview")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["module_name"] == "申报项目"
    assert payload["path"] == "/registration/project"
    assert len(payload["modules"]) == 2
    assert {item["key"] for item in payload["modules"]} == {
        "project-ledger",
        "declaration-progress",
    }

    ledger_module = next(
        item for item in payload["modules"] if item["key"] == "project-ledger"
    )

    assert ledger_module["path"] == "/registration/project-ledger"
    assert len(ledger_module["child_pages"]) == 4
    assert any(
        endpoint["path"] == "/api/v1/registration/project-ledger/overview"
        for endpoint in ledger_module["api_endpoints"]
    )
