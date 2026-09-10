# 单服务器 CD 与恢复

目标服务器：192.168.40.251，Ubuntu 22.04，4 核、8 GB。现有 CI 留在 GitHub；
本机 rootless BuildKit 串行构建，root 管理的 controller 验证候选、备份、迁移和发布。
此方案是单机故障恢复，不是高可用。尚无异机备份，整机或双盘损坏可能导致数据丢失。

## 权限及不可变边界

- `dazah-runner` 仅在 `/var/lib/dazah-candidates/<SHA>.json` 写候选，不 checkout
  或执行仓库脚本，不拥有 sudo、生产 Docker socket 或 `/opt/dazah` 访问权限。
- GitHub `single-host-cd` Environment 限制 main；controller 再通过 GitHub API
  独立验证仓库、protected main、SHA、push 事件和对应 CI Gate。
- 候选不是授权。正式控制程序在 `/opt/dazah/control`，配置在
  `/etc/dazah-cd/config.json`，均由 root 管理。发布包不能更新控制程序。
- `dazah-build` 使用 rootless BuildKit，无正式密钥和生产 Docker socket。
  `dazah-build.slice` 合并限制 BuildKit daemon、构建容器和 buildctl 客户端为
  2 GiB、1 核、256 进程，禁用构建 swap；Runner 限制 256 MiB。
- 所有 action 固定 SHA；CI 的 PR 任务继续使用 GitHub hosted runners。
  公开仓库的 self-hosted runner 仍须持续维护系统补丁，不能把环境标签当作安全隔离。

## 磁盘和备份

已授权初始化的磁盘是 HGST HTS541010B7E610，序列号 WX21A97N64F5。
使用 GPT/ext4，UUID 挂载 `/data`，`nofail` 允许数据盘异常时已有应用继续启动。
**不得把磁盘初始化步骤当成可重复执行的安装步骤。**

- `/data/dazah/releases`：root 管理的镜像包、校验清单。
- `/data/dazah/backups`：数据库、持久卷和配置副本，0700。
- `/data/dazah/work`：父目录 root-owned、0711；仅每个 SHA 的工作目录交给构建账号。
  `build-cache` 由构建账号管理。恢复演练临时目录位于 root-only 的 `backups/.drills`，
  不在构建账号可改写的目录中解包配置。
- `/opt/dazah/current`、PostgreSQL 和 Docker/containerd 继续使用 SSD。
- controller 校验 `/data` 的精确 UUID；挂载丢失时拒绝备份和发布。
- 原历史发布包在新盘完成 checksum 比对后才允许删除；首次实施保留旧副本。

```sh
sudo python3 /opt/dazah/control/controller.py status
sudo python3 /opt/dazah/control/controller.py backup
sudo python3 /opt/dazah/control/controller.py drill
```

每日 01:00 备份，月初 00:00 在独立 PostgreSQL 容器恢复演练。
备份成功以 `manifest.json` 及每个文件的 SHA-256 为准；无 manifest 的目录是失败或未完成备份。
保留最近 7 份日备份、4 周各一份备份、最近 3 次部署前备份及当前/上一版本恢复点。
在线备份标记 `online_independent_copies`，不保证数据库和对象文件同一时间点；
发布前停止应用写入后标记 `writers_stopped`。
Redis 另生成 `redis.rdb` 一致快照；卷归档中的在线 AOF 仅用于保留现场。
Redis 容器上限 192 MiB，数据集上限 128 MiB，使用 `noeviction` 保留持久业务状态；
容量不足时拒绝新写入，不通过淘汰业务键或反复重启处理。请求边界将此类不足转换为 503。
恢复 Redis 时先在隔离实例禁用 AOF、加载该 RDB 并核验，再重新生成 AOF；
不得让旧 AOF 覆盖刚恢复的 RDB。发布清单还记录服务器运行配置校验和，
验证后配置发生变化会阻止切换，需重新验证。
本机备份周期目标为 24 小时；配置备份包含密钥，不得下载到普通工作区、上传 CI artifact 或打印内容。

## 发布流程

1. CI Gate 成功后的 main push 由 Runner 登记 SHA/run ID。
   每个 SHA 独立记录，旧 CI 晚完成不会覆盖新提交的候选；调度器按 GitHub 当前 main 选择记录。
2. systemd timer 每日北京时间 02:00 唤醒 controller；不补跑错过的窗口。
3. `enabled=false` 时只记录未启用；启用后检查 API 来源、资源和当前部署状态。
4. 固定 SHA 源码下载到独立目录。基镜像必须匹配 operator-owned
   `/etc/dazah-cd/base-images.json` 中的 digest；解析不到或网络失败即延期。
5. 后端、前端、Hermes、隔离验证用开发后端依次构建，最多 120 分钟。
   MemAvailable 连续 30 秒低于 1 GiB、业务连续异常或到 05:00 时终止构建。
6. 停止 builder 后校验镜像，在无外网 Docker network 内将正式库副本恢复到临时库，
   用开发镜像检查单一 migration head、升级及应用导入。测试不连接正式数据库或模型服务。
7. 没有 schema 变化时自动继续；有变化时 `deploy/migration-policy.json`
   必须包含明确的 from/to revision、`backward_compatible: true` 和 `review_reference`。
   该声明须经过代码审查，不能为了部署通过而填入未经验证的兼容结论。
   首轮过渡配置另以 `deployment_hold` 将源码 head `c9d400000026` 的部署目标固定为
   `c9d400000025`，暂缓删除部门联系人表。源码新增后续迁移即拒绝沿用；
   验证与正式迁移均执行明确目标，不执行隐含的 `upgrade head`。详见剩余验收执行单。
8. 04:30 后不开始切换。进入维护模式，等待请求排空，停止应用写入源，完成部署前备份。
9. 单独执行迁移并核对 revision；再按后端、Hermes、前端顺序启动，重建 Nginx。
10. 容器、依赖及容器内 readiness probe 通过后开放流量，观察 5 分钟，记录成功 SHA。

`compose.release.yml` 只写入校验后的 image ID。服务器原有入口、数据卷、密钥及配置
不由仓库 Compose 无条件覆盖。`compose.single-host.yml` 是受控资源覆盖层。
首次切换要明确移除旧 Compose 中 EDBO 的依赖和服务，然后仅删除
`dazah-edbo-service-1`；不得使用 `--remove-orphans` 或全局 prune。

## 首次启用清单

安装可以在白天完成，现有应用重建、EDBO 下线、故障演练仅在维护窗口执行。

公开仓库的 Runner 必须由组织级 Runner Group 限制为选定仓库，以及
`Livzon-DS-Sector-AI-Innovation/Livzon-NX/.github/workflows/ci.yml@refs/heads/main`。
仅依赖 job 的 `if`、标签或 environment 不足以阻止其他工作流调用 Runner。
组织管理员已完成专用组限制，用户提供截图确认仓库及 main 工作流路径；Runner 已恢复服务。
当前 CLI 无组织 API 读取权限。PR/其他工作流的实际拒绝调度测试仍待进行，
不能把注册成功或在线状态当作完整门禁验收，CD timer 在验收前保持关闭。
参见 https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access 。

Runner 与备份、发布、巡检服务统一加入 `dazah-control.slice`，总预算 384 MiB、0.25 CPU。
构建服务使用独立预算，不加入此 slice。

1. 将 controller/readiness 及 Nginx guard 文件安装到 `/opt/dazah/control`；
   控制程序 root-owned，runner 不可写。
2. 安装提供的 systemd units；`dazah-build` 按需启动，不设开机常驻。
3. 使用 `stage_site.py` 从当前 Nginx 文件生成候选，不覆盖当前文件。
   `nginx-capacity.conf` 在 http 上下文加载；普通 API 加限流，MCP 限制连接数。
   在隔离 nginx 容器执行 `nginx -t` 后才应用候选和资源 overlay。
4. 验证维护标记 `/var/lib/dazah-cd/public/maintenance` 生效、排空探针可用。
5. 首次受控发布、应用回退、迁移失败及中断恢复演练通过。
6. 在隔离业务环境完成 20 用户混合负载及双倍过载测试，不可用 `/health` 压测替代业务容量验收。
7. 本次仓库变更通过 PR/CI 进入 main 后，方可将配置 `enabled` 改为 true 并启用 CD timer。
   未完成前不要启用定时发布。备份 timer 可在备份和恢复演练通过后独立启用。

## 故障处理

- 进程退出：`restart: unless-stopped`；应用 unhealthy：主机 watchdog 连续 3 次失败后定向恢复。
- 15 分钟最多 3 次恢复，60 秒冷却；超预算禁用该容器自动重启、停止容器并进入维护状态。
  排除原因后人工恢复 restart policy、清理 watchdog blocked 记录，并验证后解除维护。
- 人工停止的容器不自动拉起；依赖异常不批量重启数据库或应用。
- 迁移、备份和切换共享 `/var/lock/dazah-deploy.lock`，watchdog 不干预进行中的发布。
- `recovery_required` 或未完成的迁移状态禁止自动再部署。先保留事件和备份，核对实际 revision。
- 备份之前失败：恢复原应用。迁移成功且已确认兼容时，可回退应用镜像。
- 迁移失败、状态不明或不兼容：保留维护模式，不自动 downgrade，不盲目启动旧应用。
- **流量开放后不得自动恢复旧数据库。** 要先评估新写入的数据损失、停止全部写入，
  再由人工在隔离库验证恢复点，最后实施正式恢复。
- 整机掉电不自动触发可信远程告警；飞书和异机备份当前均为未启用。

当前控制程序提供本机事件和数据库恢复演练，不提供无人确认的正式数据库还原命令。
完整业务恢复还需验证对象文件、Redis 持久状态、Hermes 数据与选定数据库恢复点一致，
数据库恢复演练通过不能代替这一验收。

## 人工完整恢复顺序

1. 禁用 CD/watchdog timer，取得部署锁，开启维护模式。记录故障 SHA、容器状态、
   当前 revision、流量是否曾开放；将现状另外归档，不覆盖部署前备份。
2. 选择带完整 manifest 的恢复点，逐文件核对 SHA-256。优先选择 `writers_stopped`；
   日常在线备份的数据与对象文件时间不完全一致，须评估丢失窗口。
3. 停止全部写入源，包含应用、Hermes、后台任务及首次切换前的 EDBO；
   检查剩余数据库连接来源，不能仅凭维护页已显示就认定没有写入。
4. 先恢复到新的隔离数据库和临时文件目录，核对 revision、关键表数量、文件引用和对象。
   Redis 从独立 RDB 加载，验证后再生成 AOF；Hermes 数据与同一恢复点配套使用。
5. 明确记录允许损失的时间范围。流量曾开放时必须先处理新增数据，不能自动用旧备份覆盖。
6. 正式恢复保留旧数据库和旧卷作为故障现场，准备新的数据库/卷并恢复，
   核对 UID/GID、权限及配置挂载后切换。不要在唯一故障副本上直接反复重试还原。
7. 镜像归档通过 `docker load` 恢复；基线 manifest 中同时保存 image ID 与原引用，
   必要时按该映射恢复标签。选择与恢复 revision 兼容的镜像；需要升级结构时先执行迁移。
8. 依次启动后端、Hermes、前端，重建 Nginx；验证内部就绪、登录、只读业务与文件读取。
9. 人工确认后开放流量，观察至少 5 分钟，记录从维护开始到业务恢复的实测时长。
   故障原因和未完成的迁移状态未明确前，不重新启用自动发布。

## 2026-09-10 实施记录

- `/data` UUID：`079b531c-a624-4337-91c2-535b34935570`；历史发布包完成复制和 checksum 比对，
  原 SSD 副本保留。Docker/containerd 和正式数据库均未迁移。
- 当前 8 个服务镜像完整归档：`/data/dazah/releases/baseline-20260910T012920Z`，
  归档大小 2,153,540,096 字节；manifest 保存 SHA-256、image ID 和原镜像引用。
- 初始配置与数据库快照：`/opt/dazah/backups/bootstrap-20260909T090137Z`。
  新版完整在线备份：`/data/dazah/backups/daily-20260910T012503489043Z`。
- 新版恢复演练成功：数据库、6 份文件归档和 Redis 快照，约 13 秒；
  这不包含完整平台切换及人工核验，不能据此宣称达成 30 分钟 RTO。
  收紧演练目录权限后的复验同样通过，耗时 20.4 秒。
- 正式库仍为 `a7c100000021`。正式备份的隔离副本已成功升级至 `c9d400000023`；
  中间包含批次血缘唯一约束，尚未声明旧应用写入兼容性，`transitions` 保持空列表。
- 备份和月度恢复 timer 已启用。CD/watchdog timer 未启用，`enabled=false`。
  用户完成组织级注册并确认组 `dazah-production-cd-nx` 仅允许 `Livzon-NX` 的
  `.github/workflows/ci.yml@refs/heads/main`。13:21 CST 已迁移服务安全配置并启用 Runner，
  日志确认 `Connected to GitHub` 和 `Listening for Jobs`。组织 API 当前仍无读取权限，
  组策略以用户提供的设置截图和确认为依据；允许/拒绝工作流的实际调度验收尚未完成。
- 正式应用未重建，资源/入口覆盖层仅完成候选配置验证，EDBO 仍保留运行，等待首次值守切换。
- main 当前规则包含 PR、`CI Gate`、严格最新分支要求；尚未用落后 PR 做实际拦截演练。
  本次代码已通过 PR #76 推送；安全修复提交 `995a90f` 的 CI Gate 已通过。
  后续构建优化需在最新提交上重新验证；尚未执行首次正式发布。

### 单机前端构建

生产 Dockerfile 使用 `pnpm build:single-host`，仍运行标准 `next build --webpack`。
该命令内部设置 `DAZAH_SINGLE_HOST_BUILD=1`，限定 Node 堆 1280 MiB、构建 worker 1 个，
并将 `RAYON_NUM_THREADS`、`UV_THREADPOOL_SIZE` 设为 1，限制原生编译线程，
关闭该次构建的 Webpack 缓存和 source map。外围 systemd slice 的 2 GiB 总预算仍是硬限制，
不能用 Node 堆设置替代进程树限制。普通开发和 CI 的 `pnpm build` 保留原行为。

构建使用 `tsconfig.build.json` 检查所有生产源码和生成路由类型，保留 strict 和 noEmit，
不设置 ignoreBuildErrors。原 `pnpm typecheck` 继续在 CI 检查包含测试文件的完整源码集。
`pnpm test:build` 验证生产源码覆盖范围和失败退出行为，并进入 Frontend Quality 门禁。
初期仓库命令复验曾触发 OOM。限制原生线程并移除额外 Node 父进程后，
固定提交 `addf5b1` 的命令已在 1792 MiB / 1 CPU / 无 swap 开发容器完成全部阶段；
服务器 rootless 进程树 2 GiB / 1 CPU / 无 swap 下也已完成前端开发产物构建（1674 秒），
没有 OOM，期间正式业务健康；该产物关键 E2E 32 项通过。其余服务与正式切换仍需验收。

### Docker Hub 不可达时的镜像输入

rootless BuildKit 不共享生产 Docker 的镜像存储。运维可把与基础镜像策略及 Dockerfile
syntax 完全相同 digest 的镜像导出为 OCI layout，校验归档与各内容块摘要后放入
`/data/dazah/build-inputs/<名称>`。该目录及内容必须 root 所有，构建账号只读；
不得放到构建账号可替换的 work 或 build-cache 目录。

`/etc/dazah-cd/offline-images.json` 使用 `deploy/single-host/offline-images.json.example`
的映射格式，文件由 root 管理且不可被组或其他用户写入。配置存在时，所有本次引用都必须
有完整缓存；控制器重新验证每个 blob、引用 digest、linux/amd64 配置与必需镜像层，
通过 BuildKit OCI named context 提供镜像，并在 build.json 记录缓存策略校验和。
不会改变固定 digest，不使用陌生镜像代理，不向 Runner 开放 Docker socket。
缓存不完整或校验失败时停止构建；没有配置该文件时仍使用正常 registry 解析。
此缓存只覆盖容器镜像，npm、Python、系统包与上游下载的锁定依赖仍需要可访问源或已有缓存。

未完成的发布验收仍包括：完整三镜像服务器构建、首次值守切换、旧应用写入兼容性、
完整平台回退/RTO、构建 OOM 与发布中断的实际故障演练，以及前端/AI/外部集成混合容量测试。
控制器测试中的故障模拟不能代替这些实际验收。

### 代码和基础设施验证

- 后端相关测试 79 项、Hermes 记忆相关测试 53 项通过；相关 Ruff 和类型检查通过。
- CD/就绪/入口/转换限制四组脚本测试在 Windows 为 40 通过、5 跳过；
  Linux 为 43 通过、2 跳过。平台相关锁测试和显式容器集成测试的运行条件不同。
- 另行启用真实开发容器集成验证：Nginx 限流、SSE/MCP 隔离、维护页及恢复，
  LibreOffice 转换、队列满拒绝和包装进程退出后的子进程清理均通过。
- 最新后端及 Hermes 开发镜像构建通过。服务器 rootless BuildKit 完成实际 scratch/COPY 构建，
  确认 daemon 和客户端同受 2 GiB、无 swap、1 CPU 的 slice 约束；验证后构建服务已停止。
- 主机安装的控制器 SHA-256 与工作区一致；Compose 候选配置和 systemd 单元校验通过。
  正式入口配置未切换，CD 和 watchdog 未启用；Runner 后续启用情况见上述实施记录。
- 生成 API 脚本未产生语义差异；两份环境变量示例已同步。此次没有新增数据库迁移。

### 13:23 CST 非中断预验收复验

- 在运行中 Runner 的 mount namespace 内，以 UID/GID 1002、无附加组及 no-new-privileges
  实际验证：正式环境配置、控制器配置、备份和控制程序不可读，Docker socket 连接被拒绝，
  控制程序目录不可写，候选目录可写。此检查验证文件访问边界，不代表网络隔离或 GitHub 调度门禁验收。
- 服务器 Linux 四组脚本测试 43 通过、2 跳过；覆盖不可信候选、窗口、UUID、迁移失败、
  回退和巡检预算等逻辑。故障分支使用模拟依赖，未向正式服务注入故障。
- 本地显式开发容器集成测试 4 通过、2 个 Linux 专属测试跳过（已由服务器测试覆盖）；
  实测 Nginx 维护响应、限流、SSE/MCP 容量隔离及转换进程生命周期保护通过。
- 再次独立恢复数据库、6 份文件归档及 Redis，20.9 秒完成，systemd Result=success。
- 测试后正式应用及依赖保持健康，Runner active，CD/watchdog timer disabled。
  数据盘 UUID 正确，主机可用内存约 4.6 GiB。未执行正式迁移、EDBO 删除或版本切换。
- 结论：本轮非中断预验收通过，完整上线验收未通过收口。
  GitHub 实际允许/拒绝调度需要受控工作流变更；当前未获得 Git 推送权限，尚未执行。
  正式切换、完整平台恢复时间及主机故障场景仍需维护窗口验收。

### 隔离混合负载结果

同机运行独立 PostgreSQL、Redis、开发后端与 Nginx；真实登录 40 个合成管理员账号，
每个活跃账号约每秒一次请求，混合身份/组织架构/员工查询以及员工写入。
正式服务同时保留运行，期间执行了受限备份、恢复演练和镜像归档。

| 阶段 | 活跃用户 | 请求数 | 成功请求 P95 | 429/503 | 非预期错误 |
|---|---:|---:|---:|---:|---:|
| 常规 30 分钟 | 20 | 35,938 | 0.1677 秒 | 0 | 0 |
| 双倍负载 120 秒 | 40 | 4,791 | 0.5559 秒 | 1,131 | 0 |
| 降载恢复 120 秒 | 20 | 2,398 | 0.0691 秒 | 0 | 0 |

采样收尾使三个阶段总计时分别为 1,804、150、150 秒；后两阶段包含约 30 秒采样收尾。
恢复阶段首个 30 秒采样已无错误或限流。主机 `oom_kill` 始终为 0，四个测试容器均无 OOM/重启。
测试容器、网络和数据库卷已清理，正式服务保持健康。

测试开发后端 image ID：`sha256:e7c11d9bc45dc8a5e1cb72d1d29623a677a1a9b43c283765fb63f4f25748eb66`。
此结果不覆盖前端、普通用户完整权限路径、AI 重任务、MinIO 上传或真实外部集成，
也不替代最终提交的容量验收。采购接口因依赖未配置的外部集成未纳入此离线负载。
工具位于 `scripts/tests/load_single_host.py`、`scripts/tests/run_single_host_load.sh`；
后续版本额外将 OOM 计数与容器运行状态纳入自动判定，本次相同项目由现场检查确认。
