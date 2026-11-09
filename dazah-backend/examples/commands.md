# 常用命令

在 `dazah-backend/` 运行 `uv` 命令；`docker compose` 和根目录检查脚本在工作区
根目录运行。先确认本次修改触达的调用链和测试，不把全量检查作为局部修改的默认步骤。

## 定向代码验证

开发环境依赖尚未准备时，按当前 CI 同步两种开发依赖集合：

```powershell
uv sync --frozen --extra dev --group dev
```

依赖齐备后按触达路径选择检查：

```powershell
uv run --no-sync ruff check app/modules/quality tests/unit/test_quality_management_state_boundaries.py
uv run --no-sync mypy app/modules/quality
uv run --no-sync pytest tests/unit/test_quality_management_state_boundaries.py
```

以上用现有质量模块举例，实际执行时替换为触达代码和对应测试路径；API 路由
变化还要运行对应的 `AsyncClient` 接口测试。
新增或修改 Model/migration 时，先确认独立测试库的 `TEST_DATABASE_URL` 与
开发库隔离，再验证 Alembic head、相关升级/降级和数据库测试。降级只在可重建的
独立测试库执行，不在日常开发库试运行。

`TEST_DATABASE_URL` 用于测试 fixture；Alembic 从 `app/core/config.py` 的
`DATABASE_URL` 取目标，不会因配置了测试 URL 自动迁移测试库。验证测试库迁移时，
由配置加载器在隔离子进程内将已核对的 `TEST_DATABASE_URL` 映射为该进程的
`DATABASE_URL`，然后执行 `alembic heads/current`、升级或降级；不改写环境文件，
不把连接串写入命令、日志或输出。未建立这种隔离执行环境时停止数据库验证，
不得直接运行默认 `alembic upgrade head`。纯单测也先检查 fixture 导入是否要求
测试库配置，不绕过数据库安全检查。

## 开发库迁移

需要启动依赖数据库的开发服务时，先核对根目录 `.env.local` 指向本次授权的
开发库，并确认代码只有一个 Alembic head、数据库 current 是否落后。数据库
落后时，在根目录通过开发镜像的 `migrate` 服务升级；成功后再次核对
`current == head`，再启动或重建 `app` 并检查容器健康和 `/health`。

数据库服务已在本次授权开发环境中运行时，以下命令仅查看目标与迁移计划：

```powershell
docker compose --env-file .env.local -f compose.dev.yml run --rm --no-deps -T migrate plan
```

确认计划后执行开发库迁移；已有明确迁移授权时按根规范传入 `-MigrationApproval`：

```powershell
.\scripts\dev.ps1 -Migrate
docker compose --env-file .env.local -f compose.dev.yml run --rm --no-deps -T migrate check
```

当前 `migrate` 的入口为 `app.core.dev_migration`，默认命令是只读 `check`，
`plan` 展示经核对的目标、唯一 head 和待执行版本；不能把 Alembic 命令直接追加
到该服务名后。不要替换 entrypoint 绕过确认。`dev.ps1 -Migrate` 完成迁移后返回，
不会自动重启应用；依赖或镜像需要更新时先构建，迁移验证成功后再按根规范重建或
启动 `app`，检查容器健康和 `/health`。出现多个 head、版本不在迁移链、未预期
DROP 或目标库无法确认时停止，不使用 `stamp` 或手工 SQL 绕过。

## 提交前的范围检查

```powershell
python scripts/check-test-impact.py --base origin/main --head HEAD
```

`origin/main` 仅用于目标分支确为 `main` 的仓库。该脚本检查已提交历史；
未提交改动仍需按 `.ci/test-impact-policy.toml` 人工核对。
完整后端 CI 门禁及适用条件见 `../AGENTS.md`。
