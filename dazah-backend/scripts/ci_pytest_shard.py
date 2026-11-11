"""Partition backend CI tests and verify complete coverage inputs."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Generator, Sequence
from pathlib import Path
from typing import TypedDict

import pytest

SHARD_COUNT = 4
DEFAULT_SECONDS_PER_CASE = 0.045
# File totals from the full-suite JUnit report for CI run 42756118132.
# Lighter and newly collected files use a per-case estimate.
TEST_FILE_SECONDS = {
    "tests/modules/agent/test_phase_two_scheduler.py": 8.1,
    "tests/modules/agent/test_role_permission_acceptance.py": 12.3,
    "tests/modules/agent/test_stage_two_governance.py": 4.9,
    "tests/modules/equipment/test_inspection_feishu_config.py": 8.1,
    "tests/modules/hr/test_contract_expiry_quarter.py": 7.0,
    "tests/modules/hr/test_employee_page_permissions.py": 8.2,
    "tests/modules/hr/test_feishu_member_sync_source_migration.py": 13.1,
    "tests/modules/hr/test_hr_qualification_response.py": 12.2,
    "tests/modules/production/test_batch_workshop_scope.py": 4.3,
    "tests/modules/production/test_page_permission_acceptance.py": 7.6,
    "tests/modules/production/test_production_api_smoke.py": 8.5,
    "tests/modules/production/test_production_page_authorization.py": 6.9,
    "tests/modules/quality/test_cpv_retired_routes.py": 5.4,
    "tests/modules/quality/test_historical_deviation_api.py": 5.8,
    "tests/modules/quality/test_quality_management_service_lists.py": 7.3,
    "tests/modules/quality/test_validation_review_service.py": 18.4,
    "tests/modules/registration/test_knowledge_tasks_migration.py": 6.4,
    "tests/modules/registration/test_project_ledger_api_source_migration.py": 4.5,
    "tests/modules/safety/test_work_permits_api.py": 4.5,
    "tests/platform/identity/test_authorization_core.py": 5.5,
    "tests/platform/identity/test_dept_rule_api.py": 4.3,
    "tests/platform/identity/test_hr_members_sync_page_binding.py": 4.9,
    "tests/platform/identity/test_page_permission_write_api.py": 12.5,
    "tests/platform/identity/test_permission_verification_source_migration.py": 10.5,
    "tests/platform/identity/test_training_page_bindings.py": 6.0,
    "tests/unit/test_api_route_delegation_smoke.py": 17.3,
    "tests/unit/test_business_todo_contract.py": 18.3,
    "tests/unit/test_feishu_credential_boundary.py": 9.0,
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
