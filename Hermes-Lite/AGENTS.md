# Hermes-Lite AI 开发规范

Hermes-Lite 是 Dazah / Livzon Agent 的编排层和飞书 Gateway，不承载
Dazah 业务规则、数据库访问或最终权限判定。

## 架构边界

- 上游 Hermes 固定为 `v2026.7.7.2`、commit
  `9de9c25f620ff7f1ce0fd5457d596052d5159596`，禁止本地修改上游源码。
- `services/dazah_feishu_gateway.py` 是唯一上游兼容边界。普通消息使用
  上游公开 API；raw-card 私有适配只能存在于已登记并有契约测试的方法中。
- 飞书原生文档、云盘、Base、Wiki 等资源使用 `lark_cli`，权限只由飞书
  Scope、资源授权和可见性决定。
- Dazah 业务能力只能经 `tools/dazah_platform.py` 的 `dazah_tool` 调用。
- 不直接连接 Dazah 的 PostgreSQL、Redis、MinIO 或业务模块接口。
- 模型不能提供或覆盖可信用户、租户、平台身份或权限上下文。

## AgentBackend V2

唯一运行接口：

```text
POST /v2/agent/runs
POST /v2/agent/runs/stream
```

请求必须包含由 Gateway 或 Dazah 后端产生的可信 `subject`。流事件必须有
`event_id`、`trace_id`、`run_id`、递增 `sequence`、`occurred_at`、
`type` 和类型化 `data`。不得恢复旧聊天请求、旧流事件或从 prompt/context
提取身份的逻辑。

## Dazah 工具

Hermes 只注册一个 `dazah_tool`，支持：

- `action=search`：搜索当前可信主体可用的目录能力。
- `action=describe`：按稳定 operation 读取实时 Schema。
- `action=execute`：执行已描述的能力。

后端 `module_registry` 和 Tool Registry 是唯一事实源。Hermes 不维护业务
operation 枚举、白名单、别名、旧参数转换或离线运行时目录。新增模块能力
时只需在后端模块声明 Provider，禁止修改 Hermes 注册代码。

写操作必须使用后端 confirmation；返回 `requires_confirmation=true` 时
只能说明已生成待确认项。审批、驳回、处分等人工责任判断不得代理执行。

## 飞书 Gateway

- 生产环境只允许 Hermes Gateway 消费 Livzon 飞书应用事件。
- 每条入站消息先调用 Dazah 身份解析接口，未绑定或禁用身份必须拒绝。
- 群聊准入由 Dazah 控制；飞书资源操作不得与 Dazah 模块 RBAC 做交集。
- 主动消息统一进入 `/internal/feishu/deliveries`，使用幂等键和 Trace。
- Gateway 配置由 Dazah 管理后台推送版本，版本变化安全重建连接。
- 配置、日志、审计和测试不得包含真实 Token、Cookie、密钥或资源正文。

## 环境和验证

环境变量变更同步工作区根目录 `.env.example`（生产）和 `.env.local.example`（开发）。
容器内通过服务名访问 Dazah，不使用 `127.0.0.1`。

常用验证：

```bash
python -m compileall -q services tools
pytest -q
```

变更 Gateway、V2、Delivery、确认或 `dazah_tool` 时，测试必须覆盖身份
伪造、事件顺序、幂等、断线恢复、卡片回调、配置热刷新和后端目录动态新增。
