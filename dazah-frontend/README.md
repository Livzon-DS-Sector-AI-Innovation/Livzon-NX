# Dazah Frontend

原料药厂管理系统前端 — Next.js 16 + TypeScript + Ant Design。

## Tech Stack

- **Next.js 16** with App Router
- **React 19** + **TypeScript**
- **Ant Design V6** (antd)
- **Tailwind CSS** for utility styles
- **Zustand** for client state
- **React Query** for server state
- **React Hook Form** + **Zod** for forms

## Quick Start

```bash
# Install dependencies
pnpm install

# Start development server
docker compose -f docker-compose.dev.yml up -d --build

# Or run directly
pnpm dev --port 3000
```

Access at http://localhost:3000

## Architecture

```
src/
├── app/(dashboard)/     # Route pages (Server Components)
├── components/          # UI components by module
├── actions/             # Server Actions (write operations)
├── stores/              # Zustand stores (client state)
├── types/               # TypeScript type definitions
├── lib/                 # Utilities and API helpers
└── proxy.ts             # API proxy to backend
```

**Key principles:**
- Pages are Server Components that fetch data and pass to Client Components
- Write operations use Server Actions in `actions/`
- Each module has its own directory boundary — import through `index.ts`
- Client components use `'use client'` directive

## Business Modules

| Module | Description |
|--------|-------------|
| **Production** | Batch management, process records, material balance |
| **Equipment** | Asset registry, maintenance, inspection, spare parts |
| **Safety** | Hazard identification, risk management, special operations |
| **Energy** | Device monitoring, alerts, collection logs |
| **Quality** | Deviations, CAPA, CPV (process validation) |
| **HR** | Employee profiles, onboarding, training, attendance |
| **Registration** | Dossier writing, regulatory tracking, supplementary replies |
| **Research** | Experiments, Bayesian optimization, ICH analysis |

## API Integration

The frontend connects to `dazah-backend` (FastAPI):

- **Client code**: Use relative paths `/api/v1/...` (proxied automatically)
- **Server code**: Use `API_BASE_URL` environment variable
- **Development**: Next.js proxy forwards to backend at port 8000
- **Production**: nginx reverse proxy handles routing

## Development

```bash
# Development with hot reload (recommended)
docker compose -f docker-compose.dev.yml up -d --build

# Production build
docker compose up -d --build
```

**Important**: Always use `docker-compose.dev.yml` for daily development to get hot reload.

If file changes are still not reflected immediately in Docker Desktop/Windows,
recreate the dev container so the polling watcher settings are applied:

```bash
docker compose -f docker-compose.dev.yml up -d --force-recreate frontend
```

When accessing the dev server through a LAN IP or custom host, add it to
`NEXT_ALLOWED_DEV_ORIGINS` as a comma-separated list before starting the
container.

## Design System

UI components follow the design system in `DESIGN.md` — includes color palette, typography, spacing, and component specifications based on Ant Design V6.

## Project Conventions

See `AGENTS.md` for detailed coding standards:
- Module boundary rules
- Server vs Client component patterns
- Naming conventions
- API routing architecture

## Health Check

```bash
curl http://localhost:3000
```
