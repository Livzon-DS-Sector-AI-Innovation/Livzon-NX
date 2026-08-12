# Dazah Project

This workspace contains the Dazah platform parts used together during local
development:

- `dazah-backend/` - FastAPI modular monolith and business API.
- `dazah-frontend/` - Next.js App Router frontend.
- `Hermes-Lite/` - Livzon Agent orchestration layer.

The root only provides development orchestration. Business code, module
boundaries, Feishu ownership, migrations, and Agent tool rules remain governed
by each subproject's `AGENTS.md`.

## Daily Development

Start the complete root development stack (backend, frontend, Hermes-Lite,
EDBO, PostgreSQL, Redis, and MinIO):

```powershell
Copy-Item .env.local.example .env.local
.\scripts\dev.ps1
```

Reuse the existing development images without rebuilding:

```powershell
.\scripts\dev.ps1 -NoBuild
```

Useful local URLs:

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Hermes health: http://localhost:8100/health
- MinIO console: http://localhost:9001

## API Type Sync

After backend API changes, regenerate the OpenAPI spec and frontend TypeScript
types from the root:

```powershell
.\scripts\generate-api.ps1
```

This runs:

1. `uv run python scripts/export_openapi.py` in `dazah-backend/`
2. `pnpm generate:api` in `dazah-frontend/`

Commit the backend `openapi.json` and frontend generated schema together when
the API contract changed.

## Configuration Notes

- Browser-side frontend code must call relative `/api/v1/...` paths.
- Frontend server-side code must use `API_BASE_URL`.
- Do not use `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_API_URL`, or similar
  variables for backend API access.
- Do not introduce a global Feishu configuration store; each business module
  owns its own Feishu configuration source.

## Root Docker Images

The root Dockerfiles expose one target per application service while preserving
the platform's separate-container architecture:

| Environment | Dockerfile | Runtime environment file |
| --- | --- | --- |
| Production | `Dockerfile` | `.env` |
| Development | `Dockerfile.dev` | `.env.local` |

Available targets are `backend`, `edbo`, `frontend`, and `hermes`.

Start the complete development stack from the workspace root:

```powershell
Copy-Item .env.local.example .env.local
docker compose --env-file .env.local -f compose.dev.yml up -d --build
```

Environment files are runtime inputs and are intentionally excluded from the
Docker build context. Never copy production credentials into an image. Use
`.env.example` and `.env.local.example` as templates.

Production uses the root `compose.yml` and a single root `.env`. The application
images and dependency images must be built or pulled on a connected workstation,
exported with `docker save`, uploaded, and loaded on the Linux host before:

```bash
docker compose --env-file .env -f compose.yml config --quiet
docker compose --env-file .env -f compose.yml up -d
```

Production services use `pull_policy: never`, so deployment does not depend on
the server reaching an image registry. The root Compose runs Alembic migrations
to `head` before starting the backend. The subproject Compose files are retained
for historical compatibility but are not workspace deployment entry points.
