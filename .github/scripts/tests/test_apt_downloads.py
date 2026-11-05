"""APT fault injection uses a synthetic repository on loopback, never public mirrors.

Run the HTTP tests on Linux with apt-get and dpkg-deb (or in an isolated container).
"""

from __future__ import annotations

import gzip
import hashlib
import shutil
import subprocess
import tempfile
import threading
import unittest
from collections import Counter
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "docker" / "apt-download.conf"


class BuildCacheTests(unittest.TestCase):
    def test_every_apt_consumer_uses_locked_caches_and_shared_policy(self):
        for filename in ("Dockerfile", "Dockerfile.dev"):
            with self.subTest(filename=filename):
                backend = (
                    (ROOT / filename).read_text(encoding="utf-8").split("\nFROM ", 2)[1]
                )
                self.assertIn(
                    "COPY docker/apt-download.conf /etc/apt/apt.conf.d/80dazah-download",
                    backend,
                )
                self.assertIn("rm -f /etc/apt/apt.conf.d/docker-clean", backend)
                self.assertNotIn("rm -rf /var/lib/apt/lists", backend)
                commands = backend.replace("\\\n", " ").split("\nRUN ")[1:]
                consumers = [
                    command
                    for command in commands
                    if "apt-get update" in command or "install --with-deps" in command
                ]
                self.assertEqual(len(consumers), 2)
                for command in consumers:
                    for cache_id, target in (
                        ("dazah-debian-apt", "/var/cache/apt"),
                        ("dazah-debian-apt-lists", "/var/lib/apt/lists"),
                    ):
                        self.assertIn(
                            f"--mount=type=cache,id={cache_id},target={target},sharing=locked",
                            command,
                        )
                self.assertIn(
                    "id=dazah-backend-uv,target=/home/app/.cache/uv,sharing=locked",
                    backend,
                )


@contextmanager
def apt_repository():
    with tempfile.TemporaryDirectory(prefix="dazah-apt-") as directory:
        root = Path(directory)
        package = root / "package"
        (package / "DEBIAN").mkdir(parents=True)
        (package / "DEBIAN" / "control").write_text(
            "Package: dazah-cache-probe\nVersion: 1.0\nArchitecture: all\n"
            "Maintainer: CI <ci@example.invalid>\nDescription: synthetic cache probe\n",
            encoding="utf-8",
        )
        archive = root / "probe.deb"
        subprocess.run(
            ["dpkg-deb", "--build", str(package), str(archive)],
            check=True,
            capture_output=True,
            timeout=15,
        )
        data = archive.read_bytes()
        packages = (
            (package / "DEBIAN" / "control").read_bytes()
            + f"Filename: probe.deb\nSize: {len(data)}\n"
            f"SHA256: {hashlib.sha256(data).hexdigest()}\n\n".encode()
        )
        index = gzip.compress(packages)
        release = (
            "Origin: Dazah test\nLabel: Dazah test\nSHA256:\n"
            f" {hashlib.sha256(index).hexdigest()} {len(index)} Packages.gz\n"
            f" {hashlib.sha256(packages).hexdigest()} {len(packages)} Packages\n"
        ).encode()
        state = {"requests": Counter(), "failures": Counter()}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                name = self.path.rsplit("/", 1)[-1]
                state["requests"][name] += 1
                if state["failures"][name]:
                    state["failures"][name] -= 1
                    self.send_error(502)
                    return
                content = {
                    "Release": release,
                    "Packages.gz": index,
                    "Packages": packages,
                    "probe.deb": data,
                }.get(name)
                if content is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            (root / "lists" / "partial").mkdir(parents=True)
            (root / "archives" / "partial").mkdir(parents=True)
            (root / "status").touch()
            (root / "sources.list").write_text(
                f"deb [trusted=yes] http://127.0.0.1:{server.server_port} ./\n",
                encoding="utf-8",
            )

            def apt(*arguments):
                # Ignore the host's sources, status, hooks, proxies and caches.
                return subprocess.run(
                    [
                        "apt-get",
                        "-c",
                        str(CONFIG),
                        "-o",
                        "Dir::Etc::parts=-",
                        "-o",
                        "Dir::Etc::main=-",
                        "-o",
                        f"Dir::Etc::sourcelist={root / 'sources.list'}",
                        "-o",
                        "Dir::Etc::sourceparts=-",
                        "-o",
                        f"Dir::State::status={root / 'status'}",
                        "-o",
                        f"Dir::State::lists={root / 'lists'}",
                        "-o",
                        f"Dir::Cache::archives={root / 'archives'}",
                        "-o",
                        "Acquire::http::Proxy=DIRECT",
                        "-o",
                        "APT::Sandbox::User=",
                        *arguments,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=50,
                    env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C"},
                )

            try:
                yield root, state, apt
            finally:
                server.shutdown()
                thread.join(timeout=5)


@unittest.skipUnless(
    shutil.which("apt-get") and shutil.which("dpkg-deb"),
    "Linux apt-get and dpkg-deb required for loopback fault injection",
)
class AptHTTPTests(unittest.TestCase):
    def test_502_recovery_and_reuse_of_downloaded_package(self):
        with apt_repository() as (root, state, apt):
            updated = apt("update")
            self.assertEqual(updated.returncode, 0, updated.stdout + updated.stderr)
            state["failures"]["probe.deb"] = 2
            cold = apt("install", "--download-only", "--yes", "dazah-cache-probe")
            self.assertEqual(cold.returncode, 0, cold.stdout + cold.stderr)
            self.assertEqual(state["requests"]["probe.deb"], 3)
            self.assertTrue(list((root / "archives").glob("*.deb")))
            state["failures"]["probe.deb"] = 100
            warm = apt("install", "--download-only", "--yes", "dazah-cache-probe")
            self.assertEqual(warm.returncode, 0, warm.stdout + warm.stderr)
            self.assertEqual(state["requests"]["probe.deb"], 3)

    def test_package_502_exhaustion_is_bounded_and_fails(self):
        with apt_repository() as (_, state, apt):
            updated = apt("update")
            self.assertEqual(updated.returncode, 0, updated.stdout + updated.stderr)
            state["failures"]["probe.deb"] = 100
            failed = apt("install", "--download-only", "--yes", "dazah-cache-probe")
            self.assertNotEqual(failed.returncode, 0, failed.stdout + failed.stderr)
            self.assertEqual(state["requests"]["probe.deb"], 4)

    def test_failed_index_refresh_cannot_succeed_using_stale_lists(self):
        with apt_repository() as (_, state, apt):
            updated = apt("update")
            self.assertEqual(updated.returncode, 0, updated.stdout + updated.stderr)
            state["failures"]["Release"] = 100
            state["failures"]["Packages.gz"] = 100
            state["failures"]["Packages"] = 100
            before = state["requests"]["Release"]
            failed = apt("update")
            self.assertNotEqual(failed.returncode, 0, failed.stdout + failed.stderr)
            self.assertEqual(state["requests"]["Release"] - before, 4)


if __name__ == "__main__":
    unittest.main()
