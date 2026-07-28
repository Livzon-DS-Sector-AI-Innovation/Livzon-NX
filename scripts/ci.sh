#!/usr/bin/env bash
set -euo pipefail

repository_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_ci="${repository_dir}/dazah-frontend/scripts/ci.sh"
backend_ci="${repository_dir}/dazah-backend/scripts/ci.sh"

run_frontend() {
  bash "$frontend_ci" "$1"
}

run_backend() {
  bash "$backend_ci" "$1"
}

usage() {
  cat >&2 <<'EOF'
Usage: ./scripts/ci.sh {
  quality|build|integration|container|security|all|
  frontend-quality|frontend-build|frontend-container|frontend-security|
  backend-quality|backend-integration|backend-container|backend-security
}
EOF
  exit 2
}

case "${1:-}" in
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
  frontend-container) run_frontend container ;;
  frontend-security) run_frontend security ;;
  backend-quality) run_backend quality ;;
  backend-integration) run_backend integration ;;
  backend-container) run_backend container ;;
  backend-security) run_backend security ;;
  all)
    run_frontend quality
    run_frontend build
    run_backend quality
    run_backend integration
    run_frontend container
    run_backend container
    run_frontend security
    run_backend security
    ;;
  *) usage ;;
esac
