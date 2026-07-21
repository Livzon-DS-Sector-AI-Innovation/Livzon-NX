#!/bin/bash
set -e

echo "========================================"
echo "  Database Initialization"
echo "========================================"

# 等待 PostgreSQL 就绪
until pg_isready -h localhost -p 5432 -U postgres; do
  echo "Waiting for database..."
  sleep 2
done

# 创建数据库（如果不存在）
psql -h localhost -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'dazah'" | grep -q 1 || \
  psql -h localhost -U postgres -c "CREATE DATABASE dazah"

# 执行数据库迁移（创建 schema）
cd /app/backend
uv run alembic upgrade head

# 检查是否已有数据（以 employees 表记录数判断）
EMP_COUNT=$(psql -h localhost -U postgres -d dazah -tc "SELECT COUNT(*) FROM hr.employees" | xargs)
if [ "$EMP_COUNT" -eq "0" ] && [ -f /app/backend/dump.sql ]; then
  echo "Importing existing data from dump.sql..."
  psql -h localhost -U postgres -d dazah < /app/backend/dump.sql
  echo "Data import complete."
else
  echo "Database already has data ($EMP_COUNT employees), skipping import."
fi

# 执行种子数据（幂等，补充 departments/teams 等基础数据）
uv run python scripts/seed.py

echo "Database initialization complete."
