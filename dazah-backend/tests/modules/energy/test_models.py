from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.modules.energy.models import (
    EnergyFeishuConfig,
    EnergyFeishuSourceRoot,
    EnergyMetricFact,
    EnergySheetSnapshot,
    EnergySnapshotRow,
)


def test_feishu_source_root_uses_active_only_unique_index() -> Any:
    table = EnergyFeishuSourceRoot.__table__
    assert not any(
        constraint.name == "uq_energy_feishu_source_root"
        for constraint in table.constraints  # type: ignore[attr-defined]
    )

    index = next(
        item
        for item in table.indexes  # type: ignore[attr-defined]
        if item.name == "uq_energy_feishu_source_root_active"
    )
    assert index.unique
    assert str(index.dialect_options["postgresql"]["where"]) == ("is_deleted = false")


def test_energy_wiki_models_do_not_create_cross_schema_foreign_keys() -> Any:
    assert not EnergyFeishuConfig.__table__.foreign_keys
    assert not EnergyMetricFact.__table__.foreign_keys


def test_snapshot_rows_keep_raw_cells_and_fact_identity() -> Any:
    snapshot = EnergySheetSnapshot(
        sheet_id="00000000-0000-0000-0000-000000000001",
        sync_run_id="00000000-0000-0000-0000-000000000002",
        snapshot_number=1,
        content_hash="a" * 64,
        header_values=["日期", "用量"],
        row_count=2,
    )
    row = EnergySnapshotRow(
        snapshot_id=snapshot.id,
        row_index=2,
        values=["2026-07-01", 12.5],
        display_values=["2026/07/01", "12.50"],
        row_hash="b" * 64,
    )
    fact = EnergyMetricFact(
        mapping_id="00000000-0000-0000-0000-000000000003",
        mapping_version=1,
        sheet_id=snapshot.sheet_id,
        snapshot_id=snapshot.id,
        metric_key="daily_usage",
        source_row_index=2,
        observed_at=datetime(2026, 7, 1, tzinfo=UTC),
        energy_type="电力",
        unit="kWh",
        value_semantics="direct",
        value=12.5,
        dimensions={"车间": "发酵"},
    )

    assert row.values[1] == 12.5
    assert row.display_values == ["2026/07/01", "12.50"]
    assert fact.metric_key == "daily_usage"
    assert fact.dimensions["车间"] == "发酵"
