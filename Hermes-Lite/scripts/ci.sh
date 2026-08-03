#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

command -v uv >/dev/null 2>&1 || {
  echo "Required command not found: uv" >&2
  exit 1
}
[[ -f uv.lock ]] || {
  echo "uv.lock is required for reproducible installs." >&2
  exit 1
}

uv sync --frozen --extra dev

echo "== AgentBackend V2 residual scan =="
uv run --no-sync python "${project_dir}/../scripts/check-agent-v2-residuals.py"

echo "== Hermes-Lite Python compilation =="
uv run --no-sync python -m py_compile \
  run_agent.py \
  model_tools.py \
  toolsets.py \
  services/dazah_agent_service.py \
  tools/dazah_platform.py

echo "== Hermes-Lite Ruff =="
uv run --no-sync ruff check \
  services/dazah_agent_service.py \
  services/dazah_feishu_gateway.py \
  tools/dazah_platform.py \
  tests/test_dazah_*.py \
  tests/test_feishu_runtime.py

echo "== Hermes-Lite tests =="
uv run --no-sync pytest \
  -ra \
  --junitxml=.pytest_cache/hermes-quality-junit.xml
