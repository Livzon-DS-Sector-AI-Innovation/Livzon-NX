# Jenkins CI/CD 全流程方案（单台生产服务器）

> 状态：方案与参考实现，**尚未启用**。本文件不改变当前 GitHub Actions 的
> `CI Gate`，也不改变服务器上的 `dazah-cd.timer` 或现有发布流程。
>
> 适用项目：`dazah-project`（Next.js 前端 + FastAPI 后端 + Hermes-Lite）。
> 生产服务器：`192.168.40.251`，Ubuntu 22.04，4 核 8 GB，单机。
>
> 参考实现：
>
> - [`Jenkinsfile`](../../Jenkinsfile)
> - [`scripts/jenkins/build-release.sh`](../../scripts/jenkins/build-release.sh)
> - [`scripts/jenkins/deploy-release.sh`](../../scripts/jenkins/deploy-release.sh)

## 1. 结论（TL;DR）

1. **一台 4 核 8 GB 的生产服务器可以运行 Jenkins Controller，但不建议在这台
   机器上同时跑完整 CI 构建。** 现有生产容器按单机 overlay 已限制在约 4.2 GB，
   Jenkins 自己还要 0.5～1 GB，构建又需要 2 GB 以上；三者叠加会挤占正式业务，
   甚至触发 OOM。
2. **推荐拓扑**：Jenkins Controller 放在一台独立 Linux 虚机/办公 PC，构建也在
   该机或同网段的构建 Agent 上完成；生产服务器只保留现有的
   `deploy-production-remote.sh` 作为唯一发布执行器。Jenkins 通过 SSH 上传发布包、
   发起部署、等待验证。
3. **如果只有这一台服务器**：Jenkins Controller 可以放在生产机上，但只做
   “编排 + 上传 + 调用部署脚本”，不要在白天构建；构建放到独立的构建 Agent，
   或使用服务器上已有的 rootless BuildKit（2 GB / 1 CPU）在 02:00 后串行构建。
   这是降级方案，不是推荐方案。
4. **不要重写现有发布安全逻辑。** 维护模式、请求排空、迁移策略、健康检查、
   代理检查、旧版本回退都在 `deploy-production-remote.sh` 和
   `/opt/dazah/control/controller.py` 中。Jenkins 只负责触发、审批、记录和
   上传；迁移和 Compose 操作仍由服务器脚本执行。
5. **不要同时启用两套 CD。** 现有 `dazah-cd.timer`、GitHub `cd-candidate` 与
   Jenkins 发布只能保留一个所有者。切换前必须停用旧 CD，并确认
   `compose.release.yml` 不存在（该文件存在时手工部署脚本会拒绝发布）。
6. **发布前必须有可恢复的备份。** 手工部署脚本只备份配置文件，不备份数据库；
   流水线在部署前调用 `controller.py backup` 并校验 `manifest.json`，失败即中止。
   该备份是在线备份，数据库与对象文件不保证同一时间点；涉及结构变更时仍需
   按现有单机 CD 的 `writers_stopped` 备份流程人工确认。
7. **建议分三阶段落地**：先让 Jenkins 只做 CI/构建（不部署）→ 用一个无业务变化
   的版本完成首次发布和回退演练 → 再把 PR 门禁从 GitHub Actions 切到 Jenkins。
   不要第一天就把 `main` 的自动部署打开。

### 1.1 2026-10-22 环境确认

- **生产服务器**：4 核 8 GB，128 GB SSD + 1 TB HDD。SSD 承载系统、Docker、
  PostgreSQL 等；1 TB 数据盘承载 `/data/dazah` 的 releases/backups。落地上线前用
  `findmnt /data`、`df -h /data` 确认实际挂载和剩余空间。
- **2 核 3.6 GB、69 GB 磁盘服务器**：本次唯一的 Jenkins 主机，建议作为
  Controller + 发布编排；若同时承担构建，必须先解决 GitHub、Docker Hub 等境外
  网络不可达的问题：本地 Git 镜像/源码包、离线基础镜像、PyPI/npm/apt/Playwright
  以及 Hermes `lark-cli`/上游依赖的缓存或国内镜像。3.6 GB 低于推荐的 8 GB，
  只能单 executor、加 4 GB swap、使用 `pnpm build:single-host`、关闭 E2E、把
  BuildKit 缓存上限降到 20–30 GB，并先做一次完整构建实测。离线依赖链未建成前，
  不要让它直接 `checkout` GitHub 或执行 `docker build`。
- **构建与制品**：推荐先在可联网的构建工作站生成发布包，再通过 SCP/USB 传到
  2C 服务器或生产机；Jenkins 只做校验、审批、上传、部署和回滚。这样 2C 不需要
  访问 GitHub/Docker Hub，也不承担重构建。只有决定把构建迁到 2C 时，才需要建设
  本地 Git 镜像和完整离线依赖缓存。
- **云服务器**：本次不纳入方案。
- **审批人**：当前仅项目负责人一人。Jenkins 的 `dazah-approvers` 组先放该账号，
  后续加人只需改组，不需要改 Jenkinsfile；单人审批不构成双人复核，需在运维记录
  中明确 break-glass 流程。
- **controller.py**：允许后续单独 PR 增加 `predeploy` 备份入口；备份应包含数据库、
  Redis、持久卷、旧版本配置和镜像 ID，并在停止写入源后生成
  `consistency=writers_stopped` 的 manifest。应用回退仍不自动 downgrade 数据库。
- **服务账号**：允许创建 `dazah-jenkins`；目标是用受限 sudo 包装脚本替代
  `livzon` 的宽权限账号。
- **旧 CD**：允许停用 `dazah-cd.timer` 和 `cd-candidate`；保留
  `dazah-backup.timer`、`dazah-restore-drill.timer`、`dazah-watchdog.timer`。
- **待确认**：2 核 3.6 GB 服务器到生产 `192.168.40.251:22` 的网络；现有可联网
  构建工作站到 2C/生产的传输路径；是否建设本地 Git 镜像和离线依赖缓存；生产
  `/data` 是否确为 1 TB 盘。

## 2. 现状与约束

### 2.1 现有链路

| 环节 | 当前实现 | 备注 |
| --- | --- | --- |
| PR/主线 CI | GitHub Actions `.github/workflows/ci.yml` | `CI Gate` 是主线的必需检查 |
| 变更范围 | `.github/scripts/change_scope.py` | 按路径判定 frontend/backend/hermes/shared/docker/docs |
| 测试影响门禁 | `scripts/check-test-impact.py` | 生产代码变化必须带对应测试 |
| 自动 CD | `dazah-cd.timer` + `scripts/cd/controller.py schedule` | 当前 `enabled=false`，未启用 |
| 手工发布 | `scripts/deploy-production.ps1` → 上传 → `deploy-production-remote.sh` | Windows 构建，离线镜像包 |
| 生产编排 | 根 `compose.yml` + `deploy/compose.single-host.yml` + `deploy/compose.edge.yml` | `pull_policy: never` |
| 维护/排空 | `deploy/nginx-maintenance.conf`、`controller.py announce/drain` | 页面倒计时 + 503 维护闸门 |
| 迁移策略 | `deploy/migration-policy.json` | 明确 from/to revision、兼容性审批 |
| 备份/演练 | `controller.py backup/drill`、systemd timer | 每日 01:00 备份，月初演练 |

### 2.2 生产机约束

- 4 核 8 GB，单机，无高可用；整机或双盘损坏可能导致数据丢失（见
  [`single-host-cd.md`](single-host-cd.md)）。
- 单机 overlay 的限制：`app` 1792m、`db` 768m、`frontend` 512m、
  `hermes-lite` 512m、`minio` 384m、`redis` 192m、`nginx` 96m，合计约 4.2 GB。
- 现有 CD 控制器在构建前要求 `MemAvailable >= 3 GiB`、系统盘剩余 20 GiB、
  数据盘剩余 50 GiB；rootless BuildKit 的 slice 限制为 2 GiB / 1 CPU / 无 swap。
- 前端单机生产构建实测约 1674 秒（约 28 分钟），不能按 GitHub hosted runner
  的速度估算。
- 生产镜像必须先在别处构建/导出，再在服务器上 `docker load`；Compose 禁止
  从网络拉取应用镜像。当前没有镜像仓库。
- `/data/dazah/releases` 是 root 管理的不可变发布目录，`/opt/dazah/releases`
  链接到该目录；上传、发布、回退都会校验数据盘挂载身份。

### 2.3 为什么不能把 GitHub Actions 原样搬到单机 Jenkins

| GitHub Actions 能力 | Jenkins 对应做法 | 注意 |
| --- | --- | --- |
| `ubuntu-latest` 每次全新 runner | 固定 Agent + 容器化测试 | 需要自己清理容器、端口和缓存 |
| `services: postgres/redis` | `docker run` + 固定端口 + `lock` | 端口冲突、残留容器要处理 |
| `actions/cache` / `setup-*` | Agent 预装 + Docker BuildKit cache | 版本必须固定，不能漂移 |
| `upload-artifact` | `archiveArtifacts` / 服务器发布目录 | 2 GB 镜像包不适合长期放 Jenkins |
| `environment` + 审批 | `input` + `submitter` + 凭据 | 审批组、凭据作用域要单独设计 |
| Branch protection 的 `CI Gate` | Jenkins GitHub status 或保留 GitHub CI | 切换门禁是独立变更，不能顺手做 |
| GitHub webhook | 公网 Jenkins 或 SCM 轮询 | 内网 Jenkins 收不到 GitHub webhook |

## 3. 目标流水线

### 3.1 分支与触发

| 分支/事件 | 流水线行为 | 是否部署 |
| --- | --- | --- |
| `feature/*` / PR | 变更范围、测试影响、后端/前端/Hermes 质量门禁、按需集成测试 | 否 |
| `dev` | 同 PR，可选 nightly 全量 | 否 |
| `main` push | 同上；`DEPLOY=true` 时构建不可变发布包 | 需人工审批 |
| `main` + 定时 | 02:00 后由发布 Job 取最新通过 CI 的提交 | 需审批/窗口 |
| 手工 `PIPELINE_MODE=rollback` | 只执行回退和验证 | 需审批 |
| `workflow_dispatch` 等价 | Jenkins `build with parameters` | 按参数 |

内网 Jenkins 无法接收 GitHub webhook 时，使用 SCM 轮询：

```groovy
triggers {
  pollSCM('H/5 * * * *')
}
```

轮询有 0～5 分钟延迟，并受 GitHub API 速率限制。配置 GitHub Token 后使用认证
请求；如果 Jenkins 有公网 HTTPS 入口，再改为 webhook 并删除轮询。

### 3.2 阶段与门禁

| 阶段 | 何时执行 | 关键命令/动作 | 失败后果 |
| --- | --- | --- | --- |
| Checkout | 总是 | `checkout scm`、校验工作区干净、拉取 `origin/main` | 终止 |
| Change Scope | 总是 | `.github/scripts/change_scope.py` | 终止 |
| Repository Policy | 非回退 | `check-agent-instruction-bridges.py`、`check-test-impact.py` | 阻止合并/发布 |
| Backend Quality | 后端或 shared 变化 | `bash dazah-backend/scripts/ci.sh quality` | 终止 |
| Frontend Quality | 前端或 shared 变化 | `bash dazah-frontend/scripts/ci.sh quality` | 终止 |
| Hermes Quality | Hermes 或 shared 变化 | `bash Hermes-Lite/scripts/ci.sh` | 终止 |
| Backend Integration | 后端或 shared 变化 | 独立 PostgreSQL/Redis + `ci.sh integration` | 终止 |
| Frontend Build | 前端或 shared 变化 | `bash dazah-frontend/scripts/ci.sh build` | 终止 |
| Frontend E2E | 参数开启且前端变化 | `bash dazah-frontend/scripts/ci.sh e2e` | 终止 |
| Build Release | `main` 且 `DEPLOY=true` 或 `PIPELINE_MODE=release` | `scripts/jenkins/build-release.sh` | 不部署 |
| Deploy Production | `main` + `DEPLOY=true` + 审批 | 备份 → 上传 → `deploy-production.sh deploy` → `verify` | 维护可能保持开启，人工处理 |
| Rollback Production | `PIPELINE_MODE=rollback` | `deploy-production.sh rollback` | 人工处理 |

参考 `Jenkinsfile` 覆盖了核心阶段；以下 GitHub Actions 门禁尚未内置，需要按
业务风险逐步补齐（命令可直接复用 `.github/workflows/ci.yml`）：

- `Source Security`：Trivy `fs` 全量报告 + HIGH/CRITICAL 阻断。
- `Backend Image Verify`：后端交付镜像构建、Trivy 镜像扫描、Chromium 非 root
  渲染验证、隔离数据库迁移和 `/health` 冒烟。
- `Hermes Contract`：后端 Agent/Tool Registry 契约 + Hermes 适配契约。
- `Frontend Flaky Quarantine`：`@flaky` 用例隔离运行，不阻断主门禁。

### 3.3 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `PIPELINE_MODE` | `auto` | `auto` / `ci-only` / `release` / `rollback` |
| `RUN_FULL_CI` | `false` | 忽略变更范围，跑全部 CI |
| `RUN_E2E` | `false` | 前端构建后跑稳定 E2E |
| `DEPLOY` | `false` | 是否部署本次构建的版本 |
| `ALLOW_OUTSIDE_WINDOW` | `false` | 允许 02:00–04:30 之外部署（需额外审批） |
| `NOTICE_SECONDS` | `180` | 维护预告秒数，0–3600 |
| `RELEASE_VERSION` | 空 | 显式版本；空则 `YYYYMMDD-<7sha>` |
| `ROLLBACK_VERSION` | 空 | 回退目标版本 |
| `PUBLIC_HOST` | `192.168.40.251` | 渲染 `nginx.default.conf` 的主机名/IP |
| `DEPLOY_MODE` | `ssh` | `ssh` 或 `local`（Jenkins 就在生产机时） |
| `DEPLOY_HOST` | `192.168.40.251` | 生产 SSH 地址 |
| `DEPLOY_USER` | `livzon` | 允许执行部署脚本的 SSH 用户 |
| `PREDEPLOY_BACKUP` | `true` | 部署前调用 `controller.py backup` |
| `CLEAN_WORKSPACE` | `true` | 结束后删除工作区 |
| `FEISHU_NOTIFY` | `false` | 发送构建结果到飞书 |

### 3.4 版本与发布包

版本格式与服务器脚本一致：

```text
YYYYMMDD-<git short sha 7>
例如：20261021-03d6d39
```

允许 `[A-Za-z0-9][A-Za-z0-9._-]{0,80}`；重跑时使用 `-r2` 等后缀。**版本目录
不可变**：远端已存在同版本目录时，上传脚本拒绝覆盖。

发布包目录必须包含：

| 文件 | 用途 |
| --- | --- |
| `dazah-<version>.tar` | 三个应用镜像的离线包 |
| `dazah-<version>.tar.sha256` | 服务器 `sha256sum -c` 校验 |
| `compose.yml` | 生产 Compose |
| `compose.edge.yml` | Nginx / 维护入口 |
| `nginx.default.conf` | 由模板渲染 `__PUBLIC_HOST__` |
| `nginx-maintenance.conf` | 维护页与状态探针 |
| `nginx-capacity.conf` | API 限流 / MCP 连接限制 |
| `migration-policy.json` | 迁移兼容性审批 |
| `deploy-production.sh` | 服务器部署脚本 |
| `manifest.json` | 版本、提交、镜像 ID、逐文件 SHA-256 |

`build-release.sh` 会校验 `nginx.default.conf` 包含维护 include 和
`listen 127.0.0.1:8090`、`compose.edge.yml` 包含 `/run/dazah:ro`，否则拒绝生成
发布包。

### 3.5 部署窗口与审批

- 标准窗口：**Asia/Shanghai 02:00–04:30**，与现有单机 CD 的切换窗口一致。
- 默认预告 180 秒；预告期间用户可以保存，但不能把终端输出当作通知。
- 审批组建议为 `dazah-approvers`，只包含生产负责人；`input` 步骤必须显示
  版本、目标主机和“数据库迁移不会自动回退”的提示。
- 窗口外部署必须同时满足：`ALLOW_OUTSIDE_WINDOW=true`、审批人明确同意、
  有回退方案。流水线只做技术拦截，不替代变更审批。

### 3.6 并发与锁

三层串行：

1. Jenkins Job：`disableConcurrentBuilds()`，避免同一 Job 并发。
2. Jenkins 资源锁：`lock(resource: 'dazah-production-deploy')`，跨 Job 串行。
3. 服务器：`flock /var/lock/dazah-deploy.lock`，由 `deploy-production-remote.sh`
   持有；已有另一个部署操作时直接失败。

不要为了“快一点”去掉任何一层。尤其是回退和手工发布同时进行时，第三层是最后
防线。

### 3.7 失败处理

- 构建失败：不进入部署，不产生远端版本目录。
- 上传失败：保留 `/tmp/dazah-release-<version>` 供诊断；远端版本目录不创建。
- 部署失败：**不自动重试、不自动回滚、不自动关闭维护模式**。先执行
  `status` / `verify`，确认当前 revision、容器状态和流量是否开放，再决定：
  - 应用/配置问题且迁移兼容：回退到上一版本；
  - 迁移失败或状态不明：保持维护，按 [`single-host-cd.md`](single-host-cd.md)
    的故障处理执行，不盲目启动旧应用；
  - 流量已开放后：不得自动恢复旧数据库。
- 验证失败（`verify` 非 0）：按部署失败处理。不要用“再跑一次 deploy”掩盖现场。

## 4. 拓扑选择

### 4.1 方案 A（推荐）：Jenkins 独立于生产

```text
GitHub (源码/PR)
   │  poll 或 webhook
   ▼
Jenkins Controller（办公网 Linux VM）
   │
   ├── Build Agent（Docker + Buildx，linux/amd64）
   │      构建三镜像 → 发布包 → SHA-256
   │
   └── SSH（仅发布 Job）
          │ scp 发布包 + sudo deploy-production.sh
          ▼
   生产 192.168.40.251
   .env / Compose / Nginx / PostgreSQL / Redis / MinIO
```

> 受 1.1 网络限制：本方案的 Controller 是 2C 服务器，构建 Agent 优先是
> “可联网的构建工作站”。2C 服务器只有完成本地 Git 镜像、离线基础镜像和依赖
> 缓存建设后，才适合自己执行 `docker build`；否则它只做发布编排。

优点：

- 构建不占生产 CPU/内存，不影响 4 核 8 GB 的正式业务。
- 构建 Agent 不需要生产 Docker socket，也不需要 `/opt/dazah` 写权限。
- Jenkins 故障不影响生产；生产仍可用现有脚本人工发布。
- 与现有“离线镜像包 + 服务器部署”模型一致，不需要镜像仓库。

代价：

- 需要第二台 Linux 机器（4 核 8 GB、100 GB 磁盘较合适）。
- Jenkins 到生产、Jenkins 到 GitHub/镜像源需要网络策略。
- 发布包约 2 GB，上传时间取决于内网带宽。

### 4.2 方案 B：Controller 在生产机，构建在外部 Agent

```text
生产机 192.168.40.251
  ├── 业务容器（PostgreSQL/Redis/MinIO/App/Hermes/Frontend/Nginx）
  └── Jenkins Controller（独立 slice，768 MB / 0.5 CPU，127.0.0.1:8080）
          │
          └── SSH/Agent → 外部 Build Agent（构建、测试）
```

适用：只有一台生产服务器，但办公网还有一台可长期开机的 Linux 机器。

约束：

- Controller 只做调度，不构建；`dazah-jenkins.slice` 限制内存/CPU。
- 端口只监听 `127.0.0.1`，通过 SSH 隧道访问；不要直接暴露到公网。
- Controller 与生产 Docker 隔离：`jenkins` 用户不加入 `docker` 组。
- 生产机重启后 Jenkins 自启动，但要确认不会与 `dazah-control.slice` 抢资源。

### 4.3 方案 C：全部放在生产机（不推荐，仅兜底）

如果确实没有第二台机器，只能：

- Controller 限制 512–768 MB、0.5 CPU，放独立 slice；
- 构建使用现有 rootless BuildKit（2 GB / 1 CPU / 无 swap），串行、夜间执行；
- 构建前检查 `MemAvailable >= 3 GiB`，低于阈值直接延期；
- 只保留一个构建 executor，禁止并行跑前端构建和后端全量测试；
- 前端构建预留 30–60 分钟；不要在 08:00–18:00 构建；
- 接受“构建期间正式业务变慢/可能触发维护巡检”的风险。

现有 CD 控制器在构建前要求 `MemAvailable >= 3 GiB`；如果 Controller 常驻，
这个条件更容易失败。方案 C 需要同时调整控制器和 Jenkins 的资源预算，**不建议
作为长期方案**。

### 4.4 决策表

| 条件 | 选择 |
| --- | --- |
| 有第二台 Linux 机器，网络可达生产 | 方案 A |
| 只有生产机，但有办公 Linux 机器可做 Agent | 方案 B |
| 只有生产机，且必须全自动 | 方案 C + 夜间窗口 + 严格资源上限 |
| 短期只想减少手工发布 | 先做方案 A 的“只构建 + 手工确认部署” |

### 4.5 网络与 webhook

- **内网 Jenkins 收不到 GitHub webhook**：使用 `pollSCM`，或让 GitHub
  Enterprise Server/内部 Git 镜像触发。公网入口必须加 TLS、认证和来源限制。
- Jenkins/Agent 出站需要：GitHub 443、Docker 镜像源、PyPI/npm 镜像、可选代理。
- 生产机入站只开放 Jenkins Agent 的 SSH 来源；Jenkins UI 不对公网开放。
- 如果服务器只能通过代理访问 GitHub，配置 Agent 的 `HTTP_PROXY`/`HTTPS_PROXY`
  和 Docker daemon 代理；不要把代理凭据写入镜像或仓库。

### 4.6 资源预算

| 组件 | 建议 | 说明 |
| --- | --- | --- |
| Jenkins Controller | 2 vCPU / 2 GB | 方案 B/C 可压到 0.5 CPU / 768 MB |
| Build Agent | 4 vCPU / 8 GB / 100 GB | 前端 `next build` + 后端 pytest + Docker |
| Docker BuildKit cache | 20–60 GB | `docker/buildkitd.toml` 已配置 GC 阈值 |
| 发布包 | 约 2 GB/版本 | 保留最近 10 个版本约 20 GB |
| Jenkins home | 5–10 GB | 构建记录、插件、凭据；不要存 2 GB 镜像包 |

## 5. Jenkins 安装与配置

### 5.1 Controller（Ubuntu 22.04）

以下命令用于一台新的 Linux Controller；生产机安装时先确认资源预算和端口。

```bash
# Java 21 + Jenkins LTS（示例；以 Jenkins 官方当前 LTS 仓库为准）
sudo apt-get update
sudo apt-get install -y fontconfig openjdk-21-jre-headless
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key \
  | sudo tee /etc/apt/keyrings/jenkins-keyring.asc >/dev/null
echo "deb [signed-by=/etc/apt/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/" \
  | sudo tee /etc/apt/sources.list.d/jenkins.list >/dev/null
sudo apt-get update
sudo apt-get install -y jenkins
```

资源限制（方案 B/C）：

```ini
# /etc/systemd/system/dazah-jenkins.slice
[Slice]
MemoryMax=768M
MemorySwapMax=0
CPUQuota=50%
TasksMax=512
```

```bash
sudo systemctl edit jenkins
```

```ini
[Service]
Slice=dazah-jenkins.slice
Environment="JAVA_OPTS=-Xms128m -Xmx512m"
```

监听地址与端口（具体文件随发行包版本略有差异，确保 Jenkins 只监听回环）：

```bash
# /etc/default/jenkins（Debian/Ubuntu 包示例）
HTTP_PORT=8080
JENKINS_ARGS="$JENKINS_ARGS --httpListenAddress=127.0.0.1"
```

通过 SSH 隧道访问：

```bash
ssh -N -L 127.0.0.1:8080:127.0.0.1:8080 livzon@192.168.40.251
# 浏览器打开 http://127.0.0.1:8080
```

首次启动后：

1. 用初始管理员密码解锁，创建管理员账号。
2. 关闭匿名注册/匿名读权限，启用矩阵授权或 Role Strategy。
3. 安装插件（见 5.4），重启。
4. 配置 JDK、Git、Node、pnpm、uv 等工具路径；建议直接使用 Agent 预装工具，
   在流水线 Preflight 校验版本，避免 Jenkins 全局工具漂移。
5. 配置系统时区为 `Asia/Shanghai`；Jenkins 内部仍以 UTC 记录，流水线用
   `TZ=Asia/Shanghai date` 判定窗口。

### 5.2 JCasC 最小示例

如果使用 Configuration as Code，可把以下内容保存为
`/var/lib/jenkins/jenkins.yaml`，再在 Jenkins 中启用 JCasC。凭据由 Jenkins
加密存储，**不要把真实私钥/Token 写进仓库**。

```yaml
jenkins:
  systemMessage: "Dazah CI/CD - internal use only"
  numExecutors: 1
  mode: NORMAL
  securityRealm:
    local:
      allowsSignup: false
      users:
        - id: "admin"
          password: "${JENKINS_ADMIN_PASSWORD}"
  authorizationStrategy:
    loggedInUsersCanDoAnything:
      allowAnonymousRead: false
unclassified:
  location:
    url: "http://127.0.0.1:8080/"
  timestamper:
    allPipelines: true
```

生产环境应使用 `role-strategy` 或 `matrix-auth` 按用户/组授权，而不是
`loggedInUsersCanDoAnything`。上例只用于最小启动。

### 5.3 Build Agent

建议一台独立 Linux（Ubuntu 22.04）并固定工具版本：

| 工具 | 版本/要求 | 用途 |
| --- | --- | --- |
| Docker Engine | 24+，含 buildx | 构建镜像、跑测试依赖 |
| Git | 2.30+ | 全历史 checkout、变更范围 |
| Python | 3.12 | 后端/脚本 |
| uv | 与 `dazah-backend/pyproject.toml`/CI 一致 | 后端依赖 |
| Node.js | 24.22.1（含 CVE-2026-111497 的 Brotli 修复） | 前端 |
| pnpm | 10.33.0（`packageManager` 锁定） | 前端 |
| PostgreSQL client | 提供 `pg_isready` | 等待测试库 |
| Playwright Chromium | 预装 + 系统依赖 | E2E（可选） |
| `jq`/`curl`/`openssh-client` | 最新稳定 | 脚本与通知 |

Agent 配置要点：

- 标签：`dazah-linux`（CI）与 `dazah-release`（发布）分开；PR Job 只能落在
  没有生产凭据的 `dazah-linux`。
- SCM 必须 **full history / 禁用 shallow clone**，否则 `origin/main`、
  `merge-base`、变更范围和测试影响检查都会失真。如果仓库是私有的，
  `git fetch origin main` 也需要只读凭据：把 SCM URL 配成 SSH 并使用只读
  Deploy Key，或在 Agent 上配置 credential helper；不要把明文 Token 拼进
  remote URL。
- 参考 `Jenkinsfile` 为了可读性只使用一个 `dazah-linux` 标签；正式落地时把
  Release Job 的 `agent` 改为 `dazah-release`，或复制一份固定标签的
  Jenkinsfile。不要让带发布凭据的 Job 接受 PR 分支。
- 参考流水线并行执行三个质量门禁；8 GB Agent 如果出现 OOM，把
  `Quality Gates` 的 `parallel` 改为串行，不要用提高 Node 堆上限来掩盖内存
  不足。
- 工作区放在容量足够的磁盘；`docker buildx` 的 builder 状态不要随意 prune。
- 不要把生产 `.env`、数据库密码、LLM Key 放到 Agent；发布 Job 只用
  `dazah-deploy-ssh` 凭据，且只在 Deploy 阶段注入。
- E2E 需要 Chromium 系统依赖时，在 Agent 镜像构建阶段安装，不要让流水线
  每次 `sudo apt-get`。

### 5.4 插件

至少安装：

- `configuration-as-code`
- `workflow-aggregator`（Pipeline）
- `git`、`github`、`github-branch-source`
- `credentials-binding`、`ssh-agent`
- `pipeline-stage-view`、`build-timeout`、`timestamper`
- `junit`、`coverage` / `code-coverage-api`
- `lockable-resources`
- `ws-cleanup`（可选；参考 Jenkinsfile 用 `deleteDir()`，不强制）
- `role-strategy` 或 `matrix-auth`
- `disk-usage`（监控）
- `feishu` 通知插件或直接用 webhook `curl`（参考实现用后者）

插件版本固定并记录；升级前备份 `/var/lib/jenkins` 并在测试实例验证。

### 5.5 凭据

| Credential ID | 类型 | 用途 | 作用域 |
| --- | --- | --- | --- |
| `dazah-github-token` | Username/Password 或 Secret text | 私有仓库 checkout、GitHub API/状态 | 仅 CI Job |
| `dazah-deploy-ssh` | SSH Username with private key | 发布 Job 连接生产 | 仅 Release Job |
| `dazah-feishu-webhook` | Secret text | 构建结果通知 | 仅通知步骤 |
| `dazah-build-proxy` | Secret text | 可选构建代理 | 仅 Build Agent |

原则：

- PR Job 不绑定 `dazah-deploy-ssh`；发布 Job 从 `main` 加载 `Jenkinsfile`，
  不从 PR 加载。
- 私钥使用专用账号、`from=` 限制来源、禁用端口转发/agent forwarding；
  首次连接核对主机指纹，或预置 `known_hosts`。
- 凭据只在需要的 `withCredentials`/`sshagent` 块内可见；不要 `echo`、写文件
  或放进 Docker build args。
- 定期轮换；轮换后删除旧凭据并重跑一次发布验证。

### 5.6 Job 设计

推荐两个 Job，而不是一个多分支 Job 包打天下：

1. **`dazah-pr`（不可信）**
   - Multibranch Pipeline，发现 `feature/*`、`dev`、PR。
   - Agent 标签 `dazah-linux`，**没有** `dazah-deploy-ssh`。
   - 只跑 CI，不进入 Deploy 阶段。
   - 如果需要把结果回写 GitHub，使用受限的 `dazah-github-token`（仅
     `repo:status`），不要给发布权限。

2. **`dazah-release`（可信）**
   - Pipeline from SCM，分支固定 `main`，`Jenkinsfile` 从 `main` 读取。
   - Agent 标签 `dazah-release`（可以同时有 Docker 和 SSH，或拆成两个 Agent）。
   - 凭据 `dazah-deploy-ssh` 只在这个 Job 的 Deploy 阶段使用。
   - 触发：手动 `Build with Parameters`（`DEPLOY=true`），或夜间定时任务
     选择最新通过 CI 的 `main` 提交。

为什么分开：PR 可以修改 `Jenkinsfile`。如果 PR Job 能访问生产 SSH 私钥，
恶意 PR 就能在 Agent 上读取并外传。仅靠 `when { branch 'main' }` 不能阻止
PR 在 Jenkinsfile 里新增一个带 `withCredentials` 的 stage。

### 5.7 Jenkins 备份与升级

- 备份 `/var/lib/jenkins` 中的 `config.xml`、`jobs/`、`users/`、`nodes/`、
  `credentials.xml`、`secret.key`、`secrets/`、`plugins/`（或记录插件清单）。
- `credentials.xml` 与 `secret.key` 必须一起备份，否则凭据无法解密。
- 备份文件加密后放在受限位置；不要上传到普通 CI artifact 或代码仓库。
- 每季度做一次恢复演练：在隔离实例恢复 Jenkins，确认 Job、凭据和 SSH 连接
  可用，再删除演练实例。
- 升级 LTS 前：备份 → 测试实例验证插件兼容 → 生产升级 → 重跑一条只构建不部署
  的流水线。

## 6. 权限与安全

### 6.1 信任边界

| 对象 | 不可信内容 | 必须隔离 |
| --- | --- | --- |
| PR 分支 | `Jenkinsfile`、测试、构建脚本 | 无生产 SSH、无生产 `.env`、无生产 Docker socket |
| `main` | 已合并代码 | 发布 Job 可信，但仍需审批 |
| Build Agent | 第三方依赖、构建产物 | 不持有生产数据库/密钥；Docker 组视为 root |
| Deploy 步骤 | 上传包、远程脚本 | 只允许执行 `/opt/dazah/current/deploy-production.sh` |

### 6.2 SSH 与 sudo

最小权限目标：专用账号 `dazah-jenkins`，只允许：

```sudoers
# /etc/sudoers.d/dazah-jenkins
dazah-jenkins ALL=(root) NOPASSWD: /opt/dazah/current/deploy-production.sh
```

但上传发布包需要写 `/tmp` 和 `/data/dazah/releases`。有两种做法：

- **过渡期（简单）**：沿用现有 `livzon` 账号和现有 sudo 权限，SSH key 只放
  在 Jenkins 发布 Job；这是当前手工流程的等价自动化，风险可接受但不理想。
- **加固后（推荐）**：增加一个 root-owned 的发布包装脚本（只接受固定参数、
  校验版本和路径），`dazah-jenkins` 只能 sudo 执行该脚本；上传目录由
  `dazah-jenkins` 拥有，root 只负责移动到不可变目录。

无论哪种，`deploy-production-remote.sh` 本身会校验版本、发布包、维护入口、
迁移策略和恢复路径；不要给 Jenkins 直接 `docker`/`alembic`/`compose` 的
sudo 权限。

### 6.3 供应链与构建

- Dockerfile 的基础镜像已固定 digest；不要为了“拉得快”改成浮动 tag。
- 构建使用 lockfile：`uv sync --frozen`、`pnpm install --frozen-lockfile`。
- 构建缓存只来自可信 builder；不要执行来源不明的 `docker load`。
- 发布包生成 SHA-256，服务器 `sha256sum -c` 后才 `docker load`。
- 不要在生产机执行 `docker system prune`、`docker builder prune` 或删除
  `/data/dazah/releases`；保留至少当前版本和上一个稳定版本。
- 构建代理/镜像源只影响下载，不改变镜像内容；代理凭据不进入镜像层。

### 6.4 日志与敏感信息

- Jenkins 日志会保存命令输出；不要把 `.env`、Token、数据库密码、LLM Key
  传到 stdout。
- `deploy-production-remote.sh` 已避免打印密钥；Jenkins 侧不要额外
  `cat .env` 或 `docker inspect` 完整 Env。
- Feishu webhook、SSH 私钥、GitHub Token 用 Jenkins 凭据；日志中只出现
  凭据 ID，不出现值。
- 构建失败时上传的日志先脱敏，再贴到工单/群聊。

### 6.5 分支保护切换

Phase 0/1 保留 GitHub Actions 的 `CI Gate` 作为合并门禁；Jenkins 只做发布。
只有满足以下条件后，才把必需检查切到 Jenkins：

1. Jenkins 对同一组 PR 的通过/失败结果与 GitHub Actions 一致（至少 2 周）。
2. Jenkins 能把状态回写 GitHub，且 PR 上能看到对应 check。
3. 用一个故意失败的 PR 验证分支保护会阻止合并。
4. 用一个落后于 `main` 的 PR 验证“Require branches to be up to date”生效。
5. 回退方案明确：临时恢复 GitHub Actions 作为必需检查。

在此之前，不要让两套 CI 同时成为“必需检查”，否则维护者会被重复门禁拖住。

## 7. 与生产部署的集成

### 7.1 为什么复用 `deploy-production.sh`

`scripts/deploy-production-remote.sh` 已经实现了单机生产的关键安全步骤：

1. 校验版本、发布目录、维护入口和迁移策略文件。
2. 备份当前 `.env`、Compose、Nginx 配置。
3. `announce` 预告 + 开启维护闸门。
4. `drain` 排空请求和已登记业务任务；未排空则中止并保持维护。
5. 停止应用写入源，按 `migration-policy.json` 执行明确 revision 的迁移。
6. 启动后端、Hermes、前端，重建 Nginx。
7. 检查容器健康、依赖 readiness、`/health`、`/login`、代理路由和迁移版本。
8. 全部通过才关闭维护；失败保持维护并恢复配置/旧容器（不会自动回滚数据库）。

Jenkins 重新实现这些步骤只会增加分叉风险。参考流水线通过
`scripts/jenkins/deploy-release.sh` 调用它，不直接执行 `alembic` 或
`docker compose`。

> 维护入口前提：当前运行的 Nginx 必须已经包含维护状态探针和观察脚本；
> 否则 `announce` 会在预告阶段失败并拒绝发布。首次从旧版本切换到该机制时，
> 按 [`single-host-cd.md`](single-host-cd.md) 的受控过渡步骤执行，不能把
> “新发布包里带了维护配置”当作当前入口已生效。

### 7.2 发布前备份的缺口

手工脚本的 `backup_current_files` 只备份配置文件，**不备份数据库/对象文件**。
自动 CD 的 `Controller.deploy()` 会在停止写入源后执行 `backup("predeploy")`，
但手工脚本没有这一步。

参考实现的做法：

```bash
# deploy-release.sh 在 deploy 前执行
sudo python3 /opt/dazah/control/controller.py backup
# 然后确认最新 daily-*/manifest.json 存在
```

这提供了可恢复的在线备份，但：

- 数据库、Redis、对象文件不是同一时间点；
- 不是 `writers_stopped` 一致性备份；
- 不能替代结构变更前的人工确认。

**建议的后续改造**（需要单独 PR、测试和评审）：给
`deploy-production-remote.sh` 增加“停止写入源后调用
`controller.py backup --kind predeploy`”的步骤，或给 `controller.py` 增加
受控的 `deploy-release` 入口，让 Jenkins 复用与自动 CD 相同的预部署备份和
`compose.release.yml` 固定镜像流程。完成前，涉及破坏性/不兼容迁移的发布
应按 [`single-host-cd.md`](single-host-cd.md) 的人工维护流程执行。

### 7.3 构建

```bash
bash scripts/jenkins/build-release.sh \
  --version 20261021-03d6d39 \
  --public-host 192.168.40.251 \
  --release-root "$WORKSPACE/release"
```

脚本行为：

1. 校验版本、主机名、工具和工作区干净。
2. 检查至少 12 GiB 可用空间。
3. 创建/复用 `dazah-builder`，缓存策略取自 `docker/buildkitd.toml`。
4. `docker buildx bake` 构建 `backend`、`frontend`、`hermes` 三个
   `linux/amd64` 镜像，tag 为 `dazah/<service>:<version>`。
5. `docker save` 三个镜像为单个 tar，生成 `.sha256`。
6. 复制 Compose/Nginx/迁移策略/服务器脚本，渲染 `nginx.default.conf`。
7. 校验维护入口、内部探针端口和 `compose.edge.yml` 挂载。
8. 写入 `manifest.json`（提交、分支、镜像 ID、逐文件 SHA-256）。
9. 失败时保留 `.<version>.partial` 供诊断；成功后原子重命名为正式目录。

注意：

- 不要清理 `dazah-builder` 的缓存；依赖层缓存是构建时间的主要来源。
- 构建机必须是 `linux/amd64` 或能可靠模拟；ARM 上构建生产镜像会非常慢。
- 前端构建受内存影响大；流水线设置 `NODE_OPTIONS=--max-old-space-size=4096`，
  但 Agent 至少 8 GB 内存。
- 发布包约 2 GB；Jenkins `archiveArtifacts` 只归档 `manifest.json` 和
  `.sha256`，不要把 tar 放进 Jenkins 长期 artifact。

### 7.4 上传与部署

`scripts/jenkins/deploy-release.sh deploy` 的步骤：

1. 校验版本、发布目录和 10 个必需文件。
2. 调用 `controller.py backup`，确认最新 `daily-*/manifest.json`；失败即中止，
   此时还没有消耗远端版本目录。
3. 校验数据盘挂载（当 `REMOTE_RELEASES` 指向 `/data/dazah/releases` 时）。
4. 通过 `scp` 上传到 `/tmp/dazah-release-<version>`。
5. 以 root 移动到 `/data/dazah/releases/<version>`；已存在则拒绝。
6. 安装 `deploy-production.sh` 到 `/opt/dazah/current/`。
7. 调用 `deploy-production.sh deploy <version> <release-dir> <notice>`。
8. 调用 `deploy-production.sh verify`；流水线再观察 5 分钟并再次 verify。

手工等价命令：

```bash
sudo /opt/dazah/current/deploy-production.sh deploy \
  20261021-03d6d39 /data/dazah/releases/20261021-03d6d39 180
sudo /opt/dazah/current/deploy-production.sh verify
```

### 7.5 迁移策略

`deploy/migration-policy.json` 的 transition 必须由代码评审确认：

```json
{
  "transitions": [
    {
      "from_revision": "a7c100000021",
      "to_revision": "d7e8f9a1b2c3",
      "backward_compatible": true,
      "review_reference": "docs/runbooks/..."
    }
  ]
}
```

- `from_revision`/`to_revision` 必须精确匹配当前库和代码 head。
- `backward_compatible: true` 表示旧应用仍可读取新 schema；不能为了发布通过
  而填写未经验证的结论。
- `deployment_hold` 只适用于其精确的 `source_head` 和允许的 revision；
  当前仓库中的 hold 是过渡配置，验收完成后需要单独清理。
- 没有审批的迁移会让部署失败并保持维护模式；这是预期行为，不要绕过。

### 7.6 回退

```bash
# Jenkins: PIPELINE_MODE=rollback, ROLLBACK_VERSION=<version>
bash scripts/jenkins/deploy-release.sh rollback
```

- 只切换应用镜像和 Compose 配置；**不会自动 downgrade 数据库**。
- 版本必须仍在服务器 `/data/dazah/releases`；否则先恢复发布包。
- 回退同样走维护、排空、健康/代理验证。
- 迁移不兼容或状态不明时，不要反复回退应用；按故障处理流程恢复数据库。

### 7.7 与现有 CD 共存

Jenkins 接管发布前：

```bash
# 只读检查，不要直接删除任何东西
sudo systemctl status dazah-cd.timer
sudo test -f /opt/dazah/current/compose.release.yml && echo "CD-controlled"
sudo ls -1 /data/dazah/releases | tail
sudo python3 /opt/dazah/control/controller.py status
```

切换步骤（需明确授权）：

1. `sudo systemctl disable --now dazah-cd.timer`，确认不会再生成新候选。
2. 停止/移除 GitHub `cd-candidate` Job（或在分支保护/工作流中禁用）。
3. 确认 `/opt/dazah/current/compose.release.yml` 不存在；如果存在，说明当前
   站点仍由 CD 控制器写固定镜像，手工脚本会拒绝发布。不要直接删除，先确认
   上一次自动发布的状态并取得授权。
4. 保留 `dazah-backup.timer`、`dazah-restore-drill.timer`、`dazah-watchdog.timer`；
   它们不是发布调度器，但仍会开维护/恢复，需与 Jenkins 发布锁协调。
5. 只保留一个发布所有者：Jenkins。不要让 Jenkins 和 `controller.py schedule`
   同时操作生产。

## 8. 首次落地步骤

### Phase 0：准备与只构建

1. 记录现状：当前 `DAZAH_VERSION`、数据库 revision、CD timer 状态、
   `compose.release.yml` 是否存在、最近备份。
2. 准备 Build Agent（方案 A/B），安装固定版本工具；跑通：
   ```bash
   bash dazah-backend/scripts/ci.sh quality
   bash dazah-frontend/scripts/ci.sh quality
   bash Hermes-Lite/scripts/ci.sh
   ```
3. 安装 Jenkins Controller，配置插件、凭据、Agent 标签。
4. 创建 `dazah-pr`（无发布凭据）和 `dazah-release`（main，含发布凭据）。
5. 只跑 `PIPELINE_MODE=release`、`DEPLOY=false`：构建发布包但不部署；
   核对 `manifest.json`、镜像 ID、tar 校验和与现有 PowerShell 发布包是否一致。
6. 在隔离环境验证 `deploy-release.sh` 的 SSH、上传、`sudo -n` 和路径；
   不要对生产执行 `deploy`。

### Phase 1：首次受控发布与回退演练

1. 选择一个无 schema 变化、低风险的 `main` 提交。
2. 在维护窗口（02:00–04:30）执行 `PIPELINE_MODE=release` + `DEPLOY=true`，
   审批人确认预告和回退方案。
3. 观察维护页、倒计时、503、排空、迁移 revision、健康/代理验证。
4. 开放流量后观察至少 5 分钟；确认登录、关键页面、文件读取。
5. 用上一版本做一次回退演练（同样在窗口内），确认：
   - 回退不执行数据库 downgrade；
   - 维护、排空、验证链路正常；
   - 回退后业务可用。
6. 记录实际耗时、失败点和人工操作，更新本手册。

### Phase 2：启用 main 发布

1. 将 `dazah-release` 的 `DEPLOY` 默认值保持 `false`，由发布负责人在窗口内
   手动勾选；不要默认自动部署。
2. 配置飞书/邮件通知：构建失败、部署失败、验证失败、维护未关闭。
3. 每日检查：Jenkins 队列、磁盘、构建时长、发布记录、服务器 `last-success`。
4. 运行 2–4 周，确认无“构建成功但部署失败”或“维护未关闭”事故。

### Phase 3：CI 门禁迁移（可选）

1. 让 Jenkins 对 PR 回写 GitHub status；用 2 周对比 GitHub Actions 结果。
2. 在分支保护中把必需检查切到 Jenkins；保留 GitHub Actions 至少一个迭代
   作为回退。
3. 用故意失败的 PR、落后分支的 PR 验证拦截。
4. 确认后再停用重复的 GitHub Actions Job；不要删除历史工作流文件，先保留
   可回退路径。

## 9. 验收清单

### CI

- [ ] PR 只跑 `dazah-pr`，Agent 上没有 `dazah-deploy-ssh`。
- [ ] `change_scope.py` 对前端/后端/Hermes/shared/docs 的判定与 GitHub 一致。
- [ ] `check-test-impact.py` 能阻止“生产代码无对应测试”的 PR。
- [ ] 后端 Quality + Integration 在独立 PostgreSQL/Redis 上通过；无残留容器。
- [ ] 前端 Quality + Build 通过；`pnpm build` 产物可供 E2E 使用。
- [ ] Hermes Quality 通过；JUnit/覆盖率报告可在 Jenkins 查看。
- [ ] 失败日志不包含 `.env`、Token、数据库密码或 LLM Key。

### 构建

- [ ] 版本格式合法，重复版本被拒绝。
- [ ] 工作区有未提交的跟踪文件时构建失败。
- [ ] 三个镜像 tag 正确，`manifest.json` 中镜像 ID 可 `docker image inspect`。
- [ ] tar 的 SHA-256 与 `.sha256` 一致。
- [ ] `nginx.default.conf` 包含维护 include 和 `127.0.0.1:8090`。
- [ ] `compose.edge.yml` 包含 `/run/dazah:ro`。
- [ ] 构建失败不产生正式发布目录；`.partial` 保留可诊断。

### 部署

- [ ] 非 `main`、无审批、窗口外（未显式 override）均被拒绝。
- [ ] 上传后远端版本目录不可变；重复版本被拒绝。
- [ ] 发布前备份存在 `manifest.json`；备份失败时部署中止。
- [ ] 维护页/503/倒计时实际可见（不是只在终端打印）。
- [ ] 排空失败时保持维护，不继续迁移。
- [ ] 迁移策略缺失/不兼容时部署失败并保持维护。
- [ ] 容器健康、`/health`、`/login`、代理路由、迁移 revision 全部通过。
- [ ] 部署后 5 分钟观察通过；`last-success` 记录版本。
- [ ] 回退只切换应用，不 downgrade 数据库；回退后验证通过。
- [ ] 部署失败不自动重试/回滚/关维护。

### 安全与运维

- [ ] Jenkins UI 不对公网开放；SSH 隧道或来源白名单可用。
- [ ] 凭据最小作用域；PR Job 无法读取发布私钥。
- [ ] Jenkins 备份可恢复（凭据 + `secret.key` 一起）。
- [ ] 磁盘/构建缓存有监控；未执行 `builder prune`。
- [ ] 旧 CD timer 已停用；只有一个发布所有者。
- [ ] 回退演练和备份恢复演练有记录。

## 10. 日常运维

### 每日

```bash
# Jenkins
sudo systemctl status jenkins
df -h /var/lib/jenkins
# 生产
sudo /opt/dazah/current/deploy-production.sh status
sudo python3 /opt/dazah/control/controller.py status
```

### 每周

- 检查 Jenkins 构建趋势、失败率、平均构建/部署时长。
- 检查 `/data/dazah/releases` 和 Docker 镜像占用；按保留策略清理，
  至少保留当前版本和上一个稳定版本。
- 检查备份 timer、恢复演练 timer、watchdog 状态。
- 检查 TLS 证书和 Nginx 维护页是否仍正常。

### 每月

- 一次 Jenkins 配置/凭据备份恢复演练。
- 一次生产回退演练（可复用上一版本，窗口内执行）。
- 一次备份恢复演练（现有 `controller.py drill`，不要对正式库执行）。
- 评审 Jenkins/插件安全更新；先在测试实例验证。

## 11. 风险与未决项

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 单机生产无高可用 | 整机故障即停机/可能丢数据 | 现有备份/演练；不要宣称 Jenkins 提供 HA |
| Jenkins 与生产抢资源 | 业务变慢、OOM、构建失败 | 2C 只做编排；构建放工作站；资源 slice；夜间窗口；单 executor |
| 2C 构建机内存/磁盘不足 | 构建 OOM、缓存占满 | 4 GB swap、`build:single-host`、单 executor、缓存 20–30 GB；先实测 |
| 2C 无法访问 GitHub/Docker Hub | 无法 checkout 或构建 | 本地 Git 镜像 + 离线基础镜像/依赖；否则构建放可联网工作站 |
| 内网收不到 webhook | 发布延迟 | 手工触发/本地 Git 轮询；不要依赖 GitHub webhook |
| PR 读取发布凭据 | 生产被未授权发布 | 分离 PR/Release Job 与 Agent；可信 main Jenkinsfile |
| Docker 组等于 root | Agent 被攻破即 root | 专用 Agent；不在 Agent 放生产密钥；最小镜像 |
| 手工脚本缺少预部署 DB 备份 | 迁移失败恢复点不足 | 流水线调用 `controller.py backup`；后续改造 predeploy |
| 迁移策略被“为了发布”放行 | 旧应用不兼容新 schema | 代码评审；`backward_compatible` 必须可验证 |
| 维护未关闭 | 用户无法访问 | 失败告警；`status/verify`；人工 `maintenance-off` |
| 发布包 2 GB 上传失败 | 发布延迟/半成品 | 稳定内网；校验和；失败保留现场；可改 rsync |
| Jenkins 插件/凭据泄露 | 供应链/生产风险 | 固定版本、最小权限、备份加密、定期轮换 |

未决问题（需要项目/运维确认）：

1. 2C 服务器最终只做 Controller，还是也要承担构建？若承担构建，本地 Git 镜像
   和离线依赖链何时就绪？
2. 现有可联网构建工作站的规格、开机时间和到 2C/生产的传输方式（SCP/USB）。
3. `dazah-approvers` 暂定项目负责人一人，后续备份审批人何时加入？
4. `controller.py` 的 `predeploy` 备份和 `dazah-jenkins` 包装脚本由谁实现、
   评审和安装？
5. 是否引入内网镜像仓库（可简化 2 GB tar 传输和回退）？
6. 分支保护切换到 Jenkins 的时间点和回退方案？

## 12. 附录

### A. GitHub Actions → Jenkins 对照

| GitHub Actions Job | Jenkins 阶段 | 说明 |
| --- | --- | --- |
| `change-scope` | Change Scope | 复用 `.github/scripts/change_scope.py` |
| `source-security` | 未内置 | 用 Trivy 容器/二进制补 |
| `frontend-quality` | Frontend Quality + Frontend Build | 拆成质量与构建两个阶段 |
| `frontend-e2e` | Frontend E2E | 需预装 Chromium |
| `backend-quality` | Backend Quality | 直接调用 `ci.sh quality` |
| `backend-integration` | Backend Integration | Docker PostgreSQL/Redis |
| `backend-image-verify` | 未内置 | 建议 Phase 2 补 |
| `hermes-quality` | Hermes Quality | 直接调用 `ci.sh` |
| `hermes-contract` | 未内置 | 需后端 DB + Hermes 依赖 |
| `ci-gate` | Jenkins 构建结果 | 用 Jenkins status 或保留 GitHub CI Gate |
| `cd-candidate` | Deploy Production | 由 Jenkins 审批 + 部署脚本替代 |

### B. 常用命令

```bash
# 构建（不部署）
bash scripts/jenkins/build-release.sh \
  --version "$(TZ=Asia/Shanghai date +%Y%m%d)-$(git rev-parse --short=7 HEAD)" \
  --public-host 192.168.40.251 \
  --release-root "$PWD/release"

# 上传 + 部署 + 验证（需要 SSH/sudo 权限）
VERSION=20261021-03d6d39 \
RELEASE_DIR="$PWD/release/20261021-03d6d39" \
DEPLOY_MODE=ssh DEPLOY_HOST=192.168.40.251 DEPLOY_USER=livzon \
NOTICE_SECONDS=180 PREDEPLOY_BACKUP=1 \
bash scripts/jenkins/deploy-release.sh deploy

# 查看状态 / 验证
DEPLOY_HOST=192.168.40.251 DEPLOY_USER=livzon \
  bash scripts/jenkins/deploy-release.sh status
DEPLOY_HOST=192.168.40.251 DEPLOY_USER=livzon \
  bash scripts/jenkins/deploy-release.sh verify

# 回退（不 downgrade 数据库）
VERSION=20261020-abc1234 DEPLOY_HOST=192.168.40.251 DEPLOY_USER=livzon \
  bash scripts/jenkins/deploy-release.sh rollback
```

### C. 验证状态说明

本次只提供方案、参考 `Jenkinsfile` 和辅助脚本，未在真实 Jenkins/Linux
构建机上执行。落地前必须在预发布 Jenkins 完成：

- Jenkinsfile 语法/沙箱验证；
- `bash -n` 与 ShellCheck（或等价检查）；
- 在隔离环境执行一次 `build-release.sh`，核对 manifest/镜像 ID/校验和；
- 在隔离环境执行 `deploy-release.sh` 的 SSH/`sudo -n` 路径；
- 首次生产发布和回退演练。

在完成上述验证前，不要把 `DEPLOY` 设为默认 `true`，也不要停用现有 GitHub
Actions 的 `CI Gate`。
