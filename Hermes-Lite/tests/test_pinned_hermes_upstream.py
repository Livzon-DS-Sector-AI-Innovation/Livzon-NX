from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "install_pinned_hermes_upstream.py"
MANIFEST_PATH = PROJECT_ROOT / "upstream-hermes.json"

spec = importlib.util.spec_from_file_location("install_pinned_hermes_upstream", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def _write_fake_archive(path: Path, *, include_send: bool = True) -> str:
    adapter_methods = """
class FeishuAdapter:
    async def _feishu_send_with_retry(self): ...
    async def connect(self): ...
    async def disconnect(self): ...
    async def edit_message(self): ...
    async def send_exec_approval(self): ...
"""
    if include_send:
        adapter_methods += "    async def send(self): ...\n"
    base_methods = """
class MessageEvent:
    text: str
    message_type: str
    source: object
    message_id: str
    media_urls: list
    media_types: list
    reply_to_message_id: str
    reply_to_text: str
    metadata: dict

class BasePlatformAdapter:
    async def connect(self): ...
    async def disconnect(self): ...
    async def edit_message(self): ...
    async def handle_message(self): ...
    async def on_processing_complete(self): ...
    async def on_processing_start(self): ...
    async def send(self): ...
    async def send_draft(self): ...
    def set_message_handler(self): ...
    def supports_draft_streaming(self): ...
"""
    session_source = """
class SessionSource:
    platform: str
    chat_id: str
    chat_type: str
    user_id: str
    user_name: str
    thread_id: str
    user_id_alt: str
    parent_chat_id: str
    message_id: str
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hermes-test/gateway/config.py", "class PlatformConfig: ...\n")
        archive.writestr("hermes-test/gateway/platforms/base.py", base_methods)
        archive.writestr("hermes-test/gateway/session.py", session_source)
        archive.writestr(
            "hermes-test/plugins/platforms/feishu/adapter.py",
            adapter_methods,
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_manifest(tmp_path: Path, archive_hash: str) -> Path:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["archive_sha256"] = archive_hash
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_pinned_manifest_and_dockerfile_use_exact_release() -> None:
    manifest = installer.load_manifest(MANIFEST_PATH)
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert manifest["release_tag"] == "v2026.7.7.2"
    assert manifest["release_version"] == "0.18.2"
    assert manifest["commit_sha"] == "9de9c25f620ff7f1ce0fd5457d596052d5159596"
    assert (
        manifest["archive_sha256"]
        == "4986ef5c422f5855eaa51a104d833d2202ffcfa372bd0f83e3dbb21ae80864d3"
    )
    assert "install_pinned_hermes_upstream.py" in dockerfile
    assert "archive/refs/tags" not in dockerfile
    assert "HERMES_FEISHU_GATEWAY_TAG" not in dockerfile


def test_installer_verifies_archive_and_adapter_contract(tmp_path: Path) -> None:
    archive = tmp_path / "hermes.zip"
    archive_hash = _write_fake_archive(archive)
    manifest = _fake_manifest(tmp_path, archive_hash)
    target = tmp_path / "target"

    installer.install(
        manifest_path=manifest,
        target=target,
        archive_path=archive,
    )

    provenance = json.loads(
        (target / ".dazah-upstream-provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["commit_sha"] == "9de9c25f620ff7f1ce0fd5457d596052d5159596"
    assert provenance["verification"]["required_classes"] == "passed"
    assert provenance["verification"]["required_class_attributes"] == "passed"


def test_installer_rejects_checksum_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "hermes.zip"
    _write_fake_archive(archive)
    manifest = _fake_manifest(tmp_path, "0" * 64)

    with pytest.raises(installer.UpstreamVerificationError, match="checksum mismatch"):
        installer.install(
            manifest_path=manifest,
            target=tmp_path / "target",
            archive_path=archive,
        )


def test_installer_rejects_adapter_contract_drift(tmp_path: Path) -> None:
    archive = tmp_path / "hermes.zip"
    archive_hash = _write_fake_archive(archive, include_send=False)
    manifest = _fake_manifest(tmp_path, archive_hash)

    with pytest.raises(installer.UpstreamVerificationError, match="methods are missing"):
        installer.install(
            manifest_path=manifest,
            target=tmp_path / "target",
            archive_path=archive,
        )
