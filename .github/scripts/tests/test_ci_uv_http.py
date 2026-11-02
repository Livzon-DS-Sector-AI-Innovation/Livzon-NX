"""Exercise uv against a loopback wheel server, never a public package index."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "ci_support_http", Path(__file__).parents[1] / "ci_support.py"
)
assert SPEC and SPEC.loader
support = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(support)


def wheel_bytes():
    files = {
        "ci_probe/__init__.py": b"VALUE = 1\n",
        "ci_probe-1.0.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: ci-probe\nVersion: 1.0.0\n",
        "ci_probe-1.0.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: ci-fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    records = []
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in files.items():
            digest = (
                base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                .rstrip(b"=")
                .decode()
            )
            records.append(f"{name},sha256={digest},{len(data)}")
            archive.writestr(name, data)
        archive.writestr(
            "ci_probe-1.0.0.dist-info/RECORD",
            "\n".join(records) + "\nci_probe-1.0.0.dist-info/RECORD,,\n",
        )
    return stream.getvalue()


@unittest.skipUnless(
    shutil.which("uv"), "uv required for loopback HTTP fault injection"
)
class UVHTTPTests(unittest.TestCase):
    def test_bounded_retry_cold_install_offline_warm_install_and_exhaustion(self):
        data = wheel_bytes()
        state = {"requests": 0, "failures": 0}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                state["requests"] += 1
                if state["failures"]:
                    state["failures"] -= 1
                    self.send_error(503)
                elif self.path.endswith("ci_probe-1.0.0-py3-none-any.whl"):
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header(
                        "Cache-Control", "public, max-age=31536000, immutable"
                    )
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_error(404)

            def log_message(self, *args):
                pass

        with (
            tempfile.TemporaryDirectory() as directory,
            ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server,
        ):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                root = Path(directory)
                project = root / "dazah-backend"
                project.mkdir()
                origin = f"http://127.0.0.1:{server.server_port}"
                (project / "pyproject.toml").write_text(
                    '[project]\nname="ci-fixture"\nversion="0.0.0"\nrequires-python=">=3.11"\n'
                    f'dependencies=["ci-probe @ {origin}/ci_probe-1.0.0-py3-none-any.whl"]\n'
                    "[project.optional-dependencies]\ndev=[]\n[dependency-groups]\ndev=[]\n",
                    encoding="utf-8",
                )
                environment = {
                    "UV_CACHE_DIR": str(root / "lock-cache"),
                    "UV_PYTHON": sys.executable,
                    "UV_PYTHON_DOWNLOADS": "never",
                    "UV_NO_CONFIG": "1",
                    "UV_DEFAULT_INDEX": origin + "/simple",
                    "CI_PHASE_FILE": str(root / "phases.jsonl"),
                    "UV_NO_PROGRESS": "1",
                }
                with (
                    patch.dict(os.environ, environment),
                    patch.object(support, "ROOT", root),
                ):
                    locked = subprocess.run(
                        ["uv", "lock", "--project", str(project)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertEqual(locked.returncode, 0, locked.stderr)
                    lock = (project / "uv.lock").read_bytes()
                    state["failures"], state["requests"] = 2, 0
                    with patch.dict(
                        os.environ,
                        {
                            "UV_CACHE_DIR": str(root / "runtime-cache"),
                            "UV_PROJECT_ENVIRONMENT": str(root / "cold-env"),
                        },
                    ):
                        self.assertEqual(support.install_project("backend"), 0)
                    self.assertGreaterEqual(state["requests"], 3)
                    requests = state["requests"]
                    with patch.dict(
                        os.environ,
                        {
                            "UV_CACHE_DIR": str(root / "runtime-cache"),
                            "UV_OFFLINE": "1",
                            "UV_PROJECT_ENVIRONMENT": str(root / "warm-env"),
                        },
                    ):
                        self.assertEqual(support.install_project("backend"), 0)
                    self.assertEqual(state["requests"], requests)
                    state["failures"], state["requests"] = 100, 0
                    with patch.dict(
                        os.environ,
                        {
                            "UV_CACHE_DIR": str(root / "failed-cache"),
                            "UV_PROJECT_ENVIRONMENT": str(root / "failed-env"),
                        },
                    ):
                        self.assertNotEqual(support.install_project("backend"), 0)
                    self.assertLessEqual(state["requests"], 4)
                    self.assertEqual((project / "uv.lock").read_bytes(), lock)
                    phases = support.read_phases(root / "phases.jsonl")
                    self.assertEqual(
                        [item["exit_code"] == 0 for item in phases], [True, True, False]
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
