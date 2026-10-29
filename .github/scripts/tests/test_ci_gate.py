from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).parents[1] / "ci_gate.py"
WORKFLOW = Path(__file__).parents[2] / "workflows" / "ci.yml"
SPEC = importlib.util.spec_from_file_location("ci_gate", SCRIPT)
assert SPEC and SPEC.loader
ci_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ci_gate
SPEC.loader.exec_module(ci_gate)


def results(value: str = "success") -> dict[str, str]:
    return {
        job: value
        for job in ci_gate.expected_jobs(
            {
                "frontend_changed": True,
                "backend_changed": True,
                "hermes_changed": True,
            }
        )
    }


class GateTests(unittest.TestCase):
    def test_independent_checks_start_after_scope_and_remain_required(self) -> None:
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        independent = {
            "frontend-image-verify",
            "backend-integration",
            "backend-image-verify",
            "hermes-contract",
        }
        for job in independent:
            with self.subTest(job=job):
                self.assertEqual(jobs[job]["needs"], "change-scope")
                self.assertIn(job, jobs["ci-gate"]["needs"])

    def test_frontend_image_is_required_for_frontend_and_shared_changes(self) -> None:
        for scope in ("frontend_changed", "shared_changed"):
            for result in ("skipped", "failure", "cancelled", "", "success"):
                with self.subTest(scope=scope, result=result):
                    job_results = results()
                    job_results["frontend-image-verify"] = result
                    checks = ci_gate.evaluate({scope: True}, job_results)
                    check = next(c for c in checks if c.job == "frontend-image-verify")
                    self.assertTrue(check.expected)
                    self.assertEqual(check.ok, result == "success")

    def test_workflow_gate_wires_every_required_result(self) -> None:
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        expected = ci_gate.expected_jobs({"shared_changed": True})
        self.assertEqual(set(jobs["ci-gate"]["needs"]), set(expected))
        evaluate = next(
            s
            for s in jobs["ci-gate"]["steps"]
            if s["name"] == "Evaluate required checks"
        )
        for job in expected:
            self.assertEqual(
                evaluate["env"][job.upper().replace("-", "_") + "_RESULT"],
                "${{ needs." + job + ".result }}",
            )

    def test_e2e_reuses_bundle_without_waiting_for_image(self) -> None:
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        quality, image, e2e = (
            jobs[job]
            for job in ("frontend-quality", "frontend-image-verify", "frontend-e2e")
        )
        self.assertEqual(image["if"], quality["if"])
        self.assertEqual(e2e["needs"], ["change-scope", "frontend-quality"])
        self.assertNotIn("continue-on-error", image)
        quality_commands = "\n".join(step.get("run", "") for step in quality["steps"])
        for command in (
            "pnpm lint",
            "pnpm typecheck",
            "pnpm test:build",
            "pnpm test:coverage",
            "--minimum 80",
            "pnpm generate:api",
            "pnpm build",
        ):
            self.assertIn(command, quality_commands)
        self.assertFalse(any("docker/" in s.get("uses", "") for s in quality["steps"]))
        build = next(s for s in image["steps"] if s.get("id") == "build")
        self.assertEqual(build["with"]["target"], "frontend")
        self.assertEqual(build["with"]["context"], ".")
        self.assertEqual(build["with"]["file"], "Dockerfile")
        self.assertIs(build["with"]["load"], True)
        self.assertEqual(build["with"]["cache-from"], "type=gha,scope=frontend")
        self.assertEqual(build["with"]["cache-to"], "type=gha,mode=max,scope=frontend")
        self.assertNotIn("continue-on-error", build)
        self.assertTrue(
            any(
                "compose.dev.yml config --no-interpolate --quiet" in s.get("run", "")
                for s in image["steps"]
            )
        )
        upload = next(
            s
            for s in quality["steps"]
            if s.get("with", {}).get("name") == "frontend-e2e-bundle"
        )
        download = next(
            s
            for s in e2e["steps"]
            if s.get("with", {}).get("name") == "frontend-e2e-bundle"
        )
        self.assertIn("upload-artifact@", upload["uses"])
        self.assertIn("download-artifact@", download["uses"])
        self.assertEqual(upload["with"]["if-no-files-found"], "error")
        self.assertIn("pnpm test:e2e:critical --grep-invert @flaky", str(e2e))
        self.assertNotIn("pnpm build", str(e2e))

    def test_metrics_cannot_mask_gate_failure_or_expand_build_permissions(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        gate = jobs["ci-gate"]
        self.assertEqual(gate["permissions"], {"contents": "read", "actions": "read"})
        self.assertNotIn("continue-on-error", gate)
        evaluate = next(
            s for s in gate["steps"] if s["name"] == "Evaluate required checks"
        )
        self.assertNotIn("continue-on-error", evaluate)
        metrics = next(
            s
            for s in gate["steps"]
            if s["name"] == "Report CI timing and cache statistics"
        )
        self.assertEqual(metrics["if"], "${{ always() }}")
        self.assertIs(metrics["continue-on-error"], True)
        self.assertGreater(gate["steps"].index(metrics), gate["steps"].index(evaluate))
        for job in ("frontend-quality", "frontend-e2e"):
            self.assertEqual(
                jobs[job]["outputs"]["pnpm_cache_hit"],
                "${{ steps.node.outputs.cache-hit }}",
            )

    def test_metadata_still_requires_security_and_scope_success(self) -> None:
        job_results = results("skipped")
        job_results["change-scope"] = "success"
        job_results["source-security"] = "success"
        self.assertTrue(all(c.ok for c in ci_gate.evaluate({}, job_results)))
        job_results["source-security"] = "failure"
        self.assertFalse(all(c.ok for c in ci_gate.evaluate({}, job_results)))

    def test_expected_jobs_must_succeed(self) -> None:
        job_results = results()
        job_results["frontend-quality"] = "skipped"
        checks = ci_gate.evaluate({"frontend_changed": True}, job_results)
        self.assertFalse(next(c for c in checks if c.job == "frontend-quality").ok)

    def test_unneeded_skips_are_allowed(self) -> None:
        job_results = results("skipped")
        job_results["change-scope"] = "success"
        job_results["source-security"] = "success"
        checks = ci_gate.evaluate({"docs_only": True}, job_results)
        self.assertTrue(all(check.ok for check in checks))

    def test_failure_and_cancelled_always_fail(self) -> None:
        for result in ("failure", "cancelled"):
            with self.subTest(result=result):
                job_results = results("skipped")
                job_results["change-scope"] = "success"
                job_results["source-security"] = "success"
                job_results["backend-quality"] = result
                checks = ci_gate.evaluate({"docs_only": True}, job_results)
                self.assertFalse(
                    next(c for c in checks if c.job == "backend-quality").ok
                )

    def test_source_security_cannot_be_skipped(self) -> None:
        job_results = results("skipped")
        job_results["change-scope"] = "success"
        checks = ci_gate.evaluate({"docs_only": True}, job_results)
        self.assertFalse(next(c for c in checks if c.job == "source-security").ok)

    def test_contract_runs_for_backend_or_hermes(self) -> None:
        for scope in ("backend_changed", "hermes_changed", "shared_changed"):
            with self.subTest(scope=scope):
                expected = ci_gate.expected_jobs({scope: True})
                self.assertTrue(expected["hermes-contract"])


if __name__ == "__main__":
    unittest.main()
