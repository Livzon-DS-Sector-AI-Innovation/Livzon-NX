from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "change_scope.py"
SPEC = importlib.util.spec_from_file_location("change_scope", SCRIPT)
assert SPEC and SPEC.loader
change_scope = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = change_scope
SPEC.loader.exec_module(change_scope)


class ChangeScopeTests(unittest.TestCase):
    def test_business_source_edits_keep_application_tests_without_image_builds(self):
        scopes = change_scope.classify_paths(
            {
                "dazah-frontend/src/components/hr/Employee.tsx",
                "dazah-backend/app/modules/hr/service.py",
            }
        )
        self.assertTrue(scopes["frontend_changed"])
        self.assertTrue(scopes["backend_changed"])
        self.assertFalse(scopes["frontend_image_changed"])
        self.assertFalse(scopes["backend_image_changed"])

    def test_packaging_runtime_dependencies_and_assets_require_images(self):
        for project, flag, paths in (
            (
                "dazah-frontend",
                "frontend_image_changed",
                (
                    "package.json",
                    "pnpm-lock.yaml",
                    "next.config.ts",
                    "tsconfig.json",
                    "scripts/build.mjs",
                    "public/logo.svg",
                    "src/middleware.ts",
                    "src/assets/report-template.docx",
                ),
            ),
            (
                "dazah-backend",
                "backend_image_changed",
                (
                    "pyproject.toml",
                    "uv.lock",
                    "alembic.ini",
                    "scripts/start.sh",
                    "app/main.py",
                    "app/core/config.py",
                    "app/templates/report.docx",
                    "alembic/versions/new.py",
                ),
            ),
        ):
            for relative in paths:
                with self.subTest(project=project, relative=relative):
                    scopes = change_scope.classify_paths({f"{project}/{relative}"})
                    self.assertTrue(scopes[flag])

    def test_source_layout_changes_require_images_but_new_tests_do_not(self):
        for path, flag in (
            ("dazah-frontend/src/components/hr/New.tsx", "frontend_image_changed"),
            ("dazah-backend/app/modules/hr/new.py", "backend_image_changed"),
        ):
            scopes = change_scope.classify_paths({path}, layout_paths={path})
            self.assertTrue(scopes[flag])
        for path in (
            "dazah-frontend/src/components/hr/New.test.tsx",
            "dazah-backend/tests/modules/hr/test_new.py",
        ):
            scopes = change_scope.classify_paths({path}, layout_paths={path})
            self.assertFalse(scopes["frontend_image_changed"])
            self.assertFalse(scopes["backend_image_changed"])

    def test_git_layout_filter_distinguishes_edits_from_additions_and_renames(self):
        import os

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.run(
                    ["git", *args], cwd=root, check=True, capture_output=True
                )

            git("init", "-q")
            git("config", "user.name", "CI")
            git("config", "user.email", "ci@example.invalid")
            source = root / "dazah-backend/app/modules/hr"
            source.mkdir(parents=True)
            (source / "edit.py").write_text("old")
            (source / "rename.py").write_text("rename")
            git("add", ".")
            git("commit", "-qm", "base")
            (source / "edit.py").write_text("new")
            (source / "rename.py").rename(source / "renamed.py")
            git("add", "-A")
            git("commit", "-qm", "change")
            previous = Path.cwd()
            try:
                os.chdir(root)
                layout = change_scope.collect_changed_paths(
                    "HEAD^", "HEAD", diff_filter="AD"
                )
            finally:
                os.chdir(previous)
            self.assertEqual(
                layout,
                {
                    "dazah-backend/app/modules/hr/rename.py",
                    "dazah-backend/app/modules/hr/renamed.py",
                },
            )

    def test_runtime_markdown_is_packaged_content(self):
        for path, flag in (
            ("dazah-frontend/public/help.md", "frontend_image_changed"),
            ("dazah-backend/app/templates/prompt.md", "backend_image_changed"),
        ):
            scopes = change_scope.classify_paths({path})
            self.assertFalse(scopes["docs_only"])
            self.assertTrue(scopes[flag])

    def test_shared_paths_require_both_images(self):
        for path in (
            "Dockerfile",
            "Dockerfile.dev",
            ".dockerignore",
            "docker/apt-download.conf",
            "scripts/cd/readiness.py",
            ".github/workflows/ci.yml",
            "unknown-runtime/config.yaml",
        ):
            scopes = change_scope.classify_paths({path})
            self.assertTrue(scopes["frontend_image_changed"])
            self.assertTrue(scopes["backend_image_changed"])

    def test_manual_run_verifies_full_tree_even_with_empty_diff(self) -> None:
        import argparse

        args = argparse.Namespace(base=None, head="HEAD", github_output=None)
        with (
            patch.object(change_scope, "parse_args", return_value=args),
            patch.object(change_scope, "collect_changed_paths", return_value=set()),
            patch.object(change_scope, "resolve_head", return_value="HEAD"),
            patch.object(change_scope, "_git", return_value=b"Dockerfile\0"),
            patch.object(change_scope, "write_outputs") as output,
            patch.dict("os.environ", {"GITHUB_EVENT_NAME": "workflow_dispatch"}),
        ):
            self.assertEqual(change_scope.main(), 0)
        self.assertTrue(output.call_args.args[0]["shared_changed"])

    def test_codeowners_only_does_not_run_application_suites(self) -> None:
        scopes = change_scope.classify_paths({".github/CODEOWNERS"})
        self.assertFalse(any(scopes.values()))

    def test_metadata_does_not_hide_mixed_application_changes(self) -> None:
        scopes = change_scope.classify_paths(
            {".github/CODEOWNERS", "dazah-backend/app/main.py"}
        )
        self.assertTrue(scopes["backend_changed"])
        self.assertFalse(scopes["shared_changed"])

    def test_unknown_and_ci_paths_fail_safe_to_all_projects(self) -> None:
        for path in (
            ".github/workflows/ci.yml",
            ".ci/test-impact-policy.toml",
            "scripts/check-test-impact.py",
            "docker/hermes-entrypoint.sh",
            "new-runtime/main.py",
            "compose.dev.yml",
        ):
            with self.subTest(path=path):
                self.assertTrue(change_scope.classify_paths({path})["shared_changed"])

    def test_classifies_each_module_and_docker(self) -> None:
        scopes = change_scope.classify_paths(
            {
                "dazah-frontend/src/app/page.tsx",
                "dazah-backend/app/main.py",
                "Hermes-Lite/tools/dazah_platform.py",
                "Dockerfile",
            }
        )
        self.assertTrue(scopes["frontend_changed"])
        self.assertTrue(scopes["backend_changed"])
        self.assertTrue(scopes["hermes_changed"])
        self.assertTrue(scopes["docker_changed"])
        self.assertFalse(scopes["docs_only"])

    def test_docs_only_does_not_enable_modules(self) -> None:
        scopes = change_scope.classify_paths(
            {"README.md", "docs/ci.md", "dazah-frontend/README.md"}
        )
        self.assertTrue(scopes["docs_only"])
        self.assertFalse(scopes["frontend_changed"])
        self.assertFalse(scopes["shared_changed"])

    def test_mixed_docs_and_code_is_not_docs_only(self) -> None:
        scopes = change_scope.classify_paths(
            {"docs/ci.md", "dazah-frontend/src/app/page.tsx"}
        )
        self.assertFalse(scopes["docs_only"])
        self.assertTrue(scopes["frontend_changed"])

    def test_shared_contract_enables_shared_scope(self) -> None:
        scopes = change_scope.classify_paths({"dazah-backend/openapi.json"})
        self.assertTrue(scopes["backend_changed"])
        self.assertTrue(scopes["shared_changed"])

    def test_unknown_base_falls_back_safely(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "ci@example.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "CI"],
                cwd=repository,
                check=True,
            )
            (repository / "README.md").write_text("docs", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "initial"], cwd=repository, check=True
            )
            frontend = repository / "dazah-frontend" / "src"
            frontend.mkdir(parents=True)
            (frontend / "page.tsx").write_text("export {}", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "frontend"], cwd=repository, check=True
            )
            previous = Path.cwd()
            try:
                import os

                os.chdir(repository)
                paths = change_scope.collect_changed_paths("0" * 40, "HEAD")
            finally:
                os.chdir(previous)
            self.assertEqual(
                paths,
                {"README.md", "dazah-frontend/src/page.tsx"},
            )

    def test_merge_commit_diff_includes_merged_module(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "ci@example.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "CI"],
                cwd=repository,
                check=True,
            )
            (repository / "README.md").write_text("initial", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "initial"], cwd=repository, check=True
            )
            subprocess.run(
                ["git", "checkout", "-qb", "feature"], cwd=repository, check=True
            )
            backend = repository / "dazah-backend" / "app"
            backend.mkdir(parents=True)
            (backend / "main.py").write_text("app = None", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "backend"], cwd=repository, check=True
            )
            subprocess.run(["git", "checkout", "-q", "-"], cwd=repository, check=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "merge", "--no-ff", "-qm", "merge", "feature"],
                cwd=repository,
                check=True,
            )
            previous = Path.cwd()
            try:
                import os

                os.chdir(repository)
                paths = change_scope.collect_changed_paths(base, "HEAD")
            finally:
                os.chdir(previous)
            self.assertEqual(paths, {"dazah-backend/app/main.py"})


if __name__ == "__main__":
    unittest.main()
