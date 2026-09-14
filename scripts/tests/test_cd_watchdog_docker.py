"""Opt-in recovery test with a disposable development container, never production."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest

SPEC = importlib.util.spec_from_file_location(
    "watchdog_controller", Path(__file__).parents[1] / "cd" / "controller.py"
)
cd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cd)


@pytest.mark.skipif(os.environ.get("DAZAH_DOCKER_TESTS") != "1", reason="opt-in Docker recovery drill")
def test_real_unhealthy_container_restart_budget(tmp_path, monkeypatch):
    """Real Docker restart/stop; dependency health and elapsed cooldown are fixtures."""
    name = "dazah-watchdog-dev-" + uuid.uuid4().hex[:10]

    def docker(*args):
        return subprocess.check_output(["docker", *args], text=True, timeout=45).strip()

    def inspect():
        return json.loads(docker("inspect", name))[0]

    def wait_unhealthy():
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if inspect()["State"]["Health"]["Status"] == "unhealthy":
                return
            time.sleep(.25)
        pytest.fail("isolated fixture did not become unhealthy")

    control = cd.Controller({"data_root": str(tmp_path), "current": str(tmp_path),
                             "state_dir": str(tmp_path / "state")})

    def inventory():
        result = {s: {"state": "running", "health": "healthy"} for s in (*cd.DEPS, *cd.APPS)}
        item = inspect()
        result["app"] = {"id": item["Id"], "state": item["State"]["Status"],
                         "health": item["State"]["Health"]["Status"],
                         "restarts": item["RestartCount"]}
        return result

    monkeypatch.setattr(control, "containers", inventory)
    docker("run", "-d", "--pull=never", "--name", name, "--network", "none",
           "--label", "dazah.role=isolated-test", "--memory", "64m", "--memory-swap", "64m",
           "--cpus", ".25", "--pids-limit", "32", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--restart", "unless-stopped",
           "--health-cmd", "exit 1", "--health-interval", "1s", "--health-timeout", "1s",
           "--health-retries", "1", "--health-start-period", "0s",
           "dazah/frontend:cd-verify-dev", "sleep", "600")
    try:
        for attempt in range(3):
            wait_unhealthy()
            before = inspect()["State"]["StartedAt"]
            # Advance only persisted cooldown timestamps. Docker lifecycle remains real.
            path = control.state_dir / "watchdog.json"
            records = cd.read_json(path, {})
            if records:
                records["app"]["attempts"] = [time.time() - 61] * attempt
                cd.atomic_json(path, records)
            for _ in range(3):
                control.watchdog()
            assert inspect()["State"]["StartedAt"] != before
            records = cd.read_json(path)
            assert len(records["app"]["attempts"]) == attempt + 1
            assert not records["app"]["blocked"]

        wait_unhealthy()
        for _ in range(3):
            control.watchdog()
        item = inspect()
        assert item["State"]["Status"] == "exited"
        assert item["HostConfig"]["RestartPolicy"]["Name"] == "no"
        assert (control.state_dir / "public" / "maintenance").exists()
        assert cd.read_json(control.state_dir / "watchdog.json")["app"]["blocked"]
        # Further inspections must not resurrect the exhausted service.
        control.maintenance(False)
        control.watchdog()
        assert inspect()["State"]["Status"] == "exited"
        events = [json.loads(line)["event"] for line in
                  (control.state_dir / "events.jsonl").read_text().splitlines()]
        assert events.count("application_restarted") == 3
        assert events.count("recovery_budget_exhausted") == 1
    finally:
        docker("rm", "-f", name)
