"""Partition backend CI tests and verify complete coverage inputs."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Generator, Sequence
from pathlib import Path
from time import perf_counter
from typing import TypedDict

import pytest

SHARD_COUNT = 5
DEFAULT_SECONDS_PER_CASE = 0.021
# File totals from the four full-suite JUnit reports for CI run 42948663467.
# Files below one second and newly collected files use a per-case estimate.
TEST_FILE_SECONDS = {
    "tests/integration/test_dev_migration_guard.py": 1.152,
    "tests/integration/test_equipment_safety_drift_migration.py": 1.492,
    "tests/integration/test_extraction_report_api.py": 1.065,
    "tests/integration/test_fermentation_board_api.py": 1.526,
    "tests/integration/test_fl_board_api.py": 1.345,
    "tests/integration/test_migration_module_api.py": 1.768,
    "tests/integration/test_module_access_control.py": 1.325,
    "tests/integration/test_quality_hr_warehouse_page_authorization.py": 2.099,
    "tests/integration/test_schedule_excel_api.py": 1.24,
    "tests/modules/agent/test_llm_error_security.py": 1.069,
    "tests/modules/agent/test_llm_proxy.py": 1.542,
    "tests/modules/agent/test_module_coverage.py": 1.19,
    "tests/modules/agent/test_phase_one_automation.py": 5.003,
    "tests/modules/agent/test_phase_two_scheduler.py": 12.059,
    "tests/modules/agent/test_role_permission_acceptance.py": 18.573,
    "tests/modules/agent/test_stage_two_governance.py": 3.341,
    "tests/modules/agent/test_supplier_analytics_permissions.py": 1.133,
    "tests/modules/agent/test_tool_catalog.py": 2.559,
    "tests/modules/energy/test_dashboard_source.py": 1.879,
    "tests/modules/energy/test_direct_entry.py": 1.162,
    "tests/modules/energy/test_report_loading.py": 1.064,
    "tests/modules/energy/test_source_result_review.py": 1.355,
    "tests/modules/energy/test_source_workbook.py": 1.051,
    "tests/modules/equipment/test_api.py": 1.648,
    "tests/modules/equipment/test_equipment_health.py": 1.031,
    "tests/modules/equipment/test_equipment_health_api.py": 1.241,
    "tests/modules/equipment/test_equipment_import.py": 1.644,
    "tests/modules/equipment/test_equipment_knowledge.py": 1.151,
    "tests/modules/equipment/test_equipment_personal_todos.py": 1.855,
    "tests/modules/equipment/test_equipment_plan_e.py": 2.014,
    "tests/modules/equipment/test_equipment_plan_e_branches.py": 2.417,
    "tests/modules/equipment/test_equipment_purchase_and_cost.py": 1.947,
    "tests/modules/equipment/test_equipment_service_branches.py": 2.499,
    "tests/modules/equipment/test_feishu_apps.py": 3.715,
    "tests/modules/equipment/test_inspection_feishu_config.py": 8.531,
    "tests/modules/equipment/test_inspection_feishu_mirror.py": 4.128,
    "tests/modules/equipment/test_integration.py": 1.098,
    "tests/modules/equipment/test_maintenance_api.py": 5.414,
    "tests/modules/equipment/test_maintenance_repository.py": 1.071,
    "tests/modules/equipment/test_maintenance_service.py": 3.706,
    "tests/modules/equipment/test_repair_photo.py": 1.157,
    "tests/modules/equipment/test_work_order_feishu_bot.py": 1.23,
    "tests/modules/equipment/test_workshops.py": 4.211,
    "tests/modules/hr/test_contract_expiry_quarter.py": 8.952,
    "tests/modules/hr/test_dept_scope_isolation_source_migration.py": 2.758,
    "tests/modules/hr/test_email_encryption_security.py": 3.833,
    "tests/modules/hr/test_employee_page_permissions.py": 11.825,
    "tests/modules/hr/test_employee_update_security.py": 2.05,
    "tests/modules/hr/test_esg_sync_from_ledger_source_migration.py": 2.737,
    "tests/modules/hr/test_feishu_member_sync_source_migration.py": 13.181,
    "tests/modules/hr/test_hr_qualification_response.py": 19.017,
    "tests/modules/hr/test_offboarding_sync.py": 1.172,
    "tests/modules/hr/test_onboarding_attachment_security.py": 4.83,
    "tests/modules/hr/test_position_transfer_todos.py": 5.393,
    "tests/modules/hr/test_recruitment_service_rules.py": 1.098,
    "tests/modules/hr/test_training_document_generators_migration.py": 1.571,
    "tests/modules/hr/test_training_personnel_config_scope.py": 1.08,
    "tests/modules/procurement/test_material_source_api.py": 1.128,
    "tests/modules/production/test_batch_workshop_scope.py": 2.462,
    "tests/modules/production/test_page_permission_acceptance.py": 8.388,
    "tests/modules/production/test_production_api_smoke.py": 8.767,
    "tests/modules/production/test_production_page_authorization.py": 3.611,
    "tests/modules/quality/test_capa_change_page_scope.py": 1.817,
    "tests/modules/quality/test_capa_plan_department.py": 1.807,
    "tests/modules/quality/test_change_action_plan_api.py": 3.396,
    "tests/modules/quality/test_change_api.py": 2.784,
    "tests/modules/quality/test_cpv_retired_routes.py": 11.251,
    "tests/modules/quality/test_deviation_ai_session_api.py": 1.03,
    "tests/modules/quality/test_deviation_page_permissions.py": 3.062,
    "tests/modules/quality/test_deviation_workbench_api.py": 1.804,
    "tests/modules/quality/test_deviation_workbench_service.py": 1.121,
    "tests/modules/quality/test_document_attachment_revision.py": 4.603,
    "tests/modules/quality/test_document_catalog_page_scope.py": 2.554,
    "tests/modules/quality/test_external_quality_api.py": 1.187,
    "tests/modules/quality/test_finished_product_anomaly_api.py": 2.118,
    "tests/modules/quality/test_historical_deviation_api.py": 2.458,
    "tests/modules/quality/test_import_transaction_regression.py": 1.21,
    "tests/modules/quality/test_inspection_api.py": 1.315,
    "tests/modules/quality/test_inspection_dashboard_trend_alert.py": 1.388,
    "tests/modules/quality/test_inspection_finished_mirror_sync.py": 2.395,
    "tests/modules/quality/test_inspection_instrument_mirror_sync.py": 1.311,
    "tests/modules/quality/test_inspection_material_mirror_sync.py": 1.779,
    "tests/modules/quality/test_inspection_stage2_api.py": 1.39,
    "tests/modules/quality/test_instrument_certificate_analyze.py": 1.022,
    "tests/modules/quality/test_quality_ai_service_migration.py": 3.05,
    "tests/modules/quality/test_quality_feishu_settings_recovery.py": 1.128,
    "tests/modules/quality/test_quality_items_mirror_sync.py": 1.744,
    "tests/modules/quality/test_quality_management_service_lists.py": 7.95,
    "tests/modules/quality/test_quality_notification_settings.py": 2.383,
    "tests/modules/quality/test_security_fixes_source_migration.py": 1.619,
    "tests/modules/quality/test_settings_page_permissions.py": 3.039,
    "tests/modules/quality/test_supplier_qualification_mirror.py": 1.956,
    "tests/modules/quality/test_tracking_records_api.py": 3.916,
    "tests/modules/quality/test_trend_ai_analysis.py": 3.127,
    "tests/modules/quality/test_trend_alert_escalation.py": 1.354,
    "tests/modules/quality/test_trend_chart_render.py": 2.061,
    "tests/modules/quality/test_validation_api.py": 2.336,
    "tests/modules/quality/test_validation_classification.py": 2.042,
    "tests/modules/quality/test_validation_review_api.py": 5.508,
    "tests/modules/quality/test_validation_review_service.py": 18.268,
    "tests/modules/quality/test_validation_service.py": 1.076,
    "tests/modules/registration/test_certificate_workbook_api_source_migration.py": (
        2.989
    ),
    "tests/modules/registration/test_knowledge_tasks_migration.py": 6.454,
    "tests/modules/registration/test_project_ledger_api_source_migration.py": 4.708,
    "tests/modules/regulatory_tracker/test_tracker_sync_service.py": 1.754,
    "tests/modules/safety/test_emergency_mgmt_api.py": 1.032,
    "tests/modules/safety/test_feishu_settings_service.py": 1.964,
    "tests/modules/safety/test_fire_equipment_api.py": 1.278,
    "tests/modules/safety/test_fire_equipment_service.py": 2.804,
    "tests/modules/safety/test_hazchem_facilities_api.py": 1.121,
    "tests/modules/safety/test_hazchem_msds_files_api.py": 1.046,
    "tests/modules/safety/test_knowledge_feishu_sync.py": 1.514,
    "tests/modules/safety/test_oh_detection_report_api.py": 2.105,
    "tests/modules/safety/test_oh_detection_report_parser.py": 1.087,
    "tests/modules/safety/test_regulation_compliance.py": 2.092,
    "tests/modules/safety/test_regulation_radar.py": 3.65,
    "tests/modules/safety/test_safety_targets_api.py": 1.486,
    "tests/modules/safety/test_target_responsibility_api.py": 3.521,
    "tests/modules/safety/test_work_certificates.py": 1.376,
    "tests/modules/safety/test_work_permits_api.py": 4.955,
    "tests/modules/warehouse/test_api_source_migration.py": 1.489,
    "tests/modules/warehouse/test_material_page_permissions.py": 3.329,
    "tests/platform/identity/test_authorization_core.py": 8.899,
    "tests/platform/identity/test_builtin_role_operations.py": 1.878,
    "tests/platform/identity/test_hr_members_sync_page_binding.py": 4.13,
    "tests/platform/identity/test_menus_source_migration.py": 1.198,
    "tests/platform/identity/test_page_permission_catalog_enforcement.py": 2.291,
    "tests/platform/identity/test_page_permission_enforcement.py": 1.599,
    "tests/platform/identity/test_page_permission_write_api.py": 14.982,
    "tests/platform/identity/test_permission_verification_source_migration.py": 5.581,
    "tests/platform/identity/test_rbac_source_migration.py": 2.908,
    "tests/platform/identity/test_role_candidates.py": 1.204,
    "tests/platform/identity/test_role_create_api.py": 1.716,
    "tests/platform/identity/test_training_page_bindings.py": 11.984,
    "tests/platform/system/test_feedback_api.py": 1.256,
    "tests/unit/test_api_route_delegation_smoke.py": 16.308,
    "tests/unit/test_business_todo_contract.py": 30.68,
    "tests/unit/test_feishu_credential_boundary.py": 8.018,
    "tests/unit/test_identity_integration_discovery.py": 4.422,
    "tests/unit/test_migration_module_imports.py": 1.291,
    "tests/unit/test_warehouse_feishu_client.py": 1.255,
}


class Manifest(TypedDict):
    shard: int
    collected: list[str]
    finished: list[str]


def partition(node_ids: Sequence[str]) -> list[set[str]]:
    files: dict[str, list[str]] = defaultdict(list)
    for node_id in node_ids:
        files[node_id.split("::", 1)[0]].append(node_id)

    durations = {
        file: TEST_FILE_SECONDS.get(file, DEFAULT_SECONDS_PER_CASE * len(cases))
        for file, cases in files.items()
    }
    shards: list[set[str]] = [set() for _ in range(SHARD_COUNT)]
    totals = [0.0] * SHARD_COUNT
    for file in sorted(files, key=lambda path: (-durations[path], path)):
        target = totals.index(min(totals))
        shards[target].update(files[file])
        totals[target] += durations[file]
    return shards


class IntegrationShard:
    def __init__(self, shard: int, manifest_path: Path) -> None:
        self.manifest_path = manifest_path
        self.started_at = perf_counter()
        self.manifest: Manifest = {"shard": shard, "collected": [], "finished": []}

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(
        self, config: pytest.Config, items: list[pytest.Item]
    ) -> Generator[None, None, None]:
        yield
        node_ids = [item.nodeid for item in items]
        if len(set(node_ids)) != len(node_ids):
            raise pytest.UsageError("Backend collection contains duplicate test IDs")
        self.manifest["collected"] = sorted(node_ids)
        selected = partition(node_ids)[self.manifest["shard"] - 1]
        if not selected:
            raise pytest.UsageError("No tests assigned to this backend shard")
        config.hook.pytest_deselected(
            items=[item for item in items if item.nodeid not in selected]
        )
        items[:] = [item for item in items if item.nodeid in selected]

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal is not None:
            collected = len(self.manifest["collected"])
            terminal.write_line(
                f"Backend shard {self.manifest['shard']}/{SHARD_COUNT}: "
                f"{len(session.items)} of {collected} tests selected; "
                f"pytest startup and collection {perf_counter() - self.started_at:.2f}s"
            )

    def pytest_runtest_logfinish(self, nodeid: str) -> None:
        self.manifest["finished"].append(nodeid)

    def pytest_sessionfinish(self) -> None:
        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8"
        )


def run_shard(shard: int, output: Path) -> int:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["COVERAGE_FILE"] = str(output / "coverage-data")
    return int(
        pytest.main(
            [
                "-p",
                "no:anyio",
                "--cov",
                "--cov-branch",
                "--cov-report=",
                "--durations=15",
                f"--junitxml={output / 'junit.xml'}",
                "-ra",
            ],
            plugins=[IntegrationShard(shard, output / "manifest.json")],
        )
    )


def verify_shards(artifacts: Path) -> list[Path]:
    inventory: list[str] | None = None
    finished: Counter[str] = Counter()
    coverage_files: list[Path] = []
    for shard in range(1, SHARD_COUNT + 1):
        directory = artifacts / f"backend-integration-shard-{shard}"
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"Missing manifest for backend shard {shard}")
        manifest: Manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["shard"] != shard or not manifest["finished"]:
            raise ValueError(f"Invalid manifest for backend shard {shard}")
        collected = manifest["collected"]
        if inventory is None:
            if not collected or len(set(collected)) != len(collected):
                raise ValueError(
                    "Backend shard inventory is empty or contains duplicates"
                )
            inventory = collected
        elif collected != inventory:
            raise ValueError(
                f"Backend shard {shard} collected a different test inventory"
            )
        finished.update(manifest["finished"])
        coverage_file = directory / "coverage-data"
        if not coverage_file.is_file():
            raise ValueError(f"Missing coverage data for backend shard {shard}")
        coverage_files.append(coverage_file)

    expected = Counter(inventory)
    if finished != expected:
        raise ValueError(
            "Backend shards did not finish every collected test exactly once "
            f"(missing {sum((expected - finished).values())}, "
            f"extra or repeated {sum((finished - expected).values())})"
        )
    print(
        f"Verified {sum(finished.values())} tests across {SHARD_COUNT} backend shards"
    )
    return coverage_files


def combine_coverage(artifacts: Path) -> None:
    from coverage import Coverage, CoverageData

    coverage_files = verify_shards(artifacts)
    for file in coverage_files:
        data = CoverageData(basename=str(file))
        data.read()
        if not data.has_arcs() or not data.measured_files():
            raise ValueError(f"Empty or non-branch coverage data in {file.parent.name}")

    coverage = Coverage()
    coverage.combine([str(file) for file in coverage_files], strict=True, keep=True)
    coverage.save()
    coverage.report(show_missing=True)
    coverage.xml_report(outfile="coverage.xml")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("shard", type=int, choices=range(1, SHARD_COUNT + 1))
    run.add_argument("output", type=Path)
    combine = commands.add_parser("combine")
    combine.add_argument("artifacts", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        return run_shard(args.shard, args.output)
    combine_coverage(args.artifacts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
