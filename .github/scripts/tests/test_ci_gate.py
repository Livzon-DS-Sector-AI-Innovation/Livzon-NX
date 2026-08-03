from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "ci_gate.py"
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
