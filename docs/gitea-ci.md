# Gitea PR 合并门禁

## 仓库与门禁范围

当前仓库是 monorepo。合并门禁覆盖两个主要交付物：

- `dazah-frontend/`：Next.js 16、React 19、TypeScript 5、pnpm 10、ESLint、Vitest。
- `dazah-backend/`：FastAPI、Python 3.12、uv、Ruff、mypy、pytest、Alembic、PostgreSQL。

`Hermes-Lite/` 是独立的 Agent 编排层，目前没有纳入本次固定 Required Status
Checks。若它需要独立阻断，应另建稳定的 `hermes-quality` 和
`hermes-container` Job，不能复用或动态改名现有 Job。

## 仓库检测记录

- 前端 `package.json` 声明 `packageManager: pnpm@10.33.0`，Dockerfile 使用
  Node 20；虽然同时存在历史 `package-lock.json`，项目规范、锁文件和脚本均以
  `pnpm-lock.yaml`/pnpm 为权威。脚本包含 `lint`、`typecheck`、`test:unit`、
  `build`、`generate:api`；Vitest 使用 run mode，另有 Playwright E2E 配置。
- 前端 ESLint 为 flat config，TypeScript 开启 strict。现有 lint 使用
  `eslint-warning-baseline.json`：本次实测 0 error、1090/1090 个历史 warning，
  新增 warning 会失败，但尚未达到绝对零 warning。
- 后端没有主项目 `requirements.txt`，以 `pyproject.toml`、`uv.lock` 和
  Python `>=3.12` 为权威；配置了 Ruff、strict mypy、pytest/pytest-asyncio 和
  60% coverage 门槛。`edbo_service/` 与 `Hermes-Lite/` 另有 requirements。
- 后端使用 Alembic，迁移目录为 `dazah-backend/alembic/versions/`；实测只有
  `d6e8f4a1b2c3` 一个 head。仓库已提交 `dazah-backend/openapi.json`，导出脚本
  已改为递归键排序、UTF-8 和固定末尾换行。
- 前后端都有 production Dockerfile 与 `docker-compose.yml`，前端另有 dev/
  runtime Dockerfile，后端 Compose 包含 PostgreSQL、Redis、MinIO 和 EDBO。
- 检查时还发现根 `.github/workflows/ci.yml`，以及工作区中已被用户删除的两个
  子项目旧 GitHub workflow；本次未修改这些用户工作，只新增 Gitea workflow。
- 本机检测值为 Node 24.18.0、npm 11.16.0、pnpm 11.9.0、系统 Python
  3.11.15、隔离 `.venv-ci` Python 3.12.13、uv 0.11.32、Docker 29.6.1、
  Compose 5.3.0。Runner 必须使用下文项目要求版本，不能照搬本机版本。

## 文件结构

```text
.gitea/
  CODEOWNERS
  workflows/ci.yml
.pre-commit-config.yaml
scripts/
  ci.sh
  check-branch-policy.sh
  prepare-integration.sh
  wait-for-database.sh
dazah-frontend/scripts/ci.sh
dazah-backend/scripts/
  ci.sh
  ruff-changed.sh
docs/gitea-ci.md
```

`.gitattributes` 强制 shell 脚本使用 LF。工作流只监听进入 `dev` 和 `main` 的
Pull Request，不执行 push、镜像推送、部署或生产 migration。

这些新脚本在当前 WSL 文件系统中已设置可执行位。由于 Windows Git 对 NTFS
通常使用 `core.filemode=false`，最终维护者暂存文件时应在 Linux/WSL 核对
`git ls-files --stage '*.sh'` 为 `100755`；若显示 `100644`，在暂存范围确认后
由维护者执行 `git update-index --chmod=+x <脚本路径>`。工作流显式使用
`bash` 调用，因此不会依赖 checkout 后的执行位才能启动。

## 固定 Job 与作用

| Required Status Check | 作用 |
| --- | --- |
| `branch-policy` | `main` 仅接受 `dev`；`dev` 仅接受允许前缀的开发分支并拒绝 `main`。 |
| `frontend-quality` | 合并目标分支后检查前端生成 API 类型漂移，并执行冻结依赖安装、ESLint、独立 TypeScript 检查和 Vitest。 |
| `frontend-build` | 对合并结果执行 Next.js production build，使用本机安全占位 API 地址。 |
| `frontend-container` | 校验 Compose，使用 PR SHA 和 `--pull=false` 构建本地镜像，不推送。 |
| `backend-quality` | 冻结安装后对 PR 新增/修改的 Python 文件执行 Ruff lint，再运行 compileall、核心基础设施严格 mypy，并在隔离 PostgreSQL 上运行后端单元测试。 |
| `backend-integration` | 使用独立 PostgreSQL，验证唯一 Alembic head、升级、drift、OpenAPI、应用导入、全量 pytest 与 60% coverage。 |
| `backend-container` | 校验 Compose，使用 PR SHA 和 `--pull=false` 构建本地镜像，不推送。 |

除 `branch-policy` 外，每个 Job 都从 PR head SHA checkout 完整历史，然后运行
`prepare-integration.sh` 拉取并以 `--no-commit --no-ff` 合入最新目标分支。
冲突、空白错误或冲突标记会在任何业务检查前失败；不会创建提交或 push。

## 本地执行

以下命令应在 Linux 或 WSL 的仓库根目录执行。数据库检查必须使用专用测试库，
绝不能使用开发共享库或生产库。

根聚合入口支持 `bash scripts/ci.sh quality|build|integration|container|security|all`
以及 `frontend-*`/`backend-*` 精确阶段；下列子项目入口更适合定向调试。

```bash
bash dazah-frontend/scripts/ci.sh quality
API_BASE_URL=http://127.0.0.1:8000 bash dazah-frontend/scripts/ci.sh build
bash dazah-frontend/scripts/ci.sh container
bash dazah-frontend/scripts/ci.sh security

export DATABASE_URL=postgresql+asyncpg://dazah_ci:dazah_ci_test@localhost:5432/dazah_ci_test
export TEST_DATABASE_URL="$DATABASE_URL"
export PGHOST=localhost PGPORT=5432 PGUSER=dazah_ci
export PGPASSWORD=dazah_ci_test PGDATABASE=dazah_ci_test
bash dazah-backend/scripts/ci.sh quality
bash dazah-backend/scripts/ci.sh integration
bash dazah-backend/scripts/ci.sh container
bash dazah-backend/scripts/ci.sh security
```

后端 Ruff 采用增量门禁：CI 根据 PR base/head SHA 只检查新增或修改的 Python
文件，历史告警不会阻塞无关变更。开发机可启用同一套 pre-commit 钩子：

```bash
uvx pre-commit install
uvx pre-commit run --all-files
```

日常提交默认只检查暂存的后端 Python 文件；`--all-files` 用于主动清理历史问题。

在本地验证分支策略：

```bash
GITHUB_HEAD_REF=feature/example GITHUB_BASE_REF=dev \
  bash scripts/check-branch-policy.sh
GITHUB_HEAD_REF=dev GITHUB_BASE_REF=main \
  bash scripts/check-branch-policy.sh
```

`prepare-integration.sh` 只接受 `GITHUB_EVENT_NAME=pull_request`，并会修改当前
worktree/index 为未提交的临时 merge 状态；请仅在干净的临时 clone 中运行，
不要在有开发修改的工作区运行。

## Gitea Actions 与 Runner

Runner 必须注册 `linux-amd64` 标签，并在 Job 环境中提供：

- bash、git，且 checkout 必须是完整历史；
- Node.js 20、Corepack/pnpm 10.33.0；
- Python 3.12、uv；
- Docker CLI、可访问的 Docker daemon、支持 `config --no-env-resolution` 的较新
  Docker Compose v2 plugin；
- PostgreSQL client（`pg_isready`）；
- 出站或内部镜像源访问，用于冻结依赖安装及缺失的基础镜像/service image。

工作流唯一使用的外部 Action 是 `actions/checkout@v4`，没有依赖
`setup-node`、`setup-python`、缓存或 artifact Action。根据
[Gitea Actions 官方说明](https://docs.gitea.com/usage/actions/comparison)，
`DEFAULT_ACTIONS_URL=github` 时 Runner 从 GitHub 获取它；若实例设置为 `self`，
管理员必须先在本 Gitea 镜像 `actions/checkout` 并保留 `v4` tag。首次启用前应
用一个诊断 Job 确认上述命令版本和 Docker daemon 权限。仓库本身无法读取实例
级 `DEFAULT_ACTIONS_URL` 或 Runner 镜像内容，因此这一步必须由管理员核对。

PostgreSQL Job service 使用 `postgres:17`。内网 Runner 应预先缓存或在 Docker
daemon 配置允许的内部 registry mirror；应用 Docker build 使用
`--pull=false`，不会主动刷新已经存在的 base image。

两个后端 Job 都按容器化 act_runner 的标准 service DNS 使用
`postgres:5432`，不发布宿主机端口，因此并行执行不会争抢 `5432`。若
`linux-amd64` 被配置成纯 host executor 而不是 Job 容器，管理员必须先验证
service DNS；不支持时应为两个 Job 配置不同的宿主机测试端口并同步各自
`DATABASE_URL`/`PG*`，不能改接共享或生产数据库。

## Protected Branch 配置

先至少成功运行一次本工作流，再从 Gitea 最近上报的 Status Context 中选择准确
名称。不要手工猜测 Context，也不要启用通过 PR 标题或 commit message 跳过
Actions 的策略。

### `dev`

1. Repository Settings → Branches → Branch protection 新建精确规则 `dev`。
2. 禁止直接 Push 和 Force Push。
3. 仅允许 `Developers`、`Owners` 合并。
4. 要求 Pull Request；至少一人批准。
5. 启用“新提交撤销旧批准”。
6. 启用 PR 落后目标分支时禁止合并/必须为最新。
7. 选择本文列出的全部七个 Required Status Checks。
8. 启用 Code Owner 审批，并要求管理员同样遵守规则、不得绕过。

### `main`

1. 新建精确规则 `main`，禁止直接 Push 和 Force Push。
2. 只允许 `Owners` 合并，并要求 Pull Request 和至少一人批准。
3. 启用“新提交撤销旧批准”和“PR 必须为最新”。
4. 选择本文列出的全部七个 Required Status Checks。
5. 启用 Code Owner 审批，并要求管理员同样遵守规则、不得绕过。
6. `branch-policy` 强制来源严格为 `dev`；任何 feature/fix/hotfix 直达
   `main` 都会失败。

`.gitea/CODEOWNERS` 使用 Gitea 要求的 Go 正则格式，而不是 GitHub glob。
规则当前指向 `@Livzon-DS-Sector-AI-Innovation/Owners`。若 Gitea 上的组织
slug 与当前 Git remote 组织不同，管理员必须在启用 Code Owner 审批前把该
slug 改为 Gitea 的真实组织 slug。语法依据：
[Gitea Code Owners 文档](https://docs.gitea.com/usage/repository/code-owners)。

## 安全扫描

`dazah-frontend/scripts/ci.sh security` 运行 `pnpm audit --audit-level high`；
`dazah-backend/scripts/ci.sh security` 使用 `pip-audit` 审计由 `uv.lock` 导出的
生产依赖。当前未把两项加入 Required Job：审计依赖实时漏洞源和网络，且尚未
确认现有锁文件无历史漏洞。命令保留真实非零退出码；清理基线并确保 Runner 可
稳定访问漏洞源后，再新增固定的非动态 Job，经过观察期后设为 Required。

严格 mypy 当前先阻断 `app/core`。全量 `mypy app` 的现有错误尚未清零；每次扩展
范围必须先修复目标模块，不能通过新增 ignore 或降低 strict 规则换取通过。

## 渐进式质量基线

- 全量 `ruff check .` 初始实测有 7497 个既有错误，主要分布于历史 migration、
  `versions_backup`、内嵌 EDBO、scripts 以及旧 app/test 代码。Required Job
  只拦截 PR 新增/修改的 Python 文件；全量扫描仍用于度量并应按模块逐批清理。
- `chore/ruff-format-baseline` 独立 worktree 已执行 `ruff format .`，格式化 558
  个文件，`ruff format --check .` 随后通过。该分支不得混入业务或 migration
  修复，需独立审查和发布。
- schema drift 已通过 `fbffa92623e9` migration 修复；PostgreSQL 17 上的空库和
  合法存量数据均完成 upgrade/downgrade 往返，`alembic check` 无新增操作。
- `mypy app/core` 通过；全量 `mypy app` 仍有大量既有 strict 错误，所以当前只
  阻断核心目录。

这些历史问题没有通过 `continue-on-error` 或 `|| true` 掩盖。前端 lint、
typecheck、Vitest、production build、Compose 校验和 Docker build 已实跑通过；
后端 Docker build、唯一 Alembic head、迁移往返、核心 mypy 和 OpenAPI 稳定性
检查已通过；完整 pytest 实测 880 项通过，覆盖率 62.35%（门槛 60%）。Gitea
仍会在 PR 合并结果上重新执行同一套 `backend-integration`。

## 常见失败

- `branch-policy`：检查日志中的 Source/Target；开发分支必须使用允许前缀，
  `main` PR 的 source 必须精确为 `dev`。
- merge 或 `git diff --check`：先把目标分支更新合入开发分支，在本地解决冲突
  或空白错误，再 push 新提交。
- checkout Action 无法下载：检查 `DEFAULT_ACTIONS_URL`，内网 `self` 实例需
  镜像 `actions/checkout@v4`。
- `pnpm`/`uv`/`pg_isready`/Docker 缺失：修复 `linux-amd64` Runner 镜像，
  不要在命令后添加 `|| true`。
- Alembic 多 head 或 drift：创建并审查正常 migration；不要在 CI 自动 merge
  migration heads，也不要连接生产库。
- OpenAPI drift：从仓库根目录运行 `./scripts/generate-api.ps1`（Windows）或
  等价的现有契约生成链路，审查并提交后端/前端生成文件。
- Compose 校验失败：确认 Compose v2、必需 Docker 网络声明和配置语法；CI
  使用 `/dev/null` 和 `--no-env-resolution`，不读取项目 env file、不启动服务。
- Docker build 因 base image 缺失失败：预缓存固定 base image 或配置内部
  registry mirror；CI 不 push 镜像。
