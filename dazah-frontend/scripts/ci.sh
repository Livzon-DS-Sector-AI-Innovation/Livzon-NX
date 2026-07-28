#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

install_dependencies() {
  require_command pnpm
  [[ -f pnpm-lock.yaml ]] || {
    echo "pnpm-lock.yaml is required for reproducible installs." >&2
    exit 1
  }
  pnpm install --frozen-lockfile
}

run_quality() {
  install_dependencies
  echo "== Frontend generated API contract =="
  pnpm generate:api
  git diff --exit-code -- src/types/generated/schema.ts
  echo "== Frontend ESLint =="
  pnpm lint
  echo "== Frontend TypeScript =="
  pnpm typecheck
  echo "== Frontend unit tests (Vitest run mode) =="
  pnpm test:unit
}

run_build() {
  install_dependencies
  export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
  echo "== Frontend production build =="
  pnpm build
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
  echo "== Frontend Compose validation: ${file} =="
  docker compose --env-file /dev/null -f "$file" config --no-env-resolution --quiet
  echo "== Frontend image build: dazah-frontend:ci-${commit_sha} =="
  docker build \
    --pull=false \
    --tag "dazah-frontend:ci-${commit_sha}" \
    .
}

run_security() {
  install_dependencies
  echo "== Frontend dependency audit =="
  pnpm audit --audit-level high
}

usage() {
  echo "Usage: $0 {quality|build|container|security|all}" >&2
  exit 2
}

case "${1:-}" in
  quality) run_quality ;;
  build) run_build ;;
  container) run_container ;;
  security) run_security ;;
  all)
    run_quality
    run_build
    run_container
    run_security
    ;;
  *) usage ;;
esac
