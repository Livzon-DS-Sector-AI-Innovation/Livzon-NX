#!/usr/bin/env bash
# Upload a release directory and drive the production deployment helper.
#
# This script intentionally delegates all production safety checks to
# /opt/dazah/current/deploy-production.sh: maintenance gate, request draining,
# migration policy, health checks, proxy checks and rollback of the previous
# application version. It does not run migrations or Docker Compose directly.
#
# Two modes:
#   DEPLOY_MODE=ssh   (default) Jenkins agent -> SSH -> production host
#   DEPLOY_MODE=local Run on the production host itself
#
# The remote account must be able to run the deployment helper through
# passwordless sudo. Prefer a dedicated account and a restricted sudoers rule;
# see docs/runbooks/jenkins-ci-cd.md.
set -Eeuo pipefail

ACTION="${1:-deploy}"
VERSION="${VERSION:-}"
RELEASE_DIR="${RELEASE_DIR:-}"
NOTICE_SECONDS="${NOTICE_SECONDS:-180}"
DEPLOY_MODE="${DEPLOY_MODE:-ssh}"
DEPLOY_HOST="${DEPLOY_HOST:-192.168.40.251}"
DEPLOY_USER="${DEPLOY_USER:-livzon}"
REMOTE_ROOT="${REMOTE_ROOT:-/opt/dazah}"
REMOTE_RELEASES="${REMOTE_RELEASES:-/data/dazah/releases}"
REMOTE_DATA="${REMOTE_DATA:-/data/dazah}"
PREDEPLOY_BACKUP="${PREDEPLOY_BACKUP:-1}"
SSH_KEY="${SSH_KEY:-}"

SSH_OPTS=(
  -o BatchMode=yes
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=10
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=10
)
[[ -n "$SSH_KEY" ]] && SSH_OPTS+=(-i "$SSH_KEY")

log() {
  printf '[dazah-jenkins-deploy] %s\n' "$*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
用法:
  scripts/jenkins/deploy-release.sh <deploy|rollback|verify|status|backup>

环境变量:
  VERSION             deploy/rollback 必填，例如 20261021-03d6d39。
  RELEASE_DIR         deploy 必填，本地发布包目录。
  NOTICE_SECONDS      维护预告秒数，0-3600，默认 180。
  DEPLOY_MODE         ssh 或 local，默认 ssh。
  DEPLOY_HOST         生产服务器，默认 192.168.40.251。
  DEPLOY_USER         SSH 用户，默认 livzon。
  PREDEPLOY_BACKUP    1/0，默认 1；部署前调用 controller.py backup。
  REMOTE_ROOT         服务器部署根目录，默认 /opt/dazah。
  REMOTE_RELEASES     服务器不可变发布目录，默认 /data/dazah/releases。
  REMOTE_DATA         服务器数据根目录，默认 /data/dazah。
  SSH_KEY             可选 SSH 私钥；Jenkins 用 sshagent 时不需要。

说明:
  - deploy 会先上传发布包，再执行发布前备份，最后调用服务器部署脚本。
  - 部署失败时不会自动回滚，也不会关闭维护模式；先检查 status/verify。
  - rollback 只切换应用镜像和配置，不会回滚数据库迁移。
EOF
}

validate_version() {
  local value="${1:-}"
  [[ -n "$value" ]] || die "缺少版本号"
  [[ "$value" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$ ]] || die "版本号不合法: $value"
}

remote_sudo() {
  local command_text="$1"
  if [[ "$DEPLOY_MODE" == "local" ]]; then
    sudo -n bash -lc "$command_text"
  else
    local quoted
    quoted="$(printf '%q' "$command_text")"
    ssh "${SSH_OPTS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "sudo -n bash -lc $quoted"
  fi
}

release_store_guard() {
  remote_sudo "if [ '$REMOTE_RELEASES' = '/data/dazah/releases' ] || [ '$REMOTE_RELEASES' = '/opt/dazah/releases' ] || [ \"\$(readlink -f '$REMOTE_RELEASES' 2>/dev/null)\" = '/data/dazah/releases' ]; then python3 '$REMOTE_ROOT/control/controller.py' mount-check; fi"
}

RELEASE_FILES=()

validate_release_input() {
  [[ -n "$VERSION" ]] || die "deploy 需要 VERSION"
  validate_version "$VERSION"
  [[ -n "$RELEASE_DIR" && -d "$RELEASE_DIR" ]] || die "发布目录不存在: ${RELEASE_DIR:-<empty>}"

  local name
  RELEASE_FILES=(
    "dazah-$VERSION.tar"
    "dazah-$VERSION.tar.sha256"
    "compose.yml"
    "compose.edge.yml"
    "nginx.default.conf"
    "nginx-maintenance.conf"
    "nginx-capacity.conf"
    "migration-policy.json"
    "deploy-production.sh"
    "manifest.json"
  )
  for name in "${RELEASE_FILES[@]}"; do
    [[ -f "$RELEASE_DIR/$name" ]] || die "发布目录缺少文件: $name"
  done
}

publish_release() {
  local name
  release_store_guard

  local staging="/tmp/dazah-release-$VERSION"
  log "上传发布包到 $DEPLOY_HOST:$staging"
  if [[ "$DEPLOY_MODE" == "local" ]]; then
    sudo -n rm -rf "$staging"
    sudo -n mkdir -p "$staging"
    sudo -n cp -a "$RELEASE_DIR"/. "$staging"/
  else
    remote_sudo "set -e; rm -rf '$staging' && mkdir -p '$staging' && chown '$DEPLOY_USER': '$staging'"
    for name in "${RELEASE_FILES[@]}"; do
      scp "${SSH_OPTS[@]}" "$RELEASE_DIR/$name" "$DEPLOY_USER@$DEPLOY_HOST:$staging/$name"
    done
  fi

  log "登记不可变发布目录 $REMOTE_RELEASES/$VERSION"
  remote_sudo "set -e; if [ -e '$REMOTE_RELEASES/$VERSION' ]; then echo '远端版本目录已存在，拒绝覆盖' >&2; exit 1; fi; mkdir -p '$REMOTE_RELEASES/$VERSION'; mv '$staging'/* '$REMOTE_RELEASES/$VERSION'/; rmdir '$staging'; install -m 0755 '$REMOTE_RELEASES/$VERSION/deploy-production.sh' '$REMOTE_ROOT/current/deploy-production.sh'"
}

predeploy_backup() {
  if [[ "$PREDEPLOY_BACKUP" != "1" ]]; then
    log "WARNING: PREDEPLOY_BACKUP=0，跳过发布前备份"
    return 0
  fi
  log "执行发布前在线备份（数据库、Redis、持久卷和配置）"
  remote_sudo "python3 '$REMOTE_ROOT/control/controller.py' backup" \
    || die "发布前备份失败，终止部署"

  local latest
  latest="$(remote_sudo "latest=\$(ls -1dt '$REMOTE_DATA'/backups/daily-* 2>/dev/null | head -1); if [ -n \"\$latest\" ] && [ -f \"\$latest/manifest.json\" ]; then printf '%s\n' \"\$latest\"; else exit 1; fi")" \
    || die "未找到带 manifest.json 的备份目录，终止部署"
  log "发布前备份完成: $latest"
  log "提示：这是在线备份，数据库与对象文件不保证同一时间点；关键迁移仍需人工确认恢复点"
}

verify_release() {
  log "验证生产部署"
  remote_sudo "'$REMOTE_ROOT/current/deploy-production.sh' verify" \
    || die "部署后验证失败；不要自动重试或关闭维护模式"
}

deploy_release() {
  validate_release_input
  predeploy_backup
  publish_release

  log "调用生产部署脚本: $VERSION"
  if ! remote_sudo "'$REMOTE_ROOT/current/deploy-production.sh' deploy '$VERSION' '$REMOTE_RELEASES/$VERSION' '$NOTICE_SECONDS'"; then
    log "ERROR: 部署失败。维护模式可能仍然开启；先执行 status/verify，确认现场后再决定回滚或修复。" >&2
    exit 1
  fi
  verify_release
  log "部署完成并通过验证: $VERSION"
}

rollback_release() {
  validate_version "$VERSION"
  release_store_guard

  log "检查服务器回滚版本: $VERSION"
  remote_sudo "test -d '$REMOTE_RELEASES/$VERSION'" \
    || die "服务器缺少 $VERSION 的发布目录"

  log "调用生产回滚脚本: $VERSION"
  if ! remote_sudo "'$REMOTE_ROOT/current/deploy-production.sh' rollback '$VERSION' '$REMOTE_RELEASES/$VERSION' '$NOTICE_SECONDS'"; then
    log "ERROR: 回滚失败；维护模式可能仍然开启，先检查 status/verify。" >&2
    exit 1
  fi
  verify_release
  log "回滚完成并通过验证: $VERSION"
}

case "$ACTION" in
  deploy|rollback|verify|status|backup) ;;
  *)
    usage
    exit 2
    ;;
esac

[[ "$DEPLOY_MODE" == "ssh" || "$DEPLOY_MODE" == "local" ]] || die "DEPLOY_MODE 只能是 ssh 或 local"
[[ "$DEPLOY_HOST" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$ ]] || die "DEPLOY_HOST 不合法"
[[ "$DEPLOY_USER" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "DEPLOY_USER 不合法"
[[ "$REMOTE_ROOT" =~ ^/[A-Za-z0-9._/-]+$ ]] || die "REMOTE_ROOT 必须是不含空格的绝对路径"
[[ "$REMOTE_RELEASES" =~ ^/[A-Za-z0-9._/-]+$ ]] || die "REMOTE_RELEASES 必须是不含空格的绝对路径"
[[ "$REMOTE_DATA" =~ ^/[A-Za-z0-9._/-]+$ ]] || die "REMOTE_DATA 必须是不含空格的绝对路径"
[[ "$NOTICE_SECONDS" =~ ^[0-9]+$ ]] || die "NOTICE_SECONDS 必须是整数"
NOTICE_SECONDS=$((10#$NOTICE_SECONDS))
(( NOTICE_SECONDS <= 3600 )) || die "NOTICE_SECONDS 不能超过 3600"

case "$ACTION" in
  deploy)
    deploy_release
    ;;
  rollback)
    rollback_release
    ;;
  verify)
    verify_release
    ;;
  status)
    remote_sudo "'$REMOTE_ROOT/current/deploy-production.sh' status"
    ;;
  backup)
    predeploy_backup
    ;;
esac
