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

For faster source reloads on Windows, use the hybrid native-development
launcher. It keeps PostgreSQL, Redis, MinIO, and EDBO in Docker, while running
the Backend, Frontend, and Hermes-Lite as local processes:

```powershell
.\scripts\dev-native.ps1
```

On the first run, or after dependency changes, synchronize native dependencies:

```powershell
.\scripts\dev-native.ps1 -Sync
```

The launcher uses `pnpm` when it is available and otherwise falls back to
Node.js Corepack, using the `pnpm@10.33.0` version declared by the project.

The launcher runs the native Alembic migration before starting the Backend,
automatically maps Compose service URLs to localhost, and uses Next.js
Turbopack by default. Use `-FrontendWebpack` if the Webpack development
command is needed. Before starting Frontend, it stops a leftover Next.js
process for this project and clears the generated `.next/dev` route cache; it
also probes a protected page route before reporting Frontend as ready. Press
`Ctrl+C` to stop the three native processes; the four infrastructure
containers remain running. Stop those containers explicitly when the
development environment is no longer needed:

```powershell
docker compose --env-file .env.local -f compose.dev.yml stop db redis minio edbo-service
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

- Environment configuration has one source per environment: the workspace
  root `.env.local` for development and the workspace root `.env` for
  production. Do not create `.env`, `.env.local`, or other environment files
  inside `dazah-backend/`, `dazah-frontend/`, or `Hermes-Lite/`.
- The root `.env.local` is used by native development and `compose.dev.yml`;
  the production host keeps its root `.env` at `/opt/dazah/current/.env`.
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
for historical compatibility, read `../.env.local`/`../.env`, and are not
workspace deployment entry points.
