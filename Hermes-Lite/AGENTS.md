# Hermes-Lite AI 开发规范

`Hermes-Lite` 是 Dazah / Livzon Agent 场景中的轻量中枢 Agent。它负责理解用户意图、组织提示词、调用平台 LLM 代理、选择 Dazah 受控工具，并把结果组织成适合前端聊天窗口展示的回复。

Hermes-Lite 不是业务后端，不是数据库访问层，也不是权限系统。所有业务能力必须经由 Dazah 后端 Agent 工具网关执行。

## 项目边界

- Hermes-Lite 只能作为智能编排层，不承载工厂业务规则的最终判定。
- 不直接连接 PostgreSQL、Redis、MinIO、飞书业务表或任何 Dazah 业务模块数据库。
- 不直接保存真实模型供应商 API Key；模型调用必须通过 Dazah 后端 LLM 代理。
- 不绕过 Dazah 后端权限、参数校验、确认流程和审计日志。
- 不新增终端命令执行、本地文件读写、浏览器自动化、代码执行等高风险默认工具。
- 不允许 LLM 调用任意 URL 执行业务操作。

## Dazah 工具调用规范

Hermes-Lite 通过 `tools/dazah_platform.py` 中的 `dazah_tool` 调用 Dazah 后端工具网关。

唯一业务工具执行入口：

```text
POST {DAZAH_API_BASE_URL}/agent/tools/execute
```

工具发现入口：

```text
GET {DAZAH_API_BASE_URL}/agent/tools
```

Dazah 后端以 `@agent_tool`、`ToolRegistry`、`ToolExecutor` 为权威工具来源。Hermes-Lite 中的 `ALLOWED_OPERATIONS` 只是本地防御层和模型工具 schema 枚举，必须与 Dazah 后端注册工具保持同步。

新增或删除 Dazah Agent 工具后，Hermes-Lite 必须同步检查：

- `tools/dazah_platform.py` 的 `ALLOWED_OPERATIONS`
- `DAZAH_TOOL_SCHEMA` 中 operation enum
- `services/dazah_agent_service.py` 的系统提示词
- `README.md` 中的工具清单与适配说明

后续如果改为启动时动态读取 `GET /api/v1/agent/tools`，本地 `ALLOWED_OPERATIONS` 可以降级为离线兜底缓存，但仍不得允许模型调用未注册工具。

## LLM 代理规范

Hermes-Lite 不直接读取 Dazah 数据库中的 LLM 配置，不直接使用供应商 API Key。

模型调用必须走：

```text
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
```

并通过 `AGENT_LLM_PROXY_TOKEN` 做服务间鉴权。

禁止：

- 在 Hermes-Lite 中硬编码模型 API Key。
- 直接读取 Dazah `.env` 中的供应商密钥并构造模型客户端。
- 绕过 `/api/v1/agent/llm/chat/completions` 直接访问模型供应商。
- 把真实 API Key 写入日志、README、示例输出或测试快照。

## 写操作与确认规范

Hermes-Lite 不执行最终业务写入。写操作必须由 Dazah 后端生成 confirmation，并由前端展示给用户确认。

Hermes 回答时必须遵守：

- 工具返回 `requires_confirmation=true` 时，只能说明“已生成待确认项”，不能声称操作已经完成。
- 用户确认前，不得说采购申请已创建、合同已生成、表已同步、工作流已运行完成等。
- 确认执行结果必须以后端 confirmation execute 返回为准。
- 审批、驳回、批准、重启等人工责任判断操作，即使模型理解了用户意图，也只能提示用户到业务页面自行判断操作。

## 工作流规范

Hermes-Lite 可调用 Dazah 后端 Agent 工作流工具，但工作流规则由 Dazah 后端控制。

允许：

- 调用 `agent.list_workflow_capabilities` 查询可编排能力。
- 基于返回结果创建工作流。
- 查询、启停、运行和查看工作流状态。

禁止：

- 编造未返回的 workflow capability。
- 把 `workflow_allowed=false` 的工具写入工作流。
- 把 `human_decision_required=true` 的工具写入工作流。
- 创建自动批量审批、自动批量驳回、自动重启关键连接等工作流。

写操作步骤会生成 confirmation，用户确认后才继续执行。

## 提示词与回复规范

修改 `services/dazah_agent_service.py` 的系统提示词时，必须保持以下原则：

- 不编造平台数据，必须通过 `dazah_tool` 查询 Dazah 数据。
- 业务数据以 Dazah 工具返回为准。
- 写操作只生成待确认项，不直接声称完成。
- 不使用 Markdown 表格作为主要回复形式。
- 少量数据使用业务卡片式文本。
- 大量数据先摘要，再展示前几条，并提示可继续查看。
- 复杂明细分组展示，避免把原始 JSON 直接甩给用户。
- 对高风险责任判断保持拒绝代执行策略。

## 新增业务模块适配流程

新增业务模块接入 Livzon Agent 时，先在 `dazah-backend` 完成：

1. 所属业务模块 Service。
2. `app/modules/<module>/agent_tools.py`。
3. Pydantic InputSchema。
4. `@agent_tool` 注册。
5. `app/modules/agent/tool_registration.py` 导入注册。
6. 后端测试、OpenAPI 导出、前端类型生成。

Hermes-Lite 侧只做：

1. 同步 `ALLOWED_OPERATIONS`。
2. 必要时更新工具 schema 描述。
3. 必要时更新系统提示词。
4. 更新 README 工具清单和适配说明。
5. 验证 `dazah_tool` 能调用对应 operation。

不要在 Hermes-Lite 中实现业务模块自己的 HTTP 客户端、数据库查询或飞书同步逻辑。

## 环境变量规范

关键变量：

```bash
HERMES_AGENT_TOKEN=change-me
AGENT_LLM_PROXY_TOKEN=change-me
DAZAH_API_BASE_URL=http://app:8000/api/v1
DAZAH_AGENT_TOOL_TOKEN=change-me
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
DAZAH_LLM_MODEL=dazah-active-text
HERMES_DAZAH_CHAT_TIMEOUT_SECONDS=90
```

容器内不要使用 `127.0.0.1` 指向 Dazah 后端；应使用 Docker 网络服务名，例如 `http://app:8000/api/v1`。

修改环境变量时：

- 同步 `.env.example`。
- 不提交真实 `.env` 密钥。
- README 中只写占位值。

## 代码组织规范

- Dazah 平台工具只放在 `tools/dazah_platform.py` 或其明确拆分的子模块中。
- Dazah Agent 服务入口放在 `services/dazah_agent_service.py`。
- 工具集开关维护在 `toolsets.py`。
- 不把 Dazah 业务规则散落到 `run_agent.py`、`model_tools.py` 或通用 Hermes runtime。
- 修改 Hermes 核心 runtime 前，先确认不是 Dazah 适配层可以解决的问题。

## 测试与验证

常用检查：

```bash
python -m py_compile run_agent.py model_tools.py toolsets.py services/dazah_agent_service.py tools/dazah_platform.py
```

服务健康检查：

```bash
curl http://127.0.0.1:8100/health
```

Dazah 后端工具发现检查：

```bash
curl -H "Authorization: Bearer $DAZAH_AGENT_TOOL_TOKEN" \
  "$DAZAH_API_BASE_URL/agent/tools"
```

Dazah 工具执行检查应覆盖：

- 查询类工具直接返回结果。
- 写操作返回 pending confirmation。
- 高风险人工判断操作返回策略拒绝。
- token 缺失或错误时返回鉴权失败。
- Dazah 后端不可用时返回可读错误，不泄露内部堆栈。

## 禁止事项

- 禁止在 Hermes-Lite 中新增业务数据库连接。
- 禁止在 Hermes-Lite 中直接调用 Dazah 业务 REST 接口绕过 `/agent/tools/execute`。
- 禁止把真实 token、secret、API Key 写入代码、README 或测试。
- 禁止让 LLM 自由决定 URL、SQL、文件路径或 shell 命令来完成业务操作。
- 禁止对 confirmation 结果进行乐观编造；必须以后端返回为准。
- 禁止将人工责任判断操作包装成普通可执行工具。
