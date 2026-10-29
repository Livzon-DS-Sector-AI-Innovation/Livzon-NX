"""CI reporting tests use synthetic API/build records and never access a token."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "ci_metrics.py"
SPEC = importlib.util.spec_from_file_location("ci_metrics", SCRIPT)
assert SPEC and SPEC.loader
metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metrics)


class MetricsTests(unittest.TestCase):
    def test_duration_ignores_missing_and_invalid_intervals(self) -> None:
        self.assertEqual(
            metrics.seconds("2026-10-29T00:00:00Z", "2026-10-29T08:01:02+08:00"), 62
        )
        self.assertIsNone(metrics.seconds(None, "2026-10-29T00:00:00Z"))
        self.assertIsNone(metrics.seconds("2026-10-29T00:00:00Z", None))
        self.assertIsNone(
            metrics.seconds("2026-10-29T00:00:02Z", "2026-10-29T00:00:00Z")
        )

    def test_build_cache_exports_only_valid_counters(self) -> None:
        record = {
            "Status": "completed",
            "NumCachedSteps": 3,
            "NumTotalSteps": 12,
            "BuildArgs": [{"Name": "private", "Value": "synthetic-sensitive-value"}],
        }
        with patch.object(
            metrics.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, json.dumps(record)),
        ) as command:
            result = metrics.build_cache('{"buildx.build.ref":"builder/node/ref"}')
        self.assertEqual(result, {"cached_steps": 3, "total_steps": 12})
        self.assertEqual(
            command.call_args.args[0],
            [
                "docker",
                "buildx",
                "--builder",
                "builder",
                "history",
                "inspect",
                "--format",
                "json",
                "ref",
            ],
        )
        self.assertEqual(command.call_args.kwargs["timeout"], 30)
        self.assertNotIn("synthetic-sensitive", json.dumps(result))

    def test_build_cache_unavailable_is_never_a_zero_hit(self) -> None:
        for record in (
            {},
            {"Status": "failed", "NumCachedSteps": 0, "NumTotalSteps": 10},
            {"Status": "completed", "NumCachedSteps": 0, "NumTotalSteps": 0},
            {"Status": "completed", "NumCachedSteps": 11, "NumTotalSteps": 10},
            {"Status": "completed", "NumCachedSteps": True, "NumTotalSteps": 10},
            {"Status": "completed", "NumCachedSteps": "3", "NumTotalSteps": 10},
        ):
            with (
                self.subTest(record=record),
                patch.object(
                    metrics.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0, json.dumps(record)),
                ),
            ):
                self.assertEqual(
                    metrics.build_cache('{"buildx.build.ref":"ref"}'),
                    {"cached_steps": None, "total_steps": None},
                )
        for failure in (
            OSError(),
            subprocess.TimeoutExpired("docker", 30),
            subprocess.CalledProcessError(1, "docker"),
        ):
            with (
                self.subTest(failure=failure),
                patch.object(metrics.subprocess, "run", side_effect=failure),
            ):
                self.assertIsNone(
                    metrics.build_cache('{"buildx.build.ref":"ref"}')["cached_steps"]
                )
        for metadata in (
            "",
            "not-json",
            "[]",
            '{"buildx.build.ref":"--help"}',
            '{"buildx.build.ref":"builder/record"}',
            '{"buildx.build.ref":"builder/node/--help"}',
            '{"buildx.build.ref":"/node/ref"}',
        ):
            with (
                self.subTest(metadata=metadata),
                patch.object(metrics.subprocess, "run") as command,
            ):
                self.assertIsNone(metrics.build_cache(metadata)["cached_steps"])
                command.assert_not_called()

    def test_native_record_id_uses_current_builder(self) -> None:
        with patch.object(
            metrics.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                [], 0, '{"Status":"completed","NumCachedSteps":0,"NumTotalSteps":10}'
            ),
        ) as command:
            self.assertEqual(
                metrics.build_cache('{"buildx.build.ref":"record"}'),
                {"cached_steps": 0, "total_steps": 10},
            )
        self.assertEqual(
            command.call_args.args[0],
            ["docker", "buildx", "history", "inspect", "--format", "json", "record"],
        )

    def test_cache_hits_misses_and_missing_outputs_have_distinct_denominators(
        self,
    ) -> None:
        report = metrics.cache_observations(
            {
                "frontend-quality": {"outputs": {"pnpm_cache_hit": "true"}},
                "frontend-e2e": {"outputs": {"pnpm_cache_hit": "false"}},
                "frontend-image-verify": {
                    "outputs": {"cached_steps": "3", "total_steps": "12"}
                },
            }
        )
        self.assertEqual(report["pnpm_hit_percent"], 50)
        self.assertEqual(report["docker"]["cached_step_percent"], 25)
        self.assertEqual(
            metrics.cache_observations({})["pnpm"]["frontend-quality"], "unavailable"
        )
        self.assertIsNone(metrics.cache_observations({})["pnpm_hit_percent"])
        self.assertIsNone(
            metrics.cache_observations({})["docker"]["cached_step_percent"]
        )
        self.assertEqual(
            metrics.cache_observations(
                {"frontend-quality": {"outputs": {"pnpm_cache_hit": "true"}}}
            )["pnpm_hit_percent"],
            100,
        )

    def test_jobs_are_paginated_with_current_attempt_in_every_request(self) -> None:
        with patch.object(
            metrics,
            "api_json",
            side_effect=[
                {"jobs": [{"name": "job"}] * 100},
                {"jobs": [{"name": "last"}]},
            ],
        ) as api:
            self.assertEqual(len(metrics.collect_jobs("owner/repo", "123", "2")), 101)
        self.assertEqual(
            [call.args[0] for call in api.call_args_list],
            [
                "/repos/owner/repo/actions/runs/123/attempts/2/jobs?per_page=100&page=1",
                "/repos/owner/repo/actions/runs/123/attempts/2/jobs?per_page=100&page=2",
            ],
        )

    def test_skipped_jobs_with_null_steps_are_not_zero_duration_measurements(
        self,
    ) -> None:
        observed = metrics.observations(
            [
                {
                    "name": "Frontend Quality",
                    "status": "completed",
                    "conclusion": "skipped",
                    "started_at": "2026-10-29T00:00:00Z",
                    "completed_at": "2026-10-29T00:00:00Z",
                    "steps": None,
                },
            ]
        )
        self.assertIsNone(observed[0]["duration_seconds"])
        self.assertEqual(observed[0]["steps"], [])

    def run_report(self, api_failure: bool = False) -> tuple[dict, str]:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metrics.json"
            summary = Path(directory) / "summary.md"
            job = {
                "name": "Frontend | Quality",
                "status": "completed",
                "conclusion": "failure",
                "started_at": "2026-10-29T00:00:00Z",
                "completed_at": "2026-10-29T00:02:00Z",
                "steps": [
                    {
                        "name": "coverage",
                        "conclusion": "failure",
                        "started_at": "2026-10-29T00:00:30Z",
                        "completed_at": "2026-10-29T00:02:00Z",
                    }
                ],
                "private": "synthetic-private-data",
            }
            responses = (
                [OSError("synthetic-private-error")]
                if api_failure
                else [
                    {
                        "jobs": [
                            job,
                            {"name": "CI Gate", "status": "in_progress", "steps": []},
                        ]
                    },
                    {"run_started_at": "2026-10-29T00:00:00Z"},
                ]
            )
            env = {
                "GITHUB_REPOSITORY": "owner/repo",
                "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "2",
                "CI_NEEDS_JSON": "{}",
                "GITHUB_STEP_SUMMARY": str(summary),
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(
                    sys, "argv", ["ci_metrics.py", "report", "--output", str(output)]
                ),
                patch.object(metrics, "api_json", side_effect=responses),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                self.assertEqual(metrics.main(), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            text = summary.read_text(encoding="utf-8")
            self.assertNotIn(
                "synthetic-private", json.dumps(report) + text + stdout.getvalue()
            )
            return report, text

    def test_report_includes_failures_and_partial_gate_without_claiming_final_duration(
        self,
    ) -> None:
        report, text = self.run_report()
        self.assertEqual(report["attempt"], "2")
        self.assertEqual(report["timing_status"], "available")
        self.assertEqual(report["jobs"][0]["duration_seconds"], 120)
        self.assertEqual(report["jobs"][0]["steps"][0]["duration_seconds"], 90)
        self.assertIsNone(report["jobs"][1]["duration_seconds"])
        self.assertIn("failure", text)
        self.assertIn("Frontend \\| Quality", text)
        self.assertIn("not final workflow duration", text)

    def test_api_failure_keeps_report_explicitly_unavailable_and_redacts_errors(
        self,
    ) -> None:
        report, text = self.run_report(api_failure=True)
        self.assertEqual(report["timing_status"], "unavailable")
        self.assertIsNone(report["elapsed_to_report_seconds"])
        self.assertIn("Timing API unavailable", text)

    def test_build_cache_command_writes_only_numeric_or_empty_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.txt"
            with (
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}),
                patch.object(sys, "argv", ["ci_metrics.py", "build-cache"]),
                patch.object(
                    metrics,
                    "build_cache",
                    return_value={"cached_steps": None, "total_steps": None},
                ),
            ):
                self.assertEqual(metrics.main(), 0)
            self.assertEqual(
                output.read_text(encoding="utf-8"), "cached_steps=\ntotal_steps=\n"
            )


if __name__ == "__main__":
    unittest.main()
