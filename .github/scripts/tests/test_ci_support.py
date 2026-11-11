"""Test phase failure propagation and CI prerequisites without live services."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "ci_support.py"
SPEC = importlib.util.spec_from_file_location("ci_support", SCRIPT)
assert SPEC and SPEC.loader
support = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(support)


class SupportTests(unittest.TestCase):
    def test_coverage_install_uses_only_locked_reporting_group(self):
        with patch.object(support, "run_phase", return_value=0) as run:
            self.assertEqual(support.install_project("coverage"), 0)
        self.assertEqual(
            run.call_args.args,
            (
                "coverage-install",
                "dependencies",
                ["uv", "sync", "--frozen", "--only-group", "ci-coverage"],
            ),
        )
        self.assertEqual(run.call_args.kwargs["cwd"], support.ROOT / "dazah-backend")
        self.assertTrue(run.call_args.kwargs["install"])

    def test_install_is_frozen_bounded_and_does_not_repeat_failed_commands(self):
        for project in ("backend", "hermes"):
            with (
                self.subTest(project=project),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory) / "phases.jsonl"
                with (
                    patch.dict(os.environ, {"CI_PHASE_FILE": str(path)}),
                    patch.object(
                        support.subprocess,
                        "run",
                        return_value=SimpleNamespace(returncode=9),
                    ) as run,
                ):
                    self.assertEqual(support.install_project(project), 9)
                run.assert_called_once()
                self.assertEqual(
                    run.call_args.args[0][:5],
                    ["uv", "sync", "--frozen", "--extra", "dev"],
                )
                self.assertEqual(run.call_args.kwargs["timeout"], 600)
                self.assertEqual(run.call_args.kwargs["env"]["UV_HTTP_RETRIES"], "3")
                self.assertEqual(run.call_args.kwargs["env"]["UV_HTTP_TIMEOUT"], "60")
                self.assertEqual(
                    run.call_args.kwargs["env"]["UV_CONCURRENT_DOWNLOADS"], "8"
                )
                self.assertEqual(support.read_phases(path)[0]["exit_code"], 9)

    def test_test_failures_are_not_retried_or_given_install_policy(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {"CI_PHASE_FILE": str(Path(directory) / "phases.jsonl")},
                clear=True,
            ),
            patch.object(
                support.subprocess, "run", return_value=SimpleNamespace(returncode=7)
            ) as run,
        ):
            self.assertEqual(support.run_phase("backend-tests", "tests", ["pytest"]), 7)
            run.assert_called_once()
            self.assertNotIn("UV_HTTP_RETRIES", run.call_args.kwargs["env"])
            self.assertIsNone(run.call_args.kwargs["timeout"])

    def test_timeout_and_missing_binary_fail_and_are_recorded(self):
        for exception, expected in (
            (subprocess.TimeoutExpired("uv", 600), 124),
            (OSError(), 127),
        ):
            with (
                tempfile.TemporaryDirectory() as directory,
                patch.dict(
                    os.environ, {"CI_PHASE_FILE": str(Path(directory) / "phases.jsonl")}
                ),
                patch.object(support.subprocess, "run", side_effect=exception),
            ):
                self.assertEqual(support.install_project("backend"), expected)
                self.assertEqual(
                    support.read_phases(support.phase_file())[0]["exit_code"], expected
                )

    def test_metric_write_failure_cannot_mask_a_test_failure(self):
        with (
            patch.object(
                support.subprocess, "run", return_value=SimpleNamespace(returncode=7)
            ),
            patch.object(
                support, "phase_file", return_value=Path("missing-parent/phases.jsonl")
            ),
        ):
            self.assertEqual(support.run_phase("tests", "tests", ["pytest"]), 7)

    def test_export_whitelists_fields_and_handles_absent_phase_data(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = (
                Path(directory) / "phases.jsonl",
                Path(directory) / "outputs",
            )
            self.assertEqual(support.read_phases(source), [])
            source.write_text(
                json.dumps(
                    {
                        "phase": "tests",
                        "category": "tests",
                        "exit_code": 7,
                        "duration_seconds": 2.0,
                        "failure_category": "tests",
                        "private": "synthetic-sensitive",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                patch.dict(
                    os.environ,
                    {"CI_PHASE_FILE": str(source), "GITHUB_OUTPUT": str(output)},
                ),
                patch.object(sys, "argv", ["ci_support.py", "summarize"]),
            ):
                self.assertEqual(support.main(), 0)
            exported = output.read_text(encoding="utf-8")
            self.assertTrue(exported.startswith("phases="))
            self.assertNotIn("synthetic-sensitive", exported)
            self.assertEqual(
                json.loads(exported.removeprefix("phases="))[0]["exit_code"], 7
            )

    def test_tools_preflight_rejects_version_drift(self):
        with (
            patch.object(
                Path, "read_text", return_value='ID=ubuntu\nVERSION_ID="24.04"'
            ),
            patch.object(support.platform, "system", return_value="Linux"),
            patch.object(support.platform, "python_version", return_value="3.12.9"),
            patch.dict(os.environ, {"PYTHON_VERSION": "3.12", "UV_VERSION": "0.13.4"}),
            patch.object(
                support.subprocess, "check_output", return_value="uv 0.13.4 (test)"
            ),
        ):
            support.preflight("tools")
            with patch.object(
                support.subprocess, "check_output", return_value="uv 0.13.5"
            ):
                with self.assertRaisesRegex(ValueError, "uv version"):
                    support.preflight("tools")

    def test_backend_preflight_checks_actual_font_rendering(self):
        font = SimpleNamespace(
            getmask=lambda text: SimpleNamespace(getbbox=lambda: (0, 0, 20, 20))
        )
        image_font = SimpleNamespace(truetype=lambda *args: font)
        with (
            patch.dict(sys.modules, {"PIL": SimpleNamespace(ImageFont=image_font)}),
            patch.object(support.shutil, "which", return_value="/bin/tool"),
        ):
            support.preflight("backend")
            with patch.object(
                image_font, "truetype", side_effect=OSError("missing font")
            ):
                with self.assertRaises(OSError):
                    support.preflight("backend")


if __name__ == "__main__":
    unittest.main()
