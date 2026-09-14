"""Fixed isolated container identities; never accepts a user-supplied production URL."""
import concurrent.futures
import json
import math
import re
from pathlib import Path
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

BASE = "http://127.0.0.1:18080"
PASSWORD = "cd-test-only-2026"
OPENER = build_opener(ProxyHandler({}))


def request(path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with OPENER.open(req, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        try:
            error = json.load(exc)
            return exc.code, {"message": error.get("message", "HTTP error")}
        except (ValueError, AttributeError):
            return exc.code, {}
    except (OSError, ValueError) as exc:
        return 599, {"failure": type(exc).__name__}


def login(username):
    for attempt in range(4):
        status, body = request("/api/v1/identity/auth/local/login", body={"username": username, "password": PASSWORD})
        if status != 429:
            break
        print("Fixture login waits for existing authentication rate limit", flush=True)
        time.sleep(30)
    if status != 200:
        raise RuntimeError(f"synthetic login failed ({status}, {body.get('failure', 'http')})")
    return body["data"]["access_token"]


def fixture():
    label = subprocess.check_output(["docker", "inspect", "--format", '{{index .Config.Labels "dazah.role"}}', "dazah-load-app-dev"], text=True).strip()
    if label != "isolated-test":
        raise RuntimeError("refusing workload without isolated container marker")
    admin = login("cd-bootstrap")
    for index in range(50):
        status, body = request("/api/v1/hr/employees", admin, employee(f"cd-seed-{index}"))
        if status not in (200, 201):
            raise RuntimeError(f"synthetic employee creation failed ({status}): {body.get('message')}")
        time.sleep(0.05)
    tokens = []
    for index in range(40):
        name = f"cd-virtual-{index}"
        status, _ = request("/api/v1/identity/users", admin,
                            {"username": name, "password": PASSWORD, "name": name, "role": "admin"})
        if status not in (200, 201):
            raise RuntimeError(f"synthetic user creation failed ({status})")
        tokens.append(login(name))
        time.sleep(0.1)
    for path in ("/api/v1/identity/me", "/api/v1/hr/employees", "/api/v1/identity/departments"):
        status, _ = request(path, admin)
        if status != 200:
            raise RuntimeError(f"fixture endpoint not ready: {path} ({status})")
    return tokens


def employee(name):
    return {"name": name, "employee_number": name, "department": "CD Test", "position": "Synthetic", "hire_date": "2026-09-01"}


def phase(name, tokens, seconds):
    started = time.monotonic()
    records = []
    mutex = threading.Lock()
    stop = threading.Event()
    def user(index, token):
        count = 0
        paths = ("/api/v1/identity/me", "/api/v1/hr/employees?page_size=20", "/api/v1/identity/departments")
        time.sleep(index / len(tokens))
        while time.monotonic() - started < seconds and not stop.is_set():
            begin = time.monotonic()
            if count % 10 == 9:
                status, _ = request("/api/v1/hr/employees", token, employee(f"cd-{name}-{index}-{count}"))
            else:
                status, _ = request(paths[count % len(paths)], token)
            with mutex:
                records.append((time.monotonic() - begin, status))
            count += 1
            time.sleep(max(0, 1 - (time.monotonic() - begin)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tokens)) as pool:
        futures = [pool.submit(user, index, token) for index, token in enumerate(tokens)]
        while any(not future.done() for future in futures):
            time.sleep(30)
            available = int(re.search(r"MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1))
            health = subprocess.check_output(["docker", "inspect", "--format", "{{.State.Health.Status}}", "dazah-app-1"], text=True).strip()
            if available < 1024**2 or health != "healthy":
                stop.set()
                raise RuntimeError("isolated load stopped to protect online service")
            with mutex:
                sample = list(records)
            print(json.dumps({"phase": name, "elapsed": round(time.monotonic()-started), **summary(sample)}), flush=True)
        for future in futures:
            future.result()
    return {"phase": name, "users": len(tokens), "duration_seconds": round(time.monotonic()-started), **summary(records)}


def summary(records):
    successful = sorted(duration for duration, status in records if 200 <= status < 300)
    throttled = sum(status in (429, 503) for _, status in records)
    errors = sum(status >= 400 and status not in (429, 503) for _, status in records)
    return {"requests": len(records), "p95_seconds": round(successful[max(0, math.ceil(len(successful)*.95)-1)], 4) if successful else None,
            "throttled": throttled, "unexpected_errors": errors}


if __name__ == "__main__":
    oom_before = int(re.search(r"(?m)^oom_kill (\d+)$", Path("/proc/vmstat").read_text()).group(1))
    gateway = json.loads(subprocess.check_output(["docker", "inspect", "dazah-load-nginx-dev"], text=True))[0]
    if gateway["Config"]["Labels"].get("dazah.role") != "isolated-test":
        raise RuntimeError("refusing unlabelled test gateway")
    address = gateway["NetworkSettings"]["Networks"]["dazah-load-test"]["IPAddress"]
    BASE = "http://" + address
    tokens = fixture()
    reports = [phase("normal", tokens[:20], 1800), phase("overload", tokens, 120), phase("recovery", tokens[:20], 120)]
    normal, overload, recovery = reports
    oom_after = int(re.search(r"(?m)^oom_kill (\d+)$", Path("/proc/vmstat").read_text()).group(1))
    names = ["dazah-load-app-dev", "dazah-load-db-dev", "dazah-load-nginx-dev", "dazah-load-redis-dev"]
    states = json.loads(subprocess.check_output(["docker", "inspect", *names], text=True))
    containers_ok = all(not item["State"]["OOMKilled"] and item["State"]["Running"] and item["RestartCount"] == 0 for item in states)
    accepted = (normal["requests"] > 1000 and normal["p95_seconds"] is not None and normal["p95_seconds"] < 2
                and normal["unexpected_errors"] / normal["requests"] < .01
                and normal["throttled"] / normal["requests"] < .01
                and overload["unexpected_errors"] / max(1, overload["requests"]) < .01
                and overload["throttled"] > 0 and oom_before == oom_after and containers_ok
                and recovery["unexpected_errors"] == 0 and recovery["throttled"] / max(1,recovery["requests"]) < .01)
    report = {"accepted": accepted, "host_oom_delta": oom_after - oom_before, "containers_ok": containers_ok,
              "profile": "synthetic admin identities, HR writes/list, identity, department list; no frontend/AI load", "phases": reports}
    Path("/var/tmp/dazah-cd-load-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    raise SystemExit(0 if accepted else 1)
