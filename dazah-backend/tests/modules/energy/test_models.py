from __future__ import annotations

from datetime import UTC, datetime

from app.modules.energy.models import (
    EnergyFeishuConfig,
    EnergyMetricFact,
    EnergySheetSnapshot,
    EnergySnapshotRow,
)


def test_energy_wiki_models_do_not_create_cross_schema_foreign_keys():
    assert not EnergyFeishuConfig.__table__.foreign_keys
    assert not EnergyMetricFact.__table__.foreign_keys


def test_snapshot_rows_keep_raw_cells_and_fact_identity():
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
