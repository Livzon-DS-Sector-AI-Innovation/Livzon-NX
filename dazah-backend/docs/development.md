# Development Setup

This project is a modular monolith. Different developers can own different
business modules, but all database structure changes must be aligned through
Alembic migrations committed to the repository.

## Database Alignment Rules

- Do not use `Base.metadata.create_all()` for development databases.
- Every ORM model change that affects PostgreSQL must have an Alembic revision.
- Before creating a migration, pull the latest branch and run migrations first:

```powershell
uv run alembic upgrade head
```

- Create a migration after editing models:

```powershell
uv run alembic revision --autogenerate -m "add production batch table"
```

- Review the generated migration before committing it. Alembic can detect many
  changes, but it cannot reliably infer data backfills, column renames, or
  destructive operations.
- If two developers create migrations from the same parent revision, resolve the
  branch before merging. Usually this means rebasing one branch and regenerating
  the migration. Use an Alembic merge revision only when both migration branches
  are intentionally kept.

## Local PostgreSQL and Redis on Windows

Copy the root development environment template once (from the workspace root):

```powershell
Copy-Item .env.local.example .env.local
```

Start only PostgreSQL and Redis:

```powershell
docker compose --env-file .env.local -f compose.dev.yml up -d db redis
```

Run migrations:

```powershell
uv run alembic upgrade head
```

Start the backend locally:

```powershell
uv run uvicorn app.main:app --reload
```

The local application should use these URLs from the root `.env.local`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/dazah
REDIS_URL=redis://localhost:6379/0
```

Pytest must use a separate database because several tests commit setup and
cleanup statements. Do not point tests at the development database above.

```env
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/dazah_test
```

Create and migrate the test database before running pytest:

```powershell
createdb -h localhost -U postgres dazah_test
$env:TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/dazah_test"
uv run alembic upgrade head
uv run pytest
```

## Optional Full Docker Run

To run the application inside Docker as well:

```powershell
docker compose --env-file .env.local -f compose.dev.yml up -d --build
```

The app container runs `alembic upgrade head` before starting Uvicorn. It uses
the Docker service hostnames from the root `.env.local.example`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/dazah
REDIS_URL=redis://redis:6379/0
```

## Useful Commands

```powershell
docker compose --env-file .env.local -f compose.dev.yml ps
docker compose --env-file .env.local -f compose.dev.yml logs -f db
docker compose --env-file .env.local -f compose.dev.yml logs -f redis
docker compose --env-file .env.local -f compose.dev.yml down
```

To reset only local container data:

```powershell
docker compose --env-file .env.local -f compose.dev.yml down -v
docker compose --env-file .env.local -f compose.dev.yml up -d db redis
uv run alembic upgrade head
```
