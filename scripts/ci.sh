#!/usr/bin/env bash
set -euo pipefail

repository_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_ci="${repository_dir}/dazah-frontend/scripts/ci.sh"
backend_ci="${repository_dir}/dazah-backend/scripts/ci.sh"
hermes_ci="${repository_dir}/Hermes-Lite/scripts/ci.sh"

run_frontend() {
  bash "$frontend_ci" "$1"
}

run_backend() {
  bash "$backend_ci" "$1"
}

run_hermes() {
  bash "$hermes_ci"
}

run_test_impact() {
  python "${repository_dir}/scripts/check-test-impact.py"
}

run_instruction_bridges() {
  python "${repository_dir}/scripts/check-agent-instruction-bridges.py"
}

usage() {
  cat >&2 <<'EOF'
Usage: ./scripts/ci.sh {
  instructions|test-impact|quality|build|integration|container|security|all|
  frontend-quality|frontend-build|frontend-e2e|frontend-container|frontend-security|
  backend-quality|backend-integration|backend-container|backend-security|
  hermes-quality
}
EOF
  exit 2
}

case "${1:-}" in
  instructions) run_instruction_bridges ;;
  test-impact) run_test_impact ;;
  quality)
    run_frontend quality
    run_backend quality
    ;;
  build) run_frontend build ;;
  integration) run_backend integration ;;
  container)
    run_frontend container
    run_backend container
    ;;
  security)
    run_frontend security
    run_backend security
    ;;
  frontend-quality) run_frontend quality ;;
  frontend-build) run_frontend build ;;
  frontend-e2e) run_frontend e2e ;;
  frontend-container) run_frontend container ;;
  frontend-security) run_frontend security ;;
  backend-quality) run_backend quality ;;
  backend-integration) run_backend integration ;;
  backend-container) run_backend container ;;
  backend-security) run_backend security ;;
  hermes-quality) run_hermes ;;
  all)
    run_instruction_bridges
    run_test_impact
    run_frontend quality
    run_frontend build
    run_frontend e2e
    run_backend quality
    run_backend integration
    run_frontend container
    run_backend container
    run_frontend security
    run_backend security
    run_hermes
    ;;
  *) usage ;;
esac
