from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.modules.energy.models import (
    EnergyFeishuConfig,
    EnergySheetSnapshot,
    EnergySnapshotRow,
    EnergySyncRun,
    EnergyWikiDocument,
    EnergyWorkbookSheet,
)
from app.modules.energy.wiki_repository import EnergyWikiRepository


@pytest.mark.asyncio
async def test_repository_archives_source_and_pages_immutable_snapshot_rows(db_session):
    repo = EnergyWikiRepository(db_session)
    config = await repo.save_config(
        EnergyFeishuConfig(
            id=uuid4(),
            app_id="cli_energy_test",
            encrypted_app_secret="encrypted",
            root_wiki_url="https://example.feishu.cn/wiki/root",
            root_wiki_token="root",
        )
    )
    document = await repo.save_document(
        EnergyWikiDocument(
            id=uuid4(),
            config_id=config.id,
            wiki_node_token="july-node",
            document_token="spreadsheet-token",
            title="2026年7月能源台账",
            node_path=[{"token": "root", "title": "能源台账"}],
            period_month=date(2026, 7, 1),
            classification_status="monthly",
        )
    )
    sheet = await repo.save_sheet(
        EnergyWorkbookSheet(
            id=uuid4(),
            document_id=document.id,
            external_sheet_id="sheet-a",
            title="水电明细",
            headers=["日期", "电量"],
            schema_hash="a" * 64,
        )
    )
    run = await repo.save_sync_run(
        EnergySyncRun(
            id=uuid4(),
            config_id=config.id,
            idempotency_key="energy:wiki:test:repository",
            status="success",
            completed_at=datetime.now(UTC),
        )
    )
    first = await repo.save_snapshot(
        EnergySheetSnapshot(
            id=uuid4(),
            sheet_id=sheet.id,
            sync_run_id=run.id,
            snapshot_number=1,
            content_hash="1" * 64,
            header_values=["日期", "电量"],
            row_count=2,
        )
    )
    latest = await repo.save_snapshot(
        EnergySheetSnapshot(
            id=uuid4(),
            sheet_id=sheet.id,
            sync_run_id=run.id,
            snapshot_number=2,
            content_hash="2" * 64,
            header_values=["日期", "电量"],
            row_count=3,
        )
    )
    await repo.add_snapshot_rows(
        [
            EnergySnapshotRow(
                id=uuid4(),
                snapshot_id=latest.id,
                row_index=1,
                values=["日期", "电量"],
                row_hash="a" * 64,
            ),
            EnergySnapshotRow(
                id=uuid4(),
                snapshot_id=latest.id,
                row_index=2,
                values=["2026-07-01", 12.5],
                row_hash="b" * 64,
            ),
            EnergySnapshotRow(
                id=uuid4(),
                snapshot_id=latest.id,
                row_index=3,
                values=["2026-07-02", 13.0],
                row_hash="c" * 64,
            ),
        ]
    )

    assert first.snapshot_number == 1
    assert (await repo.next_snapshot_number(sheet.id)) == 3
    assert (await repo.get_latest_snapshot(sheet.id)).id == latest.id
    rows, total = await repo.list_snapshot_rows(
        snapshot_id=latest.id, page=2, page_size=1
    )
    assert total == 3
    assert [row.row_index for row in rows] == [2]
