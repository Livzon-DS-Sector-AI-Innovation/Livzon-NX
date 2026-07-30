#!/usr/bin/env python3
"""Install and verify the exact Hermes upstream release used by Dazah."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any


class UpstreamVerificationError(RuntimeError):
    """Raised when pinned upstream provenance or source validation fails."""


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required_strings = (
        "repository",
        "release_tag",
        "release_version",
        "tag_object_sha",
        "commit_sha",
        "archive_sha256",
        "adapter_path",
    )
    for key in required_strings:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise UpstreamVerificationError(f"manifest field is missing: {key}")
    for key in ("tag_object_sha", "commit_sha", "archive_sha256"):
        expected_length = 64 if key == "archive_sha256" else 40
        if not re.fullmatch(rf"[0-9a-f]{{{expected_length}}}", data[key]):
            raise UpstreamVerificationError(f"manifest field is invalid: {key}")
    if not isinstance(data.get("required_files"), list) or not data["required_files"]:
        raise UpstreamVerificationError("manifest required_files must not be empty")
    if not isinstance(data.get("required_classes"), dict):
        raise UpstreamVerificationError("manifest required_classes must be an object")
    if not isinstance(data.get("required_class_attributes"), dict):
        raise UpstreamVerificationError(
            "manifest required_class_attributes must be an object"
        )
    return data


def archive_url(manifest: dict[str, Any]) -> str:
    repository = str(manifest["repository"]).rstrip("/")
    return f"{repository}/archive/{manifest['commit_sha']}.zip"


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
        raise UpstreamVerificationError(
            f"upstream checksum mismatch: expected {expected}, got {actual}"
        )


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def extract_archive(path: Path, target: Path) -> None:
    if target.exists() and any(target.iterdir()):
        raise UpstreamVerificationError(f"target directory is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if not members:
            raise UpstreamVerificationError("upstream archive is empty")
        roots = {
            PurePosixPath(info.filename).parts[0]
            for info in members
            if PurePosixPath(info.filename).parts
        }
        if len(roots) != 1:
            raise UpstreamVerificationError("upstream archive has an invalid root")
        root = next(iter(roots))

        for info in members:
            member = PurePosixPath(info.filename)
            if (
                not member.parts
                or member.parts[0] != root
                or member.is_absolute()
                or ".." in member.parts
                or _is_zip_symlink(info)
            ):
                raise UpstreamVerificationError(
                    f"unsafe upstream archive member: {info.filename}"
                )
            relative = PurePosixPath(*member.parts[1:])
            if not relative.parts or info.is_dir():
                continue
            destination = target.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def _class_methods(source_path: Path) -> dict[str, set[str]]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    result: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        result[node.name] = {
            child.name
            for child in node.body
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
        }
    return result


def _class_attributes(source_path: Path) -> dict[str, set[str]]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    result: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        attributes = {
            child.target.id
            for child in node.body
            if isinstance(child, ast.AnnAssign)
            and isinstance(child.target, ast.Name)
        }
        attributes.update(
            target.id
            for child in node.body
            if isinstance(child, ast.Assign)
            for target in child.targets
            if isinstance(target, ast.Name)
        )
        result[node.name] = attributes
    return result


def verify_source_tree(target: Path, manifest: dict[str, Any]) -> None:
    for relative in manifest["required_files"]:
        source_path = target / str(relative)
        if not source_path.is_file():
            raise UpstreamVerificationError(
                f"required upstream file is missing: {relative}"
            )

    for relative, class_contracts in manifest["required_classes"].items():
        source_path = target / str(relative)
        classes = _class_methods(source_path)
        for class_name, required_methods in class_contracts.items():
            actual_methods = classes.get(class_name)
            if actual_methods is None:
                raise UpstreamVerificationError(
                    f"required upstream class is missing: {relative}:{class_name}"
                )
            missing = sorted(set(required_methods) - actual_methods)
            if missing:
                raise UpstreamVerificationError(
                    "required upstream methods are missing: "
                    f"{relative}:{class_name}:{','.join(missing)}"
                )

    for relative, class_contracts in manifest["required_class_attributes"].items():
        source_path = target / str(relative)
        classes = _class_attributes(source_path)
        for class_name, required_attributes in class_contracts.items():
            actual_attributes = classes.get(class_name)
            if actual_attributes is None:
                raise UpstreamVerificationError(
                    f"required upstream class is missing: {relative}:{class_name}"
                )
            missing = sorted(set(required_attributes) - actual_attributes)
            if missing:
                raise UpstreamVerificationError(
                    "required upstream attributes are missing: "
                    f"{relative}:{class_name}:{','.join(missing)}"
                )


def write_verified_provenance(target: Path, manifest: dict[str, Any]) -> None:
    output = {
        **manifest,
        "source_archive_url": archive_url(manifest),
        "verified_at": datetime.now(UTC).isoformat(),
        "verification": {
            "archive_sha256": "passed",
            "required_files": "passed",
            "required_classes": "passed",
            "required_class_attributes": "passed",
        },
    }
    (target / ".dazah-upstream-provenance.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def install(
    *,
    manifest_path: Path,
    target: Path,
    archive_path: Path | None = None,
) -> None:
    manifest = load_manifest(manifest_path)
    with tempfile.TemporaryDirectory(prefix="dazah-hermes-upstream-") as temp_dir:
        resolved_archive = archive_path or Path(temp_dir) / "hermes-upstream.zip"
        if archive_path is None:
            urllib.request.urlretrieve(archive_url(manifest), resolved_archive)
        verify_archive(resolved_archive, manifest)
        extract_archive(resolved_archive, target)
    verify_source_tree(target, manifest)
    write_verified_provenance(target, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    install(
        manifest_path=args.manifest,
        target=args.target,
        archive_path=args.archive,
    )


if __name__ == "__main__":
    main()
