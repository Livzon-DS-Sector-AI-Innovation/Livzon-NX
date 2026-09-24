# Development Setup

本项目是模块化单体。日常开发使用工作区根目录 `.env.local`、`compose.dev.yml`
和 `Dockerfile.dev`；业务归属见 `../../docs/business-module-boundaries.md`。

## 数据库和迁移前提

- ORM 结构变化必须有 Alembic revision；不使用 `Base.metadata.create_all()`
  建开发库，不改已执行的历史 migration。
- Git 同步、分支和提交按根目录 `AGENTS.md` 的授权边界执行；开发指南不自动执行
  `pull`、`merge` 或切换分支。
- 启动开发后端或依赖数据库的验证前，确认 `.env.local` 中 `DATABASE_URL` 指向
  本次授权的开发库。先检查代码只有一个 Alembic head，再比较数据库 current；
  版本不在当前迁移链、多个 head 或目标库不明时停止。
- `TEST_DATABASE_URL` 必须指向独立、可重建的测试库。运行数据库测试时不得回退
  到 `DATABASE_URL`，也不在开发库上试运行 downgrade。

在**工作区根目录**启动开发依赖并检查迁移状态：

```powershell
docker compose --env-file .env.local -f compose.dev.yml up -d db redis
docker compose --env-file .env.local -f compose.dev.yml run --rm migrate .venv/bin/alembic heads
docker compose --env-file .env.local -f compose.dev.yml run --rm migrate .venv/bin/alembic current
```

确认数据库落后后，使用开发栈的迁移服务；依赖或镜像输入改变时先更新开发镜像：

```powershell
docker compose --env-file .env.local -f compose.dev.yml build migrate app
docker compose --env-file .env.local -f compose.dev.yml run --rm migrate
docker compose --env-file .env.local -f compose.dev.yml run --rm migrate .venv/bin/alembic current
```

迁移成功且 `current == head` 后，再启动或重建后端：

```powershell
docker compose --env-file .env.local -f compose.dev.yml up -d --force-recreate app
docker compose --env-file .env.local -f compose.dev.yml ps app
Invoke-RestMethod http://localhost:8000/health
```

`migrate` 默认执行 `alembic upgrade head`。生成 migration 时可在已确认目标的
开发环境使用 `uv run alembic revision --autogenerate -m "<变更说明>"`，随后逐行
审查 `upgrade()`、`downgrade()` 和跨模块 drift；未预期 DROP 立即停止。

## 定向测试与日常排查

在 `dazah-backend/` 运行与改动直接相关的 Ruff、Mypy 和 Pytest；涉及数据库的
Pytest 必须先确认根目录 `.env.local` 的专用 `TEST_DATABASE_URL` 已配置并迁移。
命令选择见 `../examples/commands.md`。纯单测和静态检查不需要等待开发库迁移。

在工作区根目录查看开发服务状态：

```powershell
docker compose --env-file .env.local -f compose.dev.yml ps
docker compose --env-file .env.local -f compose.dev.yml logs -f db
docker compose --env-file .env.local -f compose.dev.yml logs -f redis
```

重置持久化卷会删除本地数据，不属于日常开发或迁移流程；仅在明确要求重置并
核对卷范围后单独执行。不得用重置、`stamp` 或手工 SQL 掩盖迁移失败。
