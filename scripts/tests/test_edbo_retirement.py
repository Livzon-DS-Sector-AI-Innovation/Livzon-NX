"""Deployment inputs must no longer require the retired optimization service."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "filename", ["compose.yml", "compose.dev.yml"]
)
def test_application_can_start_without_optimization_service(filename: str) -> None:
    services = yaml.safe_load((ROOT / filename).read_text(encoding="utf-8"))["services"]
    assert "edbo-service" not in services
    assert {"app", "db", "redis", "minio"} <= services.keys()
    for service in services.values():
        assert "edbo-service" not in service.get("depends_on", {})
        assert "EDBO_SERVICE_URL" not in service.get("environment", {})


@pytest.mark.parametrize(
    "filename",
    [
        "Dockerfile", "Dockerfile.dev", "scripts/deploy-production.ps1",
        "scripts/deploy-production-remote.sh",
        ".env.example", ".env.local.example",
        ".github/workflows/ci.yml",
    ],
)
def test_build_and_release_inputs_have_no_retired_dependency(filename: str) -> None:
    assert "edbo" not in (ROOT / filename).read_text(encoding="utf-8").lower()
