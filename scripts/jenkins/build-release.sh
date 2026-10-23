#!/usr/bin/env bash
# Build an immutable Dazah release directory from a clean Git checkout.
#
# This is the Linux/Jenkins equivalent of the build and packaging half of
# scripts/deploy-production.ps1. It only builds and packages; it never uploads,
# stops production services, runs migrations, or deploys.
#
# Output layout (consumed by scripts/jenkins/deploy-release.sh and
# deploy-production-remote.sh):
#   <release-root>/<version>/
#     dazah-<version>.tar
#     dazah-<version>.tar.sha256
#     compose.yml
#     compose.edge.yml
#     nginx.default.conf
#     nginx-maintenance.conf
#     nginx-capacity.conf
#     migration-policy.json
#     deploy-production.sh
#     manifest.json
#
# The release directory is immutable: an existing directory is never reused.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION=""
PUBLIC_HOST="${PUBLIC_HOST:-192.168.40.251}"
RELEASE_ROOT="${RELEASE_ROOT:-$ROOT_DIR/release}"
BUILDER="${BUILDX_BUILDER:-dazah-builder}"
BUILD_PROXY="${BUILD_PROXY:-}"
PLATFORM="${BUILD_PLATFORM:-linux/amd64}"

log() {
  printf '[dazah-release-build] %s\n' "$*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

[[ -n "${HOME:-}" ]] || die "HOME 未设置，无法保存 Buildx 缓存策略标记"
BUILDER_MARKER="${BUILDX_CACHE_MARKER:-$HOME/.cache/dazah-buildkit-cache-policy.sha256}"

usage() {
  cat <<'EOF'
用法:
  scripts/jenkins/build-release.sh --version <version> [选项]

选项:
  --version <version>   必填。发布版本，例如 20261021-03d6d39。
  --public-host <host>  生产入口主机名或 IP，默认取 PUBLIC_HOST 或 192.168.40.251。
  --release-root <dir>  发布包根目录，默认 <仓库>/release。
  --builder <name>      Docker Buildx builder 名称，默认 dazah-builder。
  --proxy <url>         可选的构建代理，写入 BuildKit 的 HTTP(S)_PROXY build args。
  --help                显示本帮助。

要求:
  - 在干净的 Git 工作区执行；跟踪文件不得有未提交修改。
  - 已安装 docker、docker buildx、git、python3、sha256sum。
  - 至少 12 GiB 可用磁盘空间；不要清理 dazah-builder 的构建缓存。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --public-host)
      PUBLIC_HOST="${2:-}"
      shift 2
      ;;
    --release-root)
      RELEASE_ROOT="${2:-}"
      shift 2
      ;;
    --builder)
      BUILDER="${2:-}"
      shift 2
      ;;
    --proxy)
      BUILD_PROXY="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "未知参数: $1"
      ;;
  esac
done

[[ -n "$VERSION" ]] || die "缺少 --version"
[[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$ ]] || die "版本号不合法: $VERSION"
[[ "$PUBLIC_HOST" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$ ]] || die "公网主机名/IP 不合法: $PUBLIC_HOST"
[[ "$PLATFORM" == "linux/amd64" ]] || log "WARNING: 生产目标为 linux/amd64，本次构建平台为 $PLATFORM"

for tool in docker git python3 sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || die "缺少命令: $tool"
done
docker buildx version >/dev/null 2>&1 || die "docker buildx 不可用"

cd "$ROOT_DIR"

[[ -f "$ROOT_DIR/docker-bake.hcl" ]] || die "缺少 docker-bake.hcl"
[[ -f "$ROOT_DIR/docker/buildkitd.toml" ]] || die "缺少 docker/buildkitd.toml"
[[ -f "$ROOT_DIR/deploy/nginx.default.conf.template" ]] || die "缺少 nginx 模板"
[[ -f "$ROOT_DIR/deploy/compose.edge.yml" ]] || die "缺少 deploy/compose.edge.yml"
[[ -f "$ROOT_DIR/deploy/nginx-maintenance.conf" ]] || die "缺少 deploy/nginx-maintenance.conf"
[[ -f "$ROOT_DIR/deploy/single-host/nginx-capacity.conf" ]] || die "缺少 nginx-capacity.conf"
[[ -f "$ROOT_DIR/deploy/migration-policy.json" ]] || die "缺少 migration-policy.json"
[[ -f "$ROOT_DIR/scripts/deploy-production-remote.sh" ]] || die "缺少 deploy-production-remote.sh"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  git status --short --untracked-files=no >&2
  die "工作区存在已跟踪文件的未提交修改；发布包必须从确定的提交构建"
fi

GIT_COMMIT="$(git rev-parse HEAD)"
GIT_SHORT="$(git rev-parse --short=7 HEAD)"
GIT_BRANCH_NAME="${BRANCH_NAME:-${GIT_BRANCH:-unknown}}"

mkdir -p "$RELEASE_ROOT"
RELEASE_DIR="$RELEASE_ROOT/$VERSION"
PARTIAL_DIR="$RELEASE_ROOT/.$VERSION.partial"

[[ ! -e "$RELEASE_DIR" ]] || die "发布目录已存在，版本发布包必须不可变: $RELEASE_DIR"
rm -rf "$PARTIAL_DIR"
mkdir -p "$PARTIAL_DIR"

FREE_KB="$(df -Pk "$RELEASE_ROOT" | awk 'NR == 2 { print $4 }')"
[[ "$FREE_KB" =~ ^[0-9]+$ ]] || die "无法读取可用磁盘空间"
if (( FREE_KB < 12 * 1024 * 1024 )); then
  die "发布包根目录可用空间不足 12 GiB: $RELEASE_ROOT"
fi

cleanup() {
  if [[ -d "$PARTIAL_DIR" ]]; then
    log "构建未成功，保留半成品用于诊断: $PARTIAL_DIR" >&2
  fi
}
trap cleanup EXIT

ensure_builder() {
  local config="$ROOT_DIR/docker/buildkitd.toml"
  local marker="$BUILDER_MARKER"
  local expected current
  expected="$(sha256sum "$config" | awk '{ print $1 }')"
  mkdir -p "$(dirname "$marker")"

  if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
    log "创建 Buildx builder: $BUILDER"
    docker buildx create \
      --name "$BUILDER" \
      --driver docker-container \
      --buildkitd-config "$config" \
      --use >/dev/null
    docker buildx inspect "$BUILDER" --bootstrap >/dev/null
    printf '%s' "$expected" > "$marker"
  else
    current=""
    [[ -f "$marker" ]] && current="$(cat "$marker")"
    if [[ "$current" != "$expected" ]]; then
      log "缓存策略变化，重建 builder 并保留缓存状态: $BUILDER"
      docker buildx rm --force --keep-state "$BUILDER" >/dev/null
      docker buildx create \
        --name "$BUILDER" \
        --driver docker-container \
        --buildkitd-config "$config" \
        --use >/dev/null
      docker buildx inspect "$BUILDER" --bootstrap >/dev/null
      printf '%s' "$expected" > "$marker"
    else
      docker buildx use "$BUILDER" >/dev/null
    fi
    docker buildx inspect "$BUILDER" --bootstrap >/dev/null
  fi
}

build_images() {
  local -a args=(
    --builder "$BUILDER"
    --file "$ROOT_DIR/docker-bake.hcl"
    --load
    --set "*.platform=$PLATFORM"
    --set "backend.tags=dazah/backend:$VERSION"
    --set "frontend.tags=dazah/frontend:$VERSION"
    --set "hermes.tags=dazah/hermes-lite:$VERSION"
  )

  if [[ -n "$BUILD_PROXY" ]]; then
    local name
    for name in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; do
      args+=(--set "*.args.$name=$BUILD_PROXY")
    done
    args+=(--set "*.args.NO_PROXY=localhost,127.0.0.1")
    args+=(--set "*.args.no_proxy=localhost,127.0.0.1")
  fi

  log "构建应用镜像: $VERSION（$PLATFORM）"
  docker buildx bake "${args[@]}" backend frontend hermes
}

package_images() {
  local tar_name="dazah-$VERSION.tar"
  log "导出离线镜像包: $tar_name"
  docker save \
    --output "$PARTIAL_DIR/$tar_name" \
    "dazah/backend:$VERSION" \
    "dazah/frontend:$VERSION" \
    "dazah/hermes-lite:$VERSION"
  (
    cd "$PARTIAL_DIR"
    sha256sum "$tar_name" > "$tar_name.sha256"
  )
}

stage_site_files() {
  log "准备 Compose、Nginx 与迁移策略文件"
  cp "$ROOT_DIR/compose.yml" "$PARTIAL_DIR/compose.yml"
  cp "$ROOT_DIR/deploy/compose.edge.yml" "$PARTIAL_DIR/compose.edge.yml"
  cp "$ROOT_DIR/deploy/nginx-maintenance.conf" "$PARTIAL_DIR/nginx-maintenance.conf"
  cp "$ROOT_DIR/deploy/single-host/nginx-capacity.conf" "$PARTIAL_DIR/nginx-capacity.conf"
  cp "$ROOT_DIR/deploy/migration-policy.json" "$PARTIAL_DIR/migration-policy.json"
  cp "$ROOT_DIR/scripts/deploy-production-remote.sh" "$PARTIAL_DIR/deploy-production.sh"
  chmod 0755 "$PARTIAL_DIR/deploy-production.sh"

  sed "s|__PUBLIC_HOST__|$PUBLIC_HOST|g" \
    "$ROOT_DIR/deploy/nginx.default.conf.template" > "$PARTIAL_DIR/nginx.default.conf"

  grep -q 'include /etc/nginx/dazah-maintenance.conf;' "$PARTIAL_DIR/nginx.default.conf" \
    || die "nginx 配置缺少维护入口 include"
  grep -q 'listen 127.0.0.1:8090;' "$PARTIAL_DIR/nginx.default.conf" \
    || die "nginx 配置缺少内部维护探针端口"
  grep -q '/run/dazah:ro' "$PARTIAL_DIR/compose.edge.yml" \
    || die "edge Compose 缺少维护状态挂载"
  test -s "$PARTIAL_DIR/migration-policy.json" || die "migration-policy.json 为空"
}

write_manifest() {
  log "写入发布清单"
  export BUILDX_BUILDER="$BUILDER"
  python3 - "$PARTIAL_DIR" "$VERSION" "$PUBLIC_HOST" "$GIT_COMMIT" "$GIT_BRANCH_NAME" "$PLATFORM" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
version = sys.argv[2]
public_host = sys.argv[3]
git_commit = sys.argv[4]
git_branch = sys.argv[5]
platform = sys.argv[6]

def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

files = {
    path.name: sha256(path)
    for path in sorted(root.iterdir())
    if path.is_file()
}

images = {}
for service, image in (
    ("backend", "dazah/backend"),
    ("frontend", "dazah/frontend"),
    ("hermes", "dazah/hermes-lite"),
):
    images[service] = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", f"{image}:{version}"],
        text=True,
    ).strip()

manifest = {
    "schema": 1,
    "version": version,
    "git_commit": git_commit,
    "git_branch": git_branch,
    "public_host": public_host,
    "platform": platform,
    "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "builder": os.environ.get("BUILDX_BUILDER", "dazah-builder"),
    "images": images,
    "files": files,
}
(root / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

ensure_builder
build_images
package_images
stage_site_files
write_manifest

mv "$PARTIAL_DIR" "$RELEASE_DIR"
trap - EXIT

log "发布包已完成: $RELEASE_DIR"
log "版本: $VERSION 提交: $GIT_COMMIT"
ls -lh "$RELEASE_DIR"
printf 'RELEASE_DIR=%s\n' "$RELEASE_DIR"
