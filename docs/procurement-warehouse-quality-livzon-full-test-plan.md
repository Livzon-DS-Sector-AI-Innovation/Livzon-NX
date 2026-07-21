# 采购、仓储、质量管理与 Livzon 助手全量测试修复计划

## Summary

- 范围：采购、仓储、质量管理、Livzon 助手；数据策略使用模拟数据，不污染真实业务数据。
- 当前基线：后端 `/health` 与 Hermes `/health` 可用；核心 GET 探测多为 200；`/api/v1/agent/tools` 未授权 401、带 token 200 且注册工具 110 个。
- 已发现待复测问题：前端 `/quality/validation` 日志出现 `Unexpected end of JSON input`；浏览器控制台出现 Next/React performance measure error；仓储飞书 WS 存在无效 app_id 报错；Hermes dev reloader 曾出现 watchfiles 内存异常。

## Key Changes

- 新增/补齐 Playwright 模拟数据 e2e：采购申请/审批/供应商/订单/发票/合同，仓储库存/飞书配置，质量偏差/CAPA/变更/验证/飞书设置，Livzon 悬浮助手入口、聊天、确认项展示。
- 后端测试执行矩阵：健康检查、模块清单、采购/仓储/质量主要 API CRUD 与导入导出、Agent 工具发现/执行/确认/高风险拒绝、identity Livzon 飞书设置与卡片 WS 状态。
- 性能测试用 Python/httpx 并发探针：只读 GET P95 目标小于 500ms；写操作模拟数据目标 P95 小于 1000ms；慢接口记录 SQL/外部依赖原因。
- 修复循环：按后端 5xx/校验错误、前端运行时报错、e2e 交互失败、性能退化排序修复；每修一类重跑对应失败子集，最后跑全量。
- 若修复涉及后端 API 形状，必须重新导出 OpenAPI 并同步前端生成类型；否则不改公开接口。

## Execution Plan

- 环境准备：确认 Docker 服务、迁移、测试 DB；设置 `TEST_DATABASE_URL` 到专用 test/pytest 库；外部飞书、LLM、OCR、MinIO 使用 mock 或 fixture。
- 后端执行：
  - `uv run pytest tests/integration/test_health_and_modules.py`
  - `uv run pytest tests/modules/procurement tests/modules/quality tests/modules/agent tests/unit/test_warehouse_feishu_service.py tests/unit/test_warehouse_feishu_client.py tests/unit/test_identity_feishu_config.py tests/unit/test_identity_feishu_messages.py`
  - 追加只读 OpenAPI 枚举探测，覆盖采购 21、仓储 16、质量 173、Agent 16、Livzon identity 相关端点。
- 前端执行：
  - `pnpm typecheck`
  - `pnpm lint`
  - `pnpm exec playwright test e2e/purchasing e2e/warehouse e2e/quality e2e/agent`
  - 浏览器人工模拟补充：核心页面逐页点击导航、搜索、筛选、新增弹窗、导入预览、导出按钮、助手打开/发送/确认项。
- Hermes 执行：`python -m py_compile` 关键文件、Hermes 单测、`/health`、`/v1/chat`、`/v1/chat/stream`，验证只通过 `dazah_tool` 走后端工具网关。

## Test Cases

- 采购：供应商列表/搜索/导入预览，采购申请创建/提交/审批拒绝策略，订单导出，发票识别记录列表/删除确认，合同模板/生成/文件查看。
- 仓储：原辅料、包材、成品列表；飞书配置读取/保存 mock、连接测试 mock、表目录刷新、本地快照读取、WS 状态。
- 质量：偏差、CAPA、变更、验证、CPV、部门联系人、飞书设置、同步冲突、AI 会话页面的页面渲染、表格交互、表单校验、导入导出。
- Livzon 助手：未授权拒绝、授权工具发现、读工具直接执行、写工具返回 pending confirmation、高风险人工判断拒绝、Hermes 流式响应不断流。
- 回归验收：无浏览器 console error；无 `Application error`；后端无新增 5xx；Playwright 截图/trace 仅在失败时保留；测试报告列出失败原因和修复结果。

## Assumptions

- “管理模块”已确认指质量管理模块。
- 所有 e2e 使用模拟数据和 mock 外部服务；不执行真实飞书、真实 LLM、真实业务审批。
- 当前大量未提交改动视为用户已有工作，修复时只做最小相关改动，不回滚无关文件。
