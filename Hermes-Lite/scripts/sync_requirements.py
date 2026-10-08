"""Sync direct requirements from pyproject.toml, retaining the existing layout."""

import re
import tomllib
from pathlib import Path


def requirement_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", requirement)
    if match is None:
        raise ValueError("Invalid requirement name")
    return re.sub(r"[-_.]+", "-", match.group()).lower()


def sync_requirements(project_dir: Path) -> None:
    metadata = tomllib.loads((project_dir / "pyproject.toml").read_text("utf-8"))
    dependencies = {
        requirement_name(value): value for value in metadata["project"]["dependencies"]
    }
    target = project_dir / "requirements.txt"
    lines = target.read_text("utf-8").splitlines()
    existing = {
        requirement_name(line)
        for line in lines
        if line.strip() and not line.startswith("#")
    }
    if existing != dependencies.keys():
        raise ValueError("Dependency names changed; review requirements layout first")
    output = [
        dependencies[requirement_name(line)]
        if line.strip() and not line.startswith("#")
        else line
        for line in lines
    ]
    target.write_text("\n".join(output) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sync_requirements(Path(__file__).resolve().parents[1])
