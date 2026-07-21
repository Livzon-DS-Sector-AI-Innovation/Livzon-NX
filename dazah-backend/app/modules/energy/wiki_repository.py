"""Persistence helpers for the energy Wiki ingestion domain."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.energy.models import (
    EnergyFeishuConfig,
    EnergyFeishuPageBinding,
    EnergyFeishuSourceRoot,
    EnergyMetricFact,
    EnergySheetMapping,
    EnergySheetSnapshot,
    EnergySnapshotRow,
    EnergySyncRun,
    EnergyWikiDocument,
    EnergyWorkbookSheet,
)


class EnergyWikiRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page_bindings(self, page_key: str) -> list[EnergyFeishuPageBinding]:
        result = await self.session.execute(
            select(EnergyFeishuPageBinding)
            .where(
                EnergyFeishuPageBinding.page_key == page_key,
                EnergyFeishuPageBinding.is_deleted == False,  # noqa: E712
                EnergyFeishuPageBinding.is_enabled == True,  # noqa: E712
            )
            .order_by(
                EnergyFeishuPageBinding.sort_order,
                EnergyFeishuPageBinding.created_at,
            )
        )
        return list(result.scalars().all())

    async def get_page_binding(
        self, page_key: str, binding_id: UUID
    ) -> EnergyFeishuPageBinding | None:
        return cast(
            EnergyFeishuPageBinding | None,
            await self.session.scalar(
                select(EnergyFeishuPageBinding).where(
                    EnergyFeishuPageBinding.id == binding_id,
                    EnergyFeishuPageBinding.page_key == page_key,
                    EnergyFeishuPageBinding.is_deleted == False,  # noqa: E712
                    EnergyFeishuPageBinding.is_enabled == True,  # noqa: E712
                )
            ),
        )

    async def replace_page_bindings(
        self, page_key: str, bindings: list[EnergyFeishuPageBinding]
    ) -> None:
        await self.session.execute(
            delete(EnergyFeishuPageBinding).where(
                EnergyFeishuPageBinding.page_key == page_key,
            )
        )
        self.session.add_all(bindings)
        await self.session.flush()

    async def list_source_roots(self, config_id: UUID) -> list[EnergyFeishuSourceRoot]:
        result = await self.session.execute(
            select(EnergyFeishuSourceRoot)
            .where(
                EnergyFeishuSourceRoot.config_id == config_id,
                EnergyFeishuSourceRoot.is_deleted == False,  # noqa: E712
            )
            .order_by(EnergyFeishuSourceRoot.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_source_root(self, root_id: UUID) -> EnergyFeishuSourceRoot | None:
        return cast(
            EnergyFeishuSourceRoot | None,
            await self.session.scalar(
                select(EnergyFeishuSourceRoot).where(
                    EnergyFeishuSourceRoot.id == root_id,
                    EnergyFeishuSourceRoot.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def save_source_root(
        self, root: EnergyFeishuSourceRoot
    ) -> EnergyFeishuSourceRoot:
        self.session.add(root)
        await self.session.flush()
        return root

    async def get_config(self) -> EnergyFeishuConfig | None:
        return cast(
            EnergyFeishuConfig | None,
            await self.session.scalar(
                select(EnergyFeishuConfig)
                .where(EnergyFeishuConfig.is_deleted == False)  # noqa: E712
                .order_by(EnergyFeishuConfig.updated_at.desc())
                .limit(1)
            ),
        )

    async def lock_active_config(self) -> EnergyFeishuConfig | None:
        return cast(
            EnergyFeishuConfig | None,
            await self.session.scalar(
                select(EnergyFeishuConfig)
                .where(
                    EnergyFeishuConfig.is_active == True,  # noqa: E712
                    EnergyFeishuConfig.is_deleted == False,  # noqa: E712
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            ),
        )

    async def get_config_by_id(self, config_id: UUID) -> EnergyFeishuConfig | None:
        return cast(
            EnergyFeishuConfig | None,
            await self.session.scalar(
                select(EnergyFeishuConfig).where(
                    EnergyFeishuConfig.id == config_id,
                    EnergyFeishuConfig.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def save_config(self, config: EnergyFeishuConfig) -> EnergyFeishuConfig:
        self.session.add(config)
        await self.session.flush()
        return config

    async def get_document(
        self, *, config_id: UUID, wiki_node_token: str
    ) -> EnergyWikiDocument | None:
        return cast(
            EnergyWikiDocument | None,
            await self.session.scalar(
                select(EnergyWikiDocument).where(
                    EnergyWikiDocument.config_id == config_id,
                    EnergyWikiDocument.wiki_node_token == wiki_node_token,
                    EnergyWikiDocument.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def save_document(self, document: EnergyWikiDocument) -> EnergyWikiDocument:
        self.session.add(document)
        await self.session.flush()
        return document

    async def list_documents(
        self, *, config_id: UUID, period_month: str | None = None
    ) -> list[EnergyWikiDocument]:
        query = select(EnergyWikiDocument).where(
            EnergyWikiDocument.config_id == config_id,
            EnergyWikiDocument.is_deleted == False,  # noqa: E712
        )
        if period_month:
            query = query.where(
                func.to_char(EnergyWikiDocument.period_month, "YYYY-MM") == period_month
            )
        result = await self.session.execute(
            query.order_by(
                EnergyWikiDocument.period_month.desc().nullslast(),
                EnergyWikiDocument.title,
            )
        )
        return list(result.scalars())

    async def get_sheet(
        self, *, document_id: UUID, external_sheet_id: str
    ) -> EnergyWorkbookSheet | None:
        return cast(
            EnergyWorkbookSheet | None,
            await self.session.scalar(
                select(EnergyWorkbookSheet).where(
                    EnergyWorkbookSheet.document_id == document_id,
                    EnergyWorkbookSheet.external_sheet_id == external_sheet_id,
                    EnergyWorkbookSheet.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def get_sheet_by_id(self, sheet_id: UUID) -> EnergyWorkbookSheet | None:
        return cast(
            EnergyWorkbookSheet | None,
            await self.session.scalar(
                select(EnergyWorkbookSheet).where(
                    EnergyWorkbookSheet.id == sheet_id,
                    EnergyWorkbookSheet.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def save_sheet(self, sheet: EnergyWorkbookSheet) -> EnergyWorkbookSheet:
        self.session.add(sheet)
        await self.session.flush()
        return sheet

    async def list_sheets(
        self,
        *,
        config_id: UUID,
        period_month: str | None = None,
        mapping_status: str | None = None,
    ) -> list[tuple[EnergyWorkbookSheet, EnergyWikiDocument]]:
        query = (
            select(EnergyWorkbookSheet, EnergyWikiDocument)
            .join(
                EnergyWikiDocument,
                EnergyWorkbookSheet.document_id == EnergyWikiDocument.id,
            )
            .where(
                EnergyWikiDocument.config_id == config_id,
                EnergyWikiDocument.is_deleted == False,  # noqa: E712
                EnergyWorkbookSheet.is_deleted == False,  # noqa: E712
            )
        )
        if period_month:
            query = query.where(
                func.to_char(EnergyWikiDocument.period_month, "YYYY-MM") == period_month
            )
        if mapping_status:
            query = query.where(EnergyWorkbookSheet.mapping_status == mapping_status)
        result = await self.session.execute(
            query.order_by(
                EnergyWikiDocument.period_month.desc().nullslast(),
                EnergyWikiDocument.title,
                EnergyWorkbookSheet.sheet_index,
            )
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_document_by_id(self, document_id: UUID) -> EnergyWikiDocument | None:
        return cast(
            EnergyWikiDocument | None,
            await self.session.scalar(
                select(EnergyWikiDocument).where(
                    EnergyWikiDocument.id == document_id,
                    EnergyWikiDocument.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def get_sync_run_by_key(self, key: str) -> EnergySyncRun | None:
        return cast(
            EnergySyncRun | None,
            await self.session.scalar(
                select(EnergySyncRun).where(
                    EnergySyncRun.idempotency_key == key,
                    EnergySyncRun.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def save_sync_run(self, run: EnergySyncRun) -> EnergySyncRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def list_sync_runs(
        self, *, config_id: UUID, page: int, page_size: int
    ) -> tuple[list[EnergySyncRun], int]:
        query = select(EnergySyncRun).where(
            EnergySyncRun.config_id == config_id,
            EnergySyncRun.is_deleted == False,  # noqa: E712
        )
        total = (
            await self.session.execute(
                select(func.count()).select_from(query.subquery())
            )
        ).scalar_one()
        result = await self.session.execute(
            query.order_by(EnergySyncRun.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars()), total

    async def get_latest_snapshot(self, sheet_id: UUID) -> EnergySheetSnapshot | None:
        return cast(
            EnergySheetSnapshot | None,
            await self.session.scalar(
                select(EnergySheetSnapshot)
                .where(
                    EnergySheetSnapshot.sheet_id == sheet_id,
                    EnergySheetSnapshot.is_deleted == False,  # noqa: E712
                )
                .order_by(EnergySheetSnapshot.snapshot_number.desc())
                .limit(1)
            ),
        )

    async def next_snapshot_number(self, sheet_id: UUID) -> int:
        value = await self.session.scalar(
            select(
                func.coalesce(func.max(EnergySheetSnapshot.snapshot_number), 0)
            ).where(
                EnergySheetSnapshot.sheet_id == sheet_id,
                EnergySheetSnapshot.is_deleted == False,  # noqa: E712
            )
        )
        return int(value or 0) + 1

    async def save_snapshot(self, snapshot: EnergySheetSnapshot) -> EnergySheetSnapshot:
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def add_snapshot_rows(self, rows: list[EnergySnapshotRow]) -> None:
        self.session.add_all(rows)
        await self.session.flush()

    async def get_snapshot(self, snapshot_id: UUID) -> EnergySheetSnapshot | None:
        return cast(
            EnergySheetSnapshot | None,
            await self.session.scalar(
                select(EnergySheetSnapshot).where(
                    EnergySheetSnapshot.id == snapshot_id,
                    EnergySheetSnapshot.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def list_snapshots(self, sheet_id: UUID) -> list[EnergySheetSnapshot]:
        result = await self.session.execute(
            select(EnergySheetSnapshot)
            .where(
                EnergySheetSnapshot.sheet_id == sheet_id,
                EnergySheetSnapshot.is_deleted == False,  # noqa: E712
            )
            .order_by(EnergySheetSnapshot.snapshot_number.desc())
        )
        return list(result.scalars())

    async def list_snapshot_rows(
        self, *, snapshot_id: UUID, page: int, page_size: int
    ) -> tuple[list[EnergySnapshotRow], int]:
        query = select(EnergySnapshotRow).where(
            EnergySnapshotRow.snapshot_id == snapshot_id,
            EnergySnapshotRow.is_deleted == False,  # noqa: E712
        )
        total = (
            await self.session.execute(
                select(func.count()).select_from(query.subquery())
            )
        ).scalar_one()
        result = await self.session.execute(
            query.order_by(EnergySnapshotRow.row_index)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars()), total

    async def list_all_snapshot_rows(
        self, snapshot_id: UUID
    ) -> list[EnergySnapshotRow]:
        result = await self.session.execute(
            select(EnergySnapshotRow)
            .where(
                EnergySnapshotRow.snapshot_id == snapshot_id,
                EnergySnapshotRow.is_deleted == False,  # noqa: E712
            )
            .order_by(EnergySnapshotRow.row_index)
        )
        return list(result.scalars())

    async def get_current_mapping(self, sheet_id: UUID) -> EnergySheetMapping | None:
        return cast(
            EnergySheetMapping | None,
            await self.session.scalar(
                select(EnergySheetMapping).where(
                    EnergySheetMapping.sheet_id == sheet_id,
                    EnergySheetMapping.is_current == True,  # noqa: E712
                    EnergySheetMapping.is_deleted == False,  # noqa: E712
                )
            ),
        )

    async def list_current_mappings_by_schema(
        self, schema_hash: str
    ) -> list[EnergySheetMapping]:
        result = await self.session.execute(
            select(EnergySheetMapping).where(
                EnergySheetMapping.schema_hash == schema_hash,
                EnergySheetMapping.is_current == True,  # noqa: E712
                EnergySheetMapping.is_enabled == True,  # noqa: E712
                EnergySheetMapping.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars())

    async def save_mapping(self, mapping: EnergySheetMapping) -> EnergySheetMapping:
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def invalidate_current_mapping(self, sheet_id: UUID) -> None:
        mapping = await self.get_current_mapping(sheet_id)
        if mapping:
            mapping.is_current = False
            await self.session.flush()

    async def clear_mapping_facts(self, mapping_id: UUID) -> None:
        result = await self.session.execute(
            select(EnergyMetricFact).where(
                EnergyMetricFact.mapping_id == mapping_id,
                EnergyMetricFact.is_deleted == False,  # noqa: E712
            )
        )
        for fact in result.scalars():
            fact.is_deleted = True
        await self.session.flush()

    async def add_facts(self, facts: list[EnergyMetricFact]) -> None:
        self.session.add_all(facts)
        await self.session.flush()

    async def list_current_facts(
        self,
        *,
        start: datetime,
        end: datetime,
        energy_type: str | None,
        source_scope: str,
        workshop: str | None,
        source_sheet_title: str | None,
    ) -> list[EnergyMetricFact]:
        scope_roles = {
            "detail": ("workshop_detail", "shared_detail"),
            "daily_summary": ("daily_summary",),
            "energy_summary": ("energy_summary",),
        }
        source_roles = scope_roles.get(source_scope)
        if source_roles is None:
            raise ValueError(f"未知的能源总览来源口径：{source_scope}")
        latest_number = (
            select(
                EnergySheetSnapshot.sheet_id,
                func.max(EnergySheetSnapshot.snapshot_number).label("snapshot_number"),
            )
            .where(EnergySheetSnapshot.is_deleted == False)  # noqa: E712
            .group_by(EnergySheetSnapshot.sheet_id)
            .subquery()
        )
        query = (
            select(EnergyMetricFact)
            .join(
                EnergySheetMapping, EnergyMetricFact.mapping_id == EnergySheetMapping.id
            )
            .join(
                EnergySheetSnapshot,
                EnergyMetricFact.snapshot_id == EnergySheetSnapshot.id,
            )
            .join(
                latest_number,
                (EnergySheetSnapshot.sheet_id == latest_number.c.sheet_id)
                & (
                    EnergySheetSnapshot.snapshot_number
                    == latest_number.c.snapshot_number
                ),
            )
            .join(
                EnergyWorkbookSheet,
                EnergyMetricFact.sheet_id == EnergyWorkbookSheet.id,
            )
            .where(
                EnergyMetricFact.is_deleted == False,  # noqa: E712
                EnergySheetMapping.is_deleted == False,  # noqa: E712
                EnergySheetMapping.is_current == True,  # noqa: E712
                EnergySheetMapping.is_enabled == True,  # noqa: E712
                EnergySheetMapping.source_role.in_(source_roles),
                EnergyMetricFact.observed_at <= end,
            )
        )
        if energy_type:
            query = query.where(EnergyMetricFact.energy_type == energy_type)
        if workshop:
            query = query.where(EnergyMetricFact.dimensions["车间"].astext == workshop)
        if source_sheet_title:
            query = query.where(EnergyWorkbookSheet.title == source_sheet_title)
        result = await self.session.execute(
            query.order_by(EnergyMetricFact.observed_at)
        )
        return list(result.scalars())

    async def count_invalid_current_facts(
        self, *, start: datetime, end: datetime
    ) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(EnergyMetricFact)
            .where(
                EnergyMetricFact.is_deleted == False,  # noqa: E712
                EnergyMetricFact.quality_status != "valid",
                EnergyMetricFact.observed_at >= start,
                EnergyMetricFact.observed_at <= end,
            )
        )
        return int(result.scalar_one())
