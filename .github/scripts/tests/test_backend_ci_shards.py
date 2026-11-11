"""Exercise backend shard collection and coverage inputs without a database."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPT = (
    Path(__file__).resolve().parents[3] / "dazah-backend/scripts/ci_pytest_shard.py"
)
SPEC = importlib.util.spec_from_file_location("ci_pytest_shard", SCRIPT)
assert SPEC and SPEC.loader
shards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shards)


def test_workflow_schedules_every_backend_shard() -> None:
    workflow = SCRIPT.parents[2] / ".github/workflows/ci.yml"
    job = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"][
        "backend-integration"
    ]
    count = shards.SHARD_COUNT
    assert job["strategy"]["matrix"]["shard"] == list(range(1, count + 1))
    assert job["name"] == f"Backend Integration (${{{{ matrix.shard }}}}/{count})"


def test_weighted_partition_balances_slow_files_without_splitting_them(monkeypatch):
    file_count = shards.SHARD_COUNT * 2
    inventory = [
        f"test_{index}.py::test_{case}"
        for index in range(file_count)
        for case in range(2)
    ]
    weights = {
        f"test_{index}.py": float(file_count - index) for index in range(file_count)
    }
    monkeypatch.setattr(shards, "TEST_FILE_SECONDS", weights)
    plan = shards.partition(inventory)
    totals = [
        sum(weights[file] for file in {node.split("::", 1)[0] for node in group})
        for group in plan
    ]
    assert totals == [file_count + 1] * shards.SHARD_COUNT
    assert set.union(*plan) == set(inventory)
    assert sum(map(len, plan)) == len(inventory)
    assert plan == shards.partition(inventory[::-1])


def test_pytest_runs_each_file_once_in_original_order(tmp_path: Path) -> None:
    expected = []
    for index in range(shards.SHARD_COUNT * 2):
        filename = f"test_file_{index:02d}.py"
        (tmp_path / filename).write_text(
            "import pytest\n"
            "@pytest.mark.parametrize('value', [2, 1])\n"
            "def test_values(value): assert value > 0\n"
            "@pytest.mark.skip(reason='existing skip')\n"
            "def test_skip(): pass\n",
            encoding="utf-8",
        )
        expected.extend(
            f"{filename}::{test}"
            for test in ("test_values[2]", "test_values[1]", "test_skip")
        )

    plan = shards.partition(expected)
    assert plan == shards.partition(expected[::-1])
    launcher = (
        "import sys, pytest; from pathlib import Path; "
        "sys.path.insert(0, sys.argv[1]); "
        "from ci_pytest_shard import IntegrationShard; "
        "plugin = IntegrationShard(int(sys.argv[2]), Path(sys.argv[3])); "
        "raise SystemExit(pytest.main(['-q'], plugins=[plugin]))"
    )
    for shard in range(1, shards.SHARD_COUNT + 1):
        directory = tmp_path / f"backend-integration-shard-{shard}"
        directory.mkdir()
        path = directory / "manifest.json"
        result = subprocess.run(
            [sys.executable, "-c", launcher, str(SCRIPT.parent), str(shard), str(path)],
            cwd=tmp_path,
            env={
                **os.environ,
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTEST_ADDOPTS": "",
            },
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "pytest startup and collection" in result.stdout
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["collected"] == sorted(expected)
        assert manifest["finished"] == [
            node for node in expected if node in plan[shard - 1]
        ]
        for filename in {node.split("::")[0] for node in manifest["finished"]}:
            assert all(
                node in manifest["finished"]
                for node in expected
                if node.startswith(filename + "::")
            )
        (directory / "coverage-data").touch()
    assert len(shards.verify_shards(tmp_path)) == shards.SHARD_COUNT


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        ("missing manifest", "Missing manifest"),
        ("missing coverage", "Missing coverage data"),
        ("different inventory", "collected a different test inventory"),
        ("duplicate test", "extra or repeated 1"),
        ("missing test", "missing 1"),
    ],
)
def test_rejects_incomplete_shard_results(
    tmp_path: Path, problem: str, message: str
) -> None:
    inventory = [
        f"test_{index}.py::test_{case}"
        for index in range(shards.SHARD_COUNT)
        for case in range(2)
    ]
    for index in range(shards.SHARD_COUNT):
        directory = tmp_path / f"backend-integration-shard-{index + 1}"
        directory.mkdir()
        manifest = {
            "shard": index + 1,
            "collected": inventory,
            "finished": inventory[2 * index : 2 * index + 2],
        }
        if index == 3:
            if problem == "different inventory":
                manifest["collected"] = inventory[:-1]
            elif problem == "duplicate test":
                manifest["finished"].append(inventory[0])
            elif problem == "missing test":
                manifest["finished"].pop()
        if index != 3 or problem != "missing manifest":
            (directory / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
        if index != 3 or problem != "missing coverage":
            (directory / "coverage-data").touch()

    with pytest.raises(ValueError, match=message):
        shards.verify_shards(tmp_path)
