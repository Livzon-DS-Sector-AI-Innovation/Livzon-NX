# 剩余 CD 验收执行单

当前正式发布关闭。2026-09-10 13:28 CST 核验：Runner active，controller enabled=false。
用户已确认平台日常使用正常，专用组仅允许 Livzon-NX 的 ci.yml@refs/heads/main。

## GitHub 实际门禁

必须先取得本次提交、推送、PR 与合并授权，遵守根 AGENTS.md 全部流程。
不调整组织组策略，不授予额外凭据，不执行任何正式部署命令。

1. 在单独测试 PR 中将 scripts/cd/runner-denial-probe.yml 复制为
   .github/workflows/runner-denial-probe.yml。该文件不 checkout、不访问密钥、不读写业务数据；
   如果误调度，只输出失败标记并退出。测试 PR 不合并。
2. 记录 GitHub run/job ID、head SHA、组名、实际错误和 runner_id。
   必须取得明确的访问拒绝证据；仅 queued、skipped、timeout 或未触发不算通过。
   排队超过 5 分钟时取消本次测试并记录为未定，不能将其误报为隔离成功。
3. 另在 ci.yml 的 PR 版本放入相同无副作用探针，保持文件路径相同，
   验证 refs/pull/... 不因 ci.yml 文件名匹配而取得 main 的执行权限。
   该临时探针不进入正式变更，测试 PR 均关闭，不自动删除远端分支。
4. 正式 CD 变更通过独立 PR 和 CI 后进入 main。对应 push 的 CI Gate 成功后，
   Register CD Candidate 应由 dazah-251-cd 执行成功，并生成相同 SHA/run ID 的候选。
   此时 controller 继续 enabled=false，不开启发布。
5. 正向执行成功和两组明确拒绝证据齐全后，才将调度门禁标记通过。

## 首次正式维护窗口

### 经用户授权的过渡修复

不改写 c9d400000026 等历史迁移。deploy/migration-policy.json 的 deployment_hold
限定源码 head=c9d400000026、实际 upgrade 目标=c9d400000025；从 a7c100000021
或已处于 c9d400000025 的数据库进入。任何后续源码 head、未知数据库 revision 都拒绝沿用。
控制器副本验证和正式迁移均使用同一个明确 revision，不使用 upgrade head，不 stamp、不 downgrade。
新增源码迁移时必须重新审查目标，不能假装已应用被暂缓的删除表迁移。

副本验证已确认升级到 c9d400000025 后部门联系人表行数与内容摘要不变；
新应用导入成功，旧开发镜像中的 DepartmentContact ORM 查询、插入、更新及回滚通过，
检查后内容摘要仍不变。这证明联系人表的兼容性，不代表全部旧业务路径回退验收通过。
当前 transitions 仍为空，完整迁移兼容声明在进一步验收前不启用。

固定北京时间 02:00–05:00，04:30 后不开始切换。当前白天不执行切换。
不能直接调用现有无人值守控制器绕过 EDBO 首次切换门禁。

前置条件：受保护 main 的对应 CI Gate 通过；不可变发布包校验完成；
当前版本镜像及配置归档可恢复；副本迁移通过且旧应用写入兼容性经过审查。
当前 migration-policy transitions 为空；批次血缘唯一约束的兼容性仍未确认，
不能为了赶窗口填写 backward_compatible=true。

1. 核对数据盘 UUID、磁盘余量、运行镜像和所有写入源；记录旧配置校验值和备份引用。
2. 安装已验证的维护入口，启用维护响应并等待请求排空。停止全部应用写入源，包含 EDBO。
3. 完成 writers_stopped 一致备份；失败恢复原应用，不执行迁移。
4. 在服务器专属配置中精确移除 EDBO 服务及依赖，只删除 dazah-edbo-service-1，保留业务表。
5. 单次执行新版本迁移，核对 revision 后依次启动应用和新入口。
6. 内部就绪和业务冒烟通过后开放流量，观察至少 5 分钟并由用户核对业务。
7. 完整回退验收需要再次维护及停止写入；仅对确认兼容的数据库回退应用镜像。
   不为演练自动覆盖开放流量后的数据库；不在正式库注入迁移失败。
8. 记录维护、恢复耗时及所有失败分支证据。未达到目标或兼容性未知，继续关闭无人值守发布。

本执行单不代表实际调度、正式切换或回退已经通过。

## 2026-09-10 授权后的实际执行

- 用户已授权验收所需 Git 操作。主工作区以 feature/single-host-cd 保存现有未提交改动。
- fetch 后 main 为 5ab657ab66db92adc85f412fe18147ea2cf6c1fc，比旧基线增加 #73、#74。
  新迁移 c9d400000026 会删除 quality.department_contacts，downgrade 只重建空表，
  不能恢复数据；旧版本仍定义并使用该表。暂停正式 CD 合并/发布，不能沿用之前兼容性结论。
- 独立工作目录 .deploy-tmp/runner-access-test，测试分支 feature/runner-access-acceptance，
  提交 1210d12df6f45726334d593fb8c2df5ca5a90dd9，仅含两个工作流探针。
  该工作目录内 test-impact 和 diff 检查通过；首次误在主工作区执行的 test-impact 不适用于测试提交，
  已切换正确工作目录重跑，不将其失败当作通过。
- 测试 PR：https://github.com/Livzon-DS-Sector-AI-Innovation/Livzon-NX/pull/75 。
  CI run 34441508225 的 job 102757334970、独立 run 34441508314 的 job 102757334648
  均 queued，runner_id=null，无拒绝 annotation；没有发生探针执行。
  此结果仅表示未调度，不证明策略明确拒绝。
- 因主线破坏性迁移阻断首次发布，提前取消测试运行并关闭 PR（未合并），保留测试分支供后续审计。
  没有修改组织策略、正式数据库或 EDBO。CD 仍关闭。

### 后续隔离恢复验收

- Runner 实际 cgroup 为 `/dazah.slice/dazah-control.slice/actions.runner.Livzon-DS-Sector-AI-Innovation.dazah-251-cd.service`。
  同主机普通进程连接 `192.168.40.251:80` 成功；将独立探针放入该 cgroup 并降权为
  `dazah-runner` 后连接超时，符合 IPAddressDeny 丢弃流量的行为。此对照仅证明主机网络隔离，
  不替代 GitHub 工作流访问拒绝证据。首次探针因路径断言提前退出，未计入成功结果。
- `DAZAH_DOCKER_TESTS=1 python -m pytest scripts/tests/test_cd_watchdog_docker.py -q`：
  1 项通过，129.06 秒。实际开发容器持续不健康时重启三次，随后停止并设置 restart=no，
  写入临时维护标记，后续巡检没有拉起已阻断的容器。测试结束删除该临时容器。
  依赖健康状态使用夹具，冷却时间通过调整测试状态文件推进；未声称验证真实 30 秒调度节奏，
  未操作正式容器、正式维护标记或数据库。
- root 管理控制器已从通过 CI 的 `995a90f` 单独更新，SHA-256 为
  `e12b0d17e712f39810bd233342a70f1ee027d580de6922c99aad1d41d7b2ccae`。
  旧文件保留为 `/opt/dazah/control/controller.py.before-995a90f`；在部署锁内完成原子替换，
  服务器 Python 编译和挂载检查通过，调度返回 `deployment_disabled_pending_acceptance`。
  CD/watchdog timer 继续 disabled，未通过发布包替换特权控制程序。
- `addf5b1` 的单机构建命令在开发容器中实际完成，1792 MiB、1 CPU、无 swap，
  约 400 秒，退出 0、OOMKilled=false；类型检查 77 秒，静态页面 66 个。
  早期无原生线程限制的命令及三阶段 compile/generate 试验失败，不计为通过。
- standalone 开发产物的登录页和静态脚本返回 200；匿名跳转探针缺少 401 后端夹具，
  整体未通过。补充 HTTP 夹具命令被工具自动审批以 blocked by policy 拒绝，未执行；
  随后改用仓库现有 Playwright/mock-api-server 流程，在服务器实际构建产物上运行关键 E2E：
  32 项通过（1.2 分钟），覆盖失效会话跳转、模块/页面权限、采购、助手及模型配置。
  容器限制 512 MiB / 0.5 CPU / 无 swap，OOM=false、重启 0；使用模拟后端，无正式凭据。
  此后续验证完成前述权限路径检查，但不替代真实后端全平台验收。
- 服务器首次 rootless 实构建在 Docker Hub 连接被拒绝时停止，6 秒，构建内存采样峰值
  120 MiB、OOM 计数 0，正式业务保持健康。随后按固定 digest 提供只读 OCI 缓存重新验证，
  第二次完整构建通过：1674 秒，进程树限额 2 GiB、1 CPU、无 swap，OOM/OOM kill 均为 0，
  全程正式业务健康。采样峰值触及 2048 MiB（含缓存），因此不能据此宣称仍有构建内存余量。
  编译约 9.6 分钟、类型检查约 201 秒、生成 66 页；HDD 镜像导出约 533 秒。
  开发镜像 `dazah/frontend:acceptance-addf5b1-dev` 已归档于
  `/data/dazah/releases/acceptance-addf5b1-dev/frontend-dev.tar`，大小 297267712 字节，
  SHA-256 `dc3bf334595a5b3c26aeeb9dcef97cba4b1a9515a183579ccfbe714d0deb7fea`。
  同目录 acceptance.json 保存资源结果。构建后已停止独立 BuildKit，没有载入正式 Docker 或切换服务。
- 服务器三份只读 OCI 输入（Dockerfile frontend、Node 20、Python 3.12）均通过新控制器辅助函数的
  blob 摘要、固定 digest、linux/amd64 内容完整性及 root 所有权/不可组写检查。
  辅助函数仅从临时文件执行；新增控制器尚未替换正式 root 控制程序。
