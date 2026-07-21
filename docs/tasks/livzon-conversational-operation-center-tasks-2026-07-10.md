# Livzon 对话式智能运营中枢实施总账

> 来源：`docs/livzon-conversational-operation-center-spec-2026-07-10.md` v1.1  
> 建立时间：2026-07-10  
> 执行方式：严格按 Phase 0 至 Phase 5 顺序实施；阶段状态、关键决策、代码变更和验证证据在本文件持续更新。  
> 当前阶段：全部 Phase 0–5 已完成

## 状态说明

- `未开始`：尚未进入该阶段。
- `进行中`：正在实现，尚未满足本阶段验收条件。
- `已完成`：代码、迁移、测试、OpenAPI/前端类型和阶段验收均已通过。
- `受阻`：存在无法在当前仓库或当前权限内解决的外部依赖，必须记录证据和恢复条件。

## 阶段总览

| 阶段 | 状态 | 目标 | 阶段验收 |
|---|---|---|---|
| Phase 0 契约冻结与安全基础 | 已完成 | 建立授权事实、Livzon 范围、Schema、安全与审计基础 | 管理员可授权并看到同步结果；用户只读本人范围；工作流可离线编译校验 |
| Phase 1 持久化自动化与对话查看 | 已完成 | 建立自动化领域对象、查询 API、对话工具和 artifact | 用户/管理员视图由服务端裁剪，业务载荷按权限脱敏 |
| Phase 2 可靠定时执行 | 已完成 | 建立持久化触发、幂等领取、恢复、重试与权限复验 | 多实例不重复、重启可恢复、撤权后自动暂停 |
| Phase 3 飞书投递与闭环 | 已完成 | 建立投递记录、身份解析、去重、对账和卡片回写 | 不重复发送、不越权查看、管理员可定位脱敏失败信息 |
| Phase 4 跨模块事件编排 | 已完成 | 以采购到货—仓储入库为试点建立版本化事件闭环 | 编排器不依赖模块内部实现，单一 correlation ID 可追踪全链路 |
| Phase 5 运营优化 | 已完成 | 健康评分、趋势、模板、子流程与运营报告 | 优化建议有运行证据，任何定义修改仍需所有者确认 |

## Phase 0：契约冻结与安全基础

状态：已完成

- [x] 盘点现有身份、权限、Agent 工具、审计、调度、Outbox 和迁移基线。
- [x] 固化普通用户/管理员查看矩阵与敏感字段规则。
- [x] 建立 `identity.user_module_grants` 授权事实模型、版本并发控制和针对性迁移。
- [x] 建立授权管理 Service、管理员 API、可授权边界校验和授权变更审计。
- [x] 建立授权 Outbox 事件及重试状态。
- [x] 建立 `core.agent_access_scope_snapshots` 派生快照、范围解析器和同步 Service。
- [x] 在对话、工具调用入口加入授权版本 fail-closed 校验。
- [x] 定义 Automation Schema v1、受限条件 DSL、状态枚举和稳定错误码。
- [x] 扩展 `AgentToolSpec` 兼容元数据，并保持现有工具可注册。
- [x] 建立统一 `correlation_id` 与递归敏感字段脱敏组件。
- [x] 补齐用户读取本人范围、管理员读取/修改授权和敏感治理查看审计。
- [x] 增加单元、集成与安全测试。
- [x] 导出后端 OpenAPI，并生成前端 API 类型。
- [x] 实现管理员用户详情中的模块权限与 Livzon 同步状态区域。
- [x] 完成阶段验收并记录证据。

## Phase 1：持久化自动化与对话查看

状态：已完成

- [x] 新增 Automation、Version、Trigger、Run、StepRun、RunEvent 模型和针对性迁移。
- [x] 实现个人、共享和管理员治理查询 Service。
- [x] 实现授权版本变化后的定义重校验与字段脱敏。
- [x] 实现列表、详情、版本、计划触发、运行和事件时间线 API。
- [x] 实现创建草案、预览、确认、修改、启停、归档和查询 Agent 工具。
- [x] 扩展消息 artifact 契约并完成结构化卡片渲染。
- [x] 建立 AgentWorkflow 向新模型的兼容适配。
- [x] 完成阶段测试、OpenAPI、前端类型和验收。

## Phase 2：可靠定时执行

状态：已完成

- [x] 实现 `AgentAutomationGenerator` 并接入现有 SchedulerEngine。
- [x] 持久化 `next_fire_at`、原子领取和触发幂等键。
- [x] 实现错过触发 `run_once/skip` 策略。
- [x] 实现 `forbid/queue_one/allow` 并发策略。
- [x] 实现步骤超时、幂等感知重试、指数退避与连续失败隔离。
- [x] 运行前使用 acting user 复验账户、授权版本和模块范围。
- [x] 实现模拟运行与未来执行时间预览。
- [x] 完成多实例、重启恢复、撤权暂停和阶段验收。

## Phase 3：飞书投递与闭环

状态：已完成

- [x] 新增 PushDelivery 与模板版本记录和迁移。
- [x] 按本地用户身份映射在运行时解析飞书接收人。
- [x] 实现发送幂等、聚合、静默、重试、失败对账和恢复通知。
- [x] 实现交互卡片签名、过期、身份、权限校验及 RunEvent 回写。
- [x] 实现我的推送与管理员投递健康查询。
- [x] 完成不重复发送、接收人隔离、脱敏诊断和阶段验收。

## Phase 4：跨模块事件编排

状态：已完成

- [x] 定义并实现通用版本化事件信封与最小载荷校验。
- [x] 以采购到货—仓储入库链路发布和消费 v1 业务事件。
- [x] 实现 `event_wait`、人工待办和恢复通知节点。
- [x] 实现能力版本弃用影响扫描和迁移提示。
- [x] 验证编排器只调用注册 operation/public API，不导入模块内部实现。
- [x] 完成 correlation ID 全链路查询和阶段验收。

## Phase 5：运营优化

状态：已完成

- [x] 实现任务健康度评分和无效任务识别。
- [x] 实现误报、失败、积压和重复推送趋势分析。
- [x] 实现自动化模板与可复用子流程。
- [x] 实现管理员自然语言运营报告。
- [x] 基于历史运行生成可解释优化建议，并保持所有修改需确认。
- [x] 完成非功能指标、全量安全回归和最终完成定义验收。

## 实施日志

### 2026-07-10

- 已完整读取根目录、前端、后端开发规范和前端设计规范。
- 已完整读取 Spec v1.1，并锁定 Phase 0–5 的实现顺序和完成定义。
- 已确认仓库工作树初始无已知修改；当前环境的 `git` 命令不可用，后续使用文件清单、哈希和测试结果记录变更证据。
- 正在盘点现有实现，尚未修改产品代码或数据库迁移。
- 已新增授权事实模型、授权 Outbox、Livzon 范围快照、同步生成器和 Alembic 迁移 `9df06f2aa79b`；真实 Alembic head 已确认原为 `b6e4d2f9a1c3`。
- 已新增模块授权管理 API、本人 Livzon 范围 API 和 `agent.get_my_access_scope` 工具。
- 已在聊天入口、业务工具执行、确认执行和 legacy workflow 创建/运行入口加入当前授权版本与可编排范围复验。
- 已完成 Automation Schema v1、受限条件 DSL、能力编译报告、工具兼容元数据和递归脱敏组件。
- 已使用项目 Python 3.13 完成应用导入检查；Ruff 首轮发现 9 个格式问题，正在修复后复检。
- Phase 0 已完成：授权事实、版本并发、Outbox、范围同步、fail-closed、自动化契约、安全审计、管理员界面和 Hermes-Lite 适配均已落地。
- Phase 1 已切换为进行中；下一实施断点为 Automation、Version、Trigger、Run、StepRun、RunEvent 模型与针对性迁移。
- Phase 1 正在实现自动化持久化模型、版本化定义和服务端范围查询；旧 `AgentWorkflow` 保持兼容，不迁移或改写既有记录。
- Phase 1 已完成 Automation Schema 到草案/确认/查询工具的服务层接入，并新增对话 artifact 卡片渲染；当前受环境限制，尚待 Alembic 迁移生成与后端集成测试执行。
- Phase 1 已同步 Hermes-Lite 的本地 operation 白名单、模型提示词和工具清单，模型不能绕过后端确认链路执行自动化写操作。
- Phase 1 已完成：新增自动化、版本、触发、运行、步骤运行和运行事件模型；迁移由 Alembic 自动生成 revision `12491ff54d46`，并以追加 revision `417414f45ad9` 补齐运行错误码索引。
- 已完成个人、共享与管理员平台范围查询；共享/平台非所有者只获取脱敏定义、策略快照、运行和步骤载荷。撤销 `module.agent.automate` 后，重新启用会返回 403 并将对象置为 `suspended_policy`。
- 已实现旧 `AgentWorkflow` 的只读双轨适配：新自动化查询、详情和版本查询可展示旧对象的兼容摘要与 `legacy-agent-workflow-v1` 版本；旧写入和运行接口保持不变。
- 已恢复项目 Python 执行环境，完成迁移往返、后端集成测试、OpenAPI 导出、前端类型生成和 Hermes-Lite 编译验证。
- Phase 0 复测完成：重新按阶段验收目标验证管理员授权与范围同步、匿名 fail-closed、权限规范化、离线 Automation Schema 编译、敏感字段脱敏与相关安全拒绝行为。
- Phase 2 已开始：复用 `SchedulerEngine` 与 `TaskGenerator`，不新增独立调度框架；本阶段将以数据库领取、稳定幂等键和运行前范围复验实现多实例可靠执行。
- Phase 2 已接入 `AgentAutomationGenerator`：定时触发以 `next_fire_at` 持久化，使用 `FOR UPDATE SKIP LOCKED` 领取，按自动化版本和触发窗口生成唯一幂等键；运行记录同时保存服务主体、责任主体与触发主体。
- Phase 2 已实现 Cron 时区校验、下一次触发计算和未来窗口预览，并提供自动化详情 API 与对话工具入口；错过窗口支持 `run_once`（默认）和 `skip`。
- Phase 2 已实现并发策略：创建运行时锁定自动化记录，`forbid` 跳过、`queue_one` 合并排队、`allow` 并行；每次执行前用最新责任主体重新解析 Livzon 范围并重新编译版本快照，撤权后置为 `suspended_policy`。
- Phase 2 已实现超时与失败治理：步骤使用 operation/步骤级超时；仅 `idempotent=true` operation 以指数退避加随机抖动重试，非幂等写操作不自动重试；连续失败达到阈值后自动隔离为 `quarantined`。
- Phase 2 已实现领取租约恢复：正常创建不可变 Run 后清除 Trigger 领取标记；若进程在此之前退出，租约过期会把原触发窗口重新放回队列，稳定幂等键仍确保最多创建一个 Run。
- Phase 2 已完成：新增两个独立数据库会话的 `SKIP LOCKED` 竞争验收；第一个调度实例持有触发器行锁时，第二个实例无法领取同一窗口。重启租约恢复和撤权自动暂停也已由专项测试覆盖。
- Phase 3 已开始：复用平台身份模块的飞书本地用户映射、消息发送和已认证卡片回调；Agent 模块新增独立投递事实、重试与运行事件，不让业务模块间直接耦合。
- Phase 3 首批已完成：新增 `AgentPushTemplateVersion` 和逐收件人的 `AgentPushDelivery`；`notify` 节点在运行时解析固定用户、责任人字段、部门负责人或受限角色范围，并使用本地用户到 `feishu_open_id` 的当前映射发送。
- Phase 3 首批已完成：每条投递使用运行、步骤、模板版本和收件人组成稳定幂等键；发送失败最多 3 次指数退避。模板变量和投递摘要在渲染前统一脱敏，投递完成写入 `AgentRunEvent`。
- Phase 3 闭环已接入：`AgentPushDeliveryGenerator` 以 `FOR UPDATE SKIP LOCKED` 领取到期重试，并把已认证的飞书卡片动作按外部消息 ID 对账回投递状态和 `RunEvent`。卡片回调现在额外校验原收件人 open ID 及本地账户可用状态。
- Phase 3 查询已接入：`GET /agent/push-deliveries`、`GET /agent/push-deliveries/{id}` 和对应 Agent 工具按服务端身份裁剪；普通用户只读自己的投递，管理员仅获取全局脱敏元数据。Hermes-Lite 白名单、提示词与工具清单已同步。
- Phase 3 已完成：`notify` 节点新增可持久化审计的 `aggregation_key`、聚合窗口、`incident_key` 与带时区的 `silence_until`；静默或同窗口同收件人的同类消息均保留为 `suppressed` 投递事实而不发送。
- Phase 3 已完成：发送结果只要带有飞书外部消息 ID 即视为已接受并写入 `push_external_message_reconciled`，不再盲目重试；最终失败写入 `push_delivery_failed`，同一 `incident_key` 后续成功会发送恢复前缀并写入 `push_recovery_sent`。
- Phase 3 阶段验收完成：专项测试覆盖稳定幂等键、运行时收件人映射、重试、聚合、静默、网关超时后的外部消息 ID 对账、失败恢复、卡片回写、跨用户拒绝及管理员脱敏读取；协议与前端生成类型已同步。
- Phase 4 已开始：选定“采购到货—仓储入库”作为跨模块试点；将通过 Agent 模块的版本化事件信封和业务模块公开事件入口解耦，编排器不会导入采购或仓储的内部 Service/Model。
- Phase 4 首批已完成：新增 `core.agent_domain_events` 与 `DomainEventEnvelope`，强制来源模块、版本化事件名、主体、稳定幂等键、correlation ID 和最小摘要载荷；载荷在持久化前统一脱敏。
- Phase 4 首批已完成：事件服务按 `data_event/platform_event` 触发器和确定性精确过滤创建幂等运行；`event_wait` 节点将运行置为等待状态，并在同一 correlation ID 的匹配事件到达后可靠恢复到队列。跨模块调用仅经 `app.modules.agent.public_api.publish_domain_event`。
- Phase 4 已完成：采购模块通过 `procurement.public_api.publish_purchase_arrival` 发布 `procurement.purchase_arrival.v1` 最小事件；消费者由事件触发自动化按已注册的仓储 operation 继续执行，编排器不导入采购/仓储内部实现。
- Phase 4 已完成：新增 `manual_task` 节点和 `agent.complete_manual_task` 确认工具；待办完成后将运行重新入队。事件等待恢复、人工待办完成和既有同 incident 恢复推送均写入运行时间线。
- Phase 4 已完成：新增能力影响扫描、`GET /agent/automation-capability-impacts`、`GET /agent/domain-events/{correlation_id}` 及对应对话工具；扫描移除、弃用或主版本不兼容能力，并为所有者/管理员返回迁移提示。
- Phase 5 已开始：新增基于原始 AutomationRun、PushDelivery 的健康评分、无效任务识别、失败/积压/抑制推送趋势、静态可复用模板与子流程清单、管理员中文运营报告和可解释优化建议；建议仅提示，任何修改仍经所有者确认链路。
- Phase 5 已完成：健康评分以近 30 天运行失败、等待积压、隔离/策略暂停和无运行证据为依据；趋势、模板、管理员报告和建议均通过 Agent API/工具可查询，建议始终标记为需要所有者确认，不会自动修改定义。
- 验收后授权修复：发现 `identity.user_module_grants` 此前仅用于 Livzon Agent 范围，业务模块路由未消费该授权事实，导致普通用户可直接访问未授权模块。已在 API 路由挂载层统一加入 fail-closed 的 `module.view` 校验，覆盖生产、设备、安全、环保、能源、仓储、产品、采购、行政、人事、研发、注册、质量、法规追踪和资料撰写；未登录返回 401，缺少有效授权返回 403。
- 授权体验补全：`GET /identity/me` 现在仅返回当前账号拥有有效 `module.view` 的 `module_codes`；顶部模块标签、左侧模块导航和直达模块页面均按该清单过滤/拦截。未授权的直达页面不再渲染业务内容，而显示无权限提示；管理员仍可从提示前往系统设置。研发、行政、采购等历史前端路由键已明确映射至 `research`、`administration`、`procurement` 授权码。
- 管理员默认权限：`role=admin` 现在拥有隐式的全模块权限，不依赖逐条 `user_module_grants` 记录；权限管理抽屉默认勾选全部模块权限，当前用户接口返回全部模块代码，业务路由直接放行管理员。Livzon 为管理员重建全模块、全 Agent 权限的范围快照；若管理员角色变更，`grant_version` 递增使既有范围快照失效并重建。
- 飞书卡片发送修复：统一消息接口现在尊重调用方显式指定的 `message_form=card`，不再因低价值、非结构化消息的默认策略拒绝卡片并退回文本；仅含业务处理按钮的消息继续强制使用 `interactive_card`。Hermes-Lite 同步要求卡片意图传入标题和 Markdown，并禁止在未收到后端真实结果时编造“卡片格式验证失败、已降级文本”。

## 验证证据

- `alembic heads/current`：专用 `dazah_test` 均为唯一 head `9df06f2aa79b`。
- 迁移往返：`9df06f2aa79b -> b6e4d2f9a1c3 -> 9df06f2aa79b` 成功。
- Phase 0 专属 drift 过滤：`agent_access_scope_snapshots`、`user_module_grants`、`permission_outbox_events`、`grant_version` 和 `agent_tool_calls.correlation_id` 均无差异。
- 全仓 `alembic check` 仍因产品、质量、仓储等既有基线差异失败；未把任何无关差异写入本次迁移。
- 后端 Ruff：所有 Phase 0 变更文件通过。
- Agent 回归：`59 passed`；新增 Phase 0 单元、集成与安全测试单独执行 `11 passed`。
- 前端：OpenAPI 类型生成成功，`tsc --noEmit` 通过，目标 ESLint 通过且无警告。
- Hermes-Lite：`services/dazah_agent_service.py` 与 `tools/dazah_platform.py` 通过 `py_compile`。
- OpenAPI：UTF-8 导出成功；已同步 `dazah-frontend/src/types/generated/openapi.json` 与 `schema.ts`。
- Phase 1 静态检查：`ruff check` 通过 `models.py`、`schemas.py`、`repository.py`、`automation_service.py`、`api.py` 和 `agent_tools.py`。此前受限终端曾阻止项目 Python 3.13 启动；环境恢复后已完成 Alembic、pytest 和 OpenAPI 导出，最终结果见以下证据。
- Phase 1 迁移：`dazah_test` 从 `9df06f2aa79b` 降级再升级至唯一 head `417414f45ad9` 成功；两张 Phase 1 migration 的 upgrade/downgrade 均通过。
- Phase 1 drift：全仓 `alembic check` 仍报告既有产品、质量、仓储等基线差异；针对 `agent_automations`、`agent_automation_versions`、`agent_automation_triggers`、`agent_automation_runs`、`agent_step_runs` 和 `agent_run_events` 的过滤结果为 `PHASE1_DRIFT=none`。
- Phase 1 测试：`tests/modules/agent/test_phase_one_automation.py` 为 `4 passed`；`tests/modules/agent` 全量回归为 `65 passed`。测试仅有既有 Pydantic/第三方库 deprecation warnings。
- Phase 1 前端与协议：OpenAPI UTF-8 导出成功，已同步 `dazah-frontend/src/types/generated/openapi.json` 与 `schema.ts`；`tsc --noEmit`、目标 ESLint 通过。
- Phase 1 Hermes-Lite：`ruff check` 与 `py_compile` 通过 `services/dazah_agent_service.py` 和 `tools/dazah_platform.py`。
- Phase 0 复测：`tests/modules/agent/test_phase_zero_foundation.py` 为 `11 passed`，覆盖管理员为用户分配模块权限并同步 Livzon 范围、用户范围 fail-closed、离线工作流编译、敏感字段递归脱敏、授权并发/自我提权拒绝与工具元数据兼容。测试仅输出既有 Pydantic/第三方库 deprecation warnings。
- Phase 0 管理界面复测：`dazah-frontend` 的 `tsc --noEmit` 与 `src/actions/users.ts`、`ModulePermissionsDrawer.tsx`、`UserManagementClient.tsx` ESLint 均通过。
- Phase 0 Hermes 复测：`services/dazah_agent_service.py`、`tools/dazah_platform.py` 的 `py_compile` 与 Ruff 通过。复测时 `dazah_test` 的 Alembic head/current 均为 `417414f45ad9`。
- Phase 2 迁移：Alembic 自动生成 `1420c504cb74_add_automation_scheduler_state.py`，`dazah_test` 已升级至唯一 head `1420c504cb74`；该迁移新增触发领取租约、运行计划/重试/主体字段、失败隔离状态及重试索引。
- Phase 2 专项测试：`ruff check` 通过调度执行器与专项测试；`tests/modules/agent/test_phase_two_scheduler.py` 为 `12 passed`，覆盖双独立数据库会话的多实例竞争、幂等领取、执行快照、领取租约恢复、漏跑 `skip`、三种并发策略、幂等/非幂等失败分流、连续失败隔离、撤销质量模块自动化权限后的自动暂停和未来 Cron 窗口预览。测试仅输出既有 Pydantic/第三方库 deprecation warnings。
- Phase 2 Agent 回归：`tests/modules/agent` 全量为 `77 passed`；仅输出既有 Pydantic/第三方库 deprecation warnings。
- Phase 2 迁移与协议：`alembic heads/current` 均为唯一 `1420c504cb74 (head)`；OpenAPI 已以 UTF-8 重新导出，前端 `pnpm generate:api` 与 `pnpm typecheck` 均通过。OpenAPI 导出仍提示既有 research pilot workflow operation ID 重复警告，未修改与本阶段无关的模块。
- Phase 3 首批迁移：Alembic 自动生成并经审查后保留专用 revision `ee31e7997cde_add_agent_push_deliveries.py`；`dazah_test` 当前为 `ee31e7997cde (head)`。自动生成发现的其他模块既有 drift 已全部从该迁移移除。
- Phase 3 首批验证：`ruff check` 通过模型、执行器、投递服务、迁移和专项测试；`tests/modules/agent/test_phase_three_push_deliveries.py` 为 `1 passed`，覆盖运行时本地收件人解析、单收件人幂等投递、模板版本持久化、RunEvent 写入与敏感变量脱敏。测试仅输出既有 Pydantic/第三方库 deprecation warnings。
- Phase 3 闭环验证：专项测试继续通过，覆盖到期重试、卡片动作对账回写为 `interacted`、跨用户读取拒绝；Ruff 与 Hermes `py_compile` 通过。
- Phase 3 最终验收：`tests/modules/agent/test_phase_three_push_deliveries.py` 为 `1 passed`，覆盖稳定幂等键、收件人隔离、管理员脱敏、聚合窗口、静默期、失败重试、带 `message_id` 的超时对账和同一 `incident_key` 的恢复通知；`tests/modules/agent` 全量回归为 `78 passed`。测试仅输出既有 Pydantic/第三方库 deprecation warnings。
- Phase 3 迁移与协议：`alembic heads/current` 均为唯一 `ee31e7997cde (head)`；OpenAPI 已以 UTF-8 导出，前端 `pnpm generate:api` 与 `pnpm typecheck` 均通过；Hermes-Lite 两个适配文件通过 `py_compile`。OpenAPI 导出仍仅提示既有 research pilot workflow operation ID 重复警告，未修改无关模块。
- Phase 4 首批迁移与测试：专用 migration `6c9b3dc4b141_add_agent_domain_events.py` 已审查并仅创建 `core.agent_domain_events`；`dazah_test` 已升级到唯一 head `6c9b3dc4b141`。`tests/modules/agent/test_phase_four_events.py` 为 `1 passed`，覆盖事件信封 Schema、载荷脱敏、发布幂等、触发器筛选、运行 correlation ID 继承和 `event_wait` 恢复；相关 Ruff 检查通过。测试仅输出既有 Pydantic/第三方库 deprecation warnings。
- Phase 4 首批回归：`tests/modules/agent` 全量为 `79 passed`；仅输出既有 Pydantic/第三方库 deprecation warnings。
- Phase 4 最终验收：专项测试覆盖采购到货公开事件、事件幂等、触发过滤、correlation ID 继承与查询、`event_wait` 恢复、人工待办完成恢复、敏感载荷脱敏和能力主版本影响扫描；`tests/modules/agent` 全量为 `79 passed`。OpenAPI 已以 UTF-8 导出，前端 `pnpm generate:api`、`pnpm typecheck` 与 Hermes-Lite `py_compile` 均通过。迁移唯一 head 保持 `6c9b3dc4b141`；仅有既有 Pydantic/第三方库 warnings 与既有 research pilot workflow operation ID 重复警告。
- Phase 5 最终验收：`tests/modules/agent/test_phase_five_operations.py` 为 `1 passed`，覆盖健康评分、失败/等待趋势、可解释且需确认的建议、模板清单、管理员中文报告及普通用户拒绝管理员报告；`tests/modules/agent` 全量为 `80 passed`。Ruff、OpenAPI UTF-8 导出、前端 `pnpm generate:api`/`pnpm typecheck` 和 Hermes-Lite `py_compile` 均通过。`alembic heads/current` 保持唯一 `6c9b3dc4b141 (head)`；仅有既有 Pydantic/第三方库 warnings 与既有 research pilot workflow operation ID 重复警告。
- 授权修复回归：新增 `tests/integration/test_module_access_control.py`，在专用 `dazah_test` 数据库验证未登录请求为 401、普通用户无仓储授权为 403、授予仓储 `module.view` 后仓储接口为 200、同一用户访问生产模块仍为 403；Ruff 检查通过。已重启本地后端容器，运行中 `GET /api/v1/warehouse/` 的匿名请求确认返回 401。
- 授权体验回归：`tests/integration/test_module_access_control.py` 新增当前用户授权清单验证，确保只有带 `module.view` 的有效授权被返回（`2 passed`）；后端 Ruff/编译、OpenAPI 导出、前端 API 类型生成、`pnpm typecheck` 和目标 ESLint 均通过。Livzon 继续使用相同授权事实生成范围快照，并在聊天和工具调用前 fail-closed 复验。
- 管理员默认权限回归：同一专项集成测试扩展为 `3 passed`，验证无显式授权记录的管理员可访问业务模块、登录态返回全部模块、Livzon 范围覆盖所有登记模块且包含自动化权限、权限管理读取默认全勾选；后端 Ruff 与编译通过。
- 飞书卡片发送回归：`tests/unit/test_identity_feishu_messages.py` 为 `23 passed`，新增低价值非结构化消息显式指定 `card` 时经卡片发送器派发的断言；同时回归原收件人卡片动作与本地活跃账户校验。后端 Ruff、`compileall` 和 Hermes-Lite 的 `py_compile` 均通过；测试仅输出既有 Pydantic/第三方库 deprecation warnings。
- 飞书卡片修复运行态验证：已重启 `dazah-backend-app-1` 与 `hermes-lite`；后端和 Hermes 的 `/health` 均返回 `200 {"status":"ok"}`，后端日志确认飞书卡片长连接已建立。

## 决策与偏差

- 兼容决策：现有系统没有独立 `permission_admin` 资格字段，Phase 0 暂以既有 `role=admin` 作为权限管理员资格，并禁止管理员修改自己的模块授权，避免自我提权。后续若身份模型新增独立资格，Service 校验点可直接替换。
- 数据模型决策：用户当前 `grant_version` 保存于 `identity.users`，每个模块授权行同时记录生效版本；这样即使用户当前没有任何模块授权，也能可靠表达撤权后的新版本并使旧 Livzon 快照失效。
- 同步决策：授权保存与 Outbox 同事务；请求内尝试即时同步，失败则提交授权事实和失败 Outbox，旧快照保持过期且 fail-closed，后台生成器按指数退避重试。
