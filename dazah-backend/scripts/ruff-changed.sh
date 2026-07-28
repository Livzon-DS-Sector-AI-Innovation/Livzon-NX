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
  echo "CI requires both CI_BASE_SHA and CI_HEAD_SHA." >&2
  exit 2
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
