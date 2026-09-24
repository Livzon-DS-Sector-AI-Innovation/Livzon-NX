# Hermes-Lite

> Hermes-Lite 使用仓库锁定的 Hermes 上游版本；当前版本与提交以 `AGENTS.md`
> 和 `upstream-hermes.json` 为准。
> 在 Dazah / Livzon Agent 场景中，它负责理解用户意图、编排工具调用、连接平台 LLM 代理，并将业务结果组织成适合前端聊天窗口展示的回复。

## 1. Hermes 的作用

Hermes-Lite 在当前平台中的定位不是业务系统本身，也不是直接访问数据库的数据服务，而是位于 Dazah 后端 Agent 网关之后的“智能编排层”。

它主要承担以下职责：

- 接收 Dazah 后端转发的用户消息、会话历史和用户上下文。
- 通过 Dazah 后端提供的 LLM 代理调用平台当前启用的大模型配置。
- 根据用户意图选择合适的工具，例如库存查询、采购申请、审批查询等。
- 通过 `dazah_tool` 调用 Dazah 后端受控的业务工具网关。
- 对读操作结果进行业务化总结和卡片式表达。
- 对写操作生成待确认项，由前端展示二次确认，用户确认后再由 Dazah 后端执行。
- 保持 Hermes 自身的工具边界，不直接绕过后端权限、审计和业务校验。

当前调用链路如下：

```text
Livzon Agent 前端悬浮助手
        |
        v
Dazah 后端 /api/v1/agent/chat 或 /api/v1/agent/chat/stream
        |
        v
Hermes-Lite /v2/agent/runs 或 /v2/agent/runs/stream
        |
        +-- LLM：Dazah 后端 /api/v1/agent/llm/chat/completions
        |
        +-- 工具：dazah_tool
              |
              v
           Dazah 后端 Tool Registry（search / describe / execute）
              |
              v
           仓储 / 采购 / 审批 / 飞书同步等业务模块
```

## 2. 与 Dazah 平台的适配方式

### 2.1 LLM 配置读取

Hermes-Lite 不直接保存真实模型 API Key，也不直接读取数据库中的 LLM 配置。

当前设计是：

- 平台管理员在 Dazah 中维护“LLM 系统配置”。
- Dazah 后端从平台配置表中读取当前启用的模型供应商、模型名称、Base URL、API Key 等信息。
- Hermes-Lite 只访问 Dazah 后端暴露的 LLM 代理接口。
- Hermes-Lite 与 Dazah 后端之间通过 `AGENT_LLM_PROXY_TOKEN` 做服务间鉴权。

这可以保证：

- 模型密钥集中保存在 Dazah 平台侧。
- Hermes 不需要感知具体供应商密钥。
- 切换模型配置时优先由平台配置生效，不需要频繁修改 Hermes。
- 后端可以统一做模型访问审计、错误处理和配置校验。

相关环境变量：

```bash
AGENT_LLM_PROXY_TOKEN=change-me
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
DAZAH_LLM_MODEL=dazah-active-text
```

容器内运行时不要使用 `127.0.0.1` 指向 Dazah 后端。`127.0.0.1` 在容器内代表 Hermes 容器自身，应使用 Docker 网络中的服务名，例如：

```bash
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
```

### 2.2 平台工具调用

Hermes-Lite 通过 `tools/dazah_platform.py` 中的 `dazah_tool` 调用 Dazah 平台业务能力。

`dazah_tool` 不允许模型调用任意 URL，只允许向 Dazah 后端 Agent 工具网关发送受控 operation。Dazah 后端现在以 `@agent_tool` 装饰器、`ToolRegistry` 注册中心和 `ToolExecutor` 统一执行器作为权威工具来源；Hermes 侧只负责发起工具调用，不直接操作数据库，也不绕过后端权限、参数校验、确认和审计。

```text
POST {DAZAH_API_BASE_URL}/agent/tools/execute
```

Dazah 后端同时提供服务令牌保护的工具发现接口：

```text
GET {DAZAH_API_BASE_URL}/agent/tools
```

该接口返回后端当前已注册、授权、开放给 Agent 的工具元数据，包括：

- `name`：工具名称，例如 `procurement.list_suppliers`
- `summary`：工具说明
- `input_schema`：Pydantic 输入参数 schema
- `risk_level`：风险等级，`low` / `medium` / `high`
- `write`：是否写操作
- `required_roles`：所需用户角色
- `workflow_allowed`：是否允许进入 Agent 工作流
- `human_decision_required`：是否必须人工责任判断
- `method` / `path`：兼容旧能力说明的 HTTP 元数据

相关环境变量：

```bash
DAZAH_API_BASE_URL=http://app:8000/api/v1
DAZAH_AGENT_TOOL_TOKEN=change-me
```

所有业务权限、参数校验、写操作确认、审计记录、数据库事务和飞书凭证都保留在 Dazah 后端，Hermes 只负责发起受控工具调用。

后端工具调用的执行边界为：

```text
Hermes-Lite dazah_tool
  -> Dazah /api/v1/agent/tools/execute
  -> ToolRegistry 查找 @agent_tool 注册工具
  -> ToolExecutor 校验服务令牌、用户、权限、参数、风险
  -> 写操作生成 confirmation / 读操作直接执行
  -> 调用业务模块 Service
  -> 写入 agent_tool_calls 与 audit.logs
```

### 2.3 聊天接口

Hermes-Lite 为 Dazah Agent 网关提供两个接口：

| 接口 | 说明 |
| --- | --- |
| `GET /health` | 健康检查 |
| `POST /v2/agent/runs` | AgentBackend V2 非流式运行 |
| `POST /v2/agent/runs/stream` | AgentBackend V2 类型化 SSE 事件流 |

V2 流事件包含 Trace、Run、事件 ID 和递增序列；断线恢复只恢复展示，
不得重复执行工具。

## 3. 兼容性说明

Hermes-Lite 保留 Hermes Agent 的核心运行能力，但对默认功能面做了收敛，以便更安全地嵌入业务系统。

### 3.1 保留能力

- Tool-calling 对话循环。
- OpenAI-compatible Chat Completions 调用方式。
- Prompt 组装和会话历史注入。
- Memory、session search、todo、clarify 等轻量 Agent 工具。
- Web search 与 web extract。
- Tool registry 和 toolset 机制。
- Dazah 平台工具集 `dazah`。
- 普通响应和 SSE 流式响应。

### 3.2 默认不启用的能力

以下能力虽然在工程中可能存在兼容代码或历史模块，但当前 Dazah Agent 服务默认不启用：

- 终端命令执行。
- 本地文件读写。
- 浏览器自动化。
- 代码执行。
- 多媒体生成。
- 未经 Dazah 后端网关授权的数据库直连。
- 任意第三方 URL 工具调用。

新增高权限能力时，先在 Dazah 后端建立受控 Service、权限、审计和确认机制，
再通过 `@agent_tool` 注册并验证动态目录；仅跨服务契约变化时修改 Hermes。

### 3.3 模型接口兼容

Hermes-Lite 当前主要使用 OpenAI-compatible Chat Completions 接口。实际模型供应商由 Dazah 平台 LLM 系统配置决定。

适配时需要关注：

- `/models` 接口是否可用。
- `/chat/completions` 是否支持流式输出。
- usage 字段可能存在 `prompt_tokens` / `completion_tokens` 或其他供应商差异。
- 工具调用格式是否符合 OpenAI tool calling 语义。
- 模型是否稳定支持中文业务指令和结构化 JSON 参数生成。

### 3.4 Dazah 用户记忆

Dazah Agent 不使用上游全局 `MEMORY.md` / `USER.md` 作为产品用户画像。用户长期
记忆保存在 `$HERMES_HOME/memories/user-memory.sqlite3`，以可信的
`tenant_id + Dazah user_id` 隔离，因此同一用户可在 Web 和飞书私聊间共享画像，
飞书群聊则完全不读取或写入个人记忆。

每位用户默认最多保存 32 KiB 有效内容，达到 80% 时将较早的任务、决策和交互
明细压缩为长期摘要，目标占用为 60%；用户明确要求保留的项目不会被自动淘汰。
每次注入 Agent 的记忆最多 6 KiB。用户可在私聊中使用 `/memory`、
`/memory forget <关键词>` 和 `/memory clear` 查看或管理自己的记忆。

回复后的记忆复盘先写入同一 SQLite 数据库中的有界任务队列，再由带租约的 Worker
异步处理；进程重启后可重新认领未完成任务，相同 `run_id` 只能由一个 Worker
处理。任务历史只接受脱敏后的可信工具执行证据或用户明确要求保存的陈述；稳定画像
使用 `memory_key` 覆盖旧值，避免职位、偏好等新旧事实同时生效。幂等记录和失败任务
均有数量及时间保留上限，不随会话数无限增长。

压缩会在单次摘要后重新核对实际 UTF-8 占用，并继续缩短可压缩摘要，直到达到约 60% 的
目标容量或确认已无安全压缩空间。用户明确说“记住”“记一下”或“保存到记忆”时，本轮改为
同步提取与写入，并在回复中明确报告确认保存、未通过校验或保存失败；普通对话仍走后台队列。

## 4. 当前启用的工具集

Hermes-Lite 的工具集定义位于 `toolsets.py`。

当前 Dazah Agent 服务在 `services/dazah_agent_service.py` 中启用：

```python
enabled_toolsets=["agent", "dazah", "feishu"]
disabled_toolsets=["memory"]
```

主要工具如下：

| 工具集 | 工具 | 用途 |
| --- | --- | --- |
| Dazah 用户记忆服务 | 后台提取与 `/memory` 命令 | 保存租户隔离、容量受控的用户画像 |
| `agent` | `session_search` | 检索历史会话 |
| `agent` | `todo` | 任务拆解与步骤管理 |
| `agent` | `clarify` | 在意图不明确时提出澄清问题 |
| `agent` | `web_search` | 搜索公开网页 |
| `agent` | `web_extract` | 提取网页内容 |
| `dazah` | `dazah_tool` | 搜索、描述并执行当前可信主体可用的后端工具目录 |

## 5. Dazah 工具目录

Hermes-Lite 只注册 `dazah_tool`。运行时先 `search` 当前可信主体可用的能力，再
`describe` 目标 operation 的实时输入 Schema，最后按 Schema `execute`。
后端 `dazah-backend/app/shared/module_registry.py` 声明 Provider，
`ToolRegistry` 管工具元数据，
`ToolExecutor` 执行权限、参数、风险、确认和审计。README 不复制静态 operation
清单；当前能力以有权主体调用的目录和后端模块 `agent_tools.py` 为准。

后端接口为 `POST /api/v1/agent/tools/search`、
`GET /api/v1/agent/tools/{operation}` 和
`POST /api/v1/agent/tools/execute`。Hermes 不提供任意业务 URL 调用。
飞书原生文档、云盘、Base 和 Wiki 由 `lark_cli` 处理，不通过业务工具冒充
飞书资源权限。

## 6. 新增业务 Agent 能力

1. 先按工作区 `docs/business-module-boundaries.md` 确定记录所有者，在该模块
   Service 实现业务规则、权限所需上下文和事务；handler 只做 InputSchema 接收、
   Service 调用及结果序列化。
2. 在所有者模块的 `agent_tools.py` 定义 Pydantic v2 InputSchema 和
   `@agent_tool` 元数据。operation 使用 `<module>.<verb>_<resource>`；
   查询设置 `write=False`，写入设置 `write=True` 并走后端 confirmation。
   审批、驳回等人工责任判断设置 `human_decision_required=True`、
   `workflow_allowed=False`。
3. 需要自动发现时，在 `dazah-backend/app/shared/module_registry.py` 的对应
   `ModuleDefinition` 声明 `agent_tools_module`。后端
   `app/modules/agent/tool_registration.py` 已遍历该注册表，无需手写导入；
   新业务能力也无需修改 Hermes 工具注册或在系统提示词中添加 operation 清单。
4. 验证目录搜索、实时 Schema、参数错误、无权限、风险拒绝、写入确认、取消、
   审计和所属模块核心调用。变更后端端点或请求/响应 Schema 时按根规范生成
   OpenAPI 和前端类型；只有跨服务契约变化时才修改 Hermes 适配实现。
5. 若新能力需要专门的聊天展示，在前端已有 Agent 组件中处理稳定的结构化结果，
   同时覆盖空结果、后端失败和流式中断；不要把业务规则放进展示层。

后端 Provider 入口可参考当前
`dazah-backend/app/modules/warehouse/agent_tools.py`、
`dazah-backend/app/modules/quality/agent_tools.py` 和
`dazah-backend/app/shared/module_registry.py` 的
`agent_tools_module` 声明。

## 7. 数据查询方式

Hermes-Lite 不直接查询数据库。

数据查询统一走：

```text
Hermes-Lite
  -> dazah_tool
  -> Dazah 后端 Agent 工具网关
  -> Dazah 后端业务模块
  -> PostgreSQL / 飞书同步数据 / 业务服务
```

这样可以确保：

- 数据权限仍由 Dazah 后端控制。
- 数据库表结构不会暴露给 LLM。
- 业务规则集中在后端。
- 写操作可被确认和审计。
- 后续新增模块时不会破坏 Agent 的安全边界。

## 8. 查询参数与筛选

筛选字段、操作符、分页上限和排序规则由所属模块工具的 Pydantic InputSchema
声明，并由所属模块 Service 校验。Hermes 在 `describe` 后按实时 Schema 组装
参数，不维护一套独立的 `filters` 通用 DSL、字段白名单或 SQL 规则。新增筛选
能力时先改后端工具契约及测试，再核对 Hermes 能否按目录描述调用。

## 9. 本地运行与验证

Dazah 联调使用工作区根目录的 `.env.local` 和 `compose.dev.yml`。先按后端
`docs/development.md` 确认开发库迁移和 `app` 健康，再在**工作区根目录**
启动开发镜像：

```powershell
docker compose --env-file .env.local -f compose.dev.yml up -d --build hermes-lite
docker compose --env-file .env.local -f compose.dev.yml ps hermes-lite
Invoke-RestMethod http://localhost:8100/health
```

局部代码修改在 `Hermes-Lite/` 运行受影响路径的编译和测试；完整参考命令见
`AGENTS.md`。工具发现、可信 subject、确认和风险拒绝由后端与 Hermes 契约
测试验证，不在命令示例里手填可信用户身份或服务令牌。

## 10. 环境变量

| 变量 | 说明 |
| --- | --- |
| `HERMES_AGENT_TOKEN` | Dazah 后端调用 Hermes 的服务令牌 |
| `AGENT_LLM_PROXY_TOKEN` | Hermes 调用 Dazah LLM 代理的服务令牌 |
| `DAZAH_LLM_BASE_URL` | Dazah LLM 代理地址 |
| `DAZAH_LLM_MODEL` | Hermes 请求时使用的模型名称，通常为 `dazah-active-text` |
| `DAZAH_API_BASE_URL` | Dazah 后端 API 地址 |
| `DAZAH_AGENT_TOOL_TOKEN` | Hermes 调用 Dazah 工具网关的服务令牌 |
| `HERMES_DAZAH_CHAT_TIMEOUT_SECONDS` | Hermes 对话超时时间，默认 180 秒 |
| `HERMES_DAZAH_MAX_TOOL_ITERATIONS` | 单轮 Livzon Agent 最大模型/工具迭代次数，默认 30，最高 90 |

示例：

```bash
HERMES_AGENT_TOKEN=change-me
AGENT_LLM_PROXY_TOKEN=change-me
DAZAH_API_BASE_URL=http://app:8000/api/v1
DAZAH_AGENT_TOOL_TOKEN=change-me
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
DAZAH_LLM_MODEL=dazah-active-text
HERMES_DAZAH_CHAT_TIMEOUT_SECONDS=180
HERMES_DAZAH_MAX_TOOL_ITERATIONS=30
```

## 11. 项目结构

```text
Hermes-Lite/
├── agent/                    # Agent 核心运行时
├── tools/                    # 工具注册中心和平台工具
│   └── dazah_platform.py     # Dazah 平台工具网关
├── services/
│   └── dazah_agent_service.py # Dazah Agent 适配服务
├── hermes_cli/               # 轻量配置和认证兼容辅助模块
├── providers/                # 模型提供商扩展接口
├── plugins/                  # 最小插件命名空间包
├── scripts/                  # 工具脚本
├── toolsets.py               # 工具集定义
├── model_tools.py            # 工具 schema 加载与分发逻辑
├── run_agent.py              # Agent 主入口
├── config.yaml               # 默认配置
└── docs/INTEGRATION.md       # 补充集成说明
```

## 12. 验证命令

语法检查：

```bash
python -m py_compile run_agent.py model_tools.py toolsets.py services/dazah_agent_service.py tools/dazah_platform.py
```

容器内检查：

```bash
docker exec hermes-lite python -m py_compile /app/services/dazah_agent_service.py /app/tools/dazah_platform.py
```

健康检查：

```bash
docker exec hermes-lite python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=10).read().decode())"
```

## 13. 安全边界

Hermes-Lite 在 Dazah 平台中的安全原则：

- 不直接保存真实模型供应商密钥。
- 不直接连接业务数据库。
- 不绕过 Dazah 后端权限体系。
- 不直接执行写操作，写操作必须进入确认流程。
- 不默认启用终端、文件、浏览器、代码执行等高风险工具。
- 不允许 LLM 调用任意 URL 执行业务操作。
- 所有业务操作必须先注册到 Dazah 后端 `ToolRegistry`。
- 所有工具调用都应可审计、可追踪、可失败恢复。

## 14. License

MIT. See [LICENSE](LICENSE).
