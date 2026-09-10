#!/usr/bin/env python3
"""Root-owned single-host CD controller. Never execute scripts from a release.

Configuration: /etc/dazah-cd/config.json (root-owned, not writable by runner).
The runner's candidate is a hint only; GitHub provenance is rechecked here.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from zoneinfo import ZoneInfo

APPS = ("app", "hermes-lite", "frontend")
DEPS = ("db", "redis", "minio")
UNSAFE_PHASES = {"quiescing", "backup", "migrating", "starting", "verifying", "observing", "recovery_required"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
CANDIDATES = Path("/var/lib/dazah-candidates")


class Refused(RuntimeError):
    """A safety precondition was not met; leave the existing deployment alone."""


def command(args: list[str], *, timeout: int = 60, output=None, input_data=None) -> str:
    result = subprocess.run(args, input=input_data, stdout=output or subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.returncode:
        # Do not include command arguments, stderr, URLs or config in public logs.
        raise Refused(f"operation failed: {Path(args[0]).name}, exit={result.returncode}")
    return result.stdout.decode().strip() if output is None else ""


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        os.chmod(temp, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def restore_archive(archive: Path, target: Path) -> None:
    """Restore only inside a new root-private drill directory, never into live volumes."""
    target.mkdir(mode=0o700)
    with tarfile.open(archive) as package:
        for member in package:
            destination = target / member.name
            if (Path(member.name).is_absolute() or not destination.resolve().is_relative_to(target.resolve())
                    or not (member.isfile() or member.isdir())):
                raise Refused("unsupported or unsafe backup archive entry")
    command(["tar", "-xzf", str(archive), "-C", str(target), "--no-same-owner", "--no-same-permissions"], timeout=600)


def in_window(now: dt.datetime, *, switch: bool = False) -> bool:
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    minute = local.hour * 60 + local.minute
    return 120 <= minute < (270 if switch else 300)


def migration_target(policy: dict, source_head: str, before: str) -> str:
    """A reviewed temporary hold never stamps or downgrades a database."""
    hold = policy.get("deployment_hold")
    if hold is None:
        return source_head
    target = hold.get("target_revision", "")
    if (hold.get("source_head") != source_head
            or not re.fullmatch(r"[A-Za-z0-9_]+", target)
            or target == source_head or not hold.get("review_reference")
            or before not in hold.get("allowed_from_revisions", [])):
        raise Refused("deployment migration hold requires renewed review")
    return target


def validate_candidate(candidate: dict, branch: dict, run: dict, jobs: list[dict]) -> str:
    sha = candidate.get("sha", "")
    if not SHA.fullmatch(sha):
        raise Refused("invalid candidate SHA")
    if branch.get("commit", {}).get("sha") != sha or not branch.get("protected"):
        raise Refused("candidate is not the current protected main")
    if (run.get("head_sha") != sha or run.get("head_branch") != "main"
            or run.get("event") != "push" or run.get("path") != ".github/workflows/ci.yml"
            or run.get("repository", {}).get("full_name") != candidate.get("repository")
            or run.get("conclusion") not in (None, "success")):
        raise Refused("CI provenance mismatch")
    gates = [job for job in jobs if job.get("name") == "CI Gate"]
    if len(gates) != 1 or gates[0].get("conclusion") != "success":
        raise Refused("CI Gate did not succeed")
    if any(job.get("conclusion") in ("failure", "cancelled", "timed_out")
           for job in jobs if job.get("name") != "Frontend Flaky Quarantine"):
        raise Refused("CI has a failed required job")
    return sha


class Controller:
    def __init__(self, config: dict):
        self.config = config
        self.data = Path(config["data_root"])
        self.current = Path(config["current"])
        self.state_dir = Path(config.get("state_dir", "/var/lib/dazah-cd"))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "public").mkdir(exist_ok=True)
        os.chmod(self.state_dir / "public", 0o755)
        self.state_file = self.state_dir / "state.json"

    def event(self, kind: str, **fields) -> None:
        value = {"time": dt.datetime.now(dt.timezone.utc).isoformat(), "event": kind,
                 "remote_alert": "not_enabled", "external_backup": "not_enabled", **fields}
        # Host state stays on SSD, so mount failures remain observable.
        with (self.state_dir / "events.jsonl").open("a") as handle:
            handle.write(json.dumps(value) + "\n")
        print(json.dumps(value), flush=True)

    def phase(self, name: str, **fields) -> None:
        previous = read_json(self.state_file, {})
        atomic_json(self.state_file, {**previous, **fields, "phase": name})
        self.event("phase", phase=name)

    def mount_check(self) -> None:
        actual = command(["findmnt", "-n", "-o", "UUID", "--mountpoint", "/data"])
        if not self.config.get("data_uuid") or actual != self.config["data_uuid"]:
            raise Refused("data disk UUID mismatch")
        if self.data.resolve() != Path("/data/dazah"):
            raise Refused("unexpected data root")

    def compose(self, *args: str, timeout=180, output=None) -> str:
        files = ["compose.yml", "compose.edge.yml", "compose.single-host.yml", "compose.release.yml"]
        argv = ["docker", "compose", "--project-name", "dazah", "--env-file", str(self.current / ".env")]
        for name in files:
            if (self.current / name).exists():
                argv += ["-f", str(self.current / name)]
        return command(argv + list(args), timeout=timeout, output=output)

    def maintenance(self, active: bool) -> None:
        marker = self.state_dir / "public" / "maintenance"
        if active:
            marker.touch(mode=0o600)
            # nginx runs unprivileged inside its container; marker contains no data.
            os.chmod(marker, 0o644)
        else:
            marker.unlink(missing_ok=True)

    def wait_ready(self, timeout=180) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            inventory = self.containers()
            if all(self.healthy(inventory.get(s, {})) for s in (*DEPS, *APPS, "nginx")):
                self.compose("exec", "-T", "db", "sh", "-c", 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"')
                self.compose("exec", "-T", "redis", "redis-cli", "ping")
                self.compose("exec", "-T", "minio", "curl", "-fsS", "http://127.0.0.1:9000/minio/health/ready")
                self.compose("exec", "-T", "nginx", "nginx", "-t")
                self.compose("exec", "-T", "nginx", "wget", "-q", "--spider", "http://frontend:3000/login")
                probe = Path(__file__).with_name("readiness.py").read_text()
                self.compose("exec", "-T", "app", ".venv/bin/python", "-c", probe, timeout=20)
                return
            time.sleep(5)
        raise Refused("application readiness timeout")

    def drain(self) -> None:
        end = time.monotonic() + 120
        while time.monotonic() < end:
            status = self.compose("exec", "-T", "nginx", "wget", "-qO-", "http://127.0.0.1:8089/status")
            match = re.search(r"Reading:\s+(\d+) Writing:\s+(\d+)", status)
            if match and sum(map(int, match.groups())) <= 1:
                return
            time.sleep(3)
        raise Refused("active requests did not drain")

    def revision(self) -> str:
        # Only schema revision is returned; no connection settings or row data.
        return self.compose("exec", "-T", "db", "sh", "-c",
                            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select version_num from alembic_version order by version_num"')

    def release_overlay(self, images: dict) -> None:
        if set(images) != {"app", "frontend", "hermes-lite", "migrate"}:
            raise Refused("incomplete application image set")
        for image in images.values():
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
                raise Refused("image must be pinned by local content ID")
        atomic_json(self.current / "compose.release.yml", {"services": {
            service: {"image": image, "pull_policy": "never"} for service, image in images.items()}})

    def site_checksums(self) -> dict:
        names = ("compose.yml", "compose.edge.yml", "compose.single-host.yml", ".env", "nginx.default.conf")
        return {name: digest(self.current / name) for name in names if (self.current / name).is_file()}

    def deploy(self, sha: str, manifest: dict) -> None:
        self.mount_check()
        if shutil.disk_usage("/").free < 20 * 1024**3 or shutil.disk_usage(self.data).free < 50 * 1024**3:
            raise Refused("disk headroom insufficient for release switch")
        if manifest.get("site_files") != self.site_checksums():
            raise Refused("site configuration changed since validation")
        prior_state = read_json(self.state_file, {})
        before = self.revision()
        migration = manifest.get("migration", {})
        if migration.get("from_revision") != before or not migration.get("to_revision"):
            raise Refused("migration baseline changed since validation")
        changed = before != migration["to_revision"]
        if changed and migration.get("backward_compatible") is not True:
            raise Refused("migration not approved for unattended deployment")
        previous = {}
        inventory = self.containers()
        if "edbo-service" in inventory:
            raise Refused("first commissioning must retire EDBO before unattended deployment")
        if not all(self.healthy(inventory.get(s, {})) for s in (*DEPS, *APPS)):
            raise Refused("existing deployment is not healthy; refusing upgrade")
        for service in APPS:
            previous[service] = command(["docker", "inspect", "--format", "{{.Image}}", inventory[service]["id"]])
        previous["migrate"] = previous["app"]
        atomic_json(self.state_dir / "previous-images.json", previous)
        self.phase("quiescing", candidate_sha=sha, previous_revision=before, traffic_opened=False)
        self.maintenance(True)
        migrated = False
        try:
            self.drain()
            self.compose("stop", "--timeout", "120", "hermes-lite", "app", "frontend", timeout=400)
            self.phase("backup")
            backup = self.backup("predeploy")
            self.phase("backup", backup=str(backup))
            self.release_overlay(manifest["images"])
            self.compose("config", "--quiet")
        except Exception:
            self.release_overlay(previous)
            self.compose("up", "-d", "--no-deps", *APPS)
            self.compose("up", "-d", "--no-deps", "--force-recreate", "nginx")
            self.wait_ready()
            self.maintenance(False)
            self.phase("aborted_before_migration", traffic_opened=True)
            raise
        try:
            self.phase("migrating")
            self.compose("run", "--rm", "--no-deps", "migrate", ".venv/bin/alembic", "upgrade", migration["to_revision"], timeout=300)
            if self.revision() != migration["to_revision"]:
                raise Refused("migration revision verification failed")
            migrated = True
            self.phase("starting")
            for service in APPS:
                self.compose("up", "-d", "--no-deps", service)
            self.compose("up", "-d", "--no-deps", "--force-recreate", "nginx")
            self.phase("verifying")
            self.wait_ready()
        except Exception:
            if migrated and (not changed or migration.get("backward_compatible") is True):
                self.release_overlay(previous)
                self.compose("up", "-d", "--no-deps", *APPS)
                self.compose("up", "-d", "--no-deps", "--force-recreate", "nginx")
                self.wait_ready()
                self.maintenance(False)
                self.phase("application_rolled_back", traffic_opened=True)
            else:
                self.phase("recovery_required")
            raise
        self.maintenance(False)
        self.phase("observing", traffic_opened=True)
        try:
            for _ in range(10):
                command(["curl", "-fsS", "--max-time", "10", "http://127.0.0.1/health"])
                command(["curl", "-fsS", "--max-time", "10", "http://127.0.0.1/login"])
                self.wait_ready(timeout=15)
                time.sleep(30)
        except Exception:
            # Never restore an old database after new writes have been admitted.
            self.phase("recovery_required", traffic_opened=True)
            self.maintenance(True)
            raise
        self.phase("success", successful_sha=sha,
                   previous_successful_sha=prior_state.get("successful_sha"),
                   previous_backup=prior_state.get("backup"), traffic_opened=True)
        atomic_json(self.data / "releases" / sha / "success.json", {"completed": time.time()})
        self.prune_releases()

    def prune_releases(self) -> None:
        self.mount_check()
        root = self.data / "releases"
        state = read_json(self.state_file, {})
        completed = [p for p in root.iterdir() if SHA.fullmatch(p.name) and not p.is_symlink()
                     and (p / "success.json").is_file() and (p / "manifest.json").is_file()]
        completed.sort(key=lambda p: read_json(p / "success.json")["completed"], reverse=True)
        protected = {state.get("successful_sha"), state.get("previous_successful_sha")}
        keep = set(completed[:3]) | {p for p in completed if p.name in protected}
        backup_images = set()
        for manifest_path in (self.data / "backups").glob("*/manifest.json"):
            if not manifest_path.parent.is_symlink():
                backup_images.update(read_json(manifest_path).get("images", {}).values())
        keep.update(p for p in completed if set(read_json(p / "manifest.json")["images"].values()) & backup_images)
        kept_images = {image for p in keep for image in read_json(p / "manifest.json")["images"].values()}
        for path in completed:
            if path in keep:
                continue
            if path.resolve().parent != root.resolve():
                raise Refused("release cleanup escaped root")
            old_images = set(read_json(path / "manifest.json")["images"].values()) - kept_images
            for image in old_images:
                if re.fullmatch(r"sha256:[a-f0-9]{64}", image):
                    # No force: Docker refuses images referenced by any container/tag.
                    subprocess.run(["docker", "image", "rm", image], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=30)
            shutil.rmtree(path)
            self.event("expired_release_removed", sha=path.name)

    def containers(self) -> dict:
        ids = command(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=dazah"]).split()
        result = {}
        for cid in ids:
            # Select only non-secret fields; never read Config.Env.
            value = command(["docker", "inspect", "--format",
                             '{"name":{{json .Name}},"state":{{json .State.Status}},'
                             '"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}"none"{{end}},'
                             '"restarts":{{.RestartCount}},"service":{{json (index .Config.Labels "com.docker.compose.service")}}}', cid])
            item = json.loads(value)
            result[item["service"]] = {**item, "id": cid}
        return result

    @staticmethod
    def healthy(item: dict) -> bool:
        return item.get("state") == "running" and item.get("health") in ("healthy", "none")

    def backup(self, kind="daily") -> Path:
        self.mount_check()
        if shutil.disk_usage(self.data).free < 10 * 1024**3:
            raise Refused("backup disk space insufficient")
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.data / "backups" / f"{kind}-{stamp}"
        target.mkdir(parents=True, mode=0o700)
        inventory = self.containers()
        if not all(self.healthy(inventory.get(s, {})) for s in DEPS):
            raise Refused("backup dependencies not ready")
        with (target / "database.dump").open("wb") as handle:
            command(["docker", "exec", inventory["db"]["id"], "sh", "-c",
                     'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
                    timeout=600, output=handle)
        # Use a Redis-generated snapshot; copying live AOF files alone is not a restore point.
        redis_snapshot = f"/tmp/dazah-cd-{stamp}.rdb"
        try:
            command(["docker", "exec", inventory["redis"]["id"], "redis-cli", "--rdb", redis_snapshot], timeout=300)
            command(["docker", "cp", f"{inventory['redis']['id']}:{redis_snapshot}", str(target / "redis.rdb")], timeout=120)
        finally:
            command(["docker", "exec", inventory["redis"]["id"], "rm", "-f", redis_snapshot])
        # Persistent file stores. Online copies are explicitly not a cross-store snapshot.
        volumes: list[str] = []
        for service in ("app", "hermes-lite", "minio", "redis"):
            if service not in inventory:
                raise Refused("persistent service missing")
            mounts = json.loads(command(["docker", "inspect", "--format", "{{json .Mounts}}", inventory[service]["id"]]))
            for mount in mounts:
                if mount["Type"] == "volume" and mount["Source"] not in volumes:
                    source = Path(mount["Source"])
                    if not source.is_relative_to("/var/lib/docker/volumes"):
                        raise Refused("unrecognized volume location")
                    volumes.append(str(source))
                    command(["tar", "-czf", str(target / f"{mount['Name']}.tar.gz"),
                             "-C", str(source), "."], timeout=600)
        command(["tar", "-czf", str(target / "config.tar.gz"), "-C", str(self.current), "."], timeout=120)
        files = {p.name: digest(p) for p in target.iterdir() if p.is_file()}
        if not (target / "database.dump").stat().st_size:
            raise Refused("empty database backup")
        atomic_json(target / "manifest.json", {"kind": kind, "files": files,
                    "database_revision": self.revision(),
                    "consistency": "writers_stopped" if kind == "predeploy" else "online_independent_copies",
                    "images": {s: command(["docker", "inspect", "--format", "{{.Image}}", inventory[s]["id"]]) for s in (*APPS, *DEPS)},
                    "external": False})
        self.event("backup_complete", backup=target.name)
        self.prune_backups()
        return target

    def prune_backups(self) -> None:
        """Remove only completed backups under the checked data mount."""
        self.mount_check()
        root = self.data / "backups"
        state = read_json(self.state_file, {})
        protected = {state.get("backup"), state.get("previous_backup")}
        daily = sorted((p for p in root.glob("daily-*") if not p.is_symlink()
                        and (p / "manifest.json").is_file()), reverse=True)
        before = sorted((p for p in root.glob("predeploy-*") if not p.is_symlink()
                         and (p / "manifest.json").is_file()), reverse=True)
        weeks = {}
        for path in daily:
            try:
                date = dt.datetime.strptime(path.name[6:14], "%Y%m%d").date()
            except ValueError:
                continue
            weeks.setdefault(date.isocalendar()[:2], path)
        keep = set(daily[:7] + list(weeks.values())[:4] + before[:3])
        for path in (*daily, *before):
            if path in keep or str(path) in protected:
                continue
            if path.resolve().parent != root.resolve():
                raise Refused("backup cleanup escaped root")
            shutil.rmtree(path)
            self.event("expired_backup_removed", backup=path.name)

    def drill(self) -> None:
        self.mount_check()
        backups = sorted((p for p in (self.data / "backups").glob("daily-*")
                          if not p.is_symlink() and (p / "manifest.json").is_file()), reverse=True)
        if not backups:
            raise Refused("no completed daily backup available")
        backup = backups[0]
        manifest = read_json(backup / "manifest.json")
        for name, expected in manifest["files"].items():
            if Path(name).name != name or (backup / name).is_symlink() or digest(backup / name) != expected:
                raise Refused("backup checksum failed")
        name = "dazah-cd-drill-dev"
        command(["docker", "run", "-d", "--name", name, "--network", "none", "--memory", "384m", "--cpus", ".5",
                 "--tmpfs", "/var/lib/postgresql/data:rw,size=512m", "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:17"])
        start = time.monotonic()
        try:
            for _ in range(30):
                try:
                    command(["docker", "exec", name, "pg_isready", "-U", "postgres"])
                    break
                except Refused:
                    time.sleep(1)
            with (backup / "database.dump").open("rb") as handle:
                result = subprocess.run(["docker", "exec", "-i", name, "pg_restore", "-U", "postgres", "-d", "postgres",
                                         "--no-owner", "--no-privileges", "--exit-on-error"],
                                        stdin=handle, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=600)
                if result.returncode:
                    raise Refused("database restore drill failed")
            count = command(["docker", "exec", name, "psql", "-U", "postgres", "-Atc",
                             "select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema')"])
            if int(count) < 1:
                raise Refused("restore produced no application tables")
            if manifest.get("database_revision"):
                restored_revision = command(["docker", "exec", name, "psql", "-U", "postgres", "-Atc",
                                             "select version_num from alembic_version order by version_num"])
                if restored_revision != manifest["database_revision"]:
                    raise Refused("restored database revision mismatch")
            drill_root = self.data / "backups" / ".drills"
            drill_root.mkdir(mode=0o700, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="restore-", dir=drill_root) as directory:
                archives = [n for n in manifest["files"] if n.endswith(".tar.gz")]
                for index, filename in enumerate(archives):
                    restore_archive(backup / filename, Path(directory) / str(index))
            redis_verified = False
            if "redis.rdb" in manifest["files"]:
                redis_name = "dazah-cd-redis-drill-dev"
                command(["docker", "run", "-d", "--name", redis_name, "--network", "none", "--user", "0",
                         "--memory", "192m", "--cpus", ".25", "--cap-drop", "ALL",
                         "-v", f"{backup / 'redis.rdb'}:/data/dump.rdb:ro", "redis:8-alpine",
                         "redis-server", "--appendonly", "no", "--save", ""])
                try:
                    for _ in range(30):
                        try:
                            if command(["docker", "exec", redis_name, "redis-cli", "ping"]) == "PONG":
                                redis_verified = True
                                break
                        except Refused:
                            pass
                        time.sleep(1)
                    if not redis_verified:
                        raise Refused("Redis restore did not become ready")
                finally:
                    command(["docker", "rm", "-f", redis_name])
            self.event("restore_drill_passed", backup=backup.name, archives_restored=len(archives),
                       redis_restored=redis_verified, seconds=round(time.monotonic() - start, 1))
        finally:
            command(["docker", "rm", "-f", name])

    def github(self, suffix: str) -> dict:
        repo = self.config["repository"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise Refused("invalid repository")
        request = urllib.request.Request(f"https://api.github.com/repos/{repo}/{suffix}",
                                         headers={"Accept": "application/vnd.github+json", "User-Agent": "dazah-cd"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)

    def verify_candidate(self, candidate: dict) -> str:
        if candidate.get("repository") != self.config["repository"]:
            raise Refused("wrong repository")
        run_id = candidate.get("run_id")
        if not isinstance(run_id, int) or run_id <= 0:
            raise Refused("invalid CI run ID")
        branch = self.github("branches/main")
        run = self.github(f"actions/runs/{run_id}")
        jobs, page = [], 1
        while True:
            batch = self.github(f"actions/runs/{run_id}/jobs?per_page=100&page={page}")
            jobs.extend(batch["jobs"])
            if len(jobs) >= batch["total_count"]:
                break
            page += 1
            if page > 10:
                raise Refused("CI job inventory too large")
        return validate_candidate(candidate, branch, run, jobs)

    def watchdog(self) -> None:
        state = read_json(self.state_file, {})
        if state.get("phase") in UNSAFE_PHASES or (self.state_dir / "public" / "maintenance").exists():
            return
        inventory = self.containers()
        if not all(self.healthy(inventory.get(s, {})) for s in DEPS):
            command(["systemctl", "stop", "dazah-build.service"])
            self.event("dependency_unhealthy")
            return
        path = self.state_dir / "watchdog.json"
        records = read_json(path, {})
        now = time.time()
        for service in APPS:
            item = inventory.get(service, {})
            record = records.setdefault(service, {"failures": 0, "attempts": [], "blocked": False})
            record["attempts"] = [t for t in record["attempts"] if now - t < 900]
            # Stopped/missing containers are operator-owned decisions, not recoverable probes.
            if item.get("state") not in ("running", "restarting") or record["blocked"]:
                continue
            restarts = item.get("restarts", 0)
            delta = max(0, restarts - record.get("docker_restarts", restarts))
            record["docker_restarts"] = restarts
            record["attempts"].extend([now] * min(delta, 3))
            record["failures"] = 0 if self.healthy(item) else record["failures"] + 1
            if len(record["attempts"]) >= 3 and (record["failures"] >= 3 or item.get("state") == "restarting"):
                self.maintenance(True)
                command(["docker", "update", "--restart=no", item["id"]])
                command(["docker", "stop", "--time", "30", item["id"]])
                record["blocked"] = True
                self.event("recovery_budget_exhausted", service=service)
                continue
            if record["failures"] >= 3 and (not record["attempts"] or now - record["attempts"][-1] >= 60):
                command(["docker", "restart", "--time", "30", item["id"]])
                record["attempts"].append(now)
                record["failures"] = 0
                self.event("application_restarted", service=service)
        atomic_json(path, records)

    def schedule(self) -> None:
        if not self.config.get("enabled"):
            self.event("deployment_disabled_pending_acceptance")
            return
        if not in_window(dt.datetime.now(dt.timezone.utc)):
            raise Refused("outside maintenance window")
        if read_json(self.state_file, {}).get("phase") in UNSAFE_PHASES:
            raise Refused("interrupted deployment requires operator recovery")
        self.mount_check()
        current_sha = self.github("branches/main").get("commit", {}).get("sha", "")
        if not SHA.fullmatch(current_sha):
            raise Refused("invalid main revision from GitHub")
        source = CANDIDATES / f"{current_sha}.json"
        if not source.exists():
            self.event("waiting_for_current_main_candidate")
            return
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd) as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                raise Refused("invalid candidate file")
            candidate = json.loads(handle.read(4097))
        sha = self.verify_candidate(candidate)
        if read_json(self.state_file, {}).get("successful_sha") == sha:
            return
        # Acceptance marker is root-owned and produced only after isolated release validation.
        release = self.data / "releases" / sha
        if not (release / "build.json").exists():
            self.build(candidate)
        if not (self.state_dir / "accepted" / f"{sha}.json").exists():
            self.validate_release(candidate)
        manifest = read_json(release / "manifest.json", {})
        accepted = read_json(self.state_dir / "accepted" / f"{sha}.json", {})
        if not accepted or accepted.get("manifest_sha256") != digest(release / "manifest.json"):
            raise Refused("release has no independent acceptance record")
        for name, expected in manifest.get("files", {}).items():
            if Path(name).name != name or (release / name).is_symlink() or digest(release / name) != expected:
                raise Refused("release checksum mismatch")
        if not in_window(dt.datetime.now(dt.timezone.utc), switch=True):
            raise Refused("switch cutoff reached")
        self.verify_candidate(candidate)
        self.deploy(sha, manifest)

    def build(self, candidate: dict) -> None:
        sha = self.verify_candidate(candidate)
        self.mount_check()
        available = int(re.search(r"MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1)) * 1024
        if available < 3 * 1024**3 or shutil.disk_usage("/").free < 20 * 1024**3 or shutil.disk_usage(self.data).free < 50 * 1024**3:
            raise Refused("insufficient resources for build")
        work = self.data / "work" / sha
        if work.exists():
            raise Refused("previous build directory exists; inspect failed build before retry")
        work.mkdir(mode=0o700)
        archive = work / "source.tar.gz"
        request = urllib.request.Request(f"https://api.github.com/repos/{self.config['repository']}/tarball/{sha}",
                                         headers={"User-Agent": "dazah-cd"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        source_archive_checksum = digest(archive)
        source = work / "source"
        source.mkdir()
        with tarfile.open(archive) as package:
            for member in package.getmembers():
                parts = Path(member.name).parts[1:]
                if not parts:
                    continue
                destination = source.joinpath(*parts)
                if member.issym() or member.islnk() or not destination.resolve().is_relative_to(source.resolve()):
                    raise Refused("unsafe source archive entry")
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with package.extractfile(member) as inp, destination.open("wb") as out:
                        shutil.copyfileobj(inp, out)
                    destination.chmod(member.mode & 0o755)
                else:
                    raise Refused("unsupported source archive entry")
        # Operator-owned pinned base policy, not arbitrary mutable registry tags.
        pins = read_json(Path("/etc/dazah-cd/base-images.json"), {})
        for filename in ("Dockerfile", "Dockerfile.dev"):
            dockerfile = (source / filename).read_text()
            for base in re.findall(r"^FROM\s+(\S+)", dockerfile, re.MULTILINE):
                if base not in pins or not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[a-f0-9]{64}", pins[base]):
                    raise Refused("base image digest policy missing")
                dockerfile = dockerfile.replace(f"FROM {base} ", f"FROM {pins[base]} ")
            (source / filename).write_text(dockerfile)
        output_dir = work / "output"
        output_dir.mkdir()
        migration_policy = read_json(source / "deploy" / "migration-policy.json", {"transitions": []})
        command(["chown", "-R", "dazah-build:dazah-build", str(work)])
        self.phase("building", candidate_sha=sha)
        started = time.monotonic()
        command(["systemctl", "start", "dazah-build.service"])
        try:
            deadline = time.monotonic() + 30
            while not Path("/run/dazah-build/buildkitd.sock").is_socket():
                if time.monotonic() >= deadline:
                    raise Refused("rootless builder did not become ready")
                time.sleep(.5)
            for target in ("backend", "frontend", "hermes", "backend-dev"):
                out = output_dir / f"{target}.tar"
                args = ["systemd-run", "--quiet", "--wait", "--pipe", "--collect", "--unit=dazah-build-client",
                        "--uid=dazah-build", "--gid=dazah-build", "--slice=dazah-build.slice",
                        "--property=MemoryMax=128M", "--property=MemorySwapMax=0", "--property=TasksMax=32",
                        "--property=RuntimeMaxSec=7200", "--property=NoNewPrivileges=yes",
                        "/usr/local/bin/buildctl", "--addr",
                        "unix:///run/dazah-build/buildkitd.sock", "build", "--frontend", "dockerfile.v0",
                        "--local", f"context={source}", "--local", f"dockerfile={source}",
                        "--opt", f"target={'backend' if target == 'backend-dev' else target}",
                        "--opt", f"filename={'Dockerfile.dev' if target == 'backend-dev' else 'Dockerfile'}",
                        "--output", f"type=docker,name=dazah/{target}:cd-{sha},dest={out}"]
                with (work / f"{target}.log").open("wb") as log:
                    process = subprocess.Popen(args, stdout=log, stderr=log, start_new_session=True)
                    low_since = None
                    unhealthy = 0
                    try:
                        while process.poll() is None:
                            time.sleep(5)
                            free = int(re.search(r"MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1))
                            low_since = (low_since or time.monotonic()) if free < 1024**2 else None
                            inventory = self.containers()
                            unhealthy = 0 if all(self.healthy(inventory.get(s, {})) for s in (*DEPS, *APPS)) else unhealthy + 1
                            if (not in_window(dt.datetime.now(dt.timezone.utc))
                                    or time.monotonic() - started > 7200 or unhealthy >= 3
                                    or low_since and time.monotonic() - low_since >= 30):
                                raise Refused("build stopped to protect online service")
                        if process.returncode:
                            raise Refused("bounded build failed; inspect protected build log")
                    finally:
                        if process.poll() is None:
                            subprocess.run(["systemctl", "stop", "dazah-build-client.service"],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
        finally:
            command(["systemctl", "stop", "dazah-build.service"])
        # Output remains untrusted until copied and checksummed by the controller.
        release = self.data / "releases" / sha
        release.mkdir(mode=0o700)
        for target in ("backend", "frontend", "hermes", "backend-dev"):
            item = output_dir / f"{target}.tar"
            if item.is_symlink() or not item.is_file():
                raise Refused("invalid build output")
            shutil.copyfile(item, release / item.name)
        atomic_json(release / "build.json", {"sha": sha, "run_id": candidate["run_id"],
                    "source_archive_sha256": source_archive_checksum, "base_images": pins,
                    "files": {p.name: digest(p) for p in release.iterdir() if p.suffix == ".tar"}})
        atomic_json(release / "migration-policy.json", migration_policy)
        self.phase("awaiting_isolated_validation")

    def validate_release(self, candidate: dict) -> None:
        sha = self.verify_candidate(candidate)
        release = self.data / "releases" / sha
        build = read_json(release / "build.json", {})
        if build.get("sha") != sha or set(build.get("files", {})) != {f"{s}.tar" for s in ("backend", "frontend", "hermes", "backend-dev")}:
            raise Refused("incomplete build record")
        for name, expected in build["files"].items():
            if digest(release / name) != expected:
                raise Refused("build output checksum mismatch")
            command(["docker", "load", "--input", str(release / name)], timeout=300)
        before = self.revision()
        network = f"dazah-cd-test-{sha[:12]}"
        database = f"{network}-db"
        backend = f"{network}-backend"
        command(["docker", "network", "create", "--internal", network])
        try:
            command(["docker", "run", "-d", "--name", database, "--network", network,
                     "--memory", "384m", "--cpus", ".5", "--pids-limit", "128",
                     "--tmpfs", "/var/lib/postgresql/data:rw,size=512m",
                     "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:17"])
            for _ in range(30):
                try:
                    command(["docker", "exec", database, "pg_isready", "-U", "postgres"])
                    break
                except Refused:
                    time.sleep(1)
            dump = release / "validation.dump"
            try:
                with dump.open("wb") as handle:
                    self.compose("exec", "-T", "db", "sh", "-c", 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', timeout=600, output=handle)
                with dump.open("rb") as handle:
                    result = subprocess.run(["docker", "exec", "-i", database, "pg_restore", "-U", "postgres",
                                             "-d", "postgres", "--no-owner", "--no-privileges", "--exit-on-error"],
                                            stdin=handle, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
                    if result.returncode:
                        raise Refused("isolated database restore failed")
            finally:
                dump.unlink(missing_ok=True)
            args = ["docker", "run", "--rm", "--name", backend, "--network", network,
                    "--memory", "1024m", "--cpus", "1", "--pids-limit", "128",
                    "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                    "-e", "APP_ENV=test", "-e", "FRONTEND_URL=http://localhost:3000",
                    "-e", f"DATABASE_URL=postgresql+asyncpg://postgres@{database}:5432/postgres",
                    "-e", "MINIO_ENABLED=false", f"dazah/backend-dev:cd-{sha}"]
            heads = command(args + [".venv/bin/alembic", "heads"], timeout=120)
            revisions = re.findall(r"^([A-Za-z0-9_]+) \(head\)", heads, re.MULTILINE)
            if len(revisions) != 1:
                raise Refused("expected one Alembic head")
            policy = read_json(release / "migration-policy.json", {})
            after = migration_target(policy, revisions[0], before)
            compatible = before == after or any(
                p.get("from_revision") == before and p.get("to_revision") == after
                and p.get("backward_compatible") is True and p.get("review_reference")
                for p in policy.get("transitions", []))
            if not compatible:
                raise Refused("reviewed migration compatibility declaration missing")
            command(args + [".venv/bin/alembic", "upgrade", after], timeout=300)
            actual = command(["docker", "exec", database, "psql", "-U", "postgres", "-Atc",
                              "select version_num from alembic_version order by version_num"])
            if actual != after:
                raise Refused("isolated migration revision mismatch")
            # Import smoke runs without lifespan or any external network access.
            command(args + [".venv/bin/python", "-c", "from app.main import app; assert app.openapi()['paths']"], timeout=120)
            images = {service: command(["docker", "image", "inspect", "--format", "{{.Id}}", f"dazah/{target}:cd-{sha}"])
                      for service, target in (("app", "backend"), ("migrate", "backend"), ("frontend", "frontend"), ("hermes-lite", "hermes"))}
            manifest = {"sha": sha, "run_id": candidate["run_id"], "images": images, "files": build["files"],
                        "base_images": build["base_images"], "source_archive_sha256": build["source_archive_sha256"],
                        "site_files": self.site_checksums(),
                        "migration": {"from_revision": before, "to_revision": after,
                                      "source_head": revisions[0], "backward_compatible": compatible}}
            atomic_json(release / "manifest.json", manifest)
            atomic_json(self.state_dir / "accepted" / f"{sha}.json", {"manifest_sha256": digest(release / "manifest.json")})
            self.phase("validated")
        finally:
            for name in (backend, database):
                subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            command(["docker", "network", "rm", network])


@contextlib.contextmanager
def lock(path: Path):
    import fcntl
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refused("another operation holds deployment lock") from exc
        yield


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "drill", "watchdog", "schedule", "status", "mount-check"])
    parser.add_argument("--config", default="/etc/dazah-cd/config.json")
    args = parser.parse_args()
    os.umask(0o077)
    config_path = Path(args.config)
    info = config_path.stat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise Refused("configuration must be root-owned and not group/world writable")
    controller = Controller(read_json(config_path))
    try:
        # Read-only check is also used by BuildKit ExecStartPre while schedule owns the lock.
        if args.action == "mount-check":
            controller.mount_check()
            return 0
        with lock(Path("/var/lock/dazah-deploy.lock")):
            if args.action == "status":
                controller.event("status", state=read_json(controller.state_file, {}), enabled=controller.config.get("enabled", False))
            else:
                getattr(controller, args.action)()
        return 0
    except Exception as exc:
        # Network/OS exceptions can contain URLs or subprocess details.
        controller.event("operation_failed", action=args.action, reason=str(exc) if isinstance(exc, Refused) else type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
