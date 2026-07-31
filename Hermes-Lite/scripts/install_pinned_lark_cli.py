#!/usr/bin/env python3
"""Install the exact lark-cli binary without an OS package-manager dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class LarkCliVerificationError(RuntimeError):
    """Raised when the pinned lark-cli artifact cannot be verified."""


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "package",
        "version",
        "npm_tarball",
        "npm_integrity",
        "archive_name",
        "archive_sha256",
    ):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise LarkCliVerificationError(f"manifest field is missing: {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", data["archive_sha256"]):
        raise LarkCliVerificationError("manifest archive_sha256 is invalid")
    urls = data.get("download_urls")
    if not isinstance(urls, list) or not urls:
        raise LarkCliVerificationError("manifest download_urls must not be empty")
    allowed_hosts = {
        "github.com",
        "objects.githubusercontent.com",
        "registry.npmmirror.com",
    }
    for url in urls:
        parsed = urllib.parse.urlparse(str(url))
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            raise LarkCliVerificationError(f"download URL is not allowed: {url}")
    return data


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
            urllib.request.urlretrieve(str(url), path)
            return str(url)
        except (OSError, urllib.error.URLError) as exc:
            failures.append(f"{urllib.parse.urlparse(str(url)).hostname}: {exc}")
    raise LarkCliVerificationError(
        "all pinned lark-cli download sources failed: " + "; ".join(failures)
    )


def extract_binary(archive_path: Path, target: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        candidates = [
            member
            for member in members
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
        if member.size <= 0 or member.size > 200 * 1024 * 1024:
            raise LarkCliVerificationError("lark-cli binary size is invalid")
        source = archive.extractfile(member)
        if source is None:
            raise LarkCliVerificationError("lark-cli binary cannot be extracted")
        target.parent.mkdir(parents=True, exist_ok=True)
        with source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
    target.chmod(0o755)


def install(
    *,
    manifest_path: Path,
    target: Path,
    archive_path: Path | None = None,
) -> dict[str, str]:
    manifest = load_manifest(manifest_path)
    with tempfile.TemporaryDirectory(prefix="dazah-lark-cli-") as temp_dir:
        resolved_archive = archive_path or Path(temp_dir) / manifest["archive_name"]
        source_url = (
            "provided-archive"
            if archive_path is not None
            else download_archive(resolved_archive, manifest)
        )
        verify_archive(resolved_archive, manifest)
        extract_binary(resolved_archive, target)
    return {
        "version": str(manifest["version"]),
        "archive_sha256": str(manifest["archive_sha256"]),
        "source": source_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    result = install(
        manifest_path=args.manifest,
        target=args.target,
        archive_path=args.archive,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
