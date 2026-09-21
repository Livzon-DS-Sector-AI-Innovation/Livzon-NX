import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


HARNESS = r"""
param(
  [string]$TestScript,
  [string]$TestReleaseRoot,
  [string]$TestCommandLog,
  [string]$TestReuseFrom,
  [switch]$TestBuildProxy,
  [switch]$TestFailSave
)
$ErrorActionPreference = 'Stop'
function docker {
  $commandArgs = @($args | ForEach-Object { [string]$_ })
  ConvertTo-Json -InputObject $commandArgs -Compress |
    Add-Content -LiteralPath $TestCommandLog -Encoding utf8
  $global:LASTEXITCODE = 0
  if ($args[0] -eq 'buildx' -and $args[1] -eq 'ls') {
    'dazah-builder'
  }
  if ($args[0] -eq 'save') {
    if ($TestFailSave) {
      $global:LASTEXITCODE = 17
      return
    }
    $outputIndex = [array]::IndexOf($args, '-o')
    if ($outputIndex -lt 0) { throw 'docker save requires an output path' }
    [IO.File]::WriteAllText($args[$outputIndex + 1], 'fake image archive')
  }
}
function ssh { throw 'Tests must not connect to a remote server' }
function scp { throw 'Tests must not upload files' }
$extra = @{}
if ($TestReuseFrom) { $extra.ReuseUnchangedFrom = $TestReuseFrom }
if ($TestBuildProxy) { $extra.BuildProxy = 'http://build-proxy.test:3128' }
& $TestScript Build -Version test-release -ReleaseRoot $TestReleaseRoot `
  -SkipUpload -SkipDeploy @extra
exit $LASTEXITCODE
"""


def run_package(
    tmp_path: Path,
    *,
    reuse: bool = False,
    build_proxy: bool = False,
    fail_save: bool = False,
):
    shell = shutil.which("pwsh")
    assert shell, "PowerShell 7 is required to verify the deployment script"
    harness = tmp_path / "package-harness.ps1"
    harness.write_text(HARNESS, encoding="utf-8")
    log = tmp_path / "docker-commands.jsonl"
    release_root = tmp_path / "release"
    command = [
        shell, "-NoProfile", "-NonInteractive", "-File", str(harness),
        "-TestScript", str(ROOT / "scripts/deploy-production.ps1"),
        "-TestReleaseRoot", str(release_root), "-TestCommandLog", str(log),
    ]
    if reuse:
        command += ["-TestReuseFrom", "previous-release"]
    if build_proxy:
        command += ["-TestBuildProxy"]
    if fail_save:
        command += ["-TestFailSave"]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        cwd=tmp_path,
    )
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8-sig").splitlines()]
    return result, calls, release_root / "test-release"


@pytest.mark.parametrize("reuse", [False, True], ids=["complete", "reuse-hermes"])
def test_release_exports_exactly_the_images_built_for_this_version(tmp_path: Path, reuse: bool) -> None:
    result, calls, release = run_package(tmp_path, reuse=reuse)
    assert result.returncode == 0, result.stderr
    targets = ["backend", "frontend"] + ([] if reuse else ["hermes"])
    images = ["dazah/backend:test-release", "dazah/frontend:test-release"]
    if not reuse:
        images.append("dazah/hermes-lite:test-release")
    bakes = [call for call in calls if call[:2] == ["buildx", "bake"]]
    assert len(bakes) == 1
    bake = bakes[0]
    assert bake[:6] == [
        "buildx",
        "bake",
        "--builder",
        "dazah-builder",
        "--file",
        str(ROOT / "docker-bake.hcl"),
    ]
    assert "--load" in bake
    bake_sets = [bake[index + 1] for index, value in enumerate(bake) if value == "--set"]
    assert bake_sets == [
        f"{target}.tags={image}"
        for target, image in zip(targets, images, strict=True)
    ]
    assert bake[-len(targets):] == targets
    archive = release / "dazah-test-release.tar"
    exports = [call for call in calls if call[0] == "save"]
    assert exports == [["save", *images, "-o", str(archive)]]
    assert calls.index(bake) < calls.index(exports[0])
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.with_suffix(".tar.sha256").read_text() == f"{digest}  {archive.name}"
    assert (release / "compose.yml").read_bytes() == (ROOT / "compose.yml").read_bytes()
    assert "__PUBLIC_HOST__" not in (release / "nginx.default.conf").read_text()
    assert (release / "deploy-production.sh").is_file()


def test_export_failure_does_not_produce_a_valid_release(tmp_path: Path) -> None:
    result, calls, release = run_package(tmp_path, fail_save=True)
    assert result.returncode != 0
    assert "docker save" in result.stderr
    assert calls[-1][0] == "save"
    assert not (release / "dazah-test-release.tar.sha256").exists()
    assert not (release / "compose.yml").exists()


def test_dockerignore_keeps_storage_source_module() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "**/storage" not in dockerignore
    assert "/dazah-backend/storage/" in dockerignore
    assert "**/.venv-*" in dockerignore
    assert "**/*.tsbuildinfo" in dockerignore
    assert "**/playwright-report" in dockerignore
    assert "**/test-results" in dockerignore


def test_build_proxy_is_forwarded_to_all_bake_targets(tmp_path: Path) -> None:
    result, calls, _ = run_package(tmp_path, build_proxy=True)
    assert result.returncode == 0, result.stderr
    bake = next(call for call in calls if call[:2] == ["buildx", "bake"])
    bake_sets = [bake[index + 1] for index, value in enumerate(bake) if value == "--set"]
    assert "*.args.HTTP_PROXY=http://build-proxy.test:3128" in bake_sets
    assert "*.args.HTTPS_PROXY=http://build-proxy.test:3128" in bake_sets
    assert "*.args.NO_PROXY=localhost,127.0.0.1" in bake_sets
    assert "*.args.no_proxy=localhost,127.0.0.1" in bake_sets


def test_production_dockerfile_pins_bases_and_mounts_dependency_caches() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "python:3.12-slim-bookworm@sha256:" in dockerfile
    assert "node:20-alpine@sha256:" in dockerfile
    assert "id=dazah-debian-apt,target=/var/cache/apt" in dockerfile
    assert "id=dazah-backend-uv,target=/home/app/.cache/uv" in dockerfile
    assert "id=dazah-frontend-pnpm,target=/root/.local/share/pnpm/store" in dockerfile
    assert "id=dazah-frontend-next,target=/app/.next/cache" in dockerfile
    assert "id=dazah-hermes-uv,target=/root/.cache/uv" in dockerfile


def test_production_bake_file_builds_all_release_targets() -> None:
    bake_file = (ROOT / "docker-bake.hcl").read_text(encoding="utf-8")

    assert 'targets = ["backend", "frontend", "hermes"]' in bake_file
    for target in ("backend", "frontend", "hermes"):
        assert f'target     = "{target}"' in bake_file
        assert 'platforms  = ["linux/amd64"]' in bake_file


def test_buildkit_cache_policy_keeps_dependency_caches_longer() -> None:
    config = (ROOT / "docker" / "buildkitd.toml").read_text(encoding="utf-8")
    deploy_script = (ROOT / "scripts" / "deploy-production.ps1").read_text(encoding="utf-8")

    assert 'type==exec.cachemount' in config
    assert 'keepDuration = "720h"' in config
    assert 'maxUsedSpace = "20GB"' in config
    assert 'keepDuration = "1440h"' in config
    assert '--buildkitd-config' in deploy_script
    assert '--keep-state' in deploy_script
