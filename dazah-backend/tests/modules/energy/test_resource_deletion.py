from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from app.modules.energy.models import (
    EnergyFeishuConfig,
    EnergyFeishuPageBinding,
    EnergyMetricFact,
    EnergySheetMapping,
    EnergySheetSnapshot,
    EnergySnapshotRow,
    EnergySyncRun,
    EnergyWikiDocument,
    EnergyWorkbookSheet,
)
from app.modules.energy.wiki_repository import EnergyWikiRepository


@pytest.mark.asyncio
async def test_resource_deletion_removes_snapshot_and_local_database_data(
    db_session: Any,
) -> Any:
    repo = EnergyWikiRepository(db_session)
    config = await repo.save_config(
        EnergyFeishuConfig(
            id=uuid4(),
            app_id="cli_energy_delete",
            encrypted_app_secret="encrypted",
            root_wiki_url="",
        )
    )
    document = await repo.save_document(
        EnergyWikiDocument(
            id=uuid4(),
            config_id=config.id,
            wiki_node_token="delete-node",
            document_token="delete-book",
            title="待删除资源",
            node_path=[],
        )
    )
    sheet = await repo.save_sheet(
        EnergyWorkbookSheet(
            id=uuid4(),
            document_id=document.id,
            external_sheet_id="delete-sheet",
            title="待删除数据表",
            headers=["日期", "用量"],
        )
    )
    run = await repo.save_sync_run(
        EnergySyncRun(
            id=uuid4(),
            config_id=config.id,
            idempotency_key=f"energy:delete:{uuid4()}",
            status="success",
        )
    )
    snapshot = await repo.save_snapshot(
        EnergySheetSnapshot(
            id=uuid4(),
            sheet_id=sheet.id,
            sync_run_id=run.id,
            snapshot_number=1,
            content_hash="d" * 64,
            header_values=["日期", "用量"],
            row_count=1,
        )
    )
    await repo.add_snapshot_rows(
        [
            EnergySnapshotRow(
                id=uuid4(),
                snapshot_id=snapshot.id,
                row_index=1,
                values=["日期", "用量"],
                row_hash="e" * 64,
            )
        ]
    )
    mapping = EnergySheetMapping(
        id=uuid4(),
        sheet_id=sheet.id,
        version=1,
        is_current=True,
        metrics=[],
    )
    binding = EnergyFeishuPageBinding(
        id=uuid4(),
        page_key="energy.data",
        sheet_id=sheet.id,
        tab_name="待删除",
    )
    fact = EnergyMetricFact(
        id=uuid4(),
        mapping_id=mapping.id,
        mapping_version=1,
        sheet_id=sheet.id,
        snapshot_id=snapshot.id,
        metric_key="用量",
        source_row_index=1,
        observed_at=datetime.now(UTC),
        energy_type="water",
        unit="吨",
        value=Decimal("12.5"),
        dimensions={},
    )
    row = (await repo.list_all_snapshot_rows(snapshot.id))[0]
    db_session.add_all(
        [
            mapping,
            binding,
            fact,
        ]
    )
    await db_session.flush()

    counts = await repo.delete_sheets_with_local_data([sheet])
    await db_session.flush()

    assert counts == {
        "binding_count": 1,
        "fact_count": 1,
        "snapshot_row_count": 1,
        "snapshot_count": 1,
        "mapping_count": 1,
        "deleted_count": 1,
        "document_count": 1,
    }
    assert await db_session.get(EnergyWorkbookSheet, sheet.id) is None
    assert await db_session.get(EnergyWikiDocument, document.id) is None
    assert await db_session.get(EnergySheetSnapshot, snapshot.id) is None
    assert await db_session.get(EnergySnapshotRow, row.id) is None
    assert await db_session.get(EnergySheetMapping, mapping.id) is None
    assert await db_session.get(EnergyFeishuPageBinding, binding.id) is None
    assert await db_session.get(EnergyMetricFact, fact.id) is None
    assert await db_session.get(EnergySyncRun, run.id) is not None
