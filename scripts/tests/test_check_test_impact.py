from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_checker() -> ModuleType:
    script = Path(__file__).parents[1] / "check-test-impact.py"
    spec = importlib.util.spec_from_file_location("check_test_impact", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def policy() -> dict:
    return {
        "version": 1,
        "production_roots": ["product/"],
        "production_include": [r"^product/.*\.py$"],
        "ignore": [r"\.test\.py$"],
        "rules": [
            {
                "id": "module",
                "description": "module test",
                "source": r"^product/(?P<module>[^/]+)/.*\.py$",
                "tests": [r"^tests/{module}/test_.*\.py$"],
            }
        ],
    }


def test_matching_module_test_satisfies_policy() -> None:
    violations, unmatched = checker.evaluate(
        policy(),
        {"product/quality/service.py"},
        {"tests/quality/test_service.py"},
    )

    assert violations == []
    assert unmatched == []


def test_unrelated_test_does_not_satisfy_policy() -> None:
    violations, unmatched = checker.evaluate(
        policy(),
        {"product/quality/service.py"},
        {"tests/safety/test_service.py"},
    )

    assert len(violations) == 1
    assert unmatched == []


def test_unclassified_production_change_fails_closed() -> None:
    violations, unmatched = checker.evaluate(
        policy(),
        {"product/unknown.py"},
        set(),
    )

    assert violations == []
    assert unmatched == ["product/unknown.py"]


def test_non_code_file_under_production_root_needs_no_test() -> None:
    violations, unmatched = checker.evaluate(
        policy(),
        {"product/README.md"},
        set(),
    )

    assert violations == []
    assert unmatched == []


def test_all_matching_rules_must_have_their_own_test() -> None:
    stacked_policy = policy()
    stacked_policy["rules"].append(
        {
            "id": "contract",
            "description": "contract test",
            "source": r"^product/quality/service\.py$",
            "tests": [r"^contract-tests/test_quality\.py$"],
        }
    )

    violations, unmatched = checker.evaluate(
        stacked_policy,
        {"product/quality/service.py"},
        {"tests/quality/test_service.py"},
    )

    assert [requirement.rule_id for requirement, _ in violations] == [
        "contract"
    ]
    assert unmatched == []


def test_non_production_change_needs_no_test() -> None:
    violations, unmatched = checker.evaluate(
        policy(),
        {"docs/ci.md"},
        set(),
    )

    assert violations == []
    assert unmatched == []
