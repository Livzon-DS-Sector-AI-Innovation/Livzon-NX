from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "change_scope.py"
SPEC = importlib.util.spec_from_file_location("change_scope", SCRIPT)
assert SPEC and SPEC.loader
change_scope = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = change_scope
SPEC.loader.exec_module(change_scope)


class ChangeScopeTests(unittest.TestCase):
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
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=repository, check=True)
            frontend = repository / "dazah-frontend" / "src"
            frontend.mkdir(parents=True)
            (frontend / "page.tsx").write_text("export {}", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "frontend"], cwd=repository, check=True)
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
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=repository, check=True)
            subprocess.run(["git", "checkout", "-qb", "feature"], cwd=repository, check=True)
            backend = repository / "dazah-backend" / "app"
            backend.mkdir(parents=True)
            (backend / "main.py").write_text("app = None", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "backend"], cwd=repository, check=True)
            subprocess.run(["git", "checkout", "-q", "-"], cwd=repository, check=True)
            base = (
                subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                .stdout.strip()
            )
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
