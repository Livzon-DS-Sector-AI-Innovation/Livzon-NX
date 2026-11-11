"""Exercise CI orchestration with command fakes; never connect to a database."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")


@unittest.skipUnless(BASH and Path(BASH).exists(), "Bash is required")
class BackendCIExecutionTests(unittest.TestCase):
    def run_ci(
        self,
        phase: str,
        *args: str,
        fail_tests: bool = False,
        fail_heads: bool = False,
        fail_merge: bool = False,
        isolated: bool = True,
    ) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / "dazah-backend"
            (backend / "scripts").mkdir(parents=True)
            (root / "scripts").mkdir()
            (backend / "uv.lock").touch()
            shutil.copyfile(
                ROOT / "dazah-backend/scripts/ci.sh", backend / "scripts/ci.sh"
            )
            for script in (
                backend / "scripts/ruff-changed.sh",
                root / "scripts/wait-for-database.sh",
            ):
                script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            # BASH_ENV functions replace external commands, preserving set -e behavior.
            fake = root / "fake.sh"
            fake.write_text(
                "uv() {\n"
                '  printf "%s\\n" "$*" >> "$CI_TEST_LOG"\n'
                '  if [[ "$*" == "run --no-sync alembic heads" ]]; then\n'
                '    echo "abc (head)"\n'
                '    if [[ "$CI_TEST_FAIL_HEADS" == "1" ]]; then return 9; fi\n'
                "  fi\n"
                '  if [[ "$*" == *pytest* && "$CI_TEST_FAIL" == "1" ]]; then return 7; fi\n'
                '  if [[ "$*" == *"ci_pytest_shard combine"* && "$CI_TEST_FAIL_MERGE" == "1" ]]; then return 8; fi\n'
                "  return 0\n"
                "}\n"
                "git() { return 0; }\n",
                encoding="utf-8",
            )
            log = root / "commands.log"
            log.touch()
            result = subprocess.run(
                [str(BASH), str(backend / "scripts/ci.sh"), phase, *args],
                env={
                    **os.environ,
                    "BASH_ENV": fake.as_posix(),
                    "CI_TEST_LOG": log.as_posix(),
                    "CI_TEST_FAIL": "1" if fail_tests else "0",
                    "CI_TEST_FAIL_HEADS": "1" if fail_heads else "0",
                    "CI_TEST_FAIL_MERGE": "1" if fail_merge else "0",
                    "APP_ENV": "test",
                    "TEST_DATABASE_URL": "synthetic-test",
                    "DATABASE_URL": "synthetic-test" if isolated else "synthetic-other",
                },
                capture_output=True,
                text=True,
            )
            return result.returncode, log.read_text(encoding="utf-8").splitlines()

    def test_quality_does_not_start_database_or_repeat_tests(self) -> None:
        code, commands = self.run_ci("quality")
        self.assertEqual(code, 0)
        self.assertTrue(any("mypy app/core" in command for command in commands))
        self.assertFalse(
            any("pytest" in command or "alembic" in command for command in commands)
        )

    def test_integration_runs_complete_suite_once_after_migration(self) -> None:
        code, commands = self.run_ci("integration")
        self.assertEqual(code, 0)
        tests = [command for command in commands if "pytest" in command]
        self.assertEqual(len(tests), 1)
        self.assertIn("--cov --cov-branch", tests[0])
        self.assertNotIn("--ignore", tests[0])
        self.assertLess(
            commands.index("run --no-sync alembic upgrade head"),
            commands.index(tests[0]),
        )
        self.assertTrue(
            any("--min-lines 60 --min-branches 33.5" in c for c in commands)
        )
        self.assertTrue(any("--minimum 80" in c for c in commands))

    def test_failed_suite_stops_before_coverage_gates(self) -> None:
        code, commands = self.run_ci("integration", fail_tests=True)
        self.assertEqual(code, 7)
        self.assertFalse(any("check-coverage-floor" in c for c in commands))

    def test_shard_migration_stops_when_alembic_heads_command_fails(self) -> None:
        code, commands = self.run_ci("migrate-test-database", fail_heads=True)
        self.assertEqual(code, 9)
        self.assertEqual(commands, ["run --no-sync alembic heads"])
        code, commands = self.run_ci("migrate-test-database")
        self.assertEqual(code, 0)
        self.assertEqual(
            commands[:2],
            [
                "run --no-sync alembic heads",
                "run --no-sync alembic upgrade head",
            ],
        )
        self.assertTrue(commands[2].startswith("run --no-sync python -c"))
        self.assertIn("        await seed_menus(session)", commands)

    def test_shard_entry_points_refuse_unmapped_database(self) -> None:
        for phase, args in (
            ("migrate-test-database", ()),
            ("integration-shard", ("2", "reports")),
        ):
            with self.subTest(phase=phase):
                code, commands = self.run_ci(phase, *args, isolated=False)
                self.assertEqual(code, 2)
                self.assertEqual(commands, [])

    def test_shard_and_coverage_commands_preserve_failure_and_gate_order(self) -> None:
        code, commands = self.run_ci(
            "integration-shard", "2", "reports", fail_tests=True
        )
        self.assertEqual(code, 7)
        self.assertEqual(
            commands, ["run --no-sync python -m scripts.ci_pytest_shard run 2 reports"]
        )
        code, commands = self.run_ci("merge-shard-coverage", "reports", fail_merge=True)
        self.assertEqual(code, 8)
        self.assertEqual(
            commands,
            ["run --no-sync python -m scripts.ci_pytest_shard combine reports"],
        )
        code, commands = self.run_ci("merge-shard-coverage", "reports")
        self.assertEqual(code, 0)
        self.assertIn("ci_pytest_shard combine reports", commands[0])
        self.assertIn("--min-lines 60 --min-branches 33.5", commands[1])
        self.assertIn("--minimum 80", commands[2])

    def test_split_phases_keep_install_migrations_tests_and_coverage_separate(
        self,
    ) -> None:
        commands_by_phase = {}
        for phase in (
            "quality-checks",
            "prepare-integration",
            "integration-tests",
            "coverage",
        ):
            code, commands_by_phase[phase] = self.run_ci(phase)
            self.assertEqual(code, 0)
            self.assertFalse(
                any(c.startswith("sync ") for c in commands_by_phase[phase])
            )
        self.assertTrue(
            any(
                "alembic upgrade head" in c
                for c in commands_by_phase["prepare-integration"]
            )
        )
        self.assertFalse(
            any("pytest" in c for c in commands_by_phase["prepare-integration"])
        )
        self.assertEqual(
            sum("pytest" in c for c in commands_by_phase["integration-tests"]), 1
        )
        self.assertFalse(
            any("alembic" in c for c in commands_by_phase["integration-tests"])
        )
        self.assertTrue(
            any(
                "--min-lines 60 --min-branches 33.5" in c
                for c in commands_by_phase["coverage"]
            )
        )
        self.assertTrue(any("--minimum 80" in c for c in commands_by_phase["coverage"]))


@unittest.skipUnless(BASH and Path(BASH).exists(), "Bash is required")
class HermesCIExecutionTests(unittest.TestCase):
    def run_hermes(self, mode: str, fail_tests: bool = False) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Hermes-Lite"
            (project / "scripts").mkdir(parents=True)
            (project / "uv.lock").touch()
            shutil.copyfile(
                ROOT / "Hermes-Lite/scripts/ci.sh", project / "scripts/ci.sh"
            )
            fake, log = root / "fake.sh", root / "commands.log"
            fake.write_text(
                "uv() {\n"
                '  printf "%s\\n" "$*" >> "$CI_TEST_LOG"\n'
                '  if [[ "$*" == *pytest* && "$CI_TEST_FAIL" == "1" ]]; then return 7; fi\n'
                "  return 0\n"
                "}\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [str(BASH), str(project / "scripts/ci.sh"), mode],
                env={
                    **os.environ,
                    "BASH_ENV": fake.as_posix(),
                    "CI_TEST_LOG": log.as_posix(),
                    "CI_TEST_FAIL": "1" if fail_tests else "0",
                },
                capture_output=True,
                text=True,
            )
            return result.returncode, log.read_text(encoding="utf-8").splitlines()

    def test_checks_do_not_repeat_install_and_preserve_full_suite(self):
        code, commands = self.run_hermes("checks")
        self.assertEqual(code, 0)
        self.assertFalse(any(c.startswith("sync ") for c in commands))
        self.assertEqual(sum("pytest" in c for c in commands), 1)
        self.assertTrue(any("ruff check" in c for c in commands))
        code, commands = self.run_hermes("all")
        self.assertEqual(code, 0)
        self.assertEqual(commands[0], "sync --frozen --extra dev")
        code, _ = self.run_hermes("checks", fail_tests=True)
        self.assertEqual(code, 7)
