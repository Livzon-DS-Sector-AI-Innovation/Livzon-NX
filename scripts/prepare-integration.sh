#!/usr/bin/env bash
set -euo pipefail

event_name="${GITHUB_EVENT_NAME:-}"
target_branch="${GITHUB_BASE_REF:-}"

echo "Event: ${event_name:-<missing>}"
echo "Target: ${target_branch:-<missing>}"

[[ "$event_name" == "pull_request" ]] || {
  echo "Integration preparation is only valid for pull_request workflows." >&2
  exit 1
}
[[ -n "$target_branch" ]] || {
  echo "GITHUB_BASE_REF is empty; cannot identify the pull request target." >&2
  exit 1
}

if [[ "$(git rev-parse --is-shallow-repository)" == "true" ]]; then
  echo "Repository is shallow; fetch-depth: 0 is required." >&2
  exit 1
fi

echo "Fetching latest target branch origin/${target_branch}..."
git fetch --no-tags origin \
  "+refs/heads/${target_branch}:refs/remotes/origin/${target_branch}"

echo "Merging origin/${target_branch} into PR head without committing..."
if ! git merge --no-commit --no-ff "refs/remotes/origin/${target_branch}"; then
  echo "Integration preparation failed: PR head conflicts with the latest ${target_branch}." >&2
  exit 1
fi

echo "Checking whitespace errors and conflict markers..."
git diff --cached --check
git diff --check
echo "Integration worktree is ready at $(git rev-parse HEAD)."
