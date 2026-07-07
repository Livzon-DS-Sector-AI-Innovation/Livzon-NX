# Dazah Production Deployment

This deployment runs three application services in one Docker network:

- `frontend`: Next.js dashboard
- `backend`: FastAPI platform API, database migrations, Agent gateway
- `hermes-lite`: isolated central Agent orchestration service

PostgreSQL and Redis are private containers. Hermes-Lite is also private and is
only called by the backend.

## First Deploy

```bash
cp .env.prod.example .env.prod
# Edit .env.prod and replace all change-me values.

docker compose --env-file .env.prod -f docker-compose.prod.yml build
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db redis
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d backend hermes-lite frontend
```

If bundled MinIO is required, add `--profile storage` to the `build`, `up`, and
`run` commands.

## Health Checks

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f backend
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f hermes-lite
```

Expected internal service URLs:

```text
frontend -> http://backend:8000
backend  -> http://hermes-lite:8100/v1/chat
hermes   -> http://backend:8000/api/v1/agent/llm
hermes   -> http://backend:8000/api/v1/agent/tools/execute
```

## Upgrade

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml pull
docker compose --env-file .env.prod -f docker-compose.prod.yml build
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d backend hermes-lite frontend
```

The production backend service runs `uv run alembic upgrade head` before
starting Uvicorn, so normal deploys apply committed migrations automatically.

Do not commit `.env.prod` or any real secret file.
