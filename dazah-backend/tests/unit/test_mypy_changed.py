from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest


@pytest.fixture
def gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    script = Path(__file__).resolve().parents[2] / "scripts" / "mypy_changed.py"
    spec = importlib.util.spec_from_file_location("mypy_changed_gate", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REPOSITORY_DIR = tmp_path
    module.BACKEND_DIR = tmp_path / "dazah-backend"
    (module.BACKEND_DIR / "app" / "modules" / "example").mkdir(parents=True)
    for key in ("CI", "CI_BASE_SHA", "CI_HEAD_SHA"):
        monkeypatch.delenv(key, raising=False)
    return module


def test_local_selection_combines_tracked_and_untracked_files(gate: ModuleType) -> None:
    calls: list[tuple[str, ...]] = []

    def git(*args: str) -> bytes:
        calls.append(args)
        return (
            b"dazah-backend/app/modules/example/edited.py\0"
            if args[0] == "diff"
            else b"dazah-backend/app/modules/example/new.py\0"
        )

    gate.git_output = git
    assert gate.changed_paths(None, None, ci=False) == [
        "dazah-backend/app/modules/example/edited.py",
        "dazah-backend/app/modules/example/new.py",
    ]
    assert calls[0][:4] == ("diff", "--name-only", "--diff-filter=ACMR", "-z")
    assert calls[1][:3] == ("ls-files", "--others", "--exclude-standard")


def test_ci_uses_resolved_base_and_head_without_worktree_fallback(
    gate: ModuleType,
) -> None:
    gate.commit_id = Mock(side_effect=["head-oid", "base-oid"])
    gate.git_output = Mock(
        return_value=b"dazah-backend/app/modules/example/renamed.py\0"
    )
    assert gate.changed_paths("base", "head", ci=True) == [
        "dazah-backend/app/modules/example/renamed.py"
    ]
    assert gate.git_output.call_args.args[4:6] == ("base-oid", "head-oid")


def test_first_push_checks_all_head_runtime_files(gate: ModuleType) -> None:
    gate.commit_id = Mock(return_value="head-oid")
    gate.git_output = Mock(return_value=b"dazah-backend/app/modules/example/new.py\0")
    gate.changed_paths("0" * 40, "head", ci=True)
    assert gate.git_output.call_args.args[:4] == ("ls-tree", "-r", "--name-only", "-z")


def test_manual_dispatch_on_main_checks_latest_commit(gate: ModuleType) -> None:
    gate.commit_id = Mock(side_effect=["head", "head", "parent"])
    gate.git_output = Mock(side_effect=[b"head\n", b""])
    gate.changed_paths(None, None, ci=True)
    assert gate.git_output.call_args.args[4:6] == ("parent", "head")


def test_unknown_ci_range_is_an_error_not_a_successful_skip(
    gate: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    gate.git_output = Mock(
        side_effect=subprocess.CalledProcessError(128, ["git", "diff"])
    )
    assert gate.main(["--base", "missing", "--head", "head"]) == 2
    assert "gate failed" in capsys.readouterr().err


def test_targets_filter_deduplicate_and_keep_spaces_as_one_argument(
    gate: ModuleType,
) -> None:
    source = "app/modules/example/typed file.py"
    (gate.BACKEND_DIR / source).write_text("value: int = 1\n", encoding="utf-8")
    assert gate.select_targets(
        [
            f"dazah-backend/{source}",
            source,
            "dazah-backend/tests/test_demo.py",
            "dazah-backend/app/readme.md",
        ]
    ) == [source]
    run = Mock(return_value=subprocess.CompletedProcess([], 19))
    gate.subprocess = type(
        "Process", (), {"run": run, "CalledProcessError": subprocess.CalledProcessError}
    )
    assert gate.main([source]) == 19
    assert run.call_args.args[0] == [
        sys.executable,
        "-m",
        "mypy",
        "--follow-imports=normal",
        "--",
        source,
    ]


@pytest.mark.parametrize(
    "source", ["../outside.py", "app/modules/example/missing.py", "tests/test_demo.py"]
)
def test_explicit_invalid_entry_fails(gate: ModuleType, source: str) -> None:
    assert gate.main([source]) == 2


def test_empty_change_skips_mypy(gate: ModuleType) -> None:
    gate.changed_paths = Mock(return_value=[])
    gate.subprocess = type(
        "Process",
        (),
        {"run": Mock(), "CalledProcessError": subprocess.CalledProcessError},
    )
    assert gate.main([]) == 0
    gate.subprocess.run.assert_not_called()


def test_error_in_unchanged_import_blocks_the_gate(
    gate: ModuleType, capfd: pytest.CaptureFixture[str]
) -> None:
    backend: Path = gate.BACKEND_DIR
    for directory in ("app", "app/modules", "app/modules/example"):
        (backend / directory / "__init__.py").write_text("", encoding="utf-8")
    source = backend / "app/modules/example/entry.py"
    source.write_text(
        "from app.modules.example.dependency import value\n\n"
        "def entry() -> str:\n    return value()\n",
        encoding="utf-8",
    )
    dependency = backend / "app/modules/example/dependency.py"
    dependency.write_text("def value() -> str:\n    return 42\n", encoding="utf-8")
    (backend / "mypy.ini").write_text("[mypy]\nstrict = True\n", encoding="utf-8")
    assert gate.main(["app/modules/example/entry.py"]) == 1
    assert "dependency.py" in capfd.readouterr().out
    dependency.write_text(
        "def value() -> str:\n    return 'correct'\n", encoding="utf-8"
    )
    assert gate.main(["app/modules/example/entry.py"]) == 0


def test_backend_quality_invokes_the_gate_and_preserves_core_check() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "ci.sh"
    content = script.read_text(encoding="utf-8")
    assert "uv run --no-sync mypy app/core" in content
    assert "uv run --no-sync python scripts/mypy_changed.py" in content
    assert "set -euo pipefail" in content
