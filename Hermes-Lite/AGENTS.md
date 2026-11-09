# Hermes-Lite AI 开发规范

Hermes-Lite 是 Dazah / Livzon Agent 的编排层和飞书 Gateway，不承载
Dazah 业务规则、数据库访问或最终权限判定。

## 架构边界

- 上游 Hermes 的固定版本、commit 和归档校验以 `upstream-hermes.json` 为准，
  依赖与 Python 范围以 `pyproject.toml`、`uv.lock` 为准，不在规范重复维护版本。
  禁止本地修改上游源码；普通适配任务不自动授权升级上游或更新锁定清单。
- `services/dazah_feishu_gateway.py` 是唯一上游兼容边界。普通消息使用
  上游公开 API；raw-card 私有适配只能存在于已登记并有契约测试的方法中。
- 飞书原生文档、云盘、Base、Wiki 等资源使用 `lark_cli`，权限只由飞书
  Scope、资源授权和可见性决定。
- Dazah 业务能力只能经 `tools/dazah_platform.py` 的 `dazah_tool` 调用。
- 不直接连接 Dazah 的 PostgreSQL、Redis、MinIO 或业务模块接口。
  身份解析、目录、确认、配置和投递等控制链路使用既有公开平台接口；该边界
  不禁止这些已定义的控制接口，也不允许借它们绕过业务工具权限。
- 模型不能提供或覆盖可信用户、租户、平台身份或权限上下文。

## AgentBackend V2

对话运行仅使用以下接口；健康检查、配置与投递控制接口仍按各自既有契约使用：

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
时，若现有动态协议已经支持，只在后端所属模块声明 Provider 并补测试，不为
该能力修改 Hermes 注册代码；跨项目协议确有变化时按根规范检查 Hermes 适配。
当前消息投递存在 `identity.deliver_feishu_message` 的单一强制操作回退；它是
平台交互契约，不是新增业务 operation 白名单的模板。修改它须核对可信主体、
后端目录、确认和投递测试。
`services/dazah_agent_service.py` 仍有质量查询等历史意图提示；维护这些路径时
覆盖既有路由测试，不为新增业务模块复制按模块硬编码的 operation 提示。

对话写操作必须使用后端 confirmation；返回 `requires_confirmation=true` 时
只能说明已生成待确认项，不能声称已经执行。自动化写操作仅可由后端核验已有
授权与执行策略，Hermes 不自行跳过确认。审批、驳回、处分等人工责任判断不得代理执行。

## 飞书 Gateway

- 生产环境只允许 Hermes Gateway 消费 Livzon 飞书应用事件。
- 每条入站消息先调用 Dazah 身份解析接口，未绑定或禁用身份必须拒绝。
- 群聊准入由 Dazah 控制；飞书资源操作不得与 Dazah 模块 RBAC 做交集。
- 主动消息统一进入 `/internal/feishu/deliveries`，使用幂等键和 Trace。
- Gateway 配置由 Dazah 管理后台推送版本，版本变化安全重建连接。
- 配置、日志、审计和测试不得包含真实 Token、Cookie、密钥或资源正文。

## 环境和验证

环境变量变更同步工作区根目录 `.env.example` 和 `.env.local.example`。容器间通过
Compose 服务名通信；`127.0.0.1` 只指当前容器，不能用于访问另一个容器中的
Dazah。同容器进程通信与健康检查可使用 loopback，不据此批量替换既有地址。

局部修改对受影响路径编译并运行对应测试；影响不能可靠收敛或共享协议、执行链变化时扩大到相关完整测试集。仅规范或文档变化检查差异、引用与桥接文件。以下是完整检查的参考命令，不是每次修改的默认要求：

依赖首次准备使用 `uv sync --frozen --extra dev`；局部验证不自动重装依赖。
以下命令在 `Hermes-Lite/` 执行；完整 CI 集合以 `scripts/ci.sh` 和根工作流为准：

```powershell
uv run --no-sync python -m compileall -q services tools
uv run --no-sync pytest -q
```

变更 Gateway、V2、Delivery、确认或 `dazah_tool` 时，按受影响能力选择身份
伪造、事件顺序、幂等、断线恢复、卡片回调、配置热刷新或后端目录动态新增测试。
新增和改变的关键分支必须覆盖；不重复验证未受影响的能力。
