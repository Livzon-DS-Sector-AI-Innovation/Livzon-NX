# Dazah Backend

原料药事业部工厂数字化基座后端服务。

## Tech Stack

- **Python 3.12+** with FastAPI
- **PostgreSQL 17** + **Redis**
- **SQLAlchemy 2.0** (async) + **Alembic** (migrations)
- **Pydantic v2** for validation
- **uv** for package management

## Quick Start

### Prerequisites

- Python >= 3.12
- PostgreSQL 17
- Redis
- [uv](https://docs.astral.sh/uv/)

### Setup

```bash
# 1. Install dependencies
uv sync

# 2. Install Playwright (required for regulatory tracker crawler)
playwright install chromium

# 3. Configure the workspace root environment
# From the workspace root, copy .env.local.example to .env.local.

# 4. Database migrations
alembic upgrade head

# 5. Seed initial data (regulatory tracker)
python scripts/seed_regulatory_tracker.py
python scripts/seed_regulatory_documents.py

# 6. Start the server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Access the API docs at http://localhost:8000/docs

## Architecture

Modular monolith with clear boundaries:

```
app/
├── core/              # Infrastructure (config, database, security, exceptions)
├── shared/            # Cross-module contracts (base models, module registry)
├── platform/          # Platform capabilities (audit, identity, integrations)
├── modules/           # Business modules
│   ├── production/    # 生产管理
│   ├── equipment/     # 设备管理
│   ├── safety/        # 安全管理
│   ├── energy/        # 能源管理
│   ├── quality/       # 质量管理
│   ├── hr/            # 人事管理
│   ├── registration/  # 注册管理
│   ├── research/      # 研发管理
│   └── ...
└── api/               # Global router
```

Each module maintains its own API routes, schemas, services, repositories, and models.

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
| **Research** | Experiments, ICH analysis |

## Development

```bash
# Run tests
uv run pytest

# Code quality
uv run ruff check .
uv run mypy app/

# 分层类型门禁（不受其他模块历史错误影响）
uv run python scripts/check_agent_types.py
uv run python scripts/check_foundation_types.py
uv run python scripts/check_identity_types.py

# Format code
uv run ruff format .
```

### Database Migrations

```bash
# Create migration (after modifying models)
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

**Important**: When adding a new schema, manually add `CREATE SCHEMA IF NOT EXISTS` at the start of `upgrade()` — Alembic won't generate it automatically.

## Docker Deployment

Run Docker commands from the workspace root. The backend image and Compose
service are defined by the root `Dockerfile` and `compose.dev.yml`/`compose.yml`.

```bash
# Development stack (from the workspace root)
docker compose --env-file .env.local -f compose.dev.yml up -d --build app

# Production stack (from the workspace root)
docker compose --env-file .env -f compose.yml up -d app
```

## Environment Variables

The canonical templates are the workspace root `.env.example` (production) and
`.env.local.example` (development). The root Compose files inject internal
container URLs such as `API_BASE_URL`; separate backend `.env` files are not
used.

### Feishu Module Boundaries and Utilities

Feishu credentials are owned by each business module. The platform integration
layer only provides stateless helpers for parsing Bitable URLs, requesting
tenant tokens from explicit credentials, and testing Bitable connectivity.
Do not add a global Feishu credential store unless a separate requirement
explicitly asks for one.

Platform app, shared by SSO, organization sync, common IM and common Bitable:

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_REDIRECT_URI=http://localhost:8000/api/v1/identity/auth/callback
FRONTEND_URL=http://localhost:3000
FEISHU_SCOPES=contact:contact.base:readonly contact:user.base:readonly
```

HR Bitable tables use the platform app credentials plus these table settings:

```env
FEISHU_BITABLE_APP_TOKEN=base_or_wiki_converted_app_token
FEISHU_BITABLE_EMPLOYEE_TABLE_ID=tblEmployee
FEISHU_BITABLE_DEPARTMENT_TABLE_ID=tblDepartment
FEISHU_BITABLE_OFFBOARDING_TABLE_ID=tblOffboarding
FEISHU_BITABLE_ONBOARDING_TABLE_ID=tblOnboarding
FEISHU_BITABLE_DEPARTURE_TABLE_ID=tblDeparture
FEISHU_BITABLE_APPROVAL_TABLE_ID=tblApproval
```

Other modules can either reuse the platform app with their own Bitable IDs:

```env
FEISHU_BITABLE_PRODUCT_APP_TOKEN=base_or_wiki_converted_app_token
FEISHU_BITABLE_PRODUCT_TABLE_ID=tblProduct
```

or use an explicitly independent Feishu app when the module owns a separate bot:

```env
SAFETY_FEISHU_APP_ID=cli_xxx
SAFETY_FEISHU_APP_SECRET=your_safety_app_secret
SAFETY_FEISHU_BITABLE_APP_TOKEN=base_or_wiki_converted_app_token
SAFETY_FEISHU_BITABLE_HAZARD_TABLE_ID=tblHazard
EQUIPMENT_FEISHU_APP_ID=cli_xxx
EQUIPMENT_FEISHU_APP_SECRET=your_equipment_app_secret
```

Warehouse Feishu settings are managed by the warehouse module itself through
`/api/v1/warehouse/feishu-config`. The warehouse module stores its own app
credentials and Bitable table IDs; it calls platform Feishu helpers only for
parsing and connectivity checks.

Module boundary rules:

- `app/platform/integrations/feishu` contains generic Feishu utilities only.
- `app/modules/<module>/feishu` contains module-specific Feishu business flows.
- Modules must not import another module's Feishu business integration package.

Operational checks:

- SSO login: `GET /api/v1/identity/auth/login`
- Organization sync: `POST /api/v1/identity/sync/departments` and `POST /api/v1/identity/sync/members`
- HR sync: `POST /api/v1/hr/employees/sync-from-feishu`
- Onboarding sync: `POST /api/v1/hr/onboarding-records/sync-from-feishu`
- Departure sync: `POST /api/v1/hr/departure-records/sync-from-feishu`
- Product sync: `POST /api/v1/product/products/sync-from-feishu`

## Frontend Integration

The frontend (`dazah-frontend/`) is a Next.js application that connects to this backend:

- **Development**: Next.js proxy forwards `/api/v1/*` requests to backend
- **Production**: nginx reverse proxy handles routing
- **API path**: All endpoints under `/api/v1/<module>/<resource>`

## Health Check

```bash
curl http://localhost:8000/health
```
