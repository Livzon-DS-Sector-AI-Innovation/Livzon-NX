from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import tarfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "install_pinned_lark_cli.py"
MANIFEST_PATH = PROJECT_ROOT / "lark-cli.json"

spec = importlib.util.spec_from_file_location("install_pinned_lark_cli", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def _archive(path: Path, *, binary_name: str = "lark-cli") -> str:
    payload = b"#!/bin/sh\necho lark-cli version 1.0.76\n"
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(binary_name)
        info.size = len(payload)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(payload))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(tmp_path: Path, archive_hash: str) -> Path:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["archive_sha256"] = archive_hash
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_lark_cli_manifest_and_dockerfile_are_exact() -> None:
    manifest = installer.load_manifest(MANIFEST_PATH)
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert manifest["version"] == "1.0.76"
    assert (
        manifest["archive_sha256"]
        == "759a676dde001bdc015384cfd741bcaca873329bbcaad8c4ea4a06acb49b3f42"
    )
    assert "install_pinned_lark_cli.py" in dockerfile
    assert "apt-get" not in dockerfile
    assert "npm install" not in dockerfile


def test_installer_verifies_and_extracts_binary(tmp_path: Path) -> None:
    archive = tmp_path / "lark-cli.tar.gz"
    manifest = _manifest(tmp_path, _archive(archive))
    target = tmp_path / "bin" / "lark-cli"

    result = installer.install(
        manifest_path=manifest,
        target=target,
        archive_path=archive,
    )

    assert result["source"] == "provided-archive"
    assert target.read_bytes().startswith(b"#!/bin/sh")
    if os.name != "nt":
        assert target.stat().st_mode & 0o111


def test_installer_rejects_checksum_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "lark-cli.tar.gz"
    _archive(archive)
    manifest = _manifest(tmp_path, "0" * 64)

    with pytest.raises(installer.LarkCliVerificationError, match="checksum"):
        installer.install(
            manifest_path=manifest,
            target=tmp_path / "lark-cli",
            archive_path=archive,
        )


def test_installer_rejects_archive_without_expected_binary(tmp_path: Path) -> None:
    archive = tmp_path / "lark-cli.tar.gz"
    manifest = _manifest(
        tmp_path,
        _archive(archive, binary_name="unexpected"),
    )

    with pytest.raises(installer.LarkCliVerificationError, match="exactly one"):
        installer.install(
            manifest_path=manifest,
            target=tmp_path / "lark-cli",
            archive_path=archive,
        )
