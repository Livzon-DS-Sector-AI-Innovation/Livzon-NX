# CI 测试与合并门禁

根目录工作流 `workflows/ci.yml` 是单体仓库唯一生效的 GitHub Actions
入口，在 `main`、`dev` 的 push、pull request 以及手动触发时运行。

## Required checks

分支保护规则使用以下稳定的 job 名称：

- `Backend Test`
- `Frontend Test`
- `Lint`
- `Type Check`
- `Unit Tests`
- `Docker Build`
- `Frontend Build`
- `Backend Docker Build`

`Frontend Test` 是前端聚合门禁；即使某个依赖检查失败，它也会运行并明确失败。
`Backend Test` 使用独立的 PostgreSQL `dazah_test` 服务容器，检查唯一 Alembic
head、在空库执行全量 migration，再运行包含接口集成测试的全量 Pytest。

## 测试分层

- 静态检查：前端全量 ESLint、TypeScript `tsc --noEmit`；后端 Ruff
  仅阻断 pull request 或 push 中新增、复制、修改、重命名的 Python 文件。
  这是历史问题清理期间的渐进门禁，变更文件必须零 Ruff 错误；基线清零后改回全库检查。
- 单元测试：前端 Vitest；后端单元测试包含在全量 Pytest 中。
- 接口集成测试：使用真实 FastAPI 路由和 PostgreSQL 测试容器运行后端测试集。
- 数据库测试：空 PostgreSQL 数据库必须能从零升级到唯一 Alembic head。
- 构建测试：Next.js production build、前端 Docker build、后端 Docker build。

## 覆盖率提升计划

当前后端门禁使用 `--cov-fail-under=50`，覆盖范围为 `app`。提升阈值时只修改
工作流中的这一参数，并在同一 pull request 中提交用于达到新基线的测试：

1. 基线稳定后从 50 提升到 60。
2. 核心模块和主要错误路径覆盖后从 60 提升到 70。
3. 达到 70 后继续按模块观察覆盖率，但不得通过排除业务文件降低统计口径。

每次提升前应连续通过主分支构建，并优先补充业务规则、权限、失败分支和真实
FastAPI 路由测试，避免为了数字编写没有行为断言的测试。

ESLint 当前同样保持零 error 门禁；历史 warning 不会被本次基线阻断，但新增代码
不得扩大 warning 数量，并应按模块逐步清理。
