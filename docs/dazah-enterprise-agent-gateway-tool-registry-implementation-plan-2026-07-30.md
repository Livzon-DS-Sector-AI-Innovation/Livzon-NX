# Dazah 企业级 Agent Gateway 与 Tool Registry 平台化实施方案

> 版本：1.0  
> 日期：2026-07-30  
> 实施账本：`docs/tasks/dazah-enterprise-agent-gateway-tool-registry-tasks-2026-07-30.md`

## 1. 文档目的

本文定义 Dazah 从现有“业务系统 + Livzon 助手”演进为企业级 Agent
Platform 的完整实施方案。方案覆盖 Hermes 上游固定、飞书原生 Gateway、
AgentBackend V2、身份绑定、双域权限、统一风险策略、Tool Registry 自动发现、
能力目录、Trace 审计、配置控制面、主动推送和业务模块接入。

本文是本轮平台化改造的权威实施入口。以下既有文档继续作为历史设计、已实现
能力和专项运行经验的事实来源，但若与本文的平台化目标冲突，以本文为准：

- `docs/Livzon助手基于Hermes设计飞书原生操作方案.md`
- `docs/Livzon助手飞书原生直连实施与问题修复总结-2026-07-24.md`
- `docs/livzon-feishu-bidirectional-chat-plan-2026-07-10.md`
- `docs/livzon-conversational-operation-center-spec-2026-07-10.md`

## 2. 目标与完成效果

完成后形成以下稳定链路：

```text
飞书
  ↓
Hermes v2026.7.7.2 原生 Feishu Gateway
  ↓
Dazah Compatibility Layer
  ↓
AgentBackend V2
  ↓
Hermes Agent Runtime
  ↓
Dazah Tool Discovery / Tool Gateway
  ↓
Identity Binding → Policy Engine → Tool Executor → Business Service
  ↓
Confirmation / Audit / Trace / Domain Events
```

最终应达到：

1. Hermes 上游按发布 Tag、Commit 和 SHA-256 固定，不跟随 `main`。
2. 飞书消息、Thread、Reaction、媒体、流式富文本消息、确认卡片、卡片回调和
   主动推送统一使用 Hermes 原生 Feishu Gateway。
3. Dazah 业务权限、风险判断、确认事实、工具执行和审计仍由 Dazah 后端负责。
4. 飞书身份能可靠映射为 Dazah 本地责任主体，且支持租户隔离和绑定生命周期。
5. 业务模块声明 `@agent_tool` 后可被自动发现，无需再手工修改 Hermes 工具列表。
6. 模型通过 `search → describe → execute` 渐进获取能力，不接收全量工具枚举。
7. 一次请求可以通过统一 Trace 关联飞书消息、Agent Run、Tool Call、确认项、
   审计和业务事件。
8. 每个阶段必须通过功能、测试、回归和回头验证后才能标记为完成。

## 3. 范围与非目标

### 3.1 本次范围

- `Hermes-Lite/` 上游版本治理、原生 Feishu Gateway 和 Dazah 兼容层。
- `dazah-backend/app/platform/identity/` 身份绑定和权限快照。
- `dazah-backend/app/modules/agent/` 协议、注册、发现、策略、执行、确认和审计。
- `dazah-frontend/` 中必要的 Agent 流式事件、确认和治理界面。
- 已有业务模块 Agent 工具迁移，以及其余模块的分批接入规范。
- OpenAPI、生成类型、测试、部署、灰度、回滚和运行观测。

### 3.2 非目标

- 不把 Dazah 模块化单体拆成微服务。
- 不允许 Hermes 直接访问 Dazah 数据库。
- 不允许模型自由调用 URL、SQL、Shell 或内部业务 API。
- 不把数据库中的字符串 `handler` 作为动态 Python 代码执行来源。
- 不把飞书 Scope 与 Dazah RBAC 合并成一张权限表。
- 不在第一阶段为约 150 个工具提前引入不必要的分布式基础设施。
- 不让 Agent 代替责任人进行审批、驳回、放行、处分或权限变更。

## 4. 当前基线

### 4.1 已有能力

- `Hermes-Lite/Dockerfile` 已固定
  `NousResearch/hermes-agent@v2026.7.7.2`，并校验下载包 SHA-256。
- Hermes worker 已实例化上游 `plugins/platforms/feishu/adapter.py`。
- Hermes 已具备凭证加密、HMAC 配置推送、版本切换、权限快照、本地确认和
  审计 outbox。
- 后端已有 `@agent_tool`、`AgentToolSpec`、`ToolRegistry` 和 `ToolExecutor`。
- 工具元数据已有版本、权限键、数据范围、敏感度、幂等、dry-run、超时、
  输出 Schema、事件和废弃替代信息。
- 后端已有工具发现和执行 API、写操作确认、人工决策拒绝、访问范围快照和
  审计。
- 前端和 Hermes 已有 SSE 流式回复和确认展示基础。
- 后端已有 correlation ID、ToolCall、AuditLog、自动化运行事件和领域事件。

### 4.2 主要缺口

1. 当前 Hermes worker 只复用了原生 Adapter，确认卡片仍由本地代码生成，并
   调用上游私有发送方法，尚未形成完整原生 Gateway 体验链。
2. 后端通过 `tool_registration.py` 手工 import 各模块工具。
3. Hermes 曾维护静态 operation 枚举，导致后端与 Hermes 工具列表漂移；
   本次实施已删除该机制。
4. 飞书 Gateway 放入上下文的发送者标识不一定是 Dazah UUID，而 ToolExecutor
   只按 UUID 解析 `context.user_id`。
5. 当前流式协议主要包含 start、delta、done、error、ping，缺少标准化
   tool_call、tool_result、confirmation 和 finished 事件。
6. 工具 Registry 只存在于进程内，没有治理投影、生命周期状态和目录查询。
7. 飞书资源操作与 Dazah 业务工具各有策略实现，但没有统一 Policy Decision
   契约。
8. 审计已脱敏和截断，但“是否允许保存业务正文”尚未按敏感等级明确。
9. 15 个业务模块中只有质量、采购、能源和仓储提供正式 `agent_tools.py`。

## 5. 架构边界

### 5.1 Hermes 原生 Feishu Gateway

负责：

- WebSocket/Webhook 连接、重连和健康状态。
- 私聊、群聊、`@Livzon`、消息去重和会话串行。
- Thread、引用回复、Reaction、正在处理状态和失败回退。
- 文本、富文本、图片、音频、视频、文件和卡片收发。
- 原生富文本消息流式创建/编辑、确认卡片、按钮事件、点击人校验和重复点击
  防护。固定上游当前没有公开的流式卡片 API，不把消息编辑伪装为流式卡片。
- Livzon Agent 主动消息和卡片的投递队列、重试和投递回执。

不负责：

- Dazah 业务权限最终判断。
- Dazah 业务写操作执行。
- Dazah confirmation 状态事实。
- 业务模块配置和业务数据存储。

### 5.2 Compatibility Layer

作为唯一 Dazah 定制边界：

- 将 Hermes Gateway 入站事件转换为 AgentBackend V2 Input Envelope。
- 将 AgentBackend V2 事件转换为 Gateway 原生回复、卡片和状态更新。
- 将飞书卡片点击转换为确认执行、取消或授权撤销请求。
- 隔离上游字段、类名、回调签名和生命周期变化。
- lark-cli 候选凭证必须显式绑定 Hermes `bot-only` workspace；模型和工具边界
  均禁止 `--as user`，飞书原生资源统一以机器人应用身份访问。
- 业务 worker 禁止直接调用上游以下划线开头的私有方法；确无公开扩展点时，
  只允许在本地窄兼容接口内保留单一调用，并通过 manifest 与契约测试固定
  行为，待上游提供公共能力后删除。

### 5.3 Hermes Agent Runtime

负责意图理解、能力搜索、Schema 获取、参数组织、工具调用和回答生成。不得
承载业务规则、业务数据库访问、权限最终裁决或确认后的业务写入。

### 5.4 Dazah Agent Runtime

负责：

- 可信身份解析。
- 工具发现和描述。
- 权限、数据范围、风险和上下文策略。
- 参数校验、确认、执行、事务和审计。
- 工具生命周期、版本兼容和自动化能力影响分析。

### 5.5 业务模块

业务规则继续位于模块 Service。`agent_tools.py` 只提供 Pydantic InputSchema、
能力元数据和薄 handler，不直接访问其他模块 repository 或绕过业务 Service。

## 6. Hermes 上游固定与供应链治理

### 6.1 固定版本

目标基线：

- Repository：`NousResearch/hermes-agent`
- Release Tag：`v2026.7.7.2`
- Release Version：`0.18.2`
- Release Commit：`9de9c25`
- Archive SHA-256：以 `Hermes-Lite/upstream-hermes.json` 的已审查值为准

构建必须：

1. 使用固定 Tag，不使用 branch 或 `main`。
2. 校验下载归档 SHA-256。
3. 校验预期上游文件和版本标识存在。
4. 在镜像中保存只读的上游 provenance JSON，包括 repository、tag、commit、
   archive hash 和构建时间。
5. CI 执行上游结构契约测试；目录或公开扩展点变化时失败关闭。
6. 上游源码保持原样，Dazah 补丁仅进入 Compatibility Layer。
7. lark-cli 通过独立 manifest 固定版本、下载主机和二进制 SHA-256；构建不得
   依赖 npm 安装脚本中的未固定二次下载。

### 6.2 升级流程

后续升级必须单独变更：

1. 阅读目标 Release 和 Gateway 变更。
2. 更新 Tag、Commit、SHA-256 和 provenance。
3. 运行 Gateway 契约、飞书模拟、Hermes 全量测试和容器构建。
4. 在测试应用完成私聊、群聊、媒体、流式富文本消息、确认卡片和主动推送
   验收。
5. 灰度后再切换生产应用。

## 7. AgentBackend V2 协议

### 7.1 输入 Envelope

```json
{
  "protocol_version": "2.0",
  "trace_id": "uuid",
  "tenant_id": "tenant-key",
  "session_id": "stable-session-id",
  "channel": "feishu|web",
  "sender": {
    "subject_type": "user",
    "external_id_type": "open_id|user_id|local_user_id",
    "external_id": "opaque-id",
    "local_user_id": "uuid-or-null"
  },
  "message": {
    "id": "channel-message-id",
    "text": "user text",
    "thread_id": "thread-id-or-null"
  },
  "attachments": [],
  "context": {}
}
```

要求：

- `trace_id` 在入口生成，后续不得替换。
- `tenant_id`、`local_user_id` 只能由可信服务写入，模型参数不得覆盖。
- `message.id` 用于渠道去重，不作为业务幂等键。
- 附件只传受控引用和元数据，不传任意本地路径。
- V1 在一个发布周期内通过适配器兼容，核心 Runtime 只消费 V2。

### 7.2 输出事件

统一事件：

- `accepted`：请求已接收。
- `thinking`：可展示的非敏感进度摘要。
- `capability_search`：能力搜索状态和候选数量，不暴露越权能力。
- `tool_call`：即将调用的 operation、call_id 和安全摘要。
- `tool_result`：成功、失败、耗时和结果摘要。
- `text_delta`：回复文本增量。
- `confirmation`：Dazah 或飞书原生确认描述。
- `delivery`：渠道投递和卡片更新状态。
- `error`：稳定错误码和用户可读信息。
- `finished`：最终消息、确认列表、trace_id 和结束状态。
- `ping`：流式连接保活。

所有事件包含：

```json
{
  "protocol_version": "2.0",
  "event_id": "uuid",
  "event": "tool_call",
  "trace_id": "uuid",
  "run_id": "uuid",
  "sequence": 3,
  "occurred_at": "RFC3339",
  "data": {}
}
```

同一 Run 的 `sequence` 必须单调递增。消费者根据 `event_id` 幂等处理。

## 8. Identity Binding

### 8.1 数据模型

新增显式绑定事实，而不是继续只依赖 User 表中的飞书字段：

```text
identity.external_identity_bindings
  id
  tenant_id
  provider                 # feishu
  app_id_fingerprint
  external_id_type         # open_id/user_id/union_id
  external_id
  local_user_id
  status                   # active/suspended/revoked
  source                   # directory_sync/oauth/admin
  verified_at
  last_seen_at
  created_at/updated_at
```

约束：

- `(tenant_id, provider, app_id_fingerprint, external_id_type, external_id)` 唯一。
- 一个 active 外部身份只能映射一个 active 本地用户。
- 不保存 App Secret、Token 或明文敏感凭据。
- `User.feishu_*` 在迁移期保留为兼容字段，绑定表稳定后降级为派生缓存。

### 8.2 可信解析流程

1. Gateway 验证飞书事件和应用来源。
2. Compatibility Layer 调用服务认证的身份解析接口。
3. 后端返回 local_user_id、tenant_id、grant_version 和最小范围摘要。
4. Hermes 只传递签名或服务通道内的可信上下文。
5. ToolExecutor 忽略模型提供的 user_id，并使用可信主体。
6. 绑定缺失、停用、租户不匹配或权限快照过期时失败关闭。

## 9. 双域权限与 Policy Engine

### 9.1 权限域

飞书资源域由以下事实共同决定：

- 飞书应用 Scope。
- 应用可见范围。
- 目标资源对机器人的授权。
- Dazah 推送的用户模块和飞书工作区授权快照。

Dazah 业务域由以下事实决定：

- Dazah 用户状态和角色。
- `UserModuleGrant`。
- 工具 `permission_key`。
- 工具和模块数据范围。
- 业务 Service 自身状态和并发规则。

两个权限域不共用事实表，但统一返回 Policy Decision。

### 9.2 Policy Decision

```json
{
  "decision": "ALLOW|DENY|CONFIRM",
  "policy_version": "string",
  "risk_level": "low|medium|high|prohibited",
  "reason_code": "stable-code",
  "user_message": "safe message",
  "confirmation_profile": "none|once|rememberable|strong",
  "audit_tags": [],
  "expires_at": null
}
```

判断输入至少包括主体、租户、渠道、工具、资源、写入性质、敏感度、影响数量、
权限快照版本、会话和业务上下文。

规则：

- 查询默认允许，但仍校验权限和数据范围。
- Dazah 业务写操作继续由后端生成 confirmation。
- 修改和中风险操作要求确认。
- 删除、覆盖、移动、权限、共享和大批量写入要求强确认。
- 审批、驳回、放行、处分和权限修改为 prohibited。
- LLM 只能上调风险，不能降低固定规则结果。
- Policy Engine 不代替业务 Service 的状态校验。

## 10. Tool Registry 自动发现

### 10.1 权威来源

Python 代码和 `@agent_tool` 是可执行能力的唯一权威来源。数据库目录是代码
Registry 的治理投影，不保存可动态 import 的 handler 字符串。

### 10.2 自动发现

启动时：

1. 从 `app.shared.module_registry` 获取已登记模块。
2. 对存在的 `<module>.agent_tools` 使用明确模块名导入。
3. 导入平台级 identity 和 agent 内建工具。
4. 拒绝重复工具名、非法模块、非法版本和不完整策略。
5. 生成稳定 `registry_version`。
6. 将公开元数据同步为 Catalog Projection。
7. 运行启动完整性检查；发现危险不一致时失败启动。

禁止递归扫描任意 Python 文件或执行数据库提供的模块路径。

### 10.3 Catalog Projection

建议数据表：

```text
core.agent_tool_catalog
  id
  tool_name
  module
  summary
  input_schema
  output_schema
  permission_key
  risk_level
  sensitivity
  capability_version
  code_fingerprint
  lifecycle_status          # active/deprecated/disabled
  discovered_at
  last_seen_at
```

说明：

- `draft/testing` 属于开发和发布流程，不应让生产运行时从数据库加载未部署代码。
- `disabled` 可以作为控制面紧急停用，但不能启用代码中不存在的工具。
- 每次启动对账；代码已移除的工具标记为 missing/deprecated，不静默保留执行。

### 10.4 渐进披露 API

- `POST /api/v1/agent/tools/search`
  - 输入自然语言、模块、读写、风险和 limit。
  - 只返回当前主体有权查看的候选摘要。
- `GET /api/v1/agent/tools/{operation}`
  - 返回单个能力完整 Schema、策略和版本。
- `POST /api/v1/agent/tools/execute`
  - 保持统一执行入口。

Hermes 对模型只暴露稳定的：

- `dazah_tool.search`
- `dazah_tool.describe`
- `dazah_tool.execute`

Hermes 运行时不保留静态 operation 枚举或离线兜底目录；后端目录是唯一
事实源，离线快照只允许用于测试和诊断。
缓存初期使用进程内 ETag/registry_version；出现多实例一致性需求后再引入 Redis。

## 11. 确认与飞书原生卡片

### 11.1 Dazah 业务确认

1. ToolExecutor 返回 CONFIRM 并持久化 `AgentConfirmation`。
2. AgentBackend V2 发送 `confirmation` 事件。
3. Compatibility Layer 使用原生 Gateway 渲染飞书卡片。
4. 卡片只携带 opaque confirmation ID、动作和签名上下文。
5. 点击后调用 Dazah confirmation execute/cancel。
6. 后端重新验证用户、权限、状态、到期、参数和资源版本。
7. Gateway 原位更新卡片状态。

Hermes 不得因为用户点击卡片而绕过 Dazah 直接执行业务工具。

### 11.2 飞书原生资源确认

飞书文档、Drive、Wiki、Sheets、Base、Slides 等通过 Hermes 原生 Gateway/CLI
执行时，可以使用 Hermes 原生审批体验。其策略版本、审计摘要和资源变化通知
必须同步至 Dazah。

### 11.3 卡片状态

至少支持：

- pending
- executing
- succeeded
- partially_succeeded
- failed
- denied
- expired
- superseded

重复点击和非原责任人点击不得触发二次执行。

## 12. Trace、审计和隐私

### 12.1 关联链

```text
Feishu message_id
  → trace_id
  → agent_run_id
  → tool_call_id
  → confirmation_id
  → audit_id
  → domain_event correlation_id
  → delivery_id
```

所有服务日志使用结构化标识，不记录完整消息正文、凭证或大对象。

### 12.2 审计保存策略

按敏感等级：

- public/internal：允许保存经过字段白名单和截断的业务摘要。
- sensitive：只保存字段名、数量、资源指纹和结果摘要。
- restricted：只保存操作、主体、策略、资源哈希、结果和错误码。

Secret、Token、Password、Key、Cookie 和完整授权响应永不进入日志、审计或
Agent 上下文。

## 13. 配置控制面

Dazah Control Plane 是唯一配置源：

- 飞书应用设置在 Dazah 管理后台维护。
- 凭证以版本化 HMAC 请求推送到 Hermes。
- Hermes 加密保存并在 tmpfs 初始化运行配置。
- 新配置探测成功后原子切换，失败保留旧版本。
- 权限快照由 Dazah 主动推送，Hermes 定时拉取作为补偿。
- 读取快照允许最长 24 小时降级；写入要求不超过 15 分钟。
- 配置和权限版本必须单调递增，回退走显式新版本。

## 14. 主动推送

Livzon Agent 产生的飞书主动消息和卡片统一进入 Hermes Gateway Delivery API，
而不是由 Agent 代码直接调用飞书 Open API。

Delivery API 需要：

- 服务鉴权。
- 接收人和会话解析。
- 幂等键。
- 文本、富文本、卡片和卡片更新。
- `reply_to`、thread 和业务按钮。
- 持久队列、有界重试和投递回执。
- delivery_id 与 trace_id。

Dazah 业务模块原有非 Agent 飞书集成不在首轮强制迁移范围；只有 Livzon Agent
产生的回复、确认和主动推送必须统一走 Hermes 原生 Gateway。

## 15. 前端治理与用户体验

前端需要：

- 消费 AgentBackend V2 事件并展示工具进度。
- 展示工具调用、确认、局部失败和最终结果。
- 维护兼容 V1 的发布期适配。
- 管理员查看工具目录、版本、状态、策略和最近发现时间。
- 管理员只能禁用已部署工具，不能从数据库创建可执行 handler。
- 查看 Trace 时按权限和敏感度裁剪载荷。
- 飞书设置页显示 Gateway 版本、连接、配置版本、权限快照、队列和最近错误。

## 16. 分阶段实施

### Phase 0：上游固定与原生 Feishu Gateway

范围：

- 固化 provenance 和上游结构契约。
- 将 Gateway 生命周期、消息、流式回复、确认卡片、卡片回调和主动推送迁移到
  Hermes 原生 Gateway 公共扩展点。
- 移除 Dazah worker 对上游私有发送方法的依赖。
- 建立 Compatibility Layer 骨架。
- 旁路测试、灰度、旧消费者停用和回滚开关。

验收：

- 构建可证明使用固定上游。
- 私聊、白名单群、必须 @、Thread、附件、Reaction、流式富文本消息、确认
  卡片、重复点击、重连、去重和主动推送全部通过。
- 同一个飞书应用只有一个生产事件消费者。
- Hermes 全量测试和镜像构建通过。

### Phase 1：Identity Binding 与可信主体

范围：

- 新增绑定模型、migration、repository、service 和内部解析 API。
- 迁移现有 User 飞书字段。
- Gateway 入站获得可信 local_user_id 和 tenant_id。
- ToolExecutor 使用可信主体，忽略不可信模型上下文身份。

验收：

- open_id、user_id、union_id 在租户和应用维度正确映射。
- 未绑定、停用、撤销、跨租户和伪造 user_id 全部失败关闭。
- Web 和飞书入口对同一用户得到一致的模块工具范围。
- migration upgrade/downgrade 和身份安全测试通过。

### Phase 2：AgentBackend V2 与原生确认闭环

范围：

- V2 Schema、版本协商、兼容层和事件序列。
- Hermes 和后端流式链改用统一事件。
- 前端消费 V2。
- Dazah confirmation 通过原生 Gateway 卡片展示和回写。

验收：

- 事件顺序、断线、重连、重复事件和最终状态可验证。
- tool_call/tool_result/confirmation/finished 可在 Web 和飞书正确呈现。
- 确认执行前重新鉴权；重复点击不重复写入。
- V1 兼容测试、后端接口测试、Hermes 测试和前端 E2E 通过。

### Phase 3：Tool Registry 自动发现与渐进披露

范围：

- 替换手工工具 import。
- Catalog Projection 和 lifecycle。
- search/describe/execute API。
- Hermes 动态目录、ETag 和离线兜底。
- Registry/Hermes 契约测试。

验收：

- 新增测试工具模块后无需修改 Hermes 即可被授权用户发现和执行。
- 未授权用户不能通过 search/describe 推断工具或 Schema。
- 重复名、非法元数据、版本冲突和缺失工具失败关闭。
- Hermes 静态手写白名单不再是正常运行依赖。

### Phase 4：统一 Policy、Trace、审计与治理

范围：

- 统一 Policy Decision。
- 双域适配、风险规则和策略版本。
- 完整 Trace 关联和敏感度审计。
- 工具目录和 Trace 管理界面。
- 运行指标、告警和应急禁用。

验收：

- ALLOW/DENY/CONFIRM 在 Web、飞书和自动化路径一致。
- 人工责任判断无法通过直接调用、工作流或卡片绕过。
- 任意抽样请求可以从 message_id 查到完整链路。
- restricted 工具审计不包含业务正文。
- 后端、Hermes、前端和安全回归通过。

### Phase 5：模块接入、主动推送与最终发布

范围：

- 迁移质量、采购、能源、仓储现有工具。
- 按优先级接入生产、设备、安全、研发、注册、人事等模块。
- Livzon Agent 主动推送统一走 Gateway Delivery API。
- 完成容量、故障、灰度、回滚和运行手册。

验收：

- 所有计划内模块都有工具清单、权限、风险、Schema、测试和负责人。
- 查询、写入确认、禁止决策和主动推送代表性场景通过。
- 无手工 Hermes operation 同步步骤。
- 全量 CI、容器、迁移、OpenAPI、前端生成类型和关键 E2E 通过。
- 生产灰度观察期无重复消费、越权、重复写入或不可追踪失败。

## 17. 阶段回头验证

每个阶段完成实现和初次测试后，必须执行独立的回头验证：

1. 回读本文对应阶段的全部范围和验收项。
2. 回读任务账本中未完成、阻塞和延期事项。
3. 重新检查调用链和安全边界，而不是只复跑新增测试。
4. 运行本阶段测试和所有已完成阶段的核心回归。
5. 检查是否产生未记录 migration、OpenAPI、环境变量或生成文件。
6. 检查文档、代码、配置和实际运行路径是否一致。
7. 将命令、结果、未执行项和风险写入账本。
8. 所有必需项通过后，才把阶段状态从“进行中”更新为“已完成并回验”。

## 18. 测试矩阵

### 18.1 Hermes

- `python -m py_compile` 关键入口。
- `pytest -ra`。
- Gateway 上游结构和 provenance 契约。
- 私聊、群聊、Thread、附件、Reaction、流式富文本消息、卡片回调和主动推送。
- 重连、去重、并发、超时、429/5xx 和队列恢复。
- 凭证不进入 argv、日志、异常和测试快照。

### 18.2 后端

- 目标 Ruff、Mypy 和 Pytest。
- API 使用 AsyncClient 覆盖认证、成功、业务 4xx 和外部失败。
- 独立 PostgreSQL 测试库 migration upgrade/downgrade。
- Tool Registry、权限、数据范围、策略、确认、审计和 Trace。
- Alembic 单 head 和全量后端门禁。

### 18.3 前端

- 单元测试覆盖 V2 事件归并、确认状态和错误映射。
- `pnpm lint`、`pnpm typecheck`、单元测试、coverage、关键 E2E 和 build。
- 加载、空数据、失败、无权限、部分成功、危险确认和窄屏状态。

### 18.4 跨项目

- `scripts/generate-api.ps1`。
- 后端 OpenAPI、前端快照和生成类型无无关漂移。
- Tool Registry 与 Hermes 动态目录契约。
- `scripts/check-test-impact.py`。
- 后端、Hermes 和前端容器构建。

## 19. 发布、灰度与回滚

发布顺序：

1. 测试飞书应用。
2. 内部管理员。
3. 只读用户。
4. 低风险新增。
5. 中风险确认写入。
6. 高风险强确认。
7. 主动推送。
8. 全量用户。

回滚要求：

- 保留 V1 协议适配一个发布周期。
- 保留旧 Gateway 开关但默认关闭，禁止双消费者长期并行。
- Catalog Projection 可重建，回滚不依赖手工修库。
- migration 有明确 downgrade；生产数据变化另走备份和恢复流程。
- 工具可应急 disabled，不能通过数据库启用未部署能力。

## 20. 完成定义

本方案只有在以下条件全部满足时才算完成：

- Phase 0–5 均为“已完成并回验”。
- 任务账本不存在未解释的待处理或阻塞项。
- 所有要求的自动化测试、容器和关键真实飞书验收有证据。
- migration、OpenAPI、环境变量和生成文件均有明确记录。
- 上游版本、运行版本和文档版本一致。
- 原生 Gateway 是 Livzon 飞书消息、确认卡片和主动推送的唯一生产通道。
- Dazah 是业务身份、权限、策略、确认、执行和审计的唯一权威。
- 新增业务工具不再需要手工修改 Hermes 工具列表。
