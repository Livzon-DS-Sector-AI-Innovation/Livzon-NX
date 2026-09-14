#!/usr/local/bin/python3
"""Bound LibreOffice processes across all modules without releasing a live child."""
from __future__ import annotations

import os
import ctypes
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def acquire(directory: Path, prefix: str, count: int):
    import fcntl
    for index in range(count):
        fd = os.open(directory / f"{prefix}-{index}", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            os.close(fd)
    return None


def run(argv: list[str]) -> int:
    directory = Path(tempfile.gettempdir()) / f"dazah-conversion-{os.getuid()}"
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        return 75
    admission = acquire(directory, "admitted", 12)
    if admission is None:
        print("Document conversion busy; retry later", file=sys.stderr)
        return 75
    slot = None
    child = None
    handlers = {}
    try:
        deadline = time.monotonic() + 10
        while slot is None:
            slot = acquire(directory, "active", 2)
            if slot is not None:
                break
            if time.monotonic() >= deadline:
                print("Document conversion queue timeout", file=sys.stderr)
                return 75
            time.sleep(0.05)
        with tempfile.TemporaryDirectory(prefix="dazah-office-") as profile:
            args = list(argv)
            if not any(arg.startswith("-env:UserInstallation=") for arg in args):
                args.insert(0, f"-env:UserInstallation={Path(profile).as_uri()}")
            parent = os.getpid()
            def parent_death_signal():
                # A caller's subprocess timeout can SIGKILL this wrapper; do not orphan Office.
                if ctypes.CDLL(None).prctl(1, signal.SIGKILL) != 0:
                    os._exit(126)
                if os.getppid() != parent:
                    os._exit(126)
            child = subprocess.Popen(
                ["/usr/lib/libreoffice/program/soffice", *args], start_new_session=True,
                pass_fds=(admission, slot), preexec_fn=parent_death_signal,
            )
            def stop(signum, frame):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                raise SystemExit(128 + signum)
            for signum in (signal.SIGTERM, signal.SIGINT):
                handlers[signum] = signal.signal(signum, stop)
            try:
                return child.wait(timeout=180)
            except subprocess.TimeoutExpired:
                return 124
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        if slot is not None:
            os.close(slot)
        os.close(admission)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
