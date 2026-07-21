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

Start backend services and the frontend dev server:

```powershell
.\scripts\dev.ps1
```

Start Hermes-Lite as well:

```powershell
.\scripts\dev.ps1 -WithHermes
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
