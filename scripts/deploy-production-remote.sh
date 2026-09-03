#!/usr/bin/env bash
# Dazah production deployment helper for the Linux host.
#
# The local PowerShell wrapper uploads an immutable release directory and then
# calls this script. It is also safe to call directly on the server:
#   sudo /opt/dazah/current/deploy-production.sh status
#
# Secrets are deliberately never printed.

set -Eeuo pipefail

ROOT_DIR="${DAZAH_DEPLOY_ROOT:-/opt/dazah/current}"
RELEASE_DIR="${DAZAH_RELEASE_DIR:-/opt/dazah/releases}"
BACKUP_DIR="${DAZAH_BACKUP_DIR:-/opt/dazah/backups/deploy}"
COMPOSE_PROJECT="${DAZAH_COMPOSE_PROJECT:-dazah}"
LOCK_FILE="${DAZAH_DEPLOY_LOCK:-/var/lock/dazah-deploy.lock}"
ENV_FILE="$ROOT_DIR/.env"
COMPOSE_FILE="$ROOT_DIR/compose.yml"
EDGE_COMPOSE_FILE="$ROOT_DIR/compose.edge.yml"

log() {
  printf '[dazah-deploy] %s\n' "$*"
}

fail() {
  log "ERROR: $*" >&2
  return 1
}

die() {
  fail "$*"
  exit 1
}

if [[ "${EUID}" -ne 0 && "${DAZAH_ALLOW_UNPRIVILEGED:-0}" != "1" ]]; then
  exec sudo -E bash "$0" "$@"
fi

mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
flock -n 9 || die "已有另一个部署操作正在执行"

require_file() {
  local path="$1"
  [[ -f "$path" ]] || die "缺少文件: $path"
}

validate_version() {
  local version="$1"
  [[ "$version" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$ ]] \
    || die "版本号不合法: $version"
}

compose() {
  local args=(
    --project-name "$COMPOSE_PROJECT"
    --env-file "$ENV_FILE"
    --file "$COMPOSE_FILE"
  )
  if [[ -f "$EDGE_COMPOSE_FILE" ]]; then
    args+=(--file "$EDGE_COMPOSE_FILE")
  fi
  docker compose "${args[@]}" "$@"
}

current_version() {
  awk -F= '$1 == "DAZAH_VERSION" { print $2; exit }' "$ENV_FILE"
}

set_version() {
  local version="$1"
  local temp_file
  temp_file="$(mktemp "$ROOT_DIR/.env.deploy.XXXXXX")"
  awk -v version="$version" '
    BEGIN { replaced = 0 }
    /^DAZAH_VERSION=/ {
      print "DAZAH_VERSION=" version
      replaced = 1
      next
    }
    { print }
    END {
      if (!replaced) print "DAZAH_VERSION=" version
    }
  ' "$ENV_FILE" > "$temp_file"
  chmod 600 "$temp_file"
  mv -f "$temp_file" "$ENV_FILE"
}

backup_current_files() {
  local previous_version="$1"
  local stamp
  local backup_path
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_path="$BACKUP_DIR/${stamp}-${previous_version:-unknown}"
  mkdir -p "$backup_path"
  chmod 700 "$BACKUP_DIR" "$backup_path"

  for name in .env compose.yml compose.edge.yml nginx.default.conf; do
    if [[ -f "$ROOT_DIR/$name" ]]; then
      cp -p "$ROOT_DIR/$name" "$backup_path/$name"
    fi
  done
  printf '%s\n' "$previous_version" > "$backup_path/current-version"
  printf '%s\n' "$backup_path" > "$BACKUP_DIR/last-backup"
  printf '%s\n' "$backup_path"
}

restore_backup() {
  local backup_path="$1"
  [[ -d "$backup_path" ]] || return 1
  for name in .env compose.yml compose.edge.yml nginx.default.conf; do
    if [[ -f "$backup_path/$name" ]]; then
      cp -p "$backup_path/$name" "$ROOT_DIR/$name"
    else
      rm -f "$ROOT_DIR/$name"
    fi
  done
  chmod 600 "$ENV_FILE"
}

restore_after_failed_change() {
  local backup_path="$1"
  log "部署失败，恢复部署前的配置文件"
  restore_backup "$backup_path" || log "WARNING: 配置恢复失败，请检查 $backup_path"
  if compose config --quiet >/dev/null 2>&1; then
    compose up -d --remove-orphans >/dev/null 2>&1 || \
      log "WARNING: 旧版本容器未能自动恢复，请执行 status 检查"
    if [[ -f "$EDGE_COMPOSE_FILE" ]]; then
      recreate_nginx >/dev/null 2>&1 || \
        log "WARNING: nginx 未能在配置恢复后重建"
    fi
  fi
}

verify_release_checksum() {
  local release_path="$1"
  local checksum_path="$release_path.sha256"
  local release_dir

  [[ -f "$release_path" ]] || return 1
  if [[ ! -f "$checksum_path" ]]; then
    log "WARNING: 未找到 SHA-256 校验文件，继续加载镜像包"
    return 0
  fi

  release_dir="$(dirname "$release_path")"
  (cd "$release_dir" && sha256sum -c "$(basename "$checksum_path")")
}

resolve_release_tar() {
  local version="$1"
  local release_path="${2:-}"

  if [[ -f "$release_path" ]]; then
    printf '%s\n' "$release_path"
  elif [[ -f "$release_path/dazah-$version.tar" ]]; then
    printf '%s\n' "$release_path/dazah-$version.tar"
  elif [[ -f "$RELEASE_DIR/dazah-$version.tar" ]]; then
    # Compatibility with the first manually deployed release layout.
    printf '%s\n' "$RELEASE_DIR/dazah-$version.tar"
  fi
}

load_release_images() {
  local version="$1"
  local release_path="${2:-}"
  if [[ -n "$release_path" && -f "$release_path" ]]; then
    verify_release_checksum "$release_path" || return 1
    log "加载离线镜像包: $(basename "$release_path")"
    docker load --input "$release_path"
  else
    log "未找到离线镜像包，检查服务器现有镜像: $version"
  fi

  docker image inspect \
    "dazah/backend:$version" \
    "dazah/frontend:$version" \
    "dazah/hermes-lite:$version" \
    >/dev/null 2>&1 || {
      log "镜像包中缺少版本 $version 所需的应用镜像" >&2
      return 1
    }
}

stage_release_compose() {
  local release_path="$1"
  if [[ -f "$release_path/compose.yml" ]]; then
    install -m 0644 "$release_path/compose.yml" "$COMPOSE_FILE"
  fi
  if [[ -f "$release_path/compose.edge.yml" ]]; then
    install -m 0644 "$release_path/compose.edge.yml" "$EDGE_COMPOSE_FILE"
  fi
  if [[ -f "$release_path/nginx.default.conf" ]]; then
    install -m 0644 "$release_path/nginx.default.conf" "$ROOT_DIR/nginx.default.conf"
  fi
}

verify_compose_images() {
  local image
  while IFS= read -r image; do
    [[ -n "$image" ]] || continue
    if ! docker image inspect "$image" >/dev/null 2>&1; then
      log "服务器缺少 Compose 所需镜像: $image" >&2
      return 1
    fi
  done < <(compose config --images)
}

wait_for_healthy() {
  local deadline=$((SECONDS + 180))
  local service
  local container_id
  local state
  local health
  local all_ok
  local services=(db redis minio app hermes-lite frontend)
  if [[ -f "$EDGE_COMPOSE_FILE" ]]; then
    services+=(nginx)
  fi

  while (( SECONDS < deadline )); do
    all_ok=1
    for service in "${services[@]}"; do
      container_id="$(compose ps -q "$service" 2>/dev/null || true)"
      if [[ -z "$container_id" ]]; then
        all_ok=0
        continue
      fi
      state="$(docker inspect -f '{{.State.Status}}' "$container_id" 2>/dev/null || true)"
      health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id" 2>/dev/null || true)"
      if [[ "$state" != "running" ]]; then
        all_ok=0
      elif [[ "$health" != "none" && "$health" != "healthy" ]]; then
        all_ok=0
      fi
    done

    if (( all_ok == 1 )) \
      && curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null \
      && curl --fail --silent --show-error http://127.0.0.1:8100/health >/dev/null; then
      return 0
    fi
    sleep 3
  done

  compose ps
  return 1
}

check_nginx() {
  local container_id
  container_id="$(compose ps -q nginx 2>/dev/null || true)"
  if [[ -n "$container_id" ]]; then
    docker exec "$container_id" nginx -t >/dev/null
  fi
}

recreate_nginx() {
  [[ -f "$EDGE_COMPOSE_FILE" ]] || return 0
  # nginx.default.conf is a single-file bind mount. stage_release_compose uses
  # an atomic replacement, so an existing container keeps the old inode even
  # after `nginx -s reload`. Recreating nginx is required to bind the new file.
  compose up -d --no-deps --force-recreate nginx >/dev/null
}

verify_proxy_routes() {
  [[ -f "$EDGE_COMPOSE_FILE" ]] || return 0
  local path
  local url
  local deadline
  local verified
  for path in health login; do
    deadline=$((SECONDS + 30))
    verified=0
    while (( SECONDS < deadline )); do
      for url in "http://127.0.0.1/$path" "https://127.0.0.1/$path"; do
        if curl --fail --silent --show-error --location --insecure --max-time 5 \
          "$url" >/dev/null; then
          verified=1
          break
        fi
      done
      if (( verified == 1 )); then
        break
      fi
      sleep 1
    done
    if (( verified == 0 )); then
      log "反向代理检查失败: /$path" >&2
      return 1
    fi
  done
}

write_success_marker() {
  local version="$1"
  local backup_path="$2"
  mkdir -p "$BACKUP_DIR"
  printf 'version=%s\nbackup=%s\ncompleted_at=%s\n' \
    "$version" "$backup_path" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$BACKUP_DIR/last-success"
}

deploy_version() {
  local version="$1"
  local release_path="${2:-$RELEASE_DIR/$version}"
  local release_tar
  local previous_version
  local backup_path

  validate_version "$version"
  require_file "$ENV_FILE"
  require_file "$COMPOSE_FILE"

  previous_version="$(current_version)"
  backup_path="$(backup_current_files "$previous_version")"
  release_tar="$(resolve_release_tar "$version" "$release_path" || true)"

  if ! load_release_images "$version" "$release_tar"; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  if ! stage_release_compose "$release_path"; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  set_version "$version"

  if ! compose config --quiet; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  if ! verify_compose_images; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  if ! compose up -d --remove-orphans; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  if ! wait_for_healthy; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  if ! recreate_nginx || ! check_nginx || ! verify_proxy_routes; then
    restore_after_failed_change "$backup_path"
    return 1
  fi

  write_success_marker "$version" "$backup_path"
  log "部署成功: $version"
  compose ps
}

rollback_version() {
  local version="$1"
  local release_path="${2:-$RELEASE_DIR/$version}"
  local release_tar
  local previous_version
  local backup_path

  validate_version "$version"
  require_file "$ENV_FILE"
  require_file "$COMPOSE_FILE"

  previous_version="$(current_version)"
  backup_path="$(backup_current_files "$previous_version")"
  release_tar="$(resolve_release_tar "$version" "$release_path" || true)"

  if ! load_release_images "$version" "$release_tar"; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  if ! stage_release_compose "$release_path"; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  set_version "$version"

  if ! compose config --quiet || ! verify_compose_images; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  if ! compose up -d --remove-orphans; then
    restore_after_failed_change "$backup_path"
    return 1
  fi
  if ! wait_for_healthy \
    || ! recreate_nginx \
    || ! check_nginx \
    || ! verify_proxy_routes; then
    restore_after_failed_change "$backup_path"
    return 1
  fi

  write_success_marker "$version" "$backup_path"
  log "回滚成功: $previous_version -> $version"
  log "注意：回滚只切换应用镜像和 Compose 配置，不会自动回滚数据库迁移"
  compose ps
}

status() {
  require_file "$ENV_FILE"
  printf 'current_version=%s\n' "$(current_version)"
  if compose config --quiet >/dev/null 2>&1; then
    compose ps
  else
    log "Compose 配置校验失败，以下为 Docker 容器状态"
    docker ps --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
      --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
  fi
}

verify() {
  require_file "$ENV_FILE"
  require_file "$COMPOSE_FILE"
  compose config --quiet
  verify_compose_images
  wait_for_healthy
  check_nginx
  verify_proxy_routes
  log "验证成功: $(current_version)"
}

usage() {
  cat <<'EOF'
用法:
  deploy-production.sh deploy <version> [release-directory]
  deploy-production.sh rollback <version> [release-directory]
  deploy-production.sh status
  deploy-production.sh verify

发布目录默认位于 /opt/dazah/releases/<version>。
EOF
}

action="${1:-}"
case "$action" in
  deploy)
    [[ $# -ge 2 ]] || die "deploy 需要版本号"
    deploy_version "$2" "${3:-$RELEASE_DIR/$2}"
    ;;
  rollback)
    [[ $# -ge 2 ]] || die "rollback 需要版本号"
    rollback_version "$2" "${3:-$RELEASE_DIR/$2}"
    ;;
  status)
    status
    ;;
  verify)
    verify
    ;;
  *)
    usage
    exit 2
    ;;
esac
