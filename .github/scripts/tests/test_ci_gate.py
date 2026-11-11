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
    def test_backend_builds_use_authenticated_action_and_separate_layer_caches(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        for job, filename, scope, suffix in (
            ("backend-image-verify", "Dockerfile", "backend", ""),
            ("backend-dev-image-verify", "Dockerfile.dev", "backend-dev", "-dev"),
        ):
            with self.subTest(scope=scope):
                steps = jobs[job]["steps"]
                build = next(step for step in steps if step.get("id") == "build")
                self.assertEqual(
                    build["uses"],
                    "docker/build-push-action@10e90e3645eae34f1e60eeb005ba3a3d33f178e8",
                )
                self.assertEqual(build["with"]["file"], filename)
                self.assertEqual(build["with"]["context"], ".")
                self.assertEqual(build["with"]["target"], "backend")
                self.assertIs(build["with"]["load"], True)
                self.assertFalse(build["with"].get("push", False))
                self.assertEqual(build["with"]["tags"], "${{ env.IMAGE_TAG }}")
                self.assertEqual(
                    jobs[job]["env"]["IMAGE_TAG"],
                    "dazah-backend:ci-${{ github.sha }}" + suffix,
                )
                self.assertEqual(build["with"]["cache-from"], f"type=gha,scope={scope}")
                self.assertIn("mode=max", build["with"]["cache-to"])
                self.assertIn(f"scope={scope}", build["with"]["cache-to"])
                self.assertNotIn("ignore-error", build["with"]["cache-to"])
                self.assertNotIn("continue-on-error", build)

    def test_backend_images_keep_runtime_checks_and_production_security_gate(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        production, development = (
            {step["name"]: step for step in jobs[job]["steps"]}
            for job in ("backend-image-verify", "backend-dev-image-verify")
        )
        for name in (
            "Verify Chromium as app",
            "Verify Chinese document conversion as app",
        ):
            self.assertEqual(production[name], development[name])
            self.assertIn(
                '--user app --entrypoint .venv/bin/python "$IMAGE_TAG"',
                production[name]["run"],
            )
            self.assertNotIn("continue-on-error", production[name])
        for name in (
            "Generate complete image vulnerability report",
            "Enforce image vulnerability gate",
            "Upload image vulnerability report",
            "Migrate container database",
            "Run bounded health and smoke checks",
            "Clean up containers",
        ):
            self.assertIn(name, production)
            self.assertNotIn(name, development)
        gate = production["Enforce image vulnerability gate"]["with"]
        self.assertEqual(gate["severity"], "HIGH,CRITICAL")
        self.assertEqual(gate["exit-code"], "1")
        self.assertIs(gate["ignore-unfixed"], True)

    def test_system_prerequisites_are_provided_by_the_same_ci_tools_image(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        producer = jobs["ci-tools"]
        upload = next(
            s for s in producer["steps"] if s["name"] == "Upload CI tools image"
        )
        self.assertEqual(upload["with"]["if-no-files-found"], "error")
        build = next(s for s in producer["steps"] if s.get("id") == "build")
        self.assertEqual(build["with"]["file"], "docker/Dockerfile.ci-tools")
        self.assertFalse(build["with"].get("push", False))
        for job in ("backend-migrations", "backend-integration", "hermes-contract"):
            with self.subTest(job=job):
                self.assertEqual(jobs[job]["needs"], ["change-scope", "ci-tools"])
                steps = {s["name"]: s for s in jobs[job]["steps"]}
                self.assertEqual(
                    steps["Download CI tools image"]["with"]["name"],
                    upload["with"]["name"],
                )
                load = steps["Load verified CI tools image"]
                self.assertEqual(
                    load["env"]["CI_TOOLS_IMAGE_ID"],
                    "${{ needs.ci-tools.outputs.image_id }}",
                )
                self.assertNotIn("continue-on-error", load)
                preflight = steps["Verify backend environment"]
                self.assertIn("ci-tools.sh {0}", preflight["shell"])
                self.assertIn("preflight backend", preflight["run"])
                self.assertNotIn("apt-get", str(steps))

    def test_repository_policy_and_security_start_without_waiting_for_scope(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        for job in ("change-scope", "repository-policy", "source-security"):
            self.assertNotIn("needs", jobs[job])
            self.assertNotIn("if", jobs[job])
        scope_steps = jobs["change-scope"]["steps"]
        self.assertEqual(
            [step["run"] for step in scope_steps if "run" in step],
            ["python3 .github/scripts/change_scope.py"],
        )
        commands = "\n".join(
            s.get("run", "") for s in jobs["repository-policy"]["steps"]
        )
        for command in (
            "scripts/check-agent-instruction-bridges.py",
            "pytest .github/scripts/tests scripts/tests -q",
            "scripts/check-test-impact.py",
        ):
            self.assertIn(command, commands)

    def test_python_phases_and_environment_remain_blocking(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        self.assertEqual(workflow["env"]["UV_VERSION"], "0.13.4")
        for job in jobs.values():
            self.assertEqual(job["runs-on"], "ubuntu-24.04")
        for name in (
            "backend-quality",
            "backend-migrations",
            "backend-integration",
            "backend-coverage",
            "hermes-quality",
            "hermes-contract",
        ):
            steps = jobs[name]["steps"]
            setup = next(s for s in steps if s.get("id") == "uv")
            python = next(s for s in steps if s["name"] == "Set up Python")
            self.assertLess(steps.index(python), steps.index(setup))
            self.assertEqual(setup["with"]["version"], "${{ env.UV_VERSION }}")
            for step in steps:
                if (
                    "ci_support.py" in step.get("run", "")
                    and step.get("id") != "phases"
                ):
                    self.assertNotIn("continue-on-error", step)
                    self.assertNotIn("always()", step.get("if", ""))
            if name != "backend-integration":
                self.assertEqual(
                    jobs[name]["outputs"]["uv_cache_hit"],
                    "${{ steps.uv.outputs.cache-hit }}",
                )
                export = next(s for s in steps if s.get("id") == "phases")
                self.assertEqual(export["if"], "${{ always() }}")
        contract_steps = jobs["hermes-contract"]["steps"]
        install_hermes = next(
            step
            for step in contract_steps
            if step["name"] == "Install Hermes contract dependencies"
        )
        self.assertEqual(
            install_hermes["run"], "python3 .github/scripts/ci_support.py install hermes"
        )
        contract = str(contract_steps)
        for filename in (
            "test_agent_v2_contracts.py",
            "test_tool_registry_executor.py",
            "test_user_tool_api.py",
            "test_dazah_feishu_tool_payload.py",
            "test_dazah_backend_contract.py",
        ):
            self.assertIn(filename, contract)
        self.assertIn(
            'chromium.launch({channel:"chromium"})', str(jobs["frontend-e2e"])
        )

    def test_independent_checks_start_after_scope_and_remain_required(self) -> None:
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        independent = {
            "frontend-quality",
            "frontend-build",
            "frontend-unit",
            "frontend-image-verify",
            "backend-image-verify",
            "backend-dev-image-verify",
            "ci-tools",
        }
        for job in independent:
            with self.subTest(job=job):
                self.assertEqual(jobs[job]["needs"], "change-scope")
                self.assertIn(job, jobs["ci-gate"]["needs"])

    def test_backend_shards_migrate_independent_services_and_merge_all_artifacts(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        migrations, integration, coverage = (
            jobs[job]
            for job in ("backend-migrations", "backend-integration", "backend-coverage")
        )
        self.assertEqual(
            integration["strategy"],
            {
                "fail-fast": False,
                "matrix": {"shard": [1, 2, 3, 4]},
            },
        )
        self.assertEqual(integration["services"], migrations["services"])
        self.assertEqual(set(integration["services"]), {"postgres", "redis"})
        self.assertNotIn("services", coverage)
        self.assertEqual(coverage["needs"], ["change-scope", "backend-integration"])
        for job in (migrations, integration, coverage):
            self.assertNotIn("continue-on-error", job)
        self.assertTrue(
            any(
                "scripts/ci.sh prepare-integration" in step.get("run", "")
                for step in migrations["steps"]
            )
        )
        steps = {step["name"]: step for step in integration["steps"]}
        names = list(steps)
        pipeline = [
            "Install backend dependencies",
            "Verify backend environment",
            "Migrate backend shard database",
            "Run backend test shard",
        ]
        self.assertEqual([name for name in names if name in pipeline], pipeline)
        self.assertIn("uv cache ${{ steps.uv.outputs.cache-hit }}", steps)
        self.assertIn("scripts/ci.sh migrate-test-database", steps[pipeline[-2]]["run"])
        run = steps[pipeline[-1]]
        self.assertEqual(run["env"]["SHARD"], "${{ matrix.shard }}")
        self.assertIn(
            'integration-shard "$SHARD" "$RUNNER_TEMP/backend-integration-shard-$SHARD"',
            run["run"],
        )
        upload = steps["Upload backend shard reports"]["with"]
        self.assertEqual(
            upload["name"], "backend-integration-shard-${{ matrix.shard }}"
        )
        self.assertEqual(upload["if-no-files-found"], "error")
        merge = {step["name"]: step for step in coverage["steps"]}
        download = merge["Download backend shard reports"]["with"]
        self.assertEqual(download["pattern"], "backend-integration-shard-*")
        self.assertIs(download["merge-multiple"], False)
        self.assertIn(
            'merge-shard-coverage "$RUNNER_TEMP/backend-shards"',
            merge["Enforce backend coverage gates"]["run"],
        )

    def test_expected_backend_jobs_must_succeed(self):
        for job in (
            "backend-migrations",
            "backend-integration",
            "backend-coverage",
            "backend-image-verify",
            "backend-dev-image-verify",
        ):
            for scope in ("backend_changed", "shared_changed"):
                for result in ("skipped", "failure", "cancelled", "", "success"):
                    with self.subTest(job=job, scope=scope, result=result):
                        job_results = results()
                        job_results[job] = result
                        check = next(
                            item
                            for item in ci_gate.evaluate({scope: True}, job_results)
                            if item.job == job
                        )
                        self.assertTrue(check.expected)
                        self.assertEqual(check.ok, result == "success")

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

    def test_e2e_and_quarantine_wait_only_for_the_production_bundle(self) -> None:
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        quality, production, image, e2e, quarantine = (
            jobs[job]
            for job in (
                "frontend-quality",
                "frontend-build",
                "frontend-image-verify",
                "frontend-e2e",
                "frontend-flaky-quarantine",
            )
        )
        self.assertEqual(e2e["needs"], ["change-scope", "frontend-build"])
        self.assertEqual(quarantine["needs"], e2e["needs"])
        self.assertIs(quarantine["continue-on-error"], True)
        self.assertNotIn("continue-on-error", image)
        quality_commands = "\n".join(step.get("run", "") for step in quality["steps"])
        for command in (
            "pnpm lint",
            "pnpm typecheck",
            "pnpm test:build",
            "node --test scripts/plan-critical-e2e-shard.test.mjs",
            "pnpm generate:api",
            "generate-page-routes.py --check",
        ):
            self.assertIn(command, quality_commands)
        self.assertNotIn("pnpm build", quality_commands)
        self.assertNotIn("pnpm test:coverage", quality_commands)
        self.assertIn("pnpm build", [step.get("run") for step in production["steps"]])
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
            for s in production["steps"]
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
        stable = next(
            step
            for step in e2e["steps"]
            if step["name"] == "Run stable critical Playwright tests"
        )
        self.assertEqual(stable["env"]["SHARD"], "${{ matrix.shard }}")
        for command in (
            "pnpm test:e2e:critical --grep-invert @flaky --list --reporter=json",
            'node scripts/plan-critical-e2e-shard.mjs "$inventory" "$SHARD" "$excluded"',
            '--reporter=html,json --test-list-invert="$excluded"',
            'node scripts/plan-critical-e2e-shard.mjs "$inventory" "$SHARD" "$excluded" "$results"',
        ):
            self.assertIn(command, stable["run"])
        self.assertNotIn("pnpm build", str(e2e))
        self.assertEqual(
            e2e["strategy"],
            {
                "fail-fast": False,
                "matrix": {"shard": [1, 2, 3, 4]},
            },
        )
        report = next(
            step for step in e2e["steps"] if step["name"] == "Upload stable E2E report"
        )
        self.assertEqual(
            report["with"]["name"], "frontend-e2e-report-${{ matrix.shard }}"
        )
        self.assertEqual(report["if"], "${{ always() }}")

    def test_frontend_coverage_requires_all_vitest_shards_and_both_coverage_gates(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        unit = jobs["frontend-unit"]
        coverage = jobs["frontend-coverage"]
        self.assertEqual(
            unit["strategy"],
            {
                "fail-fast": False,
                "matrix": {"shard": [1, 2, 3]},
            },
        )
        self.assertEqual(coverage["needs"], ["change-scope", "frontend-unit"])
        generate = next(
            step
            for step in unit["steps"]
            if step["name"] == "Generate API contract for unit tests"
        )
        shard = next(
            step
            for step in unit["steps"]
            if step["name"] == "Run Vitest shard with coverage"
        )
        self.assertEqual(generate["run"], "pnpm generate:api")
        self.assertLess(unit["steps"].index(generate), unit["steps"].index(shard))
        self.assertIn(
            'pnpm test:coverage --shard="$SHARD/3" --reporter=blob', shard["run"]
        )
        self.assertEqual(shard["env"]["SHARD"], "${{ matrix.shard }}")
        upload = next(
            step
            for step in unit["steps"]
            if step["name"] == "Upload Vitest shard report"
        )
        self.assertEqual(upload["with"]["name"], "frontend-vitest-${{ matrix.shard }}")
        self.assertEqual(upload["with"]["if-no-files-found"], "error")
        download = next(
            step
            for step in coverage["steps"]
            if step["name"] == "Download Vitest shard reports"
        )
        self.assertEqual(download["with"]["pattern"], "frontend-vitest-*")
        self.assertIs(download["with"]["merge-multiple"], True)
        merge = next(
            step
            for step in coverage["steps"]
            if step["name"] == "Merge Vitest reports and enforce coverage gates"
        )
        self.assertIn("for shard in 1 2 3", merge["run"])
        self.assertIn('if [[ ! -s "$report" ]]', merge["run"])
        self.assertIn("exit 1", merge["run"])
        self.assertIn(
            '--merge-reports="$RUNNER_TEMP/frontend-vitest" --coverage', merge["run"]
        )
        self.assertIn("--coverage-file coverage/cobertura-coverage.xml", merge["run"])
        self.assertIn("--minimum 80", merge["run"])
        for job in (unit, coverage, jobs["frontend-e2e"]):
            self.assertNotIn("continue-on-error", job)
            for step in job["steps"]:
                self.assertNotIn("continue-on-error", step)

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
        for job in ("frontend-quality", "frontend-build", "frontend-coverage"):
            self.assertEqual(
                jobs[job]["outputs"]["pnpm_cache_hit"],
                "${{ steps.node.outputs.cache-hit }}",
            )
        for job in ("frontend-unit", "frontend-e2e"):
            self.assertIn(
                "pnpm store cache ${{ steps.node.outputs.cache-hit }}",
                [step["name"] for step in jobs[job]["steps"]],
            )

    def test_metadata_still_requires_policy_security_and_scope_success(self) -> None:
        job_results = results("skipped")
        always_required = ("change-scope", "repository-policy", "source-security")
        job_results.update(dict.fromkeys(always_required, "success"))
        self.assertTrue(all(c.ok for c in ci_gate.evaluate({}, job_results)))
        for job in always_required:
            for result in ("failure", "skipped", "cancelled", ""):
                with self.subTest(job=job, result=result):
                    self.assertFalse(
                        all(
                            c.ok
                            for c in ci_gate.evaluate({}, {**job_results, job: result})
                        )
                    )

    def test_expected_frontend_jobs_must_succeed(self) -> None:
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        for job in (
            "frontend-quality",
            "frontend-build",
            "frontend-unit",
            "frontend-coverage",
            "frontend-e2e",
        ):
            self.assertEqual(jobs[job]["if"], jobs["frontend-image-verify"]["if"])
            for scope in ("frontend_changed", "shared_changed"):
                for result in ("skipped", "failure", "cancelled", "", "success"):
                    with self.subTest(job=job, scope=scope, result=result):
                        job_results = results()
                        job_results[job] = result
                        check = next(
                            c
                            for c in ci_gate.evaluate({scope: True}, job_results)
                            if c.job == job
                        )
                        self.assertTrue(check.expected)
                        self.assertEqual(check.ok, result == "success")

    def test_unneeded_skips_are_allowed(self) -> None:
        job_results = results("skipped")
        job_results["change-scope"] = "success"
        job_results["repository-policy"] = "success"
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
                self.assertTrue(expected["ci-tools"])
                for result in ("failure", "skipped", "cancelled", "", "success"):
                    check = next(
                        c
                        for c in ci_gate.evaluate(
                            {scope: True}, {**results(), "ci-tools": result}
                        )
                        if c.job == "ci-tools"
                    )
                    self.assertEqual(check.ok, result == "success")


if __name__ == "__main__":
    unittest.main()
