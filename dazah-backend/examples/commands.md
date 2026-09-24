# 常用命令

在 `dazah-backend/` 运行 `uv` 命令；`docker compose` 和根目录检查脚本在工作区
根目录运行。先确认本次修改触达的调用链和测试，不把全量检查作为局部修改的默认步骤。

## 定向代码验证

```bash
uv run ruff check app/modules/quality tests/unit/test_quality_management_state_boundaries.py
uv run mypy app/modules/quality
uv run pytest tests/unit/test_quality_management_state_boundaries.py
```

以上用现有质量模块举例，实际执行时替换为触达代码和对应测试路径；API 路由
变化还要运行对应的 `AsyncClient` 接口测试。
新增或修改 Model/migration 时，先确认独立测试库的 `TEST_DATABASE_URL` 与
开发库隔离，再验证 Alembic head、相关升级/降级和数据库测试。降级只在可重建的
独立测试库执行，不在日常开发库试运行。

## 开发库迁移

需要启动依赖数据库的开发服务时，先核对根目录 `.env.local` 指向本次授权的
开发库，并确认代码只有一个 Alembic head、数据库 current 是否落后。数据库
落后时，在根目录通过开发镜像的 `migrate` 服务升级；成功后再次核对
`current == head`，再启动或重建 `app` 并检查容器健康和 `/health`。

```bash
docker compose --env-file .env.local -f compose.dev.yml run --rm migrate .venv/bin/alembic heads
docker compose --env-file .env.local -f compose.dev.yml run --rm migrate .venv/bin/alembic current
docker compose --env-file .env.local -f compose.dev.yml run --rm migrate
```

`migrate` 的默认命令是 `alembic upgrade head`。出现多个 head、版本不在迁移链、
未预期 DROP 或目标库无法确认时停止，不使用 `stamp` 或手工 SQL 绕过。

## 提交前的范围检查

```bash
python scripts/check-test-impact.py --base origin/main --head HEAD
```

`origin/main` 仅用于目标分支确为 `main` 的仓库。该脚本检查已提交历史；
未提交改动仍需按 `.ci/test-impact-policy.toml` 人工核对。
完整后端 CI 门禁及适用条件见 `../AGENTS.md`。
