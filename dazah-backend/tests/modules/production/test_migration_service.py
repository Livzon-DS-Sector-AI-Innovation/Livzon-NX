from pathlib import Path
from typing import Any

import pytest

from app.modules.production.migration_service import (
    ENTITY_DEFINITIONS,
    ProductionMigrationService,
)


def test_empty_directory_is_a_valid_bundle(tmp_path: Path) -> None:
    bundle, errors = ProductionMigrationService.load_directory(tmp_path)
    validated, validation_errors = ProductionMigrationService.validate_bundle(bundle)

    assert errors == []
    assert validation_errors == []
    assert all(records == [] for records in validated.values())


def test_duplicate_source_record_is_rejected() -> None:
    record = {
        "source_record_id": "same-id",
        "data": {
            "batch_no": "F-001",
            "product_name": "测试产品",
            "fermenter": "F01",
            "entry_date": "2026-07-15",
        },
    }
    _, errors = ProductionMigrationService.validate_bundle(
        {"fermentation_records": [record, record]}
    )

    assert any("来源标识重复" in error for error in errors)


@pytest.mark.anyio
async def test_empty_import_run_and_reconcile(db_session: Any) -> None:
    service = ProductionMigrationService(db_session)
    bundle = {entity: [] for entity in ENTITY_DEFINITIONS}  # type: ignore[var-annotated]

    run = await service.execute(
        bundle=bundle,
        source_system="phase4-empty-test",
        run_key="phase4-empty-test-run",
        dry_run=False,
    )
    report = await service.reconcile("phase4-empty-test")

    assert run.status == "completed"
    assert run.inserted_count == 0
    assert all(item["mapped"] == 0 for item in report.values())


@pytest.mark.anyio
async def test_import_is_idempotent_and_rollback_is_audited(db_session: Any) -> None:
    service = ProductionMigrationService(db_session)
    bundle = {
        "fermentation_records": [
            {
                "source_record_id": "rollback-test-001",
                "data": {
                    "batch_no": "ROLLBACK-001",
                    "product_name": "测试产品",
                    "fermenter": "F-01",
                    "entry_date": "2026-07-15",
                },
            }
        ]
    }
    created_run = await service.execute(
        bundle=bundle,
        source_system="phase4-rollback-test",
        run_key="phase4-create-rollback-test",
        dry_run=False,
    )
    repeated_run = await service.execute(
        bundle=bundle,
        source_system="phase4-rollback-test",
        run_key="phase4-repeat-rollback-test",
        dry_run=False,
    )

    assert created_run.inserted_count == 1
    assert repeated_run.skipped_count == 1

    rollback_run = await service.rollback(
        created_run.id, "phase4-rollback-created-test"
    )
    report = await service.reconcile("phase4-rollback-test")

    assert rollback_run.status == "completed"
    assert report["fermentation_records"]["mapped"] == 0
