# 质量模块 Livzon 助手工具接入任务记录

日期：2026-07-06

## 执行规则

每个阶段必须遵循：

1. 开始前读取 `docs/quality-agent-tools-spec-2026-07-06.md`。
2. 开始前读取 `docs/tasks/quality-agent-tools-tasks-2026-07-06.md`。
3. 执行本阶段改动。
4. 阶段结束后更新 spec 的“当前阶段状态”和“变更记录”。
5. 阶段结束后更新本任务文档的状态、执行情况、验证结果和下一阶段入口。

## 阶段总览

| 阶段 | 目标 | 状态 | 开始时间 | 完成时间 |
| --- | --- | --- | --- | --- |
| 阶段 0 | 文档初始化 | 已完成 | 2026-07-06 | 2026-07-06 |
| 阶段 1 | 质量工具接口整理 | 已完成 | 2026-07-06 | 2026-07-06 |
| 阶段 2 | 后端 Agent tools 注册 | 已完成 | 2026-07-06 | 2026-07-06 |
| 阶段 3 | Hermes-Lite 接入 Livzon 助手 | 已完成 | 2026-07-06 | 2026-07-06 |
| 阶段 4 | 测试与验证 | 已完成 | 2026-07-06 | 2026-07-06 |
| 阶段 5 | 收尾审查 | 已完成 | 2026-07-06 | 2026-07-06 |

## 阶段执行记录

### 阶段 0：文档初始化

状态：已完成

已完成：

- 创建 spec 文档。
- 创建 tasks 文档。
- 写入阶段拆分、范围边界、执行规则和验收标准。

验证结果：

- 已回读 spec 与 tasks，确认文档创建成功。

下一阶段入口：

- 读取两份文档。
- 整理质量模块 service/schema 能力。
- 在 spec 中固化最终 operation 清单和输入输出模型映射。

### 阶段 1：质量工具接口整理

状态：已完成

已完成：

- 已读取 spec 与 tasks。
- 已检查质量模块 service/schema 导出。
- 已在 spec 固化最终 operation 清单与 service 映射。

验证结果：

- `rg` 与关键 service 文件读取完成。
- 本阶段未修改业务代码。

下一阶段入口：

- 根据固化的 operation 清单实现后端 `quality.agent_tools`。

### 阶段 2：后端 Agent tools 注册

状态：已完成

已完成：

- 已新增 `dazah-backend/app/modules/quality/agent_tools.py`。
- 已在 `dazah-backend/app/modules/agent/tool_registration.py` 导入质量工具。
- 已注册偏差、CAPA、变更、变更计划、验证、CPV、飞书只读/同步工具。

验证结果：

- `uv run python -m py_compile app/modules/quality/agent_tools.py app/modules/agent/tool_registration.py` 通过。
- `ensure_agent_tools_registered()` 后发现 68 个 `quality.*` operation。

下一阶段入口：

- 同步 Hermes-Lite `ALLOWED_OPERATIONS` 与 README。

### 阶段 3：Hermes-Lite 接入 Livzon 助手

状态：已完成

已完成：

- 已更新 `Hermes-Lite/tools/dazah_platform.py` 的 `ALLOWED_OPERATIONS`。
- 已更新 `dazah_tool` schema 描述。
- 已更新 `Hermes-Lite/README.md` 质量模块工具清单和边界说明。

验证结果：

- `python -m py_compile run_agent.py model_tools.py toolsets.py services/dazah_agent_service.py tools/dazah_platform.py` 通过。
- Hermes-Lite 白名单发现 68 个 `quality.*` operation。

下一阶段入口：

- 新增/更新测试并运行验证。

### 阶段 4：测试与验证

状态：已完成

已完成：

- 已新增 `dazah-backend/tests/modules/agent/test_quality_agent_tools.py`。
- 已覆盖质量工具注册、排除删除/审批/配置类工具、写工具确认项、工作流能力、Hermes 白名单一致性。
- 已修复质量模块两个测试阻断点：飞书不可用时报告记录本地兜底、飞书表选项路由只在必要时传 `table_id`。

验证结果：

- `uv run pytest tests/modules/agent/test_quality_agent_tools.py -q` 通过：5 passed。
- `uv run pytest tests/modules/agent tests/modules/quality -q` 通过：157 passed, 41 warnings。
- `python -m py_compile run_agent.py model_tools.py toolsets.py services/dazah_agent_service.py tools/dazah_platform.py` 通过。

下一阶段入口：

- 收尾审查并更新最终结果。

### 阶段 5：收尾审查

状态：已完成

已完成：

- 已回读 spec 与 tasks。
- 已核对关键文件存在：spec、tasks、后端质量工具注册文件、后端质量工具测试文件。
- 已核对 `dazah-backend/app/modules/agent/tool_registration.py` 导入 `app.modules.quality.agent_tools`。
- 已核对 Hermes-Lite 白名单包含质量 operation 代表项。
- 已在 spec 写入最终验收结果和阶段 5 变更记录。

验证结果：

- `uv run pytest tests/modules/agent tests/modules/quality -q` 通过：157 passed, 41 warnings。
- Hermes-Lite `python -m py_compile run_agent.py model_tools.py toolsets.py services/dazah_agent_service.py tools/dazah_platform.py` 通过。
- 关键文件 `Test-Path` 检查均为 True。
- `Select-String` 确认质量工具注册入口和 Hermes-Lite 质量 operation 存在。
- 工作区根路径不是 Git 仓库，`git status`/`git diff` 无法作为最终审查来源。

下一阶段入口：

- 无，全部阶段已完成。

## 后续修复记录

### 2026-07-06：pytest 数据库安全保护

背景：

- 追踪到质量飞书配置被重置的直接风险点：既有质量模块 pytest 用例会对 `quality.quality_feishu_entity_settings` 与 `quality.quality_feishu_app_settings` 执行 `DELETE` 并 `commit`。
- 原测试夹具直接使用 `settings.DATABASE_URL`。如果本地 pytest 连接到开发库 `dazah`，提交后的删除无法被夹具末尾的 `rollback()` 撤销。

已完成：

- 新增 `dazah-backend/tests/db_safety.py`。
- 更新 `dazah-backend/tests/conftest.py` 与 `dazah-backend/tests/modules/equipment/conftest.py`，测试连接统一使用安全检查后的数据库 URL。
- 支持通过 `TEST_DATABASE_URL` 指向独立测试库。
- 默认拒绝连接数据库名不包含 `test`、`testing` 或 `pytest` 的库。
- 更新 `dazah-backend/.env.example` 与 `dazah-backend/docs/development.md`，说明 pytest 必须使用独立测试库。

验证结果：

- `uv run python -m py_compile tests/db_safety.py tests/conftest.py tests/modules/equipment/conftest.py` 通过。
- 已检索确认 `.env.example` 与 `docs/development.md` 包含 `TEST_DATABASE_URL` 说明。

### 2026-07-06：Livzon 助手质量模块路由修复

背景：

- 截图复核显示：用户询问“质量模块的报告记录数据表”时，Livzon 助手回答了仓储/飞书同步表范围，未调用质量模块工具。
- 后端注册表已能发现 68 个 `quality.*` operation，且 Hermes-Lite `ALLOWED_OPERATIONS` 已包含质量工具；问题发生在模型路由上下文。
- `Hermes-Lite/services/dazah_agent_service.py` 的系统提示仍只声明仓储、采购和通讯录。
- skill resolver 默认 `business_scope` 未包含 `quality`，并且前端浮窗固定传入 `scope: ["warehouse", "procurement"]`。

已完成：

- 更新 `Hermes-Lite/services/dazah_agent_service.py` 系统提示，明确质量模块能力和边界。
- 明确“质量模块的报告记录数据表/质量报告记录”默认映射到 `quality.list_deviation_report_records`。
- 新增 `_business_scope()`，将默认 `identity/warehouse/procurement/quality` 与前端传入 scope 合并，避免前端旧 scope 覆盖质量范围。
- 更新 `Hermes-Lite/toolsets.py`、`Hermes-Lite/README.md`、`Hermes-Lite/docs/INTEGRATION.md` 的 dazah 工具集描述。
- 新增 `Hermes-Lite/tests/test_dazah_quality_routing.py` 静态回归测试。
- 更新 `dazah-frontend/src/components/agent/AgentFloatingAssistant.tsx`，前端浮窗 scope 改为 `identity/warehouse/procurement/quality`。

验证结果：

- Hermes-Lite `python -m py_compile run_agent.py model_tools.py toolsets.py services/dazah_agent_service.py tools/dazah_platform.py tests/test_dazah_quality_routing.py` 通过。
- 由于 Hermes-Lite 环境没有 pytest 可执行文件，已用 Python 直接调用 `test_dazah_quality_routing.py` 中两个测试函数，结果通过：`quality routing tests passed`。
- 后端注册表检查通过：发现 68 个 `quality.*` operation，`quality.list_deviation_report_records` 存在。
- 前端 `pnpm typecheck` 通过。

### 2026-07-06：Livzon 助手运行时质量接口复核与强制路由

背景：

- 用户再次截图显示 Livzon 助手仍回答“未内置质量管理模块”，并把问题导向 `finished_product`、`hardware`、`materials_packaging` 仓储飞书同步表。
- 静态与容器内检查均确认：后端运行时公开 68 个 `quality.*` 工具，Hermes-Lite `ALLOWED_OPERATIONS` 包含 68 个质量工具，前端浮窗 scope 包含 `quality`。
- 实际调用 Hermes-Lite `/v1/chat` 后发现 `tool_trace_count=0`，模型仍未调用工具，说明仅靠提示词和 scope 不能稳定保证质量意图命中。

已完成：

- 在 `Hermes-Lite/services/dazah_agent_service.py` 增加质量报告记录确定性预路由。
- 对“质量模块的报告记录数据表”“质量报告记录”“偏差报告记录”等明确查询，直接通过 `dazah_tool` 调用 `quality.list_deviation_report_records`。
- 保持边界：不绕过 Dazah 后端 Agent 工具网关，不直接访问质量 REST API、数据库或飞书业务表。
- 返回结果整理为卡片式文本，并写入 `tool_trace`，便于前端和日志确认命中的 operation。
- 更新 `Hermes-Lite/tests/test_dazah_quality_routing.py`，增加确定性路由静态回归检查。
- 修复 `dazah-backend/app/modules/agent/service.py` 中后端调用 Hermes 时固定覆盖 `scope: ["warehouse", "procurement"]` 的问题，改为 `identity/warehouse/procurement/quality`。
- 重启 `hermes-lite` 容器，使运行服务加载最新 Python 代码。
- 重启 `dazah-backend-app-1` 容器，使后端 Agent 代理层加载最新 scope。

验证结果：

- `python -m py_compile services/dazah_agent_service.py tests/test_dazah_quality_routing.py` 通过。
- 容器内 `python -m py_compile services/dazah_agent_service.py tests/test_dazah_quality_routing.py` 通过。
- `uv run python -m py_compile app/modules/agent/service.py` 通过。
- 容器内 `/app/.venv/bin/python -m py_compile app/modules/agent/service.py` 通过。
- 静态回归测试直接调用通过：`quality routing static tests passed`。
- 后端 `/api/v1/agent/tools` 运行时检查通过：质量工具数量 68，`quality.list_deviation_report_records=True`。
- Hermes-Lite `/v1/chat` 实际请求通过：`tool_trace` 包含 `quality.list_deviation_report_records`，返回 5 条偏差报告记录，总数 10。
- Hermes-Lite `/v1/chat/stream` 实际请求通过：`has_quality_trace=True`，`has_old_answer=False`。
- 后端 `/api/v1/agent/chat/stream` 完整链路请求通过：`has_quality_trace=True`，`has_old_answer=False`。

### 2026-07-06：前端 Livzon 助手全平台文案调整

背景：

- 浏览器标注指出质量页面 Livzon 助手浮窗标题下仍显示“仓储 / 采购”，欢迎语仍写成仓储/采购窄范围能力。
- 当前助手已接入质量、仓储、采购、通讯录和工作流，前端文案需要与实际接入范围一致。

已完成：

- 更新 `dazah-frontend/src/components/agent/AgentFloatingAssistant.tsx`。
- 去除标题下方窄范围副标题位置。
- 欢迎语改为“全平台 Agent 已接入质量、仓储、采购、通讯录和工作流能力...”。
- 快捷入口加入“查询质量偏差报告记录”“查看质量同步冲突”。
- 输入框占位改为“输入质量、仓储、采购或流程需求”。

验证结果：

- `pnpm typecheck` 通过。
- 容器内源码检查确认包含新欢迎语、新 placeholder、新质量快捷入口，且不包含 `仓储 / 采购`。
- 浏览器快照确认旧欢迎语不存在，新欢迎语、新质量快捷入口和新 placeholder 已显示。
