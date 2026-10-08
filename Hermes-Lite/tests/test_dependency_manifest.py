"""Keep the installer manifest aligned with the canonical project metadata."""

import tomllib
from pathlib import Path

import pytest

from scripts.sync_requirements import sync_requirements

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_requirements_exactly_match_declared_dependencies():
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    requirements = {
        line for line in (PROJECT_ROOT / "requirements.txt").read_text("utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert requirements == set(metadata["project"]["dependencies"])


def test_sync_refuses_to_silently_drop_an_existing_requirement(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["pypdf==6.19.0"]\n', encoding="utf-8"
    )
    manifest = tmp_path / "requirements.txt"
    original = "pypdf==6.14.2\nrequests==2.33.0\n"
    manifest.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="Dependency names changed"):
        sync_requirements(tmp_path)
    assert manifest.read_text("utf-8") == original
