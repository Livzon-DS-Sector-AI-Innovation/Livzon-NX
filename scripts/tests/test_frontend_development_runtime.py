import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_docker_frontend_uses_turbopack_development_command() -> None:
    dockerfile = (ROOT / "Dockerfile.dev").read_text(encoding="utf-8")

    assert 'CMD ["pnpm", "dev", "--hostname", "0.0.0.0", "--port", "3000"]' in dockerfile
    assert 'CMD ["pnpm", "dev:webpack", "--hostname", "0.0.0.0", "--port", "3000"]' not in dockerfile


def test_native_launcher_preserves_frontend_cache_unless_reset_is_requested() -> None:
    script = (ROOT / "scripts/dev-native.ps1").read_text(encoding="utf-8")

    assert "[switch]$ResetFrontendCache" in script
    assert "if (-not $ResetCache)" in script
    assert "-ResetCache:$ResetFrontendCache" in script
    assert "Remove-Item -LiteralPath $DevDirectory -Recurse -Force" in script


def test_docker_frontend_reconciles_named_dependency_volume_on_start() -> None:
    compose = (ROOT / "compose.dev.yml").read_text(encoding="utf-8")

    assert "pnpm install --frozen-lockfile --prefer-offline" in compose
    assert "exec pnpm dev:webpack --hostname 0.0.0.0 --port 3000" in compose
    assert "frontend_node_modules:/app/node_modules" in compose


def test_docker_compose_uses_webpack_polling_for_host_source_changes() -> None:
    compose = (ROOT / "compose.dev.yml").read_text(encoding="utf-8")
    assert "WATCHPACK_POLLING: ${WATCHPACK_POLLING:-true}" in compose
    assert "./dazah-frontend:/app" in compose
    assert "exec pnpm dev --hostname" not in compose


def _tool_environment() -> dict[str, str]:
    return {
        key: os.environ[key]
        for key in (
            "PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)",
            "ProgramData", "HOME", "HOMEDRIVE", "HOMEPATH",
        ) if key in os.environ
    }


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker Compose unavailable")
def test_rendered_dev_stack_cannot_start_an_implicit_migration(tmp_path):
    env_file = tmp_path / "synthetic.env"
    env_file.write_text("", encoding="utf-8")
    env = _tool_environment()
    # --env-file controls interpolation; service env_file needs its own override.
    env["DAZAH_ENV_FILE"] = str(env_file)
    result = subprocess.run([
        "docker", "compose", "--env-file", str(env_file), "-f",
        str(ROOT / "compose.dev.yml"), "config", "--no-env-resolution",
        "--format", "json",
    ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, "Synthetic development Compose failed"
    services = json.loads(result.stdout)["services"]
    assert "migrate" not in services
    result = subprocess.run([
        "docker", "compose", "--env-file", str(env_file), "-f",
        str(ROOT / "compose.dev.yml"), "--profile", "migration", "config",
        "--no-env-resolution", "--format", "json",
    ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, "Synthetic migration Compose profile failed"
    services = json.loads(result.stdout)["services"]
    migrate = services["migrate"]
    assert migrate["profiles"] == ["migration"]
    assert migrate["restart"] == "no"
    assert migrate.get("stdin_open", False) is False
    assert migrate["entrypoint"] == [".venv/bin/python", "-m", "app.core.dev_migration"]
    assert migrate["command"] == ["check"]
    assert "migrate" not in services["app"]["depends_on"]
    assert services["app"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert services["app"]["command"][-2:] == ["app.core.dev_migration", "serve"]


def test_native_startup_has_no_unconfirmed_migration_branch() -> None:
    script = (ROOT / "scripts/dev-native.ps1").read_text(encoding="utf-8")
    assert '"alembic", "upgrade"' not in script
    assert '"python", "-m", "app.core.dev_migration", "check"' in script
    assert '@("rm", "--force", "migrate")' in script


def _run_dev_launcher(tmp_path, *, migrate=False, approval=None,
                      legacy="", pending=True):
    shell = shutil.which("pwsh")
    if shell is None:
        pytest.skip("PowerShell unavailable")
    workspace = tmp_path / "workspace"
    (workspace / "scripts").mkdir(parents=True)
    launcher = workspace / "scripts/dev.ps1"
    shutil.copyfile(ROOT / "scripts/dev.ps1", launcher)
    (workspace / ".env.local").write_text("", encoding="utf-8")
    trace = tmp_path / "docker-trace.jsonl"
    plan = {
        "database": "db:5432/development", "current_revision": "old",
        "target_revision": "reviewed", "pending_revisions": ["reviewed"] if pending else [],
        "confirmation": "MIGRATE db:5432/development old reviewed",
    }
    env = _tool_environment()
    env.update(TEST_LAUNCHER=str(launcher), TEST_TRACE=str(trace),
               TEST_PLAN=json.dumps(plan), TEST_LEGACY=legacy,
               TEST_APPROVAL=approval or "", TEST_MIGRATE=str(migrate))
    # Only the OS shell and the launcher execute. Every Docker operation is
    # captured, including the stdin pipe, without any daemon or real env file.
    code = r'''
function global:docker {
  $NativeArguments = @($args | ForEach-Object { [string]$_ })
  Add-Content -LiteralPath $env:TEST_TRACE -Value (ConvertTo-Json -Compress -InputObject @{ args=$NativeArguments })
  $global:LASTEXITCODE = 0
  if ($NativeArguments[0] -eq 'inspect') {
    if ($env:TEST_LEGACY -eq 'running') { 'true' } else { 'false' }
    return
  }
  if ($NativeArguments -contains 'ps') {
    if ($env:TEST_LEGACY) { 'legacy-migrate' }
    return
  }
  if ($NativeArguments[-1] -eq 'plan') { $env:TEST_PLAN; return }
  if ($NativeArguments[-1] -eq 'upgrade') {
    $Approval = @($input) -join "`n"
    Add-Content -LiteralPath $env:TEST_TRACE -Value (ConvertTo-Json -Compress -InputObject @{ stdin=$Approval })
    return
  }
}
$LaunchArguments = @{ NoBuild=$true }
if ($env:TEST_MIGRATE -eq 'True') { $LaunchArguments.Migrate=$true }
if ($env:TEST_APPROVAL) { $LaunchArguments.MigrationApproval=$env:TEST_APPROVAL }
try { & $env:TEST_LAUNCHER @LaunchArguments } catch { exit 1 }
'''
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", code],
        env=env, capture_output=True, text=True, timeout=30,
    )
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8-sig").splitlines()] if trace.exists() else []
    return result, events, plan


def test_default_launcher_removes_legacy_job_without_running_migrations(tmp_path):
    result, events, _ = _run_dev_launcher(tmp_path, legacy="stopped")
    assert result.returncode == 0, result.stderr
    calls = [e["args"] for e in events if "args" in e]
    assert ["rm", "legacy-migrate"] in calls
    assert not any("upgrade" in args or "run" in args for args in calls)
    assert any("up" in args for args in calls)
    assert not any("--volumes" in args or "-v" in args for args in calls)


def test_running_legacy_migration_blocks_start_without_killing_it(tmp_path):
    result, events, _ = _run_dev_launcher(tmp_path, legacy="running")
    assert result.returncode != 0
    calls = [e["args"] for e in events if "args" in e]
    assert not any(args[0] in {"rm", "stop", "kill"} or "up" in args for args in calls)


def test_unconfirmed_migration_never_executes_upgrade(tmp_path):
    result, events, _ = _run_dev_launcher(tmp_path, migrate=True, approval="wrong")
    assert result.returncode != 0
    assert not any("upgrade" in event.get("args", []) for event in events)


def test_noninteractive_migration_without_confirmation_is_refused(tmp_path):
    result, events, _ = _run_dev_launcher(tmp_path, migrate=True)
    assert result.returncode != 0
    assert not any("upgrade" in event.get("args", []) for event in events)


def test_confirmed_migration_uses_ephemeral_stdin_and_removes_its_container(tmp_path):
    phrase = "MIGRATE db:5432/development old reviewed"
    result, events, _ = _run_dev_launcher(tmp_path, migrate=True, approval=phrase)
    assert result.returncode == 0, result.stderr
    call = next(event["args"] for event in events if "upgrade" in event.get("args", []))
    assert call[-6:] == ["run", "--rm", "--no-deps", "-T", "migrate", "upgrade"]
    assert "--rm" in call and "-T" in call and "--no-deps" in call
    assert any("--wait" in event.get("args", []) for event in events)
    assert phrase not in call
    assert {"stdin": phrase} in events
    assert any(event.get("args", [])[-2:] == ["migrate", "check"] for event in events)


def test_already_current_database_needs_no_confirmation_or_upgrade(tmp_path):
    result, events, _ = _run_dev_launcher(tmp_path, migrate=True, pending=False)
    assert result.returncode == 0, result.stderr
    assert not any("upgrade" in event.get("args", []) for event in events)


def test_approval_without_explicit_migration_intent_is_refused(tmp_path):
    result, events, _ = _run_dev_launcher(tmp_path, approval="stale-approval")
    assert result.returncode != 0
    assert not events
