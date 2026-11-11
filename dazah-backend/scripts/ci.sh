#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repository_dir="$(cd "${project_dir}/.." && pwd)"
cd "$project_dir"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

install_dependencies() {
  require_command uv
  [[ -f uv.lock ]] || {
    echo "uv.lock is required for reproducible installs." >&2
    exit 1
  }
  uv sync --frozen --extra dev --group dev
}

run_quality() {
  install_dependencies
  run_quality_checks
}

run_quality_checks() {
  echo "== Page authorization lifecycle =="
  uv run --no-sync python "${repository_dir}/scripts/check-page-permission-lifecycle.py"
  echo "== AgentBackend V2 residual scan =="
  uv run --no-sync python "${repository_dir}/scripts/check-agent-v2-residuals.py"
  echo "== Backend Ruff lint (PR additions and modifications only) =="
  bash "${project_dir}/scripts/ruff-changed.sh"
  echo "== Backend Python compilation =="
  uv run --no-sync python -m compileall -q app tests scripts
  echo "== Backend mypy (core infrastructure baseline) =="
  uv run --no-sync mypy app/core
  echo "== Backend mypy (changed runtime files and dependency chains) =="
  uv run --no-sync python scripts/mypy_changed.py
  # Unit/core tests run once in run_integration's complete coverage suite.
}

run_integration() {
  install_dependencies
  prepare_integration
  run_integration_tests
  run_coverage
}

require_test_database() {
  if [[ "${APP_ENV:-}" != test || -z "${TEST_DATABASE_URL:-}" || "${DATABASE_URL:-}" != "$TEST_DATABASE_URL" ]]; then
    echo "Backend CI shards require APP_ENV=test and matching explicit DATABASE_URL and TEST_DATABASE_URL." >&2
    return 2
  fi
}

migrate_test_database() {
  bash "${repository_dir}/scripts/wait-for-database.sh"

  echo "== Verify one Alembic head =="
  local heads_output
  local -a alembic_heads
  heads_output="$(uv run --no-sync alembic heads)"
  mapfile -t alembic_heads < <(printf '%s' "$heads_output")
  [[ "${#alembic_heads[@]}" -eq 1 ]] || {
    echo "Expected exactly one Alembic head, found ${#alembic_heads[@]}:" >&2
    printf '%s\n' "${alembic_heads[@]}" >&2
    exit 1
  }

  echo "== Apply Alembic migrations =="
  uv run --no-sync alembic upgrade head
}

prepare_shard_database() {
  require_test_database
  migrate_test_database

  echo "== Seed the page menu catalog for this backend shard =="
  uv run --no-sync python -c '
import asyncio

from app.core.database import async_session_factory
from app.platform.identity.rbac import seed_menus

async def main():
    async with async_session_factory() as session:
        await seed_menus(session)

asyncio.run(main())
'
}

prepare_integration() {
  migrate_test_database

  echo "== Check model/migration drift =="
  uv run --no-sync alembic check
  echo "== FastAPI import check =="
  uv run --no-sync python -c "from app.main import app; assert app"
  echo "== Stable OpenAPI contract check =="
  uv run --no-sync python scripts/export_openapi.py
  git diff --exit-code -- openapi.json
}

run_integration_tests() {
  echo "== Backend database and API integration tests =="
  uv run --no-sync pytest \
    -p no:anyio \
    --cov \
    --cov-branch \
    --cov-report=term-missing \
    --cov-report=xml \
    --junitxml=.pytest_cache/backend-integration-junit.xml \
    -ra
}

run_integration_shard() {
  require_test_database
  uv run --no-sync python -m scripts.ci_pytest_shard run "$@"
}

merge_shard_coverage() {
  uv run --no-sync python -m scripts.ci_pytest_shard combine "$@"
  run_coverage
}

run_coverage() {
  echo "== Backend line and branch coverage floors =="
  uv run --no-sync python "${repository_dir}/scripts/check-coverage-floor.py" \
    --coverage-file coverage.xml \
    --min-lines 60 \
    --min-branches 33.5
  echo "== Backend changed-line coverage =="
  uv run --no-sync python "${repository_dir}/scripts/check-diff-coverage.py" \
    --coverage-file coverage.xml \
    --path-prefix dazah-backend/app \
    --minimum 80
}

run_container() {
  require_command docker
  local file commit_sha
  file="${repository_dir}/compose.dev.yml"
  commit_sha="${GITHUB_SHA:-$(git rev-parse HEAD)}"

  echo "== Backend Compose validation: ${file} =="
  docker compose --env-file /dev/null -f "$file" config --no-interpolate --quiet
  echo "== Backend image build: dazah-backend:ci-${commit_sha} =="
  docker build \
    --pull=false \
    --file "${repository_dir}/Dockerfile" \
    --target backend \
    --tag "dazah-backend:ci-${commit_sha}" \
    "${repository_dir}"
}

run_security() {
  install_dependencies
  require_command uvx
  echo "== Backend dependency audit =="
  uv export --frozen --no-dev --no-emit-project --output-file /tmp/dazah-requirements.txt
  uvx pip-audit --requirement /tmp/dazah-requirements.txt
}

usage() {
  echo "Usage: $0 {quality|quality-checks|integration|prepare-integration|migrate-test-database|integration-tests|integration-shard <shard> <output>|coverage|merge-shard-coverage <artifacts>|container|security|all}" >&2
  exit 2
}

case "${1:-}" in
  quality) run_quality ;;
  quality-checks) run_quality_checks ;;
  integration) run_integration ;;
  prepare-integration) prepare_integration ;;
  migrate-test-database) prepare_shard_database ;;
  integration-tests) run_integration_tests ;;
  integration-shard) shift; run_integration_shard "$@" ;;
  coverage) run_coverage ;;
  merge-shard-coverage) shift; merge_shard_coverage "$@" ;;
  container) run_container ;;
  security) run_security ;;
  all)
    run_quality
    run_integration
    run_container
    run_security
    ;;
  *) usage ;;
esac
