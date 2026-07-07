# 质量模块 Livzon 助手工具接入规格

日期：2026-07-06

## 背景与目标

将质量模块现有业务能力整理为 Livzon 助手可调用的受控工具。所有业务能力必须通过 Dazah 后端 Agent 工具网关暴露，Hermes-Lite 只调用 `dazah_tool`，不得直接调用质量模块 REST API、数据库或飞书业务表。

本规格遵守：

- `dazah-backend/AGENTS.md`
- `Hermes-Lite/AGENTS.md`
- 根目录 `AGENTS.md`

## 当前阶段状态

- 当前阶段：阶段 5 - 收尾审查
- 当前状态：已完成
- 最新更新时间：2026-07-06

## 接入范围

第一版接入范围：

- 查询 + 普通写入
- 飞书只读与同步
- 普通写入通过 `ToolExecutor` 生成 confirmation，用户确认后执行

明确不接入：

- 删除、批量删除
- 审批通过、驳回、部门主管确认、QA 批准、执行完成确认、效果评价确认等责任判断操作
- 飞书 App 设置、实体表配置、字段映射更新/测试
- 文件导入上传、导入预览、导入确认、AI 附件上传/删除

## 风险与执行规则

- 查询类工具：`write=False`，可直接执行。
- 普通写入工具：`write=True`，`risk_level="medium"`，生成确认项后由用户确认执行。
- 同步/回拉/提醒工具：`write=True`，默认 `risk_level="medium"`。
- 人工责任判断工具：不加入 Hermes 白名单；如注册仅用于策略拒绝，必须设置 `human_decision_required=True` 且 `workflow_allowed=False`。
- 工作流只允许使用 `workflow_allowed=True` 且 `human_decision_required=False` 的工具。

## 后端设计

新增 `dazah-backend/app/modules/quality/agent_tools.py`：

- 定义轻量 Pydantic v2 InputSchema。
- 优先复用质量模块现有 schema，例如 `CreateDeviationRequest`、`UpdateCapaRequest`、`CreateChangeRequest`、`CreateValidationRequest`、`CpvProductCreate`。
- handler 只调用质量模块 service，不直接操作 ORM model、repository 私有实现或 SQL。
- handler 返回 JSON 可序列化 dict/list，避免返回 ORM 对象。

更新 `dazah-backend/app/modules/agent/tool_registration.py`：

- 导入 `app.modules.quality.agent_tools` 触发注册。

## Hermes-Lite 设计

更新 `Hermes-Lite/tools/dazah_platform.py`：

- 将质量模块 operation 加入 `ALLOWED_OPERATIONS`。
- 更新工具 schema 描述，说明 `dazah_tool` 支持质量模块查询、普通写入确认、飞书只读/同步能力。

更新 `Hermes-Lite/README.md`：

- 增加质量模块工具清单。
- 明确质量模块接入边界与确认规则。

## Operation 清单

### 偏差

| Operation | 类型 | InputSchema | Service |
| --- | --- | --- | --- |
| `quality.list_deviations` | 查询 | 偏差筛选 + 分页 | `quality_management.get_deviation_list` |
| `quality.get_deviation` | 查询 | `deviation_id` | `quality_management.get_deviation_detail` |
| `quality.list_deviation_report_records` | 查询 | 分页 | `quality_management.get_deviation_report_record_list` |
| `quality.get_related_capas` | 查询 | `deviation_id` | `quality_management.get_related_capas_for_deviation` |
| `quality.get_deviation_statistics` | 查询 | 空 | `quality_management.get_deviation_statistics` |
| `quality.create_deviation` | 普通写入 | `CreateDeviationRequest` | `quality_management.create_deviation` |
| `quality.update_deviation` | 普通写入 | `deviation_id` + `UpdateDeviationRequest` | `quality_management.update_deviation` |
| `quality.submit_deviation` | 普通写入 | `deviation_id` | `quality_management.submit_for_review` |
| `quality.submit_deviation_investigation` | 普通写入 | `deviation_id` + `SubmitInvestigationRequest` | `quality_management.submit_investigation` |
| `quality.resubmit_deviation` | 普通写入 | `deviation_id` | `quality_management.resubmit_deviation` |

### CAPA

| Operation | 类型 | InputSchema | Service |
| --- | --- | --- | --- |
| `quality.list_capas` | 查询 | CAPA 筛选 + 分页 | `quality_management.get_capa_list` |
| `quality.get_capa` | 查询 | `capa_id` | `quality_management.get_capa_detail` |
| `quality.list_capa_departments` | 查询 | 空 | `quality_management.get_capa_departments` |
| `quality.auto_fill_capa_from_deviation` | 查询 | `deviation_id` | `quality_management.auto_fill_from_deviation` |
| `quality.get_capa_statistics` | 查询 | 空 | `quality_management.get_capa_statistics` |
| `quality.create_capa` | 普通写入 | `CreateCapaRequest` | `quality_management.create_capa` |
| `quality.update_capa` | 普通写入 | `capa_id` + `UpdateCapaRequest` | `quality_management.update_capa` |
| `quality.submit_capa` | 普通写入 | `capa_id` | `quality_management.submit_capa` |
| `quality.resubmit_capa` | 普通写入 | `capa_id` | `quality_management.resubmit_capa` |
| `quality.link_capa_deviation` | 普通写入 | `capa_id` + `deviation_id` | `quality_management.link_deviation` |
| `quality.complete_capa_part` | 普通写入 | `capa_id` + `part` | `quality_management.complete_part` |
| `quality.add_capa_execution_track` | 普通写入 | `capa_id` + track dict | `quality_management.add_execution_track` |

### 变更与变更计划

| Operation | 类型 | InputSchema | Service |
| --- | --- | --- | --- |
| `quality.list_changes` | 查询 | 变更筛选 + 分页 | `quality_management.get_change_list` |
| `quality.get_change` | 查询 | `change_id` | `quality_management.get_change_detail` |
| `quality.get_next_change_code` | 查询 | 空 | `quality_management.generate_next_change_code` |
| `quality.get_change_statistics` | 查询 | 空 | `quality_management.get_change_statistics` |
| `quality.create_change` | 普通写入 | `CreateChangeRequest` | `quality_management.create_change` |
| `quality.update_change` | 普通写入 | `change_id` + `UpdateChangeRequest` | `quality_management.update_change` |
| `quality.list_change_action_plans` | 查询 | 变更计划筛选 + 分页 | `change_action_plan.get_change_action_plan_list` |
| `quality.list_change_action_plans_by_change` | 查询 | `change_id` | `change_action_plan.get_change_action_plans_for_change` |
| `quality.create_change_action_plan` | 普通写入 | `CreateChangeActionPlanRequest` | `change_action_plan.create_change_action_plan_record` |
| `quality.update_change_action_plan` | 普通写入 | `plan_id` + `UpdateChangeActionPlanRequest` | `change_action_plan.update_change_action_plan_record` |
| `quality.sync_change_action_plan` | 普通写入 | `plan_id` | `change_action_plan.sync_change_action_plan_to_feishu` |
| `quality.sync_change_action_plans_from_feishu` | 普通写入 | 空 | `change_action_plan.sync_change_action_plans_from_feishu` |
| `quality.run_change_action_plan_reminders` | 普通写入 | 空 | `change_action_plan.run_change_action_plan_reminders_now` |
| `quality.send_change_action_plan_reminder` | 普通写入 | `plan_id` | `change_action_plan.send_change_action_plan_reminder_for_plan` |

### 验证

| Operation | 类型 | InputSchema | Service |
| --- | --- | --- | --- |
| `quality.list_validations` | 查询 | 验证筛选 + 分页 | `validation.get_validation_list` |
| `quality.get_validation` | 查询 | `validation_id` | `validation.get_validation_detail` |
| `quality.get_validation_statistics` | 查询 | 空 | `validation.get_validation_statistics` |
| `quality.list_validation_executions` | 查询 | `validation_type` + 筛选分页 | `validation.get_validation_execution_list` |
| `quality.create_validation` | 普通写入 | `CreateValidationRequest` | `validation.create_validation` |
| `quality.update_validation` | 普通写入 | `validation_id` + `UpdateValidationRequest` | `validation.update_validation` |
| `quality.update_validation_execution` | 普通写入 | `validation_type` + `record_id` + `UpdateValidationExecutionRequest` | `validation.update_validation_execution` |

### CPV

| Operation | 类型 | InputSchema | Service |
| --- | --- | --- | --- |
| `quality.list_cpv_products` | 查询 | keyword/status/page/page_size | `cpv_product.get_products` |
| `quality.get_cpv_product` | 查询 | `product_id` | `cpv_product.get_product_by_id` |
| `quality.create_cpv_product` | 普通写入 | `CpvProductCreate` | `cpv_product.create_product` |
| `quality.update_cpv_product` | 普通写入 | `product_id` + `CpvProductUpdate` | `cpv_product.update_product` |
| `quality.list_cpv_parameters` | 查询 | `product_id` + 参数筛选 | `cpv_parameter.get_parameters` |
| `quality.create_cpv_parameter` | 普通写入 | `product_id` + `CpvParameterCreate` | `cpv_parameter.create_parameter` |
| `quality.update_cpv_parameter` | 普通写入 | `parameter_id` + `CpvParameterUpdate` | `cpv_parameter.update_parameter` |
| `quality.list_cpv_batches` | 查询 | `product_id` + 批次筛选分页 | `cpv_batch.get_batches` |
| `quality.list_cpv_cpp_batches` | 查询 | `product_id` + 批次筛选分页 | `cpv_batch.get_batches_wide` |
| `quality.list_cpv_cqa_batches` | 查询 | `product_id` + 批次筛选分页 | `cpv_batch.get_batches_wide` |
| `quality.get_cpv_statistics` | 查询 | `product_id` + `parameter_id` + 筛选 | `cpv_statistics.get_statistics` |
| `quality.get_cpv_trend` | 查询 | `product_id` + `parameter_id` + 筛选 | `cpv_statistics.get_trend_data` |

### 飞书只读与同步

| Operation | 类型 | InputSchema | Service |
| --- | --- | --- | --- |
| `quality.list_quality_sync_conflicts` | 查询 | limit | `quality_feishu_sync.get_quality_sync_conflicts` |
| `quality.pull_quality_records_from_feishu` | 普通写入 | optional `entity_code` | `quality_feishu_sync.pull_quality_records_from_feishu` |
| `quality.sync_deviation_to_feishu` | 普通写入 | `deviation_id` | `quality_feishu_sync.sync_deviation_to_feishu` |
| `quality.sync_deviation_report_record_to_feishu` | 普通写入 | `deviation_id` + optional `target_record_id` | `quality_feishu_sync.sync_deviation_report_record_to_feishu` |
| `quality.sync_capa_to_feishu` | 普通写入 | `capa_id` | `quality_feishu_sync.sync_capa_to_feishu` |
| `quality.sync_capa_plan_track_to_feishu` | 普通写入 | `track_id` | `quality_feishu_sync.sync_capa_plan_track_to_feishu` |
| `quality.list_feishu_capa_ledger` | 查询 | CAPA 台账筛选分页 | `feishu_capa.list_capa_ledger` |
| `quality.get_feishu_capa_ledger` | 查询 | `record_id` | `feishu_capa.get_capa_ledger_record` |
| `quality.list_feishu_capa_plan_tracks` | 查询 | keyword/page/page_size | `feishu_capa.list_capa_plan_tracks` |
| `quality.get_feishu_capa_plan_track` | 查询 | `record_id` | `feishu_capa.get_capa_plan_track_record` |
| `quality.list_feishu_validations` | 查询 | 验证筛选分页 | `quality_feishu_pages.list_validation_records_from_feishu` |
| `quality.get_feishu_validation` | 查询 | `record_id` + optional `validation_type` | `quality_feishu_pages.get_validation_record_from_feishu` |
| `quality.pull_feishu_validations` | 普通写入 | optional `validation_type` | `quality_feishu_pages.pull_validation_records_from_feishu` |

## 测试与验收

后端：

```text
uv run pytest tests/modules/agent tests/modules/quality
```

Hermes-Lite：

```text
python -m py_compile run_agent.py model_tools.py toolsets.py services/dazah_agent_service.py tools/dazah_platform.py
```

验收点：

- `ensure_agent_tools_registered()` 后质量 operation 可发现。
- 查询类工具直接执行。
- 普通写入工具首次执行返回 `requires_confirmation=True`。
- 人工责任工具不可编排或被策略拒绝。
- Hermes-Lite `ALLOWED_OPERATIONS` 与后端注册清单一致。
- 未修改数据库模型、未新增迁移、未改变质量模块现有 REST API。

## 最终验收结果

- 后端已通过 `app.modules.quality.agent_tools` 注册 68 个 `quality.*` operation。
- Hermes-Lite `ALLOWED_OPERATIONS` 已同步 68 个质量 operation，并更新 `dazah_tool` 描述与 README 工具清单。
- 写入类工具保持 `write=True` 与确认项机制；删除、审批/驳回、飞书配置管理、导入上传未接入。
- `uv run pytest tests/modules/agent tests/modules/quality -q` 通过：157 passed, 41 warnings。
- Hermes-Lite `python -m py_compile run_agent.py model_tools.py toolsets.py services/dazah_agent_service.py tools/dazah_platform.py` 通过。
- 本次未修改数据库模型、未新增迁移、未修改 Agent API schema，因此未导出 OpenAPI、未生成前端类型。
- 工作区根路径不是 Git 仓库，无法生成 `git diff` 作为收尾依据；已通过关键文件存在性、注册入口检索、Hermes 白名单检索和测试结果完成审查。
- 收尾后追踪到配置被重置的根因：质量模块既有 pytest 用例会对 `quality_feishu_app_settings` 与 `quality_feishu_entity_settings` 执行 `DELETE` 并 `commit`，而测试夹具直接使用 `DATABASE_URL`。已增加 pytest 数据库安全保护，要求测试使用独立测试库。
- 截图复核发现 Livzon 助手仍按仓储飞书同步表回答质量问题。根因是 Hermes-Lite 系统提示、默认 `business_scope` 和前端浮窗 scope 仍只覆盖仓储/采购，模型没有被明确引导到 `quality.*` operation。已补充质量模块路由提示、合并默认业务范围并扩展前端 scope。
- 运行时复核发现：即使后端、Hermes 白名单和前端 scope 均包含质量模块，模型仍可能不调用工具并回答仓储飞书表目录。已在 Hermes-Lite 增加“质量模块报告记录/质量报告记录/偏差报告记录”的确定性预路由，直接通过 `dazah_tool` 调用 `quality.list_deviation_report_records`，仍走 Dazah 后端 Agent 工具网关。
- 复测 `Hermes-Lite /v1/chat` 与 `/v1/chat/stream` 均通过：`tool_trace` 包含 `quality.list_deviation_report_records`，返回偏差报告记录，旧的 `finished_product/hardware/materials_packaging` 仓储表回答不再出现。
- 后端 Agent 代理层同步修复：`AgentService._call_hermes()` 与 `_call_hermes_stream()` 不再把上下文 scope 固定覆盖为仓储/采购，而是传递 `identity/warehouse/procurement/quality`。复测后端 `/api/v1/agent/chat/stream` 完整链路通过，返回同一质量工具 trace。
- 前端 Livzon 助手浮窗同步去除“仓储 / 采购”窄范围标识，欢迎语、快捷入口和输入占位改为全平台 Agent 表达，覆盖质量、仓储、采购、通讯录和工作流。

## 变更记录

| 时间 | 阶段 | 内容 |
| --- | --- | --- |
| 2026-07-06 | 阶段 0 | 创建规格文档，记录范围、风险规则、后端/Hermes 设计和验收标准。 |
| 2026-07-06 | 阶段 0 | 阶段 0 完成，进入阶段 1 接口整理。 |
| 2026-07-06 | 阶段 1 | 固化偏差、CAPA、变更、验证、CPV、飞书只读/同步 operation 清单。 |
| 2026-07-06 | 阶段 1 | 阶段 1 完成，进入阶段 2 后端 Agent tools 注册。 |
| 2026-07-06 | 阶段 2 | 新增 `app/modules/quality/agent_tools.py` 并在 Agent 注册入口导入质量工具。 |
| 2026-07-06 | 阶段 2 | 后端工具编译通过，注册表发现 68 个 `quality.*` operation。 |
| 2026-07-06 | 阶段 2 | 阶段 2 完成，进入阶段 3 Hermes-Lite 接入。 |
| 2026-07-06 | 阶段 3 | 更新 Hermes-Lite `ALLOWED_OPERATIONS`，加入 68 个质量工具。 |
| 2026-07-06 | 阶段 3 | 更新 Hermes-Lite 工具描述与 README 质量模块工具清单。 |
| 2026-07-06 | 阶段 3 | Hermes-Lite 编译检查通过，白名单质量工具数量为 68。 |
| 2026-07-06 | 阶段 3 | 阶段 3 完成，进入阶段 4 测试与验证。 |
| 2026-07-06 | 阶段 4 | 新增质量 Agent 工具契约测试，覆盖注册、确认项、工作流能力与 Hermes 白名单一致性。 |
| 2026-07-06 | 阶段 4 | 修复质量报告记录飞书不可用时本地兜底，以及飞书表选项接口测试替身兼容问题。 |
| 2026-07-06 | 阶段 4 | `uv run pytest tests/modules/agent tests/modules/quality -q` 通过：157 passed, 41 warnings。 |
| 2026-07-06 | 阶段 4 | Hermes-Lite `python -m py_compile ...` 通过。 |
| 2026-07-06 | 阶段 4 | 阶段 4 完成，进入阶段 5 收尾审查。 |
| 2026-07-06 | 阶段 5 | 回读 spec 与 tasks，核对关键文件、注册入口和 Hermes-Lite 质量 operation。 |
| 2026-07-06 | 阶段 5 | 确认根路径不是 Git 仓库，最终审查以文件检索、编译和测试结果为准。 |
| 2026-07-06 | 阶段 5 | 全部阶段完成，记录最终验收结果。 |
| 2026-07-06 | 后续修复 | 增加 pytest 数据库安全保护，避免测试误连开发库导致质量飞书配置表被清空/回填。 |
| 2026-07-06 | 后续修复 | 修复 Livzon 助手质量模块路由：Hermes 系统提示、skill resolver scope、toolset 描述和前端浮窗 scope 均纳入 quality。 |
| 2026-07-06 | 后续修复 | 增加 Hermes-Lite 质量报告记录确定性预路由，并通过非流式/流式实际接口验证命中 `quality.list_deviation_report_records`。 |
| 2026-07-06 | 后续修复 | 修复后端 Agent 调 Hermes 时覆盖 scope 为仓储/采购的问题，并通过 `/api/v1/agent/chat/stream` 完整链路复测。 |
| 2026-07-06 | 后续修复 | 根据浏览器标注更新前端 Livzon 助手浮窗文案，移除仓储/采购窄范围标识并改为全平台 Agent。 |
