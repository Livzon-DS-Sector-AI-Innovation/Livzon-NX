#!/usr/bin/env bash
set -euo pipefail

source_branch="${GITHUB_HEAD_REF:-}"
target_branch="${GITHUB_BASE_REF:-}"

echo "Source: ${source_branch:-<missing>}"
echo "Target: ${target_branch:-<missing>}"

fail() {
  echo "Branch policy failed: $*" >&2
  exit 1
}

[[ -n "$source_branch" ]] || fail "GITHUB_HEAD_REF is empty; this check only supports pull requests."
[[ -n "$target_branch" ]] || fail "GITHUB_BASE_REF is empty; this check only supports pull requests."

case "$target_branch" in
  main)
    [[ "$source_branch" == "dev" ]] ||
      fail "main accepts pull requests from dev only."
    ;;
  dev)
    [[ "$source_branch" != "main" ]] ||
      fail "main must never be merged back into dev through this gate."
    case "$source_branch" in
      feature/* | fix/* | chore/* | refactor/* | test/* | docs/* | hotfix/* | build/* | ci/* | perf/*)
        ;;
      *)
        fail "dev accepts only approved development branch prefixes."
        ;;
    esac
    ;;
  *)
    fail "CI workflows may target dev or main only."
    ;;
esac

echo "Branch policy passed."
