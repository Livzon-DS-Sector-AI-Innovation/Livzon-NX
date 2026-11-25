import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest


SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dazah_poseidon_executor", SCRIPTS / "poseidon-executor.py")
executor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(executor)


def test_poseidon_executor_advertises_project_operations():
    assert executor.operation({"protocol": 1, "operation": "capabilities"})["operations"] == (
        "status", "deploy", "rollback", "verify",
    )


@pytest.mark.parametrize("action", ["deploy", "rollback"])
def test_poseidon_executor_passes_version_guard_to_existing_deploy_script(action):
    request = {"protocol": 1, "operation": action, "id": str(uuid4()), "version": "v2",
               "expected": "v1", "artifact": "/opt/dazah/releases/v2"}
    process = subprocess.CompletedProcess([], 0, stdout="")
    with patch.object(executor, "deployment", return_value=process) as run:
        assert executor.operation(request) == {}
    run.assert_called_once_with(action + "-if-current", "v2", "/opt/dazah/releases/v2", "180", "v1", timeout=3400)


def test_poseidon_executor_verifies_the_reported_version():
    with patch.object(executor, "deployment", return_value=subprocess.CompletedProcess(
        [], 0, stdout="[dazah-deploy] 验证成功: v1\n",
    )):
        assert executor.operation({"protocol": 1, "operation": "verify", "version": "v1"}) == {
            "version": "v1", "health": "healthy",
        }
        with pytest.raises(ValueError, match="version changed"):
            executor.operation({"protocol": 1, "operation": "verify", "version": "v2"})


@pytest.mark.skipif(shutil.which("flock") is None, reason="requires Linux flock and Bash")
@pytest.mark.parametrize("action", ["deploy", "rollback"])
def test_shared_deploy_entry_rejects_stale_versions_before_a_project_write(tmp_path, action):
    root = tmp_path / "current"
    root.mkdir()
    (root / ".env").write_text("DAZAH_VERSION=v1\n")
    content = (SCRIPTS / "deploy-production-remote.sh").read_text(encoding="utf-8")
    content = content.replace('action="$' + '{1:-}"',
                              'switch_version() { printf "invoked %s\\n" "$1"; }\n'
                              'action="$' + '{1:-}"')
    isolated = tmp_path / "isolated.sh"
    isolated.write_text(content, encoding="utf-8")
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "DAZAH_DEPLOY_ROOT": str(root),
           "DAZAH_DEPLOY_LOCK": str(tmp_path / "lock"), "DAZAH_ALLOW_UNPRIVILEGED": "1"}
    command = ["bash", str(isolated), action + "-if-current", "v2", str(tmp_path), "0"]
    stale = subprocess.run([*command, "old"], env=env, capture_output=True, text=True, timeout=5)
    assert stale.returncode and "当前部署版本已变化" in stale.stderr
    assert "invoked" not in stale.stdout
    current = subprocess.run([*command, "v1"], env=env, capture_output=True, text=True, timeout=5, check=True)
    assert f"invoked {action}" in current.stdout
