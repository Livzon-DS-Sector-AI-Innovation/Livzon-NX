#!/usr/bin/python3
"""Dazah implementation of Poseidon's project executor protocol."""

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from uuid import UUID


OPERATIONS = ("status", "deploy", "rollback", "verify")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
DEPLOYMENT = Path(__file__).resolve().with_name("deploy-production.sh")


def version(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("invalid version")
    return value


def deployment(*args, timeout):
    return subprocess.run(
        ["/bin/bash", str(DEPLOYMENT), *args], stdin=subprocess.DEVNULL,
        cwd=DEPLOYMENT.parent, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=timeout,
    )


def operation(request):
    if request["protocol"] != 1:
        raise ValueError("unsupported protocol")
    action = request["operation"]
    if action == "capabilities":
        return {"operations": OPERATIONS}
    if action in {"deploy", "rollback"}:
        UUID(request["id"])
        candidate = version(request["version"])
        expected = version(request["expected"])
        artifact = PurePosixPath(request["artifact"])
        if not artifact.is_absolute() or artifact.name != candidate:
            raise ValueError("invalid artifact")
        deployment(action + "-if-current", candidate, str(artifact), "180", expected, timeout=3400).check_returncode()
        return {}
    if action == "status":
        result = deployment("status", timeout=7)
        result.check_returncode()
        current = next(line.removeprefix("current_version=") for line in result.stdout.splitlines()
                       if line.startswith("current_version="))
        result = deployment("verify", "--quick", timeout=11)
        current = version(current)
        verified = f"[dazah-deploy] 验证成功: {current}" in result.stdout.splitlines()
        return {"version": current, "health": "healthy" if result.returncode == 0 and verified else "unhealthy"}
    if action == "verify":
        expected = version(request["version"])
        result = deployment("verify", timeout=190)
        result.check_returncode()
        verified = f"[dazah-deploy] 验证成功: {expected}" in result.stdout.splitlines()
        if not verified:
            raise ValueError("verified version changed")
        return {"version": expected, "health": "healthy"}
    raise ValueError("unsupported operation")


def main():
    try:
        request = json.loads(sys.stdin.buffer.read(8193))
        result = {"ok": True, **operation(request)}
    except subprocess.TimeoutExpired:
        result = {"ok": False, "uncertain": True}
    except (OSError, ValueError, TypeError, AttributeError, KeyError, StopIteration, subprocess.CalledProcessError):
        result = {"ok": False}
    print(json.dumps({"protocol": 1, **result}))


if __name__ == "__main__":
    main()
