#!/usr/bin/env bash
set -euo pipefail

backend_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repository_dir="$(cd "${backend_dir}/.." && pwd)"
declare -a python_files=()

add_backend_file() {
  local path="$1"
  path="${path#./}"
  path="${path#dazah-backend/}"
  [[ "$path" == *.py ]] && python_files+=("$path")
}

if [[ "$#" -gt 0 ]]; then
  for path in "$@"; do
    add_backend_file "$path"
  done
elif [[ -n "${CI_BASE_SHA:-}" && -n "${CI_HEAD_SHA:-}" ]]; then
  while IFS= read -r -d '' path; do
    add_backend_file "$path"
  done < <(
    git -C "$repository_dir" diff \
      --name-only \
      --diff-filter=ACMR \
      -z \
      "$CI_BASE_SHA" \
      "$CI_HEAD_SHA" \
      -- "dazah-backend/**/*.py"
  )
elif [[ -n "${CI_BASE_SHA:-}" || -n "${CI_HEAD_SHA:-}" || "${CI:-}" == "true" ]]; then
  # CI 场景：workflow_dispatch 无 PR 上下文时 CI_BASE_SHA 为空。与
  # change_scope.py 一致，回退到 origin/main 的 merge-base（首个提交无祖先则
  # 退回 HEAD^），避免整仓 lint 或直接退出；真实 PR 运行仍走完整 base..head。
  lint_base="${CI_BASE_SHA:-}"
  lint_head="${CI_HEAD_SHA:-HEAD}"
  if [[ -z "${lint_base:-}" ]]; then
    lint_base="$(git -C "$repository_dir" merge-base origin/main "$lint_head" 2>/dev/null || true)"
  fi
  if [[ -z "${lint_base:-}" ]]; then
    lint_base="$(git -C "$repository_dir" rev-parse "${lint_head}^" 2>/dev/null || true)"
  fi
  if [[ -z "${lint_base:-}" ]]; then
    echo "CI requires both CI_BASE_SHA and CI_HEAD_SHA." >&2
    exit 2
  fi
  while IFS= read -r -d '' path; do
    add_backend_file "$path"
  done < <(
    git -C "$repository_dir" diff \
      --name-only \
      --diff-filter=ACMR \
      -z \
      "$lint_base" \
      "$lint_head" \
      -- "dazah-backend/**/*.py"
  )
else
  while IFS= read -r -d '' path; do
    add_backend_file "$path"
  done < <(
    git -C "$repository_dir" diff \
      --name-only \
      --diff-filter=ACMR \
      -z \
      HEAD \
      -- "dazah-backend/**/*.py"
  )
  while IFS= read -r -d '' path; do
    add_backend_file "$path"
  done < <(
    git -C "$repository_dir" ls-files \
      --others \
      --exclude-standard \
      -z \
      -- "dazah-backend/**/*.py"
  )
fi

if [[ "${#python_files[@]}" -eq 0 ]]; then
  echo "No changed backend Python files; Ruff incremental check skipped."
  exit 0
fi

cd "$backend_dir"
printf 'Ruff incremental check (%d files):\n' "${#python_files[@]}"
printf '  %s\n' "${python_files[@]}"
uv run --no-sync ruff check -- "${python_files[@]}"
