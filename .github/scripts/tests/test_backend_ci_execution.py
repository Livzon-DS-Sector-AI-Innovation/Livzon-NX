"""Exercise CI orchestration with command fakes; never connect to a database."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASH = (
    "C:/Program Files/Git/bin/bash.exe"
    if os.name == "nt"
    else shutil.which("bash")
)


@unittest.skipUnless(BASH and Path(BASH).exists(), "Bash is required")
class BackendCIExecutionTests(unittest.TestCase):
    def run_ci(self, phase: str, fail_tests: bool = False) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / "dazah-backend"
            (backend / "scripts").mkdir(parents=True)
            (root / "scripts").mkdir()
            (backend / "uv.lock").touch()
            shutil.copyfile(ROOT / "dazah-backend/scripts/ci.sh", backend / "scripts/ci.sh")
            for script in (backend / "scripts/ruff-changed.sh", root / "scripts/wait-for-database.sh"):
                script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            # BASH_ENV functions replace external commands, preserving set -e behavior.
            fake = root / "fake.sh"
            fake.write_text(
                'uv() {\n'
                '  printf "%s\\n" "$*" >> "$CI_TEST_LOG"\n'
                '  if [[ "$*" == "run --no-sync alembic heads" ]]; then echo "abc (head)"; fi\n'
                '  if [[ "$*" == *pytest* && "$CI_TEST_FAIL" == "1" ]]; then return 7; fi\n'
                '  return 0\n'
                '}\n'
                'git() { return 0; }\n',
                encoding="utf-8",
            )
            log = root / "commands.log"
            result = subprocess.run(
                [str(BASH), str(backend / "scripts/ci.sh"), phase],
                env={
                    **os.environ,
                    "BASH_ENV": fake.as_posix(),
                    "CI_TEST_LOG": log.as_posix(),
                    "CI_TEST_FAIL": "1" if fail_tests else "0",
                },
                capture_output=True,
                text=True,
            )
            self.assertTrue(log.exists(), result.stderr)
            return result.returncode, log.read_text(encoding="utf-8").splitlines()

    def test_quality_does_not_start_database_or_repeat_tests(self) -> None:
        code, commands = self.run_ci("quality")
        self.assertEqual(code, 0)
        self.assertTrue(any("mypy app/core" in command for command in commands))
        self.assertFalse(any("pytest" in command or "alembic" in command for command in commands))

    def test_integration_runs_complete_suite_once_after_migration(self) -> None:
        code, commands = self.run_ci("integration")
        self.assertEqual(code, 0)
        tests = [command for command in commands if "pytest" in command]
        self.assertEqual(len(tests), 1)
        self.assertIn("--cov=app --cov-branch", tests[0])
        self.assertNotIn("--ignore", tests[0])
        self.assertLess(commands.index("run --no-sync alembic upgrade head"), commands.index(tests[0]))
        self.assertTrue(any("--min-lines 60 --min-branches 33.5" in c for c in commands))
        self.assertTrue(any("--minimum 80" in c for c in commands))

    def test_failed_suite_stops_before_coverage_gates(self) -> None:
        code, commands = self.run_ci("integration", fail_tests=True)
        self.assertEqual(code, 7)
        self.assertFalse(any("check-coverage-floor" in c for c in commands))
