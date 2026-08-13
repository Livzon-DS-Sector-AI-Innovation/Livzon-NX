from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_checker() -> ModuleType:
    script = Path(__file__).parents[1] / "check-agent-instruction-bridges.py"
    spec = importlib.util.spec_from_file_location(
        "check_agent_instruction_bridges",
        script,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def test_matching_bridge_passes(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

    assert checker.validate_bridges(tmp_path) == []


def test_missing_bridge_fails(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")

    assert checker.validate_bridges(tmp_path) == [
        "AGENTS.md: missing same-directory CLAUDE.md"
    ]


def test_bridge_without_import_fails(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Duplicated rules\n", encoding="utf-8")

    assert checker.validate_bridges(tmp_path) == [
        "CLAUDE.md: missing exact import line @AGENTS.md"
    ]


def test_orphaned_bridge_fails(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

    assert checker.validate_bridges(tmp_path) == [
        "CLAUDE.md: imports missing same-directory AGENTS.md"
    ]


def test_ignored_runtime_directories_are_skipped(tmp_path: Path) -> None:
    for directory in ("node_modules", ".pnpm-store", "temp", "build"):
        dependency = tmp_path / directory / "package"
        dependency.mkdir(parents=True)
        (dependency / "AGENTS.md").write_text(
            "# External rules\n",
            encoding="utf-8",
        )

    assert checker.validate_bridges(tmp_path) == []
