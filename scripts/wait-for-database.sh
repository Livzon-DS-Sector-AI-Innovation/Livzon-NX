#!/usr/bin/env bash
set -euo pipefail

db_host="${PGHOST:-localhost}"
db_port="${PGPORT:-5432}"
db_user="${PGUSER:-dazah_ci}"
db_name="${PGDATABASE:-dazah_ci_test}"
attempts="${DB_WAIT_ATTEMPTS:-30}"
interval="${DB_WAIT_INTERVAL_SECONDS:-2}"

command -v pg_isready >/dev/null 2>&1 || {
  echo "pg_isready is required on the runner." >&2
  exit 1
}

echo "Waiting for PostgreSQL at ${db_host}:${db_port}/${db_name} as ${db_user}..."
for ((attempt = 1; attempt <= attempts; attempt++)); do
  if pg_isready \
    --host "$db_host" \
    --port "$db_port" \
    --username "$db_user" \
    --dbname "$db_name" >/dev/null 2>&1; then
    echo "PostgreSQL is ready."
    exit 0
  fi
  echo "Database not ready (${attempt}/${attempts})."
  sleep "$interval"
done

echo "PostgreSQL did not become ready after ${attempts} attempts." >&2
exit 1
