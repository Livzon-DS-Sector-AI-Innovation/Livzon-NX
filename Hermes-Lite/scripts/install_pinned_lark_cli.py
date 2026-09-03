#!/usr/bin/env python3
"""Install the exact lark-cli binary without an OS package-manager dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


class LarkCliVerificationError(RuntimeError):
    """Raised when the pinned lark-cli artifact cannot be verified."""


def current_platform_key() -> str:
    system = platform.system().lower()
    system_names = {"darwin": "darwin", "linux": "linux", "windows": "windows"}
    machine = platform.machine().lower()
    machine_names = {
        "amd64": "amd64",
        "x86_64": "amd64",
        "arm64": "arm64",
        "aarch64": "arm64",
        "riscv64": "riscv64",
    }
    if system not in system_names or machine not in machine_names:
        raise LarkCliVerificationError(
            f"unsupported lark-cli platform: {system or 'unknown'}-{machine or 'unknown'}"
        )
    return f"{system_names[system]}-{machine_names[machine]}"


def load_manifest(path: Path, *, platform_key: str | None = None) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("package", "version", "npm_tarball", "npm_integrity"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise LarkCliVerificationError(f"manifest field is missing: {key}")

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise LarkCliVerificationError("manifest artifacts must not be empty")
    selected_platform = platform_key or current_platform_key()
    artifact = artifacts.get(selected_platform)
    if not isinstance(artifact, dict):
        raise LarkCliVerificationError(
            f"manifest has no lark-cli artifact for {selected_platform}"
        )
    for key in ("archive_name", "archive_sha256"):
        if not isinstance(artifact.get(key), str) or not artifact[key].strip():
            raise LarkCliVerificationError(f"manifest artifact field is missing: {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", artifact["archive_sha256"]):
        raise LarkCliVerificationError("manifest archive_sha256 is invalid")

    templates = data.get("download_url_templates")
    if not isinstance(templates, list) or not templates:
        raise LarkCliVerificationError(
            "manifest download_url_templates must not be empty"
        )
    urls: list[str] = []
    allowed_hosts = {
        "github.com",
        "objects.githubusercontent.com",
        "registry.npmmirror.com",
    }
    for template in templates:
        if not isinstance(template, str):
            raise LarkCliVerificationError("manifest download URL template is invalid")
        try:
            url = template.format(
                version=data["version"], archive_name=artifact["archive_name"]
            )
        except (KeyError, ValueError) as exc:
            raise LarkCliVerificationError(
                "manifest download URL template is invalid"
            ) from exc
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            raise LarkCliVerificationError(f"download URL is not allowed: {url}")
        urls.append(url)

    return {
        **data,
        **artifact,
        "platform": selected_platform,
        "download_urls": urls,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path, manifest: dict[str, Any]) -> None:
    actual = sha256_file(path)
    expected = str(manifest["archive_sha256"])
    if actual != expected:
        raise LarkCliVerificationError(
            f"lark-cli checksum mismatch: expected {expected}, got {actual}"
        )


def download_archive(path: Path, manifest: dict[str, Any]) -> str:
    failures: list[str] = []
    for url in manifest["download_urls"]:
        try:
            with urllib.request.urlopen(str(url), timeout=30) as response:
                with path.open("wb") as output:
                    shutil.copyfileobj(response, output)
            return str(url)
        except (OSError, urllib.error.URLError) as exc:
            failures.append(f"{urllib.parse.urlparse(str(url)).hostname}: {exc}")
    raise LarkCliVerificationError(
        "all pinned lark-cli download sources failed: " + "; ".join(failures)
    )


def _copy_binary(source: Any, target: Path, *, size: int) -> None:
    if size <= 0 or size > 200 * 1024 * 1024:
        raise LarkCliVerificationError("lark-cli binary size is invalid")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging_path: Path | None = None
    try:
        with source, tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}-",
            suffix=".partial",
            dir=target.parent,
            delete=False,
        ) as output:
            staging_path = Path(output.name)
            shutil.copyfileobj(source, output)
        staging_path.chmod(0o755)
        staging_path.replace(target)
    finally:
        if staging_path is not None and staging_path.exists():
            staging_path.unlink()


def extract_binary(archive_path: Path, target: Path, *, archive_name: str) -> None:
    if archive_name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as archive:
            candidates = [
                member
                for member in archive.infolist()
                if not member.is_dir()
                and member.filename.rstrip("/").split("/")[-1] == "lark-cli.exe"
            ]
            if len(candidates) != 1:
                raise LarkCliVerificationError(
                    "lark-cli archive must contain exactly one regular binary"
                )
            member = candidates[0]
            source = archive.open(member)
            _copy_binary(source, target, size=member.file_size)
        return

    if not archive_name.endswith(".tar.gz"):
        raise LarkCliVerificationError("lark-cli archive format is unsupported")
    with tarfile.open(archive_path, "r:gz") as archive:
        candidates = [
            member
            for member in archive.getmembers()
            if member.name.rstrip("/").split("/")[-1] == "lark-cli"
            and member.isfile()
            and not member.issym()
            and not member.islnk()
        ]
        if len(candidates) != 1:
            raise LarkCliVerificationError(
                "lark-cli archive must contain exactly one regular binary"
            )
        member = candidates[0]
        source = archive.extractfile(member)
        if source is None:
            raise LarkCliVerificationError("lark-cli binary cannot be extracted")
        _copy_binary(source, target, size=member.size)


def install(
    *,
    manifest_path: Path,
    target: Path,
    archive_path: Path | None = None,
    platform_key: str | None = None,
) -> dict[str, str]:
    manifest = load_manifest(manifest_path, platform_key=platform_key)
    with tempfile.TemporaryDirectory(prefix="dazah-lark-cli-") as temp_dir:
        resolved_archive = archive_path or Path(temp_dir) / manifest["archive_name"]
        source_url = (
            "provided-archive"
            if archive_path is not None
            else download_archive(resolved_archive, manifest)
        )
        verify_archive(resolved_archive, manifest)
        extract_binary(
            resolved_archive,
            target,
            archive_name=str(manifest["archive_name"]),
        )
    return {
        "version": str(manifest["version"]),
        "archive_sha256": str(manifest["archive_sha256"]),
        "platform": str(manifest["platform"]),
        "source": source_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--platform")
    args = parser.parse_args()
    result = install(
        manifest_path=args.manifest,
        target=args.target,
        archive_path=args.archive,
        platform_key=args.platform,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
