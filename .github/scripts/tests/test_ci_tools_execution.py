"""Check the CI tools loader and shell without a Docker daemon or credentials."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "ci-tools.sh"
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
IMAGE_ID = "sha256:" + "a" * 64


@unittest.skipUnless(BASH and Path(BASH).exists(), "Bash is required")
class CIToolsExecutionTests(unittest.TestCase):
    def invoke(
        self,
        *args: str,
        image_id: str = IMAGE_ID,
        loaded_id: str = IMAGE_ID,
        load_exit: int = 0,
        run_exit: int = 0,
    ) -> tuple[int, list[str], str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "docker.log"
            exported = root / "github-env"
            (root / "docker").write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$@" >> "$CI_TEST_LOG"\n'
                'case "$1 ${2:-}" in\n'
                '  "image load") exit "$CI_TEST_LOAD_EXIT";;\n'
                '  "image inspect") printf "%s\\n" "$CI_TEST_LOADED_ID";;\n'
                '  run*) exit "$CI_TEST_RUN_EXIT";;\n'
                "  *) exit 99;;\n"
                "esac\n",
                encoding="utf-8",
                newline="\n",
            )
            (root / "docker").chmod(0o755)
            startup = root / "bash-env"
            startup.write_text(
                "if command -v cygpath >/dev/null; then\n"
                '  CI_TEST_ROOT="$(cygpath -u "$CI_TEST_ROOT")"\n'
                "fi\n"
                'export PATH="$CI_TEST_ROOT:$PATH"\n'
                'uv() { printf "%s/uv-cache\\n" "$CI_TEST_ROOT"; }\n',
                encoding="utf-8",
                newline="\n",
            )
            result = subprocess.run(
                [str(BASH), str(SCRIPT), *args],
                cwd=root,
                env={
                    **os.environ,
                    "BASH_ENV": startup.as_posix(),
                    "CI_TEST_ROOT": root.as_posix(),
                    "CI_TEST_LOG": log.as_posix(),
                    "GITHUB_ENV": exported.as_posix(),
                    "GITHUB_WORKSPACE": root.as_posix(),
                    "RUNNER_TEMP": root.as_posix(),
                    "CI_TEST_LOAD_EXIT": str(load_exit),
                    "CI_TEST_LOADED_ID": loaded_id,
                    "CI_TEST_RUN_EXIT": str(run_exit),
                    "CI_TOOLS_IMAGE_ID": image_id,
                    "GH_TOKEN": "synthetic-not-for-the-container",
                },
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            return (
                result.returncode,
                log.read_text(encoding="utf-8").splitlines() if log.exists() else [],
                exported.read_text(encoding="utf-8") if exported.exists() else "",
            )

    def test_loader_only_exports_the_verified_image_id(self) -> None:
        status, _, exported = self.invoke("load", "ci-tools-image.tar")
        self.assertEqual(status, 0)
        self.assertEqual(exported, f"CI_TOOLS_IMAGE_ID={IMAGE_ID}\n")
        for kwargs in (
            {"image_id": "dazah-ci-tools:latest"},
            {"load_exit": 4},
            {"loaded_id": "sha256:" + "b" * 64},
        ):
            with self.subTest(kwargs=kwargs):
                status, _, exported = self.invoke(
                    "load", "ci-tools-image.tar", **kwargs
                )
                self.assertNotEqual(status, 0)
                self.assertEqual(exported, "")

    def test_step_uses_local_id_and_propagates_failure_without_forwarding_token(self):
        status, command, _ = self.invoke("runner-step.sh", run_exit=7)
        self.assertEqual(status, 7)
        self.assertEqual(command[0], "run")
        self.assertIn(IMAGE_ID, command)
        self.assertIn("--pull=never", command)
        self.assertIn("TEST_DATABASE_URL", command)
        self.assertIn("SHARD", command)
        self.assertNotIn("GH_TOKEN", "\n".join(command))
        self.assertNotIn("synthetic-not-for-the-container", "\n".join(command))
        self.assertEqual(command[-1], "runner-step.sh")


if __name__ == "__main__":
    unittest.main()
