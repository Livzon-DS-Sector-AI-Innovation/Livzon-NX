"""Project parent module aggregate service."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.schemas.project import (
    ProjectApiEndpoint,
    ProjectChildPage,
    ProjectModuleOverviewItem,
    ProjectOverview,
)
from app.modules.registration.service.declaration_progress import (
    DECLARATION_PROGRESS_SHEET_CONFIG,
    DeclarationProgressWorkbookService,
)
from app.modules.registration.service.project_ledger import (
    PROJECT_LEDGER_SHEET_CONFIG,
    ProjectLedgerWorkbookService,
)

logger = logging.getLogger(__name__)


def _build_project_ledger_child_pages() -> list[ProjectChildPage]:
    return [
        ProjectChildPage(
            key=sheet_key,
            name=sheet_name,
            path=f"/registration/project-ledger/{sheet_key}",
        )
        for sheet_key, sheet_name in PROJECT_LEDGER_SHEET_CONFIG.values()
    ]


def _build_declaration_progress_child_pages() -> list[ProjectChildPage]:
    return [
        ProjectChildPage(
            key=sheet_key,
            name=sheet_name,
            path=f"/registration/declaration-progress/{sheet_key}",
        )
        for sheet_key, sheet_name in DECLARATION_PROGRESS_SHEET_CONFIG.values()
    ]


class ProjectOverviewService:
    """Aggregate project child module overviews."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_overview(self) -> ProjectOverview:
        ledger_overview = await ProjectLedgerWorkbookService(
            self.session
        ).get_overview()
        declaration_progress_overview = await DeclarationProgressWorkbookService(
            self.session
        ).get_overview()

        modules = [
            ProjectModuleOverviewItem(
                key="project-ledger",
                name="申报台账",
                description="维护申报项目主记录、子记录历史以及整本台账导入导出。",
                path="/registration/project-ledger",
                workbook_name=ledger_overview.workbook_name,
                updated_at=ledger_overview.updated_at,
                total_records=ledger_overview.total_records,
                sheet_count=len(ledger_overview.sheets),
                child_pages=_build_project_ledger_child_pages(),
                api_endpoints=[
                    ProjectApiEndpoint(
                        key="project-ledger-overview",
                        name="申报台账总览",
                        method="GET",
                        path="/api/v1/registration/project-ledger/overview",
                    ),
                    ProjectApiEndpoint(
                        key="project-ledger-workbook",
                        name="申报台账工作簿详情",
                        method="GET",
                        path="/api/v1/registration/project-ledger/workbook",
                    ),
                    ProjectApiEndpoint(
                        key="project-ledger-sheet-detail",
                        name="申报台账子表详情",
                        method="GET",
                        path="/api/v1/registration/project-ledger/sheets/{sheet_key}",
                    ),
                    ProjectApiEndpoint(
                        key="project-ledger-create",
                        name="新增申报台账主记录",
                        method="POST",
                        path="/api/v1/registration/project-ledger/entries",
                    ),
                    ProjectApiEndpoint(
                        key="project-ledger-update",
                        name="编辑申报台账主记录",
                        method="PUT",
                        path="/api/v1/registration/project-ledger/entries/{record_id}",
                    ),
                    ProjectApiEndpoint(
                        key="project-ledger-sub-record",
                        name="新增申报台账子记录",
                        method="POST",
                        path="/api/v1/registration/project-ledger/entries/{record_id}/sub-records",
                    ),
                    ProjectApiEndpoint(
                        key="project-ledger-delete",
                        name="删除申报台账主记录",
                        method="DELETE",
                        path="/api/v1/registration/project-ledger/entries/{record_id}",
                    ),
                    ProjectApiEndpoint(
                        key="project-ledger-import",
                        name="导入申报台账工作簿",
                        method="POST",
                        path="/api/v1/registration/project-ledger/workbook/import",
                    ),
                    ProjectApiEndpoint(
                        key="project-ledger-export",
                        name="导出申报台账工作簿",
                        method="GET",
                        path="/api/v1/registration/project-ledger/workbook/export",
                    ),
                ],
            ),
            ProjectModuleOverviewItem(
                key="declaration-progress",
                name="申报进度",
                description=(
                    "维护 7 个申报进度子表、主子记录层级、颜色标记以及整本工作"
                    "簿导入导出。"
                ),
                path="/registration/declaration-progress",
                workbook_name=declaration_progress_overview.workbook_name,
                updated_at=declaration_progress_overview.updated_at,
                total_records=declaration_progress_overview.total_records,
                sheet_count=len(declaration_progress_overview.sheets),
                child_pages=_build_declaration_progress_child_pages(),
                api_endpoints=[
                    ProjectApiEndpoint(
                        key="declaration-progress-overview",
                        name="申报进度总览",
                        method="GET",
                        path="/api/v1/registration/declaration-progress/overview",
                    ),
                    ProjectApiEndpoint(
                        key="declaration-progress-workbook",
                        name="申报进度工作簿详情",
                        method="GET",
                        path="/api/v1/registration/declaration-progress/workbook",
                    ),
                    ProjectApiEndpoint(
                        key="declaration-progress-sheet-detail",
                        name="申报进度子表详情",
                        method="GET",
                        path="/api/v1/registration/declaration-progress/sheets/{sheet_key}",
                    ),
                    ProjectApiEndpoint(
                        key="declaration-progress-create",
                        name="新增申报进度主记录",
                        method="POST",
                        path="/api/v1/registration/declaration-progress/entries",
                    ),
                    ProjectApiEndpoint(
                        key="declaration-progress-update",
                        name="编辑申报进度记录",
                        method="PUT",
                        path="/api/v1/registration/declaration-progress/entries/{record_id}",
                    ),
                    ProjectApiEndpoint(
                        key="declaration-progress-sub-record",
                        name="新增申报进度子记录",
                        method="POST",
                        path="/api/v1/registration/declaration-progress/entries/{record_id}/sub-records",
                    ),
                    ProjectApiEndpoint(
                        key="declaration-progress-delete",
                        name="删除申报进度主记录",
                        method="DELETE",
                        path="/api/v1/registration/declaration-progress/entries/{record_id}",
                    ),
                    ProjectApiEndpoint(
                        key="declaration-progress-import",
                        name="导入申报进度工作簿",
                        method="POST",
                        path="/api/v1/registration/declaration-progress/workbook/import",
                    ),
                    ProjectApiEndpoint(
                        key="declaration-progress-export",
                        name="导出申报进度工作簿",
                        method="GET",
                        path="/api/v1/registration/declaration-progress/workbook/export",
                    ),
                ],
            ),
        ]

        return ProjectOverview(
            module_name="申报项目",
            path="/registration/project",
            modules=modules,
        )
