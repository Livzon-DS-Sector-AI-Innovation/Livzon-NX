# 模块开发与持续集成契约

## 目标

团队成员开发业务功能时只需要按模块新增生产代码和对应测试。CI 工作流保持稳定，
自动完成变更分类、测试影响检查、覆盖率、集成测试、构建和关键 E2E。除非引入新的
测试技术或交付物，普通业务 PR 不应修改 CI YAML。

## 分支与合并路径

默认目标分支为 `main`，开发分支通过 PR 合并；若任务明确使用其他目标分支，
整个流程使用该目标。Git 写操作授权和同步要求以根目录 `AGENTS.md` 为准。
工作流兼容 `main`、`dev`，不强制旧的“开发分支 → dev → main”路径。

- `CI Gate` 是稳定的聚合检查名称，分支保护应绑定实际已上报的该 context。
- 本次范围内的必需任务必须成功；不适用的任务允许跳过，失败或取消不能当作成功。
- `.github/CODEOWNERS` / 根目录 `CODEOWNERS` 单独修改只执行范围、策略和源码安全检查。
- CI、策略、共享脚本、未知目录和根目录运行配置变更保守触发全项目；不以忽略未知路径提速。
- 手动 `workflow_dispatch` 执行全量验证，即使当前分支与 `origin/main` 相同。

## 变更与测试映射

| 生产代码 | 同一 PR 必须修改的测试 |
| --- | --- |
| `dazah-backend/app/modules/<module>/` | `tests/modules/<module>/`，或名称包含模块名的 unit/integration 测试 |
| `dazah-backend/app/core/` | `tests/core/` 或后端 unit 测试 |
| `dazah-backend/app/platform/<area>/` | 对应 platform、unit 或 integration 测试 |
| `dazah-backend/alembic/` | 名称包含 migration、schema 或 alembic 的测试 |
| 后端 Agent 工具、Agent 模块（含其 LLM 代理） | 所属业务模块测试、后端 Agent/LLM 测试、Hermes 测试三组 |
| `dazah-frontend/src/components/<module>/` | 同模块 `*.test.ts(x)` 或 `e2e/<module>/*.spec.ts` |
| `dazah-frontend/src/app/(dashboard)/<module>/` | 同模块单测或 E2E |
| 前端 actions、stores、API client | 文件所属领域的单测或 E2E |
| 其他前端 `src` 生产代码 | 至少一个前端单测或 E2E |
| Hermes runtime、service、tool、plugin | `Hermes-Lite/tests/test_*.py` |

权威机器规则位于 `.ci/test-impact-policy.toml`。规则可以叠加，例如修改
`quality/agent_tools.py` 不能只补一个无关后端测试，而是需要质量模块、Agent
契约和 Hermes 适配测试。

普通业务 `app/core/llm/` 变更要求后端 core/unit 和 Agent/LLM 测试，不无条件要求修改 Hermes 测试；实际跨服务契约变化仍需对应适配测试。

## 测试层级

1. 单元测试：纯函数、Service 规则、参数转换、权限判断、状态流转。
2. 接口集成测试：FastAPI 真实路由、认证授权、4xx、事务和响应 Schema。
3. 数据库测试：Repository、约束、空库 migration、upgrade/downgrade。
4. 组件测试：表单、筛选、分页、缓存刷新、加载/空/失败状态。
5. 关键 E2E：审批、驳回、删除、确认、权限拒绝和后端失败反馈。
6. 契约测试：OpenAPI 生成无漂移，Agent 工具与 Hermes 适配一致。

覆盖率只作为第二道防线：

- 前后端 PR 变更可执行行覆盖率不得低于 80%。
- 后端全量行覆盖率不得低于 60%，分支覆盖率不得低于 33.5%。
- 前端历史全量基线不得下降。

## 开发流程

1. 在获得 Git 操作授权后，按根目录规范从确认的目标分支准备开发分支。
2. 先确定所属模块和风险路径，再编写或更新测试。
3. 实现生产代码，运行定向测试。
4. 提交前运行测试影响检查：

   ```bash
   python scripts/check-test-impact.py --base origin/main --head HEAD
   ```

5. 按风险执行子项目门禁：

   ```bash
   bash dazah-frontend/scripts/ci.sh quality
   bash dazah-frontend/scripts/ci.sh e2e
   bash dazah-backend/scripts/ci.sh quality
   bash dazah-backend/scripts/ci.sh integration
   bash Hermes-Lite/scripts/ci.sh
   ```

6. PR 描述中填写测试证据。
7. Owners 审查业务正确性、测试断言和规则匹配，`CI Gate` 成功后合并。

## 规则调整与例外

- 不允许用无断言测试、无关测试、提高排除范围或降低阈值绕过门禁。
- 纯删除、机械重命名或不可自动测试的变化如果被规则拦截，应在 PR 中说明原因，
  由 Owners 审查并最小修改 `.ci/test-impact-policy.toml`。
- 测试影响规则、CI 工作流、覆盖率脚本和 PR 模板均受 CODEOWNERS 保护。
- 新增业务模块时，必须在同一 PR 中增加模块测试目录；现有通用规则通常无需修改。
- 只有新增新的代码根目录、测试框架或交付物时，才扩展底层规则与 CI Job。

## GitHub 分支保护

管理员先让工作流成功运行一次，然后为实际使用的目标分支配置（以根目录规范为准）：

- 禁止直接 Push 和 Force Push；
- 必须通过 PR，至少一名审批人；
- 启用 Code Owner 审批和新提交撤销旧批准；
- PR 必须基于最新目标分支；
- Required Status Check 只绑定实际已上报的 `CI Gate` context；
- 管理员同样遵守保护规则，不允许 Force merge 绕过。

## 执行成本与验证责任

- 前端 Quality 执行 lint、类型、全量单测覆盖率、构建与 Docker 验证。E2E 和隔离测试下载同次运行的 tar 包，保留隐藏目录、权限及链接，不重复构建 Next.js。
- 镜像仍通过真实 Dockerfile 独立构建；前端 Buildx 使用专用缓存 scope，避免与后端缓存互相覆盖。
- Backend Quality 仅承担静态检查；Integration 保留全量单测、接口测试、迁移、契约与覆盖率，消除 Quality 中重复的 unit/core 测试及数据库启动。
- 源码安全、镜像安全、覆盖率阈值和 Agent/Hermes 契约验证保持启用。构建产物仅保留一天，缺失必须失败，不能跳过 E2E。
- 优化效果应比较同类 PR 的任务和步骤耗时；本地静态验证不能替代 GitHub 上的 Linux 构建、产物传递与 E2E 实测。
- PostgreSQL service 使用 `POSTGRES_INITDB_ARGS` 传递 [PostgreSQL 17 的 `initdb -c` 参数](https://www.postgresql.org/docs/17/app-initdb.html)，保留连接数和会话超时配置；不使用 GitHub Actions 不支持的 `services.command`。
