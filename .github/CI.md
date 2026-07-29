# CI 测试与合并门禁

根目录工作流 `workflows/ci.yml` 是单体仓库唯一生效的 GitHub Actions
入口，在 `main`、`dev` 的 push、pull request 以及手动触发时运行。

## Required checks

GitHub 分支保护如可用，应只绑定稳定汇总 job：

- `CI Gate`

`CI Gate` 汇总 `Test Impact`、`Frontend Test`、`Backend Test`、
`Backend Docker Build` 和 `Hermes Test`。`Frontend Test` 继续汇总所有前端
检查；任一依赖失败、取消或跳过，最终门禁都会失败。

`Test Impact` 根据 `.ci/test-impact-policy.toml` 验证生产变更是否同步了对应
模块测试。未分类的生产路径失败关闭，详细开发契约见
`docs/module-development-ci.md`。

`Backend Test` 使用独立的 PostgreSQL `dazah_test` 服务容器，检查唯一 Alembic
head、在空库执行全量 migration，再运行包含接口集成测试的全量 Pytest。

## 测试分层

- 静态检查：前端全量 ESLint、TypeScript `tsc --noEmit`；后端 Ruff
  仅阻断 pull request 或 push 中新增、复制、修改、重命名的 Python 文件。
  这是历史问题清理期间的渐进门禁，变更文件必须零 Ruff 错误；基线清零后改回全库检查。
- 单元测试：前端 Vitest 同时采集全量 `src` 覆盖率；后端单元测试包含在全量
  Pytest 中；Hermes-Lite 执行 Pytest 和关键入口编译检查。
- 接口集成测试：使用真实 FastAPI 路由和 PostgreSQL 测试容器运行后端测试集。
- 数据库测试：空 PostgreSQL 数据库必须能从零升级到唯一 Alembic head。
- 浏览器测试：`Frontend E2E` 使用 Playwright Chromium 执行不依赖真实外部服务的
  采购关键流程。
- 构建测试：Next.js production build、前端 Docker build、后端 Docker build。

## 覆盖率提升计划

当前覆盖率门禁采用渐进治理：

- 前端覆盖整个 `src`（生成类型除外），初始基线为行 0.15%、语句 0.15%、
  函数 0.14%、分支 0.17%。这些数值只允许上调；PR 变更的可执行行覆盖率不得
  低于 80%。
- 后端覆盖 `app`，行覆盖率不得低于 60%，分支覆盖率不得低于 33.5%，PR
  变更的可执行行覆盖率不得低于 80%。
- 低覆盖模块不通过排除生产代码处理。触达模块时由变更行门禁强制补测试，
  全局和分支基线只允许随测试建设逐步上调。

覆盖率报告作为 CI artifact 保留 14 天。提升基线必须在同一 pull request 中提交
具有业务断言的测试，优先覆盖业务规则、权限、确认流程、失败分支和真实
FastAPI 路由。

## Gitea 合并门禁

`.gitea/workflows/ci.yml` 在 PR 的合并结果工作树上执行同一套前后端覆盖率策略，
并运行 `test-impact`、`frontend-e2e` 和 `hermes-quality`。稳定的
`merge-gate` 汇总全部子检查；Gitea 分支保护只需要长期绑定一次
`merge-gate`，以后可以在不修改保护规则的情况下扩展其依赖。

ESLint 当前同样保持零 error 门禁；历史 warning 不会被本次基线阻断，但新增代码
不得扩大 warning 数量，并应按模块逐步清理。
