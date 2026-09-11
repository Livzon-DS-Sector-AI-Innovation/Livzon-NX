"""Safety boundaries of the single-host controller, without a live Docker daemon."""
import contextlib
import datetime as dt
import importlib.util
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).parents[1] / "cd" / "controller.py"
SPEC = importlib.util.spec_from_file_location("cd_controller", PATH)
cd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cd)


def evidence():
    candidate = {"sha": "a" * 40, "repository": "org/repo", "run_id": 1}
    branch = {"commit": {"sha": candidate["sha"]}, "protected": True}
    run = {"head_sha": candidate["sha"], "head_branch": "main", "event": "push",
           "path": ".github/workflows/ci.yml", "repository": {"full_name": "org/repo"},
           "conclusion": "success"}
    return candidate, branch, run, [{"name": "CI Gate", "conclusion": "success"}]


def test_successful_protected_main():
    assert cd.validate_candidate(*evidence()) == "a" * 40


@pytest.mark.parametrize("change", ["pr", "branch", "old", "unprotected", "missing", "failure", "cancelled", "foreign"])
def test_reject_untrusted_or_unverified_candidate(change):
    candidate, branch, run, jobs = evidence()
    if change == "pr":
        run["event"] = "pull_request"
    elif change == "branch":
        run["head_branch"] = "dev"
    elif change == "old":
        branch["commit"]["sha"] = "b" * 40
    elif change == "unprotected":
        branch["protected"] = False
    elif change == "missing":
        jobs.clear()
    elif change == "foreign":
        run["repository"]["full_name"] = "other/repo"
    else:
        jobs[0]["conclusion"] = change
    with pytest.raises(cd.Refused):
        cd.validate_candidate(candidate, branch, run, jobs)


@pytest.mark.parametrize("hour,minute,allowed,switch", [(1, 59, False, False), (2, 0, True, False), (4, 30, False, True), (4, 59, True, False), (5, 0, False, False)])
def test_shanghai_window(hour, minute, allowed, switch):
    now = dt.datetime(2026, 9, 9, hour, minute, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    assert cd.in_window(now, switch=switch) is allowed


def test_disabled_scheduler_never_contacts_docker_or_github(tmp_path, monkeypatch):
    control = cd.Controller({"data_root": str(tmp_path), "current": str(tmp_path), "state_dir": str(tmp_path / "state"), "enabled": False})
    monkeypatch.setattr(cd, "command", lambda *a, **k: pytest.fail("unexpected operation"))
    control.schedule()
    assert "deployment_disabled" in (control.state_dir / "events.jsonl").read_text()


@pytest.mark.parametrize("case", ["valid", "wrong_uuid", "stacked", "missing", "subdirectory", "wrong_device", "not_block"])
def test_effective_data_mount_identity(tmp_path, monkeypatch, case):
    control = cd.Controller({"data_root": "/data/dazah", "data_uuid": "expected", "current": str(tmp_path), "state_dir": str(tmp_path)})
    mount = {"target": "/data", "source": "/dev/sdb1", "fstype": "ext4", "uuid": "expected", "fsroot": "/"}
    mounts = [mount]
    if case == "wrong_uuid":
        mount["uuid"] = "other"
    elif case == "stacked":
        mounts.append({"target": "/data", "source": "tmpfs", "fstype": "tmpfs", "uuid": None, "fsroot": "/"})
    elif case == "missing":
        mounts = []
    elif case == "subdirectory":
        mount["fsroot"] = "/another-directory"
    def mount_inventory(args, **kwargs):
        if "--json" in args:
            return json.dumps({"filesystems": mounts})
        return "\n".join(item.get("uuid") or "" for item in mounts).strip()

    monkeypatch.setattr(cd, "command", mount_inventory)
    original_stat, original_resolve = Path.stat, Path.resolve

    def mount_stat(path, *args, **kwargs):
        if path == Path("/data"):
            return SimpleNamespace(st_dev=123)
        if path == Path("/dev/sdb1"):
            return SimpleNamespace(st_rdev=456 if case == "wrong_device" else 123,
                                   st_mode=stat.S_IFREG if case == "not_block" else stat.S_IFBLK)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", mount_stat)
    monkeypatch.setattr(Path, "resolve", lambda path, *a, **k: path if path == Path("/data/dazah") else original_resolve(path, *a, **k))
    if case == "valid":
        control.mount_check()
    else:
        with pytest.raises(cd.Refused, match="UUID or effective mount"):
            control.mount_check()


def test_malformed_mount_inventory_fails_closed(tmp_path, monkeypatch):
    control = cd.Controller({"data_root": "/data/dazah", "data_uuid": "expected", "current": str(tmp_path), "state_dir": str(tmp_path)})
    monkeypatch.setattr(cd, "command", lambda *a, **k: "wrong-disk")
    with pytest.raises(cd.Refused, match="UUID or effective mount"):
        control.mount_check()


def test_ssh_build_proxy_checks_tunnel_and_scopes_worker_arguments(monkeypatch):
    requests = []

    def open_request(request, timeout):
        requests.append((request.full_url, request.get_method(), timeout))
        return contextlib.nullcontext(SimpleNamespace(status=200))

    opener = SimpleNamespace(open=open_request)
    handlers = []
    monkeypatch.setattr(cd.urllib.request, "build_opener", lambda handler: handlers.append(handler) or opener)
    result, args = cd.build_network(True)
    assert result is opener
    assert handlers[0].proxies == {"http": "http://127.0.0.1:17897", "https": "http://127.0.0.1:17897"}
    assert requests == [("https://github.com/", "HEAD", 10)]
    assert args == [item for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
                    for item in ("--opt", f"build-arg:{name}=http://127.0.0.1:17898")]


def test_disabled_build_proxy_does_not_probe_network(monkeypatch):
    opener = SimpleNamespace(open=lambda *a, **k: pytest.fail("unexpected network probe"))
    monkeypatch.setattr(cd.urllib.request, "build_opener", lambda: opener)
    assert cd.build_network(False) == (opener, [])


@pytest.mark.parametrize("value", ["true", 1, None])
def test_build_proxy_rejects_non_boolean_settings(value):
    with pytest.raises(cd.Refused, match="boolean"):
        cd.build_network(value)


def test_unavailable_ssh_proxy_leaves_no_partial_build_directory(tmp_path, monkeypatch):
    control = cd.Controller({"data_root": str(tmp_path), "current": str(tmp_path),
                             "state_dir": str(tmp_path / "state"), "ssh_build_proxy": True})
    sha = "a" * 40
    monkeypatch.setattr(control, "verify_candidate", lambda candidate: sha)
    monkeypatch.setattr(control, "mount_check", lambda: None)
    monkeypatch.setattr(cd.shutil, "disk_usage", lambda path: SimpleNamespace(free=100 * 1024**3))
    original_read = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda path, *a, **k: "MemAvailable: 4194304 kB" if path == Path("/proc/meminfo") else original_read(path, *a, **k))

    def unavailable(*args, **kwargs):
        raise OSError("private connection details must not escape")

    monkeypatch.setattr(cd.urllib.request, "build_opener", lambda *args: SimpleNamespace(open=unavailable))
    with pytest.raises(cd.Refused, match="SSH build proxy unavailable; postpone build"):
        control.build({"sha": sha})
    assert not (tmp_path / "work" / sha).exists()
    assert not control.state_file.exists()


def test_maintenance_prevents_watchdog_interference(tmp_path, monkeypatch):
    control = cd.Controller({"data_root": str(tmp_path), "current": str(tmp_path), "state_dir": str(tmp_path)})
    cd.atomic_json(control.state_file, {"phase": "migrating"})
    monkeypatch.setattr(cd, "command", lambda *a, **k: pytest.fail("must not restart during migration"))
    control.watchdog()


def test_digest_and_atomic_state(tmp_path):
    target = tmp_path / "state.json"
    cd.atomic_json(target, {"phase": "backup"})
    assert cd.read_json(target)["phase"] == "backup"
    first = cd.digest(target)
    cd.atomic_json(target, {"phase": "migrating"})
    assert cd.digest(target) != first


@pytest.mark.parametrize("entry", ["../escape", "/absolute", "symlink"])
def test_restore_archive_rejects_unsafe_members(tmp_path, monkeypatch, entry):
    import tarfile
    archive = tmp_path / "backup.tar.gz"
    with tarfile.open(archive, "w:gz") as package:
        item = tarfile.TarInfo(entry)
        if entry == "symlink":
            item.type = tarfile.SYMTYPE
            item.linkname = "/etc"
        package.addfile(item)
    monkeypatch.setattr(cd, "command", lambda *a, **kw: pytest.fail("unsafe archive must never be extracted"))
    with pytest.raises(cd.Refused, match="unsafe"):
        cd.restore_archive(archive, tmp_path / "restored")


def deployment_control(tmp_path, monkeypatch):
    current = tmp_path / "current"
    current.mkdir()
    control = cd.Controller({"data_root": str(tmp_path), "current": str(current), "state_dir": str(tmp_path / "state")})
    monkeypatch.setattr(cd, "command", lambda *a, **k: "sha256:" + "a" * 64)
    monkeypatch.setattr(control, "containers", lambda: {s: {"id": s, "state": "running", "health": "healthy"} for s in (*cd.APPS, *cd.DEPS)})
    monkeypatch.setattr(control, "mount_check", lambda: None)
    from types import SimpleNamespace
    monkeypatch.setattr(cd.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3))
    monkeypatch.setattr(control, "drain", lambda: None)
    monkeypatch.setattr(control, "wait_ready", lambda **kw: None)
    monkeypatch.setattr(control, "revision", lambda: "old")
    monkeypatch.setattr(control, "backup", lambda kind: tmp_path / "backup")
    manifest = {"site_files": {}, "images": {s: "sha256:" + "b" * 64 for s in (*cd.APPS, "migrate")},
                "migration": {"from_revision": "old", "to_revision": "new", "backward_compatible": True}}
    return control, manifest


def test_site_configuration_drift_refuses_before_maintenance(tmp_path, monkeypatch):
    control, manifest = deployment_control(tmp_path, monkeypatch)
    (control.current / "compose.yml").write_text("services: {}")
    monkeypatch.setattr(control, "compose", lambda *a, **kw: pytest.fail("configuration drift must fail before writes"))
    with pytest.raises(cd.Refused, match="configuration changed"):
        control.deploy("a" * 40, manifest)
    assert not (control.state_dir / "public" / "maintenance").exists()


def test_edbo_must_be_retired_during_attended_commissioning(tmp_path, monkeypatch):
    control, manifest = deployment_control(tmp_path, monkeypatch)
    monkeypatch.setattr(control, "containers", lambda: {"edbo-service": {"state": "running"}})
    with pytest.raises(cd.Refused, match="retire EDBO"):
        control.deploy("a" * 40, manifest)
    assert not (control.state_dir / "public" / "maintenance").exists()


def test_backup_failure_restores_apps_before_reopening(tmp_path, monkeypatch):
    control, manifest = deployment_control(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(control, "compose", lambda *a, **kw: calls.append(a))
    monkeypatch.setattr(control, "backup", lambda kind: (_ for _ in ()).throw(cd.Refused("backup failed")))
    with pytest.raises(cd.Refused, match="backup failed"):
        control.deploy("a" * 40, manifest)
    assert cd.read_json(control.state_file)["phase"] == "aborted_before_migration"
    assert not (control.state_dir / "public" / "maintenance").exists()
    assert not any("upgrade" in args for args in calls)
    assert ("up", "-d", "--no-deps", "--force-recreate", "nginx") in calls


def test_migration_failure_keeps_maintenance_and_never_restarts_old_apps(tmp_path, monkeypatch):
    control, manifest = deployment_control(tmp_path, monkeypatch)
    cd.atomic_json(control.state_file, {"traffic_opened": True})
    calls = []
    def compose(*args, **kwargs):
        calls.append(args)
        if "upgrade" in args:
            raise cd.Refused("migration failed")
        return ""
    monkeypatch.setattr(control, "compose", compose)
    with pytest.raises(cd.Refused, match="migration failed"):
        control.deploy("a" * 40, manifest)
    assert cd.read_json(control.state_file)["phase"] == "recovery_required"
    assert cd.read_json(control.state_file)["traffic_opened"] is False
    assert (control.state_dir / "public" / "maintenance").exists()
    assert not any(args[0] == "up" for args in calls)


def test_compatible_migration_start_failure_rolls_back_images_and_gateway(tmp_path, monkeypatch):
    control, manifest = deployment_control(tmp_path, monkeypatch)
    revisions = iter(["old", "new"])
    monkeypatch.setattr(control, "revision", lambda: next(revisions))
    calls = []
    failed = False
    def compose(*args, **kwargs):
        nonlocal failed
        calls.append(args)
        if args == ("up", "-d", "--no-deps", "app") and not failed:
            failed = True
            raise cd.Refused("new image startup failed")
        return ""
    monkeypatch.setattr(control, "compose", compose)
    with pytest.raises(cd.Refused, match="startup failed"):
        control.deploy("a" * 40, manifest)
    assert cd.read_json(control.state_file)["phase"] == "application_rolled_back"
    assert not (control.state_dir / "public" / "maintenance").exists()
    overlay = cd.read_json(control.current / "compose.release.yml")
    assert overlay["services"]["app"]["image"] == "sha256:" + "a" * 64
    assert ("up", "-d", "--no-deps", "--force-recreate", "nginx") in calls
    assert sum("upgrade" in args for args in calls) == 1
    assert ("run", "--rm", "--no-deps", "migrate", ".venv/bin/alembic", "upgrade", "new") in calls
    assert not any("downgrade" in args for args in calls)


def test_dependency_failure_stops_build_without_restarting_services(tmp_path, monkeypatch):
    control, _ = deployment_control(tmp_path, monkeypatch)
    inventory = {s: {"state": "running", "health": "healthy", "id": s} for s in (*cd.DEPS, *cd.APPS)}
    inventory["db"]["health"] = "unhealthy"
    monkeypatch.setattr(control, "containers", lambda: inventory)
    calls = []
    monkeypatch.setattr(cd, "command", lambda args, **kw: calls.append(args) or "")
    control.watchdog()
    assert calls == [["systemctl", "stop", "dazah-build.service"]]


def test_missing_migration_approval_does_not_quiesce(tmp_path, monkeypatch):
    control, manifest = deployment_control(tmp_path, monkeypatch)
    manifest["migration"]["backward_compatible"] = False
    monkeypatch.setattr(control, "compose", lambda *a, **kw: pytest.fail("must not stop applications"))
    with pytest.raises(cd.Refused, match="approved"):
        control.deploy("a" * 40, manifest)
    assert not (control.state_dir / "public" / "maintenance").exists()


def test_stopped_application_is_not_restarted_by_watchdog(tmp_path, monkeypatch):
    control, _ = deployment_control(tmp_path, monkeypatch)
    inventory = {s: {"state": "running", "health": "healthy", "id": s} for s in cd.DEPS}
    inventory.update({s: {"state": "exited", "health": "unhealthy", "id": s} for s in cd.APPS})
    monkeypatch.setattr(control, "containers", lambda: inventory)
    monkeypatch.setattr(cd, "command", lambda *a, **kw: pytest.fail("manual stop must be respected"))
    control.watchdog()


def test_watchdog_recovers_one_service_and_observes_budget(tmp_path, monkeypatch):
    control, _ = deployment_control(tmp_path, monkeypatch)
    inventory = {s: {"state": "running", "health": "healthy", "id": s} for s in (*cd.DEPS, *cd.APPS)}
    inventory["app"]["health"] = "unhealthy"
    monkeypatch.setattr(control, "containers", lambda: inventory)
    now = [1000.0]
    monkeypatch.setattr(cd.time, "time", lambda: now[0])
    calls = []
    monkeypatch.setattr(cd, "command", lambda args, **kw: calls.append(args) or "")
    for _ in range(3):
        for _ in range(3):
            control.watchdog()
        now[0] += 61
    assert len([a for a in calls if a[:2] == ["docker", "restart"]]) == 3
    for _ in range(3):
        control.watchdog()
    assert ["docker", "update", "--restart=no", "app"] in calls
    assert (control.state_dir / "public" / "maintenance").exists()
    assert cd.read_json(control.state_dir / "watchdog.json")["app"]["blocked"]


def test_recovered_service_is_not_stopped_at_restart_budget(tmp_path, monkeypatch):
    control, _ = deployment_control(tmp_path, monkeypatch)
    inventory = {s: {"state": "running", "health": "healthy", "id": s} for s in (*cd.DEPS, *cd.APPS)}
    monkeypatch.setattr(control, "containers", lambda: inventory)
    monkeypatch.setattr(cd.time, "time", lambda: 1000)
    cd.atomic_json(control.state_dir / "watchdog.json", {"app": {"failures": 0, "attempts": [900, 930, 960], "blocked": False}})
    monkeypatch.setattr(cd, "command", lambda *a, **kw: pytest.fail("recovered app must stay running"))
    control.watchdog()
    assert not (control.state_dir / "public" / "maintenance").exists()


def test_reboot_during_observation_requires_review(tmp_path, monkeypatch):
    control, _ = deployment_control(tmp_path, monkeypatch)
    control.config["enabled"] = True
    cd.atomic_json(control.state_file, {"phase": "observing", "traffic_opened": True})
    monkeypatch.setattr(cd, "in_window", lambda *a, **kw: True)
    monkeypatch.setattr(cd, "command", lambda *a, **kw: pytest.fail("must not resume interrupted release"))
    with pytest.raises(cd.Refused, match="interrupted"):
        control.schedule()


@pytest.mark.skipif(not hasattr(cd.os, "O_NOFOLLOW"), reason="Linux candidate file safety")
def test_late_old_ci_cannot_replace_current_main_candidate(tmp_path, monkeypatch):
    control, _ = deployment_control(tmp_path, monkeypatch)
    control.config["enabled"] = True
    monkeypatch.setattr(cd, "in_window", lambda *a, **kw: True)
    monkeypatch.setattr(cd, "CANDIDATES", tmp_path)
    current_sha = "b" * 40
    cd.atomic_json(tmp_path / (current_sha + ".json"), {"sha": current_sha, "run_id": 2})
    cd.atomic_json(tmp_path / ("a" * 40 + ".json"), {"sha": "a" * 40, "run_id": 1})
    monkeypatch.setattr(control, "github", lambda _: {"commit": {"sha": current_sha}})
    monkeypatch.setattr(control, "verify_candidate", lambda item: item["sha"])
    selected = []
    def build(candidate):
        selected.append(candidate["sha"])
        raise cd.Refused("stop before real build")
    monkeypatch.setattr(control, "build", build)
    with pytest.raises(cd.Refused, match="stop before real build"):
        control.schedule()
    assert selected == [current_sha]


def test_retention_preserves_recovery_points_and_unfinished_backups(tmp_path, monkeypatch):
    control, _ = deployment_control(tmp_path, monkeypatch)
    monkeypatch.setattr(control, "mount_check", lambda: None)
    root = tmp_path / "backups"
    root.mkdir()
    paths = []
    for day in range(1, 16):
        path = root / f"daily-202609{day:02d}T010000Z"
        path.mkdir()
        cd.atomic_json(path / "manifest.json", {"kind": "daily", "files": {}})
        paths.append(path)
    unfinished = root / "daily-20260801T010000Z"
    unfinished.mkdir()
    cd.atomic_json(control.state_file, {"backup": str(paths[0])})
    control.prune_backups()
    assert paths[0].exists() and unfinished.exists()
    assert all(path.exists() for path in paths[-7:])
    assert not paths[1].exists()


def test_complete_backup_references_protect_old_release(tmp_path, monkeypatch):
    control, _ = deployment_control(tmp_path, monkeypatch)
    monkeypatch.setattr(control, "mount_check", lambda: None)
    root = tmp_path / "releases"
    root.mkdir()
    releases = []
    for index in range(5):
        path = root / (str(index) * 40)
        path.mkdir()
        cd.atomic_json(path / "success.json", {"completed": index})
        cd.atomic_json(path / "manifest.json", {"images": {"app": "sha256:" + str(index) * 64}})
        releases.append(path)
    cd.atomic_json(tmp_path / "backups" / "daily-test" / "manifest.json", {"images": {"app": "sha256:" + "0" * 64}})
    monkeypatch.setattr(cd.subprocess, "run", lambda *a, **kw: None)
    control.prune_releases()
    assert releases[0].exists()
    assert not releases[1].exists()
    assert all(path.exists() for path in releases[-3:])


def test_migration_hold_keeps_destructive_head_unapplied():
    policy = {"deployment_hold": {"source_head": "drop", "target_revision": "keep",
              "allowed_from_revisions": ["old", "keep"], "review_reference": "review"}}
    assert cd.migration_target(policy, "drop", "old") == "keep"
    assert cd.migration_target(policy, "drop", "keep") == "keep"
    for source, before in [("later", "old"), ("drop", "drop"), ("drop", "unknown")]:
        with pytest.raises(cd.Refused):
            cd.migration_target(policy, source, before)
    policy["deployment_hold"]["review_reference"] = ""
    with pytest.raises(cd.Refused):
        cd.migration_target(policy, "drop", "old")


def oci_fixture(tmp_path, architecture="amd64", manifest_digest=None):
    import hashlib
    import json
    root = tmp_path / "inputs"
    layout = root / "node"
    blobs = layout / "blobs" / "sha256"
    blobs.mkdir(parents=True)
    def blob(value):
        data = json.dumps(value).encode()
        checksum = hashlib.sha256(data).hexdigest()
        (blobs / checksum).write_bytes(data)
        return {"digest": "sha256:" + checksum, "size": len(data)}
    config = blob({"architecture": architecture, "os": "linux"})
    layer = blob({"fixture": "not executable"})
    manifest = blob({"schemaVersion": 2, "config": config, "layers": [layer]})
    if manifest_digest:
        manifest["digest"] = manifest_digest
    manifest["platform"] = {"os": "linux", "architecture": architecture}
    index = blob({"schemaVersion": 2, "manifests": [manifest]})
    cd.atomic_json(layout / "oci-layout", {"imageLayoutVersion": "1.0.0"})
    ref = "node:20-alpine@" + index["digest"]
    return root, {"images": {ref: "node"}}, ref, blobs / layer["digest"][7:]


def test_offline_oci_preserves_pinned_digest_without_registry_substitution(tmp_path):
    root, policy, ref, _ = oci_fixture(tmp_path)
    args = cd.offline_context_args({ref}, policy, root)
    expected = "oci-layout://dazah-cache-0@" + ref.split("@", 1)[1]
    assert f"context:{ref}={expected}" in args
    assert f"context:docker.io/library/{ref}={expected}" in args
    assert f"dazah-cache-0={root / 'node'}" in args


@pytest.mark.parametrize("failure", ["missing", "traversal", "tamper", "incomplete", "mutable", "layout"])
def test_offline_cache_fails_closed(tmp_path, failure):
    root, policy, ref, layer = oci_fixture(tmp_path)
    if failure == "missing":
        policy["images"].clear()
    elif failure == "traversal":
        policy["images"][ref] = "../outside"
    elif failure == "tamper":
        layer.write_text("changed")
    elif failure == "incomplete":
        layer.unlink()
    elif failure == "mutable":
        ref = "node:latest"
    else:
        cd.atomic_json(root / "node" / "oci-layout", {"imageLayoutVersion": "0"})
    with pytest.raises(cd.Refused):
        cd.offline_context_args({ref}, policy, root)


@pytest.mark.parametrize("options", [{"architecture": "arm64"}, {"manifest_digest": "../../outside"}])
def test_offline_cache_rejects_wrong_platform_and_manifest_traversal(tmp_path, options):
    root, policy, ref, _ = oci_fixture(tmp_path, **options)
    with pytest.raises(cd.Refused, match="incomplete|platform"):
        cd.offline_context_args({ref}, policy, root)


@pytest.mark.parametrize("uid,mode,symlink", [(1002, 0o600, False), (0, 0o666, False), (0, 0o640, True)])
def test_offline_policy_rejects_untrusted_ownership(uid, mode, symlink):
    from types import SimpleNamespace
    path = SimpleNamespace(stat=lambda: SimpleNamespace(st_uid=uid, st_mode=mode),
                           is_symlink=lambda: symlink)
    with pytest.raises(cd.Refused, match="root-owned"):
        cd.root_readonly(path)


def test_without_migration_hold_target_is_source_head():
    assert cd.migration_target({}, "head_revision", "old") == "head_revision"
