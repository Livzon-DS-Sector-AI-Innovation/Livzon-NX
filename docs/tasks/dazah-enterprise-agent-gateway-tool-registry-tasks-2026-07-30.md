# Dazah 企业级 Agent Gateway 与 Tool Registry 实施账本

> 对应方案：`docs/dazah-enterprise-agent-gateway-tool-registry-implementation-plan-2026-07-30.md`  
> 建立日期：2026-07-30  
> 当前阶段：Phase 0 初验通过，等待真实飞书测试应用与单消费者切换验收

## 1. 执行规则

1. 严格按 Phase 0 至 Phase 5 实施；跨阶段前置工作必须在记录中说明。
2. 每次开始、完成或阻塞一个工作单元时更新本账本。
3. 每条完成项必须附关键文件、验证命令和结果；只写“已实现”不算完成。
4. 阶段实现和首次测试通过后，必须执行“回头验证”。
5. 回头验证必须重新核对方案中的全部验收项，并复跑已完成阶段核心回归。
6. 只有功能、测试、文档、配置和运行路径一致时，阶段才可标记为
   `已完成并回验`。
7. 外部飞书真实环境验收不能用 mock 替代；未执行时必须保持待处理或阻塞。
8. 不读取、记录或提交真实 Secret、Token、Cookie、API Key 和数据库凭据。
9. 测试数据库必须独立，禁止连接开发、共享或生产数据库。
10. 未经用户明确要求，不执行 git add、commit、push、分支切换或合并。

## 2. 状态定义

- `待处理`：尚未开始。
- `进行中`：正在实现或验证。
- `阻塞`：存在明确外部依赖，已记录原因和恢复条件。
- `初验通过`：实现和首轮测试通过，尚未完成回头验证。
- `已完成并回验`：全部验收和回归通过。

## 3. 阶段总览

| 阶段 | 状态 | 目标 | 完成门禁 |
| --- | --- | --- | --- |
| 文档与基线 | 已完成 | 固化完整方案、任务账本、阶段验收和测试矩阵 | 两份文档已建立并相互引用；现状和缺口有代码证据 |
| Phase 0 | 初验通过（外部验收待处理） | 固定上游并完成 Hermes 原生 Feishu Gateway | 原生消息、确认卡片、卡片回调、主动推送和回滚均通过 |
| Phase 1 | 待处理 | Identity Binding 与可信主体 | 飞书/Web 身份一致，伪造和跨租户失败关闭 |
| Phase 2 | 待处理 | AgentBackend V2 与原生确认闭环 | 标准事件在 Web/飞书一致，重复点击不重复执行 |
| Phase 3 | 待处理 | Tool Registry 自动发现与渐进披露 | 新工具无需修改 Hermes 即可按权限发现和执行 |
| Phase 4 | 待处理 | Policy、Trace、审计与治理 | 双域决策一致，全链可追踪，敏感审计合规 |
| Phase 5 | 待处理 | 模块接入、主动推送和最终发布 | 计划模块接入、全量门禁和生产灰度完成 |

## 4. 当前基线证据

- [x] 工作区初始 `git status --short` 无输出。
- [x] 根、后端、Hermes 和前端开发规范已读取。
- [x] 当前 Hermes Docker 构建固定
  `HERMES_FEISHU_GATEWAY_TAG=v2026.7.7.2`。
- [x] 当前构建校验上游下载归档 SHA-256。
- [x] GitHub Release 显示 `v2026.7.7.2` 对应 v0.18.2，commit `9de9c25`。
- [x] 当前 worker 实例化原生 `FeishuAdapter`。
- [x] 当前 worker 仍手工生成确认卡片并调用 `_feishu_send_with_retry` 私有方法。
- [x] 当前后端通过 `tool_registration.py` 手工 import 工具模块。
- [x] 已确认并删除 Hermes 静态 operation 枚举。
- [x] 静态核对发现后端和 Hermes 工具列表存在漂移风险。
- [x] 当前 ToolExecutor 只按 UUID 解析 `context.user_id`。
- [x] 当前流式事件尚未覆盖完整 AgentBackend V2 事件集合。
- [x] 当前 15 个业务模块中只有质量、采购、能源、仓储提供正式
  `agent_tools.py`。

## 5. Phase 0：上游固定与原生 Feishu Gateway

状态：初验通过；本地实现、上游回归、完整镜像和运行态冒烟已通过，真实飞书
测试应用及生产单消费者切换待处理。

### 5.1 供应链与版本固定

- [x] 增加可机读的 Hermes upstream provenance。
- [x] 固定并核验 repository、tag、commit 和 archive SHA-256。
- [x] 增加构建期版本/目录结构校验。
- [x] 增加 CI 上游结构契约测试。
- [x] 镜像只从已验证 stage 复制上游目录；最终镜像以非 root 用户运行且不对
  `/opt/hermes-upstream` 授予写权限，本地补丁不写入上游目录。

### 5.2 Compatibility Layer

- [x] 建立明确目录和稳定接口。
- [x] 入站消息转换为内部稳定 envelope。
- [x] 出站回复、Reaction 和消息编辑使用 Gateway 公共能力；卡片回调由原生
  Gateway 接收，raw-card 发送因固定上游无公共 API 而只通过唯一兼容层。
- [x] 删除业务 worker 对 `_feishu_send_with_retry` 的直接依赖；v2026.7.7.2
  尚无公共 raw-card API，唯一兼容调用封装在窄接口中。
- [x] 上游字段和所需兼容方法变化由构建期及兼容层契约测试捕获。

### 5.3 原生飞书体验

以下项目已通过固定上游测试与 Dazah 契约测试；真实飞书 App 验收仍以 5.4 和
运行手册第 5 节为准。

- [x] 私聊消息。
- [x] 白名单群聊和必须 `@Livzon`。
- [x] Thread/引用回复。
- [x] 文本、富文本、图片、文件、音频和视频。
- [x] 处理中 Reaction 和失败状态。
- [x] 原生富文本消息创建、增量编辑和最终收口。固定上游不提供公共流式卡片
  API，因此不虚构该能力。
- [x] Dazah 业务确认卡片渲染。
- [x] 卡片按钮回调、点击人校验、重复点击和过期。
- [x] 主动文本/卡片推送、幂等、重试和投递回执。

### 5.4 切换、灰度与回滚

- [ ] 测试应用旁路验证。
- [ ] 确认同一 App 不存在两个生产事件消费者。
- [ ] Hermes 健康后关闭 Dazah 旧事件和卡片连接。
- [ ] 保留一个发布周期的关闭态回滚开关。
- [x] 凭证轮换失败保留旧版本（本地原子轮换测试已覆盖，真实 App 轮换待 5.4）。
- [x] 建立 Phase 0 运行手册。

### 5.5 初次测试

- [x] Hermes 关键入口编译。
- [x] Hermes 全量 Pytest。
- [x] Gateway 契约测试。
- [x] 容器构建。
- [x] 模拟飞书事件和卡片回调。
- [ ] 真实测试应用验收。

### 5.6 回头验证

- [x] 回读 Phase 0 全部范围。
- [x] 搜索并确认业务 worker 无上游私有发送方法依赖；唯一 raw-card 兼容调用
  位于 Compatibility Layer，并受 manifest 与测试约束。
- [x] 复核消息、确认和主动推送均走原生 Gateway。
- [x] 复跑 Phase 0 全部核心测试。
- [x] 核对文档版本、构建版本和运行版本。
- [x] 记录未执行项、风险和回滚结果。

## 6. Phase 1：Identity Binding 与可信主体

状态：待处理

### 6.1 数据与迁移

- [ ] 新增 `identity.external_identity_bindings` 模型。
- [ ] 新增并审查 Alembic migration。
- [ ] 建立租户、应用指纹、外部 ID 类型和值的唯一约束。
- [ ] 从现有 User 飞书字段安全回填。
- [ ] 验证 upgrade、downgrade 和单 head。

### 6.2 服务与接口

- [ ] Repository 和 Service。
- [ ] 服务认证的身份解析接口。
- [ ] 绑定创建、同步、停用、撤销和最后活动时间。
- [ ] 权限快照包含可信 local_user_id 和 tenant_id。
- [ ] Gateway 使用解析结果，不把飞书 open_id 当作 Dazah user_id。
- [ ] ToolExecutor 使用可信主体并防止上下文覆盖。

### 6.3 测试

- [ ] open_id/user_id/union_id 映射。
- [ ] 多租户和多应用隔离。
- [ ] 未绑定、停用、撤销和冲突。
- [ ] 伪造 local_user_id、session/user 不匹配和跨租户。
- [ ] Web 与飞书访问范围一致。
- [ ] API、Ruff、Mypy、migration 和数据库集成测试。

### 6.4 回头验证

- [ ] 回读全部身份入口和 ToolExecutor 调用链。
- [ ] 搜索生产路径中不可信 `context.user_id` 的使用。
- [ ] 复跑 Phase 0 Gateway 核心回归。
- [ ] 复跑 Phase 1 身份与权限矩阵。
- [ ] 核对迁移、OpenAPI、生成类型和环境变量。

## 7. Phase 2：AgentBackend V2 与原生确认闭环

状态：待处理

### 7.1 协议

- [ ] 定义 V2 Input Envelope。
- [ ] 定义 accepted、thinking、capability_search、tool_call、tool_result、
  text_delta、confirmation、delivery、error、finished 和 ping。
- [ ] event_id、trace_id、run_id 和 sequence。
- [ ] 稳定错误码、版本协商和 V1 适配。
- [ ] Pydantic Schema、OpenAPI 和前端生成类型。

### 7.2 链路

- [ ] Gateway 入站转换 V2。
- [ ] Hermes Runtime 发出标准事件。
- [ ] 后端代理事件不丢失或改序。
- [ ] Web 前端消费 V2。
- [ ] 飞书 Gateway 使用事件更新原生卡片。
- [ ] Dazah confirmation 点击后重新鉴权并原位更新。

### 7.3 测试

- [ ] 事件顺序、重复、断线、超时、心跳和恢复。
- [ ] 工具成功、失败、部分成功和 confirmation。
- [ ] 重复点击、错误点击者、过期和状态冲突。
- [ ] V1/V2 兼容。
- [ ] 后端接口、Hermes、前端单元/E2E 和容器测试。

### 7.4 回头验证

- [ ] Web 与飞书相同请求的事件语义一致。
- [ ] 搜索旧 SSE 分支是否仍绕过 V2。
- [ ] 复跑 Phase 0–1 核心回归。
- [ ] 核对 OpenAPI 和生成类型无无关漂移。

## 8. Phase 3：Tool Registry 自动发现与渐进披露

状态：待处理

### 8.1 自动发现

- [ ] 基于 `module_registry` 导入存在的 `agent_tools`。
- [ ] 平台和 Agent 内建工具使用明确入口注册。
- [ ] 重复名、非法模块、非法版本和策略矛盾失败关闭。
- [ ] 生成稳定 registry_version 和 code fingerprint。
- [ ] 移除手工模块 import 清单。

### 8.2 Catalog

- [ ] Catalog Projection 模型和 migration。
- [ ] 启动对账和 lifecycle 状态。
- [ ] 代码不存在的工具不能被数据库启用。
- [ ] 管理员紧急禁用和废弃替代。
- [ ] 初期进程内缓存、ETag 和离线快照。

### 8.3 渐进披露

- [ ] search API。
- [ ] describe API。
- [ ] execute 保持统一入口。
- [ ] 搜索结果按用户权限和数据范围裁剪。
- [ ] Hermes 动态获取目录。
- [x] 删除运行时离线兜底，统一以后端 Tool Registry 为事实源。
- [ ] 模型 Schema 只包含 search/describe/execute。

### 8.4 测试

- [ ] 新模块自动发现。
- [ ] 权限过滤和防能力枚举泄漏。
- [ ] 目录版本、ETag、缓存失效和后端不可用兜底。
- [ ] 工具新增、删除、废弃、禁用和版本冲突。
- [ ] Registry 与 Hermes 全量契约。

### 8.5 回头验证

- [ ] 新增临时测试工具不修改 Hermes 即可发现和执行。
- [ ] 搜索并确认没有正常路径依赖手工 operation 列表。
- [ ] 复跑 Phase 0–2 核心回归。
- [ ] 核对 migration、OpenAPI 和生成类型。

## 9. Phase 4：Policy、Trace、审计与治理

状态：待处理

### 9.1 Policy

- [ ] 统一 Policy Decision Schema。
- [ ] Dazah 业务域适配器。
- [ ] 飞书资源域适配器。
- [ ] 风险只升不降。
- [ ] 人工责任判断固定拒绝。
- [ ] 自动化路径与交互路径复用同一策略。
- [ ] 策略版本和决策审计。

### 9.2 Trace 与隐私

- [ ] message_id → trace → run → tool call → confirmation → audit → delivery。
- [ ] 结构化日志和查询 API。
- [ ] 按 sensitivity 保存审计摘要。
- [ ] restricted 工具不保存业务正文。
- [ ] 错误和外部响应脱敏。

### 9.3 治理界面

- [ ] 工具目录、版本、状态和策略。
- [ ] Trace 查询和权限裁剪。
- [ ] Gateway 版本、连接、快照和队列状态。
- [ ] 应急禁用和审计。
- [ ] 指标、告警和运行报告。

### 9.4 测试与回头验证

- [ ] ALLOW/DENY/CONFIRM 全矩阵。
- [ ] Web、飞书、自动化一致性。
- [ ] 越权、绕过、敏感审计和日志泄漏测试。
- [ ] 任意抽样 trace 全链可查。
- [ ] 复跑 Phase 0–3 核心回归。
- [ ] 前后端和 Hermes 全量门禁。

## 10. Phase 5：模块接入、主动推送与最终发布

状态：待处理

### 10.1 现有工具迁移

- [ ] 质量。
- [ ] 采购。
- [ ] 能源。
- [ ] 仓储。
- [ ] identity 和 agent 内建能力。

### 10.2 新模块接入

- [ ] 生产。
- [ ] 设备。
- [ ] 安全。
- [ ] 环保。
- [ ] 产品。
- [ ] 行政。
- [ ] 人事。
- [ ] 研发。
- [ ] 注册。
- [ ] 法规追踪。
- [ ] 资料撰写。

每个模块必须有：

- [ ] 能力清单和明确非能力清单。
- [ ] Input/Output Schema。
- [ ] 权限键、数据范围、风险和敏感度。
- [ ] Service 薄适配。
- [ ] 注册、权限、确认、拒绝、审计和核心调用测试。
- [ ] 文档和模块负责人。

### 10.3 主动推送

- [ ] Hermes Gateway Delivery API。
- [ ] 文本、富文本、卡片和卡片更新。
- [ ] 收件人/会话解析。
- [ ] 幂等、持久队列、重试和回执。
- [ ] 现有 AgentPushDelivery 适配。
- [ ] trace_id 和 delivery_id 关联。

### 10.4 最终验证

- [ ] 后端全量 Ruff、Mypy、Pytest、coverage、migration 和 Docker。
- [ ] Hermes 全量测试和 Docker。
- [ ] 前端 lint、typecheck、unit、coverage、关键 E2E、build 和 Docker。
- [ ] OpenAPI 和生成类型。
- [ ] test-impact policy。
- [ ] 测试飞书应用完整验收。
- [ ] 生产分级灰度。
- [ ] 回滚演练。
- [ ] 观察期指标和安全审计。

### 10.5 最终回头验证

- [ ] 回读完整实施方案和本账本所有未勾选项。
- [ ] 搜索遗留手工注册、私有 Gateway 调用和身份旁路。
- [ ] 复跑 Phase 0–5 核心及全量门禁。
- [ ] 核对运行版本、配置、migration、OpenAPI 和文档。
- [ ] 记录所有外部验收证据和遗留风险。
- [ ] Phase 0–5 全部标记为“已完成并回验”。

## 11. 风险与决策记录

| 日期 | 决策或风险 | 处理 |
| --- | --- | --- |
| 2026-07-30 | 用户要求使用 GitHub 发布的 Hermes v2026.7.7 系列并固定上游 | 使用已固定的更新补丁版 `v2026.7.7.2`；若需精确回退到 `v2026.7.7`，必须单独确认 |
| 2026-07-30 | 当前只复用原生 Adapter，不是完整原生 Gateway 体验链 | Phase 0 迁移消息、卡片、回调和主动推送到公开 Gateway 能力 |
| 2026-07-30 | 当前 worker 调用上游私有发送方法 | Phase 0 删除业务依赖并用 Compatibility Layer 隔离 |
| 2026-07-30 | 数据库 Catalog 可能被误用为动态代码源 | 明确代码 Registry 为唯一执行权威，Catalog 仅作治理投影 |
| 2026-07-30 | 全量工具注入随模块增加持续膨胀 | Phase 3 实现 search/describe/execute |
| 2026-07-30 | 飞书发送者标识与 Dazah UUID 存在缝隙 | Phase 1 建立显式 Identity Binding 和可信主体 |
| 2026-07-30 | 真实飞书验收依赖外部应用配置和已授权账号 | mock 不能替代；到对应阶段时记录阻塞与恢复条件 |
| 2026-07-30 | Hermes v2026.7.7.2 没有公开 raw-card 或流式卡片 API | 普通回复使用公开 `send/edit_message` 原生富文本增量更新；raw-card 仅保留一个受 manifest 和契约测试约束的兼容调用 |
| 2026-07-30 | npm 安装脚本会在构建期执行未固定的二次下载 | 改为 `lark-cli.json` 固定 v1.0.76 二进制 SHA-256，并由 Python 安装器校验和安全解包 |
| 2026-07-30 | lark-cli v1.0.76 的 Base Skill 默认 user-first，但 Dazah 设计为 bot-only | 凭证初始化显式绑定 Hermes bot-only workspace；Prompt 和工具边界禁止 `--as user` |
| 2026-07-30 | 只读生产容器使上游 Gateway 默认锁目录不可写 | 将 `HERMES_GATEWAY_LOCK_DIR` 固定到私有 tmpfs，保留只读根文件系统 |

## 12. 实施日志

### 2026-07-30：建立平台化实施基线

- 状态：文档与基线已完成，Phase 0 开始。
- 新增完整实施方案和本任务账本。
- 已把原生 Gateway、身份、V2 协议、自动发现、Policy/Trace 和模块接入拆成
  Phase 0–5。
- 已为每个阶段建立初次测试和回头验证门禁。
- 已确认当前工作树无已有修改。
- 已确认当前 Dockerfile 固定 `v2026.7.7.2` 和 SHA-256。
- 已确认当前缺口是“原生 Adapter + 自建 worker 卡片”，而非完整原生
  Gateway 体验链。
- 下一工作单元：盘点 v2026.7.7.2 Gateway 的公开扩展接口与当前 worker 的
  私有调用，确定 Phase 0 最小安全迁移切片并先补契约测试。

### 2026-07-30：Phase 0 上游 provenance 与结构契约

- 阶段：Phase 0。
- 状态：进行中；供应链与版本固定工作单元已完成。
- 实现：
  - 新增 `Hermes-Lite/upstream-hermes.json`，记录 repository、release tag、
    release version、annotated tag object、完整 commit、commit archive SHA-256、
    必需文件和公共类方法契约。
  - Docker 构建改为按完整 commit 下载，不再允许通过 build ARG 临时改成其他
    Tag；下载后校验 SHA-256、安全解包、必需文件和公共方法。
  - 验证通过后在上游目录写入 `.dazah-upstream-provenance.json`，供镜像运行
    状态和故障排查读取。
  - 新增无网络专项测试，覆盖固定版本、正确安装、checksum 失败和公共接口漂移。
- 关键文件：
  - `Hermes-Lite/upstream-hermes.json`
  - `Hermes-Lite/scripts/install_pinned_hermes_upstream.py`
  - `Hermes-Lite/tests/test_pinned_hermes_upstream.py`
  - `Hermes-Lite/Dockerfile`
- 验证命令：
  - `.venv\Scripts\python.exe -m py_compile scripts\install_pinned_hermes_upstream.py tests\test_pinned_hermes_upstream.py`
  - `.venv\Scripts\python.exe -m ruff check scripts\install_pinned_hermes_upstream.py tests\test_pinned_hermes_upstream.py`
  - `.venv\Scripts\python.exe -m pytest tests\test_pinned_hermes_upstream.py -q`
- 验证结果：编译通过，Ruff 通过，专项测试 `4 passed`。
- 未执行项及原因：本工作单元尚未执行完整 68 MB 上游下载和 Docker 镜像构建；
  将在 Phase 0 容器验收统一执行。
- migration/OpenAPI/环境变量/生成文件：均不涉及。
- 风险与回滚：上游下载从 Tag archive 改为同一 Release 对应的完整 commit
  archive，归档 SHA-256 随之更新；恢复旧 Dockerfile 可回滚，但会失去 commit
  和公共接口契约验证。
- 下一工作单元：建立 Gateway Compatibility Layer，先把普通消息发送切换到
  `FeishuAdapter.send` 公共方法，并将业务确认卡片的唯一兼容 shim 与 worker
  解耦。

### 2026-07-30：Phase 0 Gateway Compatibility Layer 第一切片

- 阶段：Phase 0。
- 状态：进行中；稳定出站接口和确认卡片隔离初验通过。
- 实现：
  - 新增 `DazahFeishuGateway`，普通消息通过 Hermes 原生公开 `send` 方法，
    连接、断开和消息处理器注册也只暴露稳定接口。
  - 从 `feishu_gateway_worker.py` 删除确认卡片拼装和
    `_feishu_send_with_retry` 直接调用。
  - Dazah 确认卡片改为纯函数生成，保留中风险“始终允许”、高风险禁止永久
    授权的既有策略。
  - v2026.7.7.2 尚未提供公共 raw-card 发送接口，因此把唯一私有兼容点收敛到
    `_send_interactive_card`；若未来上游增加 `send_interactive_card`，兼容层
    优先自动使用公共接口。
  - 将当前必需的兼容方法纳入 upstream manifest，升级时结构变化会使构建和
    契约测试失败，而不是运行时静默退化。
- 关键文件：
  - `Hermes-Lite/services/dazah_feishu_gateway.py`
  - `Hermes-Lite/services/feishu_gateway_worker.py`
  - `Hermes-Lite/upstream-hermes.json`
  - `Hermes-Lite/tests/test_dazah_feishu_gateway.py`
  - `Hermes-Lite/tests/test_pinned_hermes_upstream.py`
- 验证命令：
  - `.venv\Scripts\python.exe -m py_compile services\dazah_feishu_gateway.py services\feishu_gateway_worker.py tests\test_dazah_feishu_gateway.py tests\test_pinned_hermes_upstream.py`
  - `.venv\Scripts\python.exe -m ruff check services\dazah_feishu_gateway.py services\feishu_gateway_worker.py tests\test_dazah_feishu_gateway.py tests\test_pinned_hermes_upstream.py`
  - `.venv\Scripts\python.exe -m pytest tests\test_dazah_feishu_gateway.py tests\test_pinned_hermes_upstream.py -q`
- 验证结果：编译通过，Ruff 通过，专项测试 `9 passed`；静态测试确认业务
  worker 已无 `_feishu_send_with_retry` 字符串。
- 回头验证：
  - Compatibility Layer 已建立，普通发送公共 API 和确认卡片兼容路径均有测试。
  - Phase 0 尚未完成：入站 envelope、附件/流式卡片、主动推送、完整容器和
    真实飞书应用验收仍待实现。
- 未执行项及原因：真实飞书应用验收依赖外部应用和测试账号；本切片不提前把
  mock 结果记作真实验收。
- migration/OpenAPI/环境变量/生成文件：均不涉及。
- 风险与回滚：上游当前缺少公共 raw-card 接口，仍保留一个受 manifest 和测试
  约束的私有兼容点；删除新增兼容层并恢复 worker 原实现可回滚。
- 下一工作单元：建立稳定入站 envelope，覆盖私聊、群聊、引用/Thread、附件和
  卡片回调，然后验证处理 Reaction 与原生回复链。

### 2026-07-30：Phase 0 入站 envelope 与主动投递闭环

- 阶段：Phase 0。
- 状态：进行中；入站契约、主动投递及本地回归初验通过。
- 实现：
  - `DazahInboundEnvelope` 固定 Hermes `MessageEvent` 到 Dazah 的入站边界，
    保留 open_id、union_id、发送者、私聊/群聊、Thread、父会话、引用消息、
    消息类型及缓存附件元数据。
  - Session 优先按 Thread 隔离，无 Thread 时按 chat 隔离，并继续按参与人隔离，
    与 `group_sessions_per_user` 目标一致。
  - upstream manifest 增加 `MessageEvent` 和 `SessionSource` 必需字段契约；
    构建期会同时验证方法与字段，防止升级后 Thread、身份或附件静默丢失。
  - 新增鉴权的 `/internal/feishu/deliveries` 投递 API 和状态查询 API。
  - 新增 SQLite `delivery_outbox`：idempotency key 唯一、原子认领、最多三次
    指数退避、最终状态、错误摘要和飞书 message_id 回执。
  - Gateway worker 在原生连接存活期间消费 outbox；文本走公开 `send`，卡片走
    已隔离的原生交互卡片通道。
  - Pytest 搜索路径固定为本项目 `tests/`，避免真实上游源码被误当成本项目
    测试收集。
  - `.dockerignore` 排除 `temp/`，真实上游验证目录不再进入镜像构建上下文。
- 关键文件：
  - `Hermes-Lite/services/dazah_feishu_gateway.py`
  - `Hermes-Lite/services/feishu_gateway_worker.py`
  - `Hermes-Lite/services/feishu_runtime.py`
  - `Hermes-Lite/services/dazah_agent_service.py`
  - `Hermes-Lite/upstream-hermes.json`
  - `Hermes-Lite/pyproject.toml`
  - `Hermes-Lite/.dockerignore`
- 验证命令与结果：
  - 真实运行 upstream installer：commit archive 下载、SHA-256、文件、方法和
    字段契约全部 `passed`。
  - `python -m ruff check <本次变更文件>`：通过。
  - `python -m pytest -q`：最终回归 `59 passed`，有 5 个既有框架弃用告警。
  - `docker build --target hermes-upstream ...`：通过，生成
    `dazah-hermes-upstream-verify:2026-07-30`。
  - 完整 `docker build`：未通过；连续两次为 Debian 软件源 HTTP 502，第三次
    为 Docker Hub manifest EOF。固定 Hermes stage 已成功，最终 lark-cli 和
    runtime stage 仍须在网络恢复后重跑。
- 回头验证：
  - 已确认 worker 使用稳定 envelope，且 worker 源码无私有发送函数直连。
  - 已确认主动文本/卡片具有幂等、重试和投递状态，但尚未完成真实飞书送达。
  - 已补充附件实际消费：只允许读取 `HERMES_HOME` 缓存和
    `HERMES_FEISHU_FILES_DIR` 内不超过 20 MiB 的文件；图片转换为视觉输入，
    文本类文档限长读取，其他媒体保留安全缓存引用，越界路径拒绝。
  - Phase 0 仍缺流式卡片、真实 Reaction/Thread/卡片回调及切换演练，因此
    阶段状态保持“进行中”。
- 未执行项及原因：
  - 真实飞书应用验收依赖外部应用与账号。
  - 完整容器构建被外部 Debian/Docker Hub 网络故障阻塞，本轮不标记通过。
- migration/OpenAPI/环境变量/生成文件：
  - 无后端 migration、无 Dazah Backend OpenAPI、无环境变量变化。
  - Hermes 本地 SQLite 启动时自动增加 `delivery_outbox` 表。
- 风险与回滚：
  - delivery outbox 与现有控制库同库，运行前应继续验证故障恢复和高并发认领。
  - 可关闭 `HERMES_FEISHU_GATEWAY_ENABLED` 停止消费；未投递记录保持可追踪。
- 下一工作单元：补齐附件安全消费、原生引用/Thread 回复和流式卡片测试，再做
  Gateway supervisor 健康/退出状态与 Phase 0 运行手册。

### 2026-07-30：Phase 0 运行态真实性与运行手册

- 阶段：Phase 0。
- 状态：进行中；运行态 provenance 和操作手册初验通过。
- 实现：
  - worker 连接原生 `FeishuAdapter` 成功后才输出 ready 握手，握手携带经构建
    验证的 release tag、release version 和完整 commit。
  - supervisor 不再以“子进程存活”等同“Gateway 已连接”；新增 `starting`、
    `connected`、`failed` 和 `inactive` 状态，45 秒无有效握手时终止并重启。
  - `/internal/feishu/status` 新增 `gateway_upstream`，可直接核对实际运行版本。
  - 新增 `docs/runbooks/hermes-native-feishu-gateway-phase0-runbook.md`，覆盖发布前
    检查、配置原则、状态验收、测试 App 十项验收、主动投递、单消费者切换、
    回滚、凭证轮换和证据保存。
- 验证命令：
  - `.venv\Scripts\python.exe -m py_compile services\feishu_gateway_worker.py services\dazah_agent_service.py tests\test_dazah_feishu_gateway.py`
  - `.venv\Scripts\python.exe -m ruff check services\feishu_gateway_worker.py services\dazah_agent_service.py tests\test_dazah_feishu_gateway.py`
  - `.venv\Scripts\python.exe -m pytest tests\test_dazah_feishu_gateway.py tests\test_feishu_runtime.py -q`
- 验证结果：编译、Ruff 均通过，专项 `23 passed`；最终全量回归
  `59 passed`。
- 回头验证：
  - 文档固定版本、manifest 固定版本、构建 stage provenance 和状态接口预期
    版本一致。
  - 尚不能确认生产运行状态，因为完整镜像未构建完成且没有真实测试 App 连接。
- 未执行项及原因：同上一工作单元的外部镜像仓库网络与测试应用依赖。
- migration/OpenAPI/环境变量/生成文件：均不涉及。
- 风险与回滚：readiness stdout 是 worker 与 supervisor 的窄 IPC 契约，异常
  或超时会失败关闭；回滚可恢复旧 supervisor，但会失去真实连接与版本证明。
- 下一工作单元：在外部依赖恢复后重跑完整镜像，按运行手册完成真实飞书十项
  验收和单消费者切换演练；通过前不进入 Phase 1。

### 2026-07-30 11:01：Phase 0 未完成项再次实施与回头验证

- 阶段：Phase 0。
- 状态：初验通过；代码、固定上游、完整镜像和无凭证运行态冒烟已通过。真实
  飞书测试应用、单消费者证明、生产切换与回滚演练仍待外部验收。
- 实现：
  - 新增 `lark-cli.json` 与固定安装器，锁定 lark-cli `1.0.76` 的下载来源、
    npm 元数据和二进制 SHA-256；Docker 不再运行 npm 包自带的二次下载脚本。
  - 普通 Agent 回复改用 `/v2/agent/runs/stream`；首个 delta 通过 Hermes 公开
    `send` 创建原生富文本消息，中间增量与最终结果通过公开 `edit_message`
    更新并以 `finalize=true` 收口。
  - Thread/引用上下文继续传入原生发送接口；编辑失败时回退为新的原生回复，
    无 delta 的直接结果交回 Hermes Base Gateway 发送，避免重复回复。
  - 增加严格 SSE 解析、错误返回、确认卡片随最终事件发送及卡片回调
    fail-closed 测试。
  - 增加错误点击人、重复点击、高风险禁止永久授权和过期确认测试。
  - 明确版本能力边界：v2026.7.7.2 支持公开消息创建/编辑，但没有公开
    raw-card/流式卡片接口；文档统一称为“流式富文本消息”，不虚报流式卡片。
- 关键文件：
  - `Hermes-Lite/lark-cli.json`
  - `Hermes-Lite/scripts/install_pinned_lark_cli.py`
  - `Hermes-Lite/Dockerfile`
  - `Hermes-Lite/services/dazah_feishu_gateway.py`
  - `Hermes-Lite/services/feishu_gateway_worker.py`
  - `Hermes-Lite/tests/test_pinned_lark_cli.py`
  - `Hermes-Lite/tests/test_dazah_feishu_gateway.py`
  - `Hermes-Lite/tests/test_feishu_runtime.py`
- 验证命令与结果：
  - 固定上游 Feishu 测试在最终 Linux 镜像中运行：
    `315 passed, 6 warnings in 18.60s`。
  - `.venv\Scripts\python.exe -m pytest -q`：
    `74 passed, 5 warnings in 1.12s`；告警均为既有 FastAPI/Starlette 弃用告警。
  - Gateway/确认专项测试：`34 passed, 5 warnings in 1.32s`。
  - 目标 Ruff、`compileall` 和 `git diff --check`：通过；仅有 Git 的
    LF/CRLF 工作区提示。
  - 全目录 `ruff check services tests` 仍有 1 个本轮之前已存在且未修改的
    `services/memory_service.py:35` 未使用 `shutil`；按“不修改无关代码”约束
    未顺手修复，Phase 0 变更文件 Ruff 全部通过。
  - 使用 `.ci/test-impact-policy.toml` 对当前工作树 21 个变更路径执行同一
    `evaluate` 规则：通过。标准 `--base/--head` 命令只能检查已提交对象，
    当前按要求未执行 git add/commit，故不能覆盖本轮未提交变更。
  - `docker build --progress=plain -t dazah-hermes-phase0-verify:2026-07-30 .`：
    通过；镜像 digest
    `sha256:065ccb4c8b9a2aad83d196902781b8c97f80131ad63bbb793065cc78bcab9ef7`。
  - 镜像内验证：运行用户 `hermes`/UID 1000；lark-cli `1.0.76`；Hermes
    release `v2026.7.7.2`、version `0.18.2`、commit
    `9de9c25f620ff7f1ce0fd5457d596052d5159596`，全部 provenance 检查通过。
  - 无真实凭证启动冒烟：`/health` 返回 `ok`，Gateway 按预期为
    `configured=false`、`inactive`，临时容器已停止并移除。
  - 静态搜索确认 worker 无 `_feishu_send_with_retry`；唯一生产调用位于
    Compatibility Layer，manifest 和测试分别固定其存在与行为。
- 回头验证结论：
  - Phase 0 本地功能、测试、构建、版本一致性和无凭证运行路径全部完成。
  - 固定上游测试已覆盖私聊、群聊 @ 门禁、Thread/引用、Reaction、媒体、
    富文本、卡片及审批按钮；Dazah 测试覆盖 envelope、流式编辑、确认和 outbox。
  - 不能把上述自动化证据替代真实飞书 App 验收，因此 Phase 0 只标记
    “初验通过”，不标记“已完成并回验”。
- 未执行项及原因：
  - 未向现有已连接 App 或未知 chat 发送测试消息，避免影响真实用户。
  - 缺少明确指定的飞书测试 App/测试群及安全注入的凭证，无法执行运行手册
    十项真实验收。
  - 未获生产切换授权，无法证明唯一事件消费者、关闭旧消费者、执行灰度和
    回滚演练。
- migration/OpenAPI/环境变量/生成文件：
  - 不涉及 Dazah Backend migration、OpenAPI 或前端生成类型。
  - 未新增运行环境变量；新增两个可机读供应链 manifest 和两个安装器。
- 风险与回滚：
  - raw-card 仍有一个上游私有兼容点；升级时 manifest/契约测试失败关闭。
  - 流式编辑已通过契约测试，真实飞书的速率限制和最终视觉效果仍需测试 App
    验收。
  - 回滚开关、步骤和 outbox 保留策略已写入运行手册，尚未做生产演练。
- 下一工作单元：由用户指定测试飞书 App 与测试会话，并明确旧消费者/生产
  切换范围后，按运行手册完成十项真实验收、单消费者证明和回滚演练。

### 2026-07-30 11:34：真实 Base 读取失败修复

- 阶段：Phase 0。
- 状态：修复完成并回验；真实飞书 Base 的 bot 身份解析、数据表列表和字段列表
  已通过。Phase 0 其余真实消息/卡片十项验收状态不变。
- 根因：
  - lark-cli `1.0.76` 检测到 Hermes 上下文后要求显式 workspace binding；
    旧流程只有 `config init` 和 strict-mode，导致 `not_configured:
    hermes context detected but lark-cli is not bound to it`。
  - `lark-base` Skill 是通用 user-first 指引，与本项目 bot-only 策略冲突，
    模型选择 `--as user` 后得到“用户身份未激活”，再错误降级到能源数据源。
  - 首次部署最终只读镜像时，上游单消费者锁默认写入
    `/home/hermes/.local/state`，触发只读文件系统错误，Gateway 无法 ready。
- 实现：
  - `stage_credentials()` 在候选目录依次执行 init、Hermes bot-only bind、
    strict-mode 和 doctor，全部成功才原子替换 active 配置。
  - bind 所需临时 Hermes `.env` 仅写入私有 tmpfs、权限 `0600`，异常和成功
    路径均删除；错误同时清洗 stdout/stderr 中的 Secret。
  - 绑定失败保留旧 active 配置和旧加密凭证。
  - Agent Prompt 强制资源命令显式使用 `--as bot`；工具参数边界拒绝
    `--as user`，不允许再次退回用户 OAuth 身份。
  - `HERMES_GATEWAY_LOCK_DIR` 固定到
    `/run/hermes-feishu/gateway-locks`，兼容只读根文件系统。
- 验证结果：
  - Hermes-Lite 全量测试：`78 passed, 5 warnings`；告警为既有框架弃用告警。
  - 目标 Ruff、编译检查：通过。
  - 真实凭证隔离 stage：`identity=bot`、`bot_status=ready`、Base URL 解析成功。
  - 最终镜像构建通过，digest
    `sha256:12b77ec60dac557a5377545937cf5b3634a0082ec2208763ee403467375ddd9c`。
  - 在线容器已切换到最终镜像，用户 `hermes`，health 为 healthy；
    Gateway `connected`，reconnects `1`，上游为
    `v2026.7.7.2 / 0.18.2 / 9de9c25f620ff7f1ce0fd5457d596052d5159596`。
  - 对用户截图中的 Base 执行只读验收：URL 解析成功，读取到 17 张数据表，
    首张表读取到 10 个字段；未读取/输出记录正文，未执行写操作。
- migration/OpenAPI/环境变量/生成文件：
  - 无 migration、OpenAPI 或前端生成类型变化。
  - 新增 `HERMES_GATEWAY_LOCK_DIR`，已同步 Dockerfile、生产/开发 Compose、
    `.env.example` 和本地 `.env`。
- 遗留项：
  - 需要用户在飞书重新发送同一请求，验证完整“消息 → Agent → lark_cli →
    原生富文本回复”体验；底层 Base 访问链已经通过。
  - 真实确认卡片、媒体、主动推送、失败重试和切换/回滚演练仍按运行手册执行。

### 2026-07-30 11:36：飞书消息 LLM 代理连接失败修复

- 阶段：Phase 0 真实环境回归。
- 状态：修复完成并完成服务侧回验；等待用户从飞书重新发送消息完成入口侧验收。
- 现象：飞书回复 `Dazah LLM 代理不可达: ConnectError: All connection
  attempts failed`。
- 根因：Hermes 容器实际注入的 `DAZAH_API_BASE_URL` 与
  `DAZAH_LLM_BASE_URL` 使用 `127.0.0.1:8000`，容器 loopback 指向 Hermes
  自身而非 Dazah 后端；Hermes 与后端实际已处于同一 Docker 网络。
- 实现：
  - 本地部署配置改为通过 Docker 服务名 `app:8000` 访问后端。
  - `.env.example` 同步容器部署安全默认值。
  - 增加配置回归断言，并在运行手册记录容器地址约束。
- 部署：
  - 明确固定 `HERMES_IMAGE=dazah-hermes-phase0-verify:2026-07-30` 与原凭证
    卷 `hermes-lite_hermes_data`，避免 Compose 默认值导致镜像或数据卷漂移。
  - 在线容器使用修复后的 `app:8000` 地址，健康检查为 healthy。
  - 原凭证卷未删除、未改写；Gateway 恢复为 `configured=true`、
    `connected`，reconnects 为 `1`。
- 验证结果：
  - 从 Hermes 容器访问 `http://app:8000/health` 返回 200。
  - 从 Hermes 容器携服务令牌访问 LLM 代理 `/models` 返回 200，并发现 1 个
    可用代理模型；未输出服务令牌或供应商密钥。
  - 通过 Hermes `/v2/agent/runs` 发起不含业务数据的最小真实调用：HTTP 200、回复
    非空、无待确认项，证明代理模型调用可完成。
  - Hermes-Lite 全量测试：`78 passed, 5 warnings`；目标 Ruff 通过。
  - 重建后日志未再出现 `ConnectError`、连接尝试失败或 Gateway failed。
- migration/OpenAPI/环境变量/生成文件：
  - 不涉及 migration、OpenAPI 或前端生成类型。
  - 未新增变量；修正两个既有变量的容器部署值。
- 遗留项：
  - 服务侧完整调用链已通过；需要用户在真实飞书中重新发送原请求，完成
    “飞书入站 → Gateway → Hermes → LLM 代理 → 飞书回复”的最终入口验收。

### 2026-07-30 15:32：Base 记录读取与连续对话路由修复

- 阶段：Phase 0 真实环境回归。
- 状态：代码修复与本地全量回验完成；等待重建 Hermes 镜像后的真实 Base
  记录读取验收。
- 根因：
  - Hermes 原生 Feishu Adapter 只提供消息、附件和卡片通道，不会自动把全部
    飞书资源 API 注册为 Agent 工具；资源 API 由固定的官方 `lark_cli` 提供。
  - `lark_cli 1.0.76` 已包含 `base +record-list`、`base +record-search` 和
    `base +record-get`，但 Agent 工具 Schema 与强制路由提示只明确到数据表和
    字段，未明确记录读取 SOP。
  - Feishu Gateway 构造 AgentBackend V2 请求时把 `messages` 固定为空；用户
    下一轮只回复“进料数据记录表”时，强制路由无法看到上一轮 Base URL 和
    table_id，模型错误降级到需要 `subject` 的 `dazah_tool`。
- 实现：
  - Gateway 增加每会话最多 20 条、最多 256 个会话的进程内有界历史，并把它
    写入 V2 `messages`；同时利用飞书 reply-to 正文恢复冷启动后的最小上下文。
  - 表名或 `tbl...` 短回复在最近存在 Base URL/数据表列表时继续强制走
    `lark_cli`，无 Base 上下文的普通“某某表”不强制改道。
  - 工具 Schema 和系统提示明确 `+record-list`、`+record-search`、
    `+record-get` 参数与 bot-only 身份，并明确 `subject` 只属于 Dazah
    内部鉴权，不是飞书 CLI 参数。
- 验证结果：
  - Hermes-Lite 定向测试：`53 passed, 5 warnings`。
  - 目标 Ruff 与 Python 编译检查：通过。
- migration/OpenAPI/环境变量/生成文件：
  - 不涉及 migration、OpenAPI、环境变量或生成文件。
- 遗留项：
  - 尚未重建/部署镜像，也未使用真实 Base 读取记录正文；部署后应按运行手册
    依次验证 `+record-list`、`+record-search` 和飞书内连续两轮表名选择。

### 2026-07-30 16:14：飞书旧消息间歇性重复回复修复

- 阶段：Phase 0 真实环境回归。
- 状态：代码修复、全量回验和 Hermes 容器部署完成；等待真实飞书重复消息验收。
- 根因与证据：
  - 固定上游 Hermes Adapter 已按 `message_id` 提供 24 小时持久去重，运行容器
    的去重文件也在持续更新，因此不能只把现象归因于飞书重投。
  - Dazah 流式消费在首个回复气泡已经创建后，若最后一次
    `edit_message(finalize=True)` 短暂失败，会再次 `send` 完整答案；这会形成
    延迟出现的第二个回复气泡。
  - Dazah Worker 自身没有独立的入站原子收据，无法在上游状态异常、子进程
    重启或多个实例误重叠时提供第二层幂等保护。
- 实现：
  - 最终编辑最多重试 3 次；首气泡已经成功创建后，即使最终编辑仍失败，也不再
    创建第二个完整答案气泡。
  - 控制库新增 `inbound_message_receipts`，在身份解析和 Agent run 之前原子
    认领 `message_id`；完成收据保留 7 天，处理中租约 1 小时以允许崩溃恢复。
  - 增加收据原子性、持久完成、租约恢复、过期清理和最终编辑失败不重复发送测试。
- 验证结果：
  - Hermes-Lite 全量测试：`82 passed, 5 warnings`。
  - 目标 Ruff、Python 编译和差异空白检查：通过。
  - 镜像 `dazah-hermes-phase0-verify:2026-07-30-dedup` 构建成功并使用原
    `hermes-lite_hermes_data` 数据卷重建；容器 healthy、无重启，
    Gateway 为 `connected`，控制库新表已创建。
  - 保持 Worker stderr 隔离；重建后容器日志未出现飞书 WebSocket 临时连接
    参数，避免 SDK 原始日志泄露凭证。
- migration/OpenAPI/环境变量/生成文件：
  - SQLite 控制库使用 `CREATE TABLE IF NOT EXISTS` 自初始化，不涉及 Alembic
    migration、OpenAPI、环境变量或生成文件。
- 遗留项：
  - 未主动向真实会话发送消息；需要用户在飞书验证同一消息只产生一个 Agent run
    和一个回复气泡。

## 13. 实时更新模板

```markdown
### YYYY-MM-DD HH:mm：<工作单元>

- 阶段：
- 状态：进行中 / 阻塞 / 初验通过 / 已完成并回验
- 实现：
- 关键文件：
- 验证命令：
- 验证结果：
- 未执行项及原因：
- migration/OpenAPI/环境变量/生成文件：
- 风险与回滚：
- 下一工作单元：
```
