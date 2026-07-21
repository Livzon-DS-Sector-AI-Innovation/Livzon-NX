# Livzon Agent 后端工具规范

本目录负责 Agent 工具注册、权限、确认、执行和审计。Agent 不能直接操作数据库，也不能绕过工具网关自由调用业务 API。

## 工具边界

- 所有业务能力使用 `@agent_tool` 注册，并由 `ToolRegistry` 和 `ToolExecutor` 统一执行。
- handler 只能调用所属模块 Service 或明确公开的 `public_api.py`，不得直接操作 ORM、私有 repository 或拼业务 SQL。
- 工具输入使用 Pydantic v2 模型，不在 handler 内解析松散 dict。
- 工具名使用 `<module>.<verb>_<resource>`；查询优先 `list_*`、`get_*`，写入使用明确业务动词。
- `summary` 使用清晰中文；`method` 和 `path` 仅是兼容或展示元数据，不构成旁路调用授权。

## 风险与确认

- 查询工具设置 `write=False`。
- `write=True` 默认先创建确认项，用户确认后才执行。
- 审批、驳回、批准和其他需要人工责任判断的操作设置 `human_decision_required=True`，不得由 Agent 代替责任人决定。
- `human_decision_required=True` 必须同时设置 `workflow_allowed=False`。
- 工作流只能包含允许自动执行且不需要人工责任判断的工具。
- 权限、参数校验、确认和审计必须复用统一执行链路，业务工具不得另造旁路。

## 新增或修改工具

必须同时检查：

- 业务逻辑位于所属模块 Service
- InputSchema、工具元数据和 handler 薄封装
- `tool_registration.py` 启动注册
- 注册、参数、权限、确认、风险拒绝和核心调用测试
- 工具调用记录和 `audit.logs` 审计
- OpenAPI、前端生成类型，以及 Hermes-Lite 的 operation 白名单或静态 schema

工具返回分页结果或业务摘要，避免把大对象写入审计。审计不得记录 secret、token、password、key 等敏感字段。

禁止在 Hermes-Lite 新增绕过后端工具网关的业务 HTTP 调用；禁止 Agent 工具直接连接 PostgreSQL、Redis、飞书业务表或第三方业务系统。
