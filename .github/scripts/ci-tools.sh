#!/usr/bin/env bash
# Run a GitHub Actions step with the system tools built for this CI run.
set -euo pipefail

if [[ ! "${CI_TOOLS_IMAGE_ID:-}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo 'Expected a CI tools image ID from this workflow run.' >&2
  exit 1
fi

if [[ "${1:-}" == load ]]; then
  docker image load --input "$2"
  # Resolve the full ID after loading; never run a tag or pull an alternate image.
  if [[ "$(docker image inspect --format '{{.Id}}' "$CI_TOOLS_IMAGE_ID")" != "$CI_TOOLS_IMAGE_ID" ]]; then
    echo 'The CI tools archive did not load the expected image ID.' >&2
    exit 1
  fi
  printf 'CI_TOOLS_IMAGE_ID=%s\n' "$CI_TOOLS_IMAGE_ID" >> "$GITHUB_ENV"
  exit 0
fi

uv_cache="$(uv cache dir)"
ci_home="$RUNNER_TEMP/ci-tools-home"
mkdir -p "$uv_cache" "$ci_home"
env_args=()
for name in CI GITHUB_ACTIONS GITHUB_ENV GITHUB_OUTPUT GITHUB_STEP_SUMMARY \
  GITHUB_WORKSPACE RUNNER_TEMP PYTHON_VERSION PYTHONUTF8 UV_VERSION \
  CI_BASE_SHA CI_HEAD_SHA SHARD PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE \
  APP_ENV DATABASE_URL TEST_DATABASE_URL REDIS_URL MAINTENANCE_TEST_REDIS_URL \
  SECRET_KEY ENCRYPTION_KEY FRONTEND_URL AGENT_TOOL_TOKEN FEISHU_WS_ENABLED \
  EQUIPMENT_FEISHU_WS_ENABLED LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED \
  LIVZON_FEISHU_EVENT_WS_ENABLED MINIO_ENABLED; do
  env_args+=(--env "$name")
done

# The job's PostgreSQL and Redis service ports are published on this Linux runner.
# Keep absolute paths and the runner UID so reports and cache files remain usable.
exec docker run --rm --init --pull=never --network host \
  --user "$(id -u):$(id -g)" --workdir "$PWD" \
  --mount "type=bind,src=$GITHUB_WORKSPACE,dst=$GITHUB_WORKSPACE" \
  --mount "type=bind,src=$RUNNER_TEMP,dst=$RUNNER_TEMP" \
  --mount "type=bind,src=$uv_cache,dst=$uv_cache" \
  --env "HOME=$ci_home" --env "UV_CACHE_DIR=$uv_cache" --env UV_LINK_MODE=copy \
  "${env_args[@]}" "$CI_TOOLS_IMAGE_ID" bash --noprofile --norc -eo pipefail "$1"
