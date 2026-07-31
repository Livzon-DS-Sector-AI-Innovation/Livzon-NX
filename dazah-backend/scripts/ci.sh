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
  echo "== AgentBackend V2 residual scan =="
  uv run --no-sync python "${repository_dir}/scripts/check-agent-v2-residuals.py"
  echo "== Backend Ruff lint (PR additions and modifications only) =="
  bash "${project_dir}/scripts/ruff-changed.sh"
  echo "== Backend Python compilation =="
  uv run --no-sync python -m compileall -q app tests scripts
  echo "== Backend mypy (core infrastructure baseline) =="
  uv run --no-sync mypy app/core
  echo "== Prepare isolated unit-test database =="
  bash "${repository_dir}/scripts/wait-for-database.sh"
  uv run --no-sync alembic upgrade head
  echo "== Backend unit tests =="
  uv run --no-sync pytest \
    tests/unit tests/core \
    -m "not integration" \
    -ra \
    --junitxml=.pytest_cache/backend-quality-junit.xml
}

run_integration() {
  install_dependencies
  bash "${repository_dir}/scripts/wait-for-database.sh"

  echo "== Verify one Alembic head =="
  mapfile -t alembic_heads < <(uv run --no-sync alembic heads)
  [[ "${#alembic_heads[@]}" -eq 1 ]] || {
    echo "Expected exactly one Alembic head, found ${#alembic_heads[@]}:" >&2
    printf '%s\n' "${alembic_heads[@]}" >&2
    exit 1
  }

  echo "== Apply Alembic migrations =="
  uv run --no-sync alembic upgrade head
  echo "== Check model/migration drift =="
  uv run --no-sync alembic check
  echo "== FastAPI import check =="
  uv run --no-sync python -c "from app.main import app; assert app"
  echo "== Stable OpenAPI contract check =="
  uv run --no-sync python scripts/export_openapi.py
  git diff --exit-code -- openapi.json
  echo "== Backend database and API integration tests =="
  uv run --no-sync pytest \
    --cov=app \
    --cov-branch \
    --cov-report=term-missing \
    --cov-report=xml \
    --junitxml=.pytest_cache/backend-integration-junit.xml \
    -ra
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

compose_file() {
  local candidate
  for candidate in compose.yml compose.yaml docker-compose.yml docker-compose.yaml; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  echo "No supported Compose file found." >&2
  return 1
}

run_container() {
  require_command docker
  local file commit_sha
  file="$(compose_file)"
  commit_sha="${GITHUB_SHA:-$(git rev-parse HEAD)}"

  echo "== Backend Compose validation: ${file} =="
  docker compose --env-file /dev/null -f "$file" config --no-env-resolution --quiet
  echo "== Backend image build: dazah-backend:ci-${commit_sha} =="
  docker build \
    --pull=false \
    --tag "dazah-backend:ci-${commit_sha}" \
    .
}

run_security() {
  install_dependencies
  require_command uvx
  echo "== Backend dependency audit =="
  uv export --frozen --no-dev --no-emit-project --output-file /tmp/dazah-requirements.txt
  uvx pip-audit --requirement /tmp/dazah-requirements.txt
}

usage() {
  echo "Usage: $0 {quality|integration|container|security|all}" >&2
  exit 2
}

case "${1:-}" in
  quality) run_quality ;;
  integration) run_integration ;;
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
