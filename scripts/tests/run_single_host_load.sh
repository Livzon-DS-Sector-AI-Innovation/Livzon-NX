#!/usr/bin/env bash
set -euo pipefail
network=dazah-load-test
volume=dazah_cd_load_pgdata
names=(dazah-load-nginx-dev dazah-load-app-dev dazah-load-redis-dev dazah-load-db-dev)
for name in "${names[@]}"; do
  if docker inspect "$name" >/dev/null 2>&1; then echo "Existing test container: $name; inspect before retry"; exit 1; fi
done
if docker volume inspect "$volume" >/dev/null 2>&1; then echo "Existing test volume; inspect before retry"; exit 1; fi
docker network create --internal "$network" >/dev/null
cleanup() {
  for name in "${names[@]}"; do docker logs --tail 50 "$name" > "/var/tmp/$name.log" 2>&1 || true; done
  for name in "${names[@]}"; do docker rm -f "$name" >/dev/null 2>&1 || true; done
  docker network rm "$network" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker volume create --label dazah.role=isolated-test "$volume" >/dev/null
docker run -d --name dazah-load-db-dev --network "$network" --label dazah.role=isolated-test --memory 768m --cpus .75 -v "$volume:/var/lib/postgresql/data" -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=dazah_cd_test postgres:17 postgres -c max_connections=80 >/dev/null
docker run -d --name dazah-load-redis-dev --network "$network" --label dazah.role=isolated-test --memory 64m --cpus .25 redis:8-alpine >/dev/null
for i in $(seq 1 30); do docker exec dazah-load-db-dev pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
env_args=(-e APP_ENV=development -e FRONTEND_URL=http://127.0.0.1:18080 -e DATABASE_URL=postgresql+asyncpg://postgres@dazah-load-db-dev:5432/dazah_cd_test -e REDIS_URL=redis://dazah-load-redis-dev:6379/0 -e LOCAL_LOGIN_MODE=enabled -e BOOTSTRAP_ADMIN_USERNAME=cd-bootstrap -e BOOTSTRAP_ADMIN_PASSWORD=cd-test-only-2026 -e SECRET_KEY=cd-isolated-test-only -e FEISHU_WS_ENABLED=false -e EQUIPMENT_FEISHU_WS_ENABLED=false -e LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=false -e LIVZON_FEISHU_EVENT_WS_ENABLED=false -e MINIO_ENABLED=false)
docker run --rm --network "$network" --memory 1024m --cpus 1 "${env_args[@]}" dazah/backend:cd-verify-dev .venv/bin/alembic upgrade head >/var/tmp/dazah-cd-load-migration.log 2>&1
docker run -d --name dazah-load-app-dev --network "$network" --label dazah.role=isolated-test --memory 1792m --cpus 1.75 --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges --tmpfs /app/data:rw,mode=1777,size=64m "${env_args[@]}" dazah/backend:cd-verify-dev .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --limit-concurrency 64 --timeout-keep-alive 5 >/dev/null
for i in $(seq 1 60); do docker exec dazah-load-app-dev .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)" >/dev/null 2>&1 && break; sleep 2; done
docker exec dazah-load-app-dev .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)" >/dev/null
install -d /var/tmp/dazah-cd-load-site
cat > /var/tmp/dazah-cd-load-site/default.conf <<'CONF'
server {
  listen 80;
  server_name localhost;
  include /etc/nginx/dazah-server-guard.conf;
  location /api/ {
    include /etc/nginx/dazah-api-guard.conf;
    proxy_pass http://dazah-load-app-dev:8000;
  }
}
CONF
docker run -d --name dazah-load-nginx-dev --network "$network" --label dazah.role=isolated-test --memory 96m --cpus .25 -p 127.0.0.1:18080:80 -v /var/tmp/dazah-cd-load-site/default.conf:/etc/nginx/conf.d/default.conf:ro -v /opt/dazah/control/nginx-capacity.conf:/etc/nginx/conf.d/dazah-capacity.conf:ro -v /opt/dazah/control/nginx-api-guard.conf:/etc/nginx/dazah-api-guard.conf:ro -v /opt/dazah/control/nginx-server-guard.conf:/etc/nginx/dazah-server-guard.conf:ro nginx:1.27-alpine >/dev/null
sleep 2
timeout 2700 python3 /var/tmp/dazah-cd-validation/load_single_host.py
docker inspect --format '{{.Name}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}' "${names[@]}"
