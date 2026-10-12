# Livzon 平台基础与功能补齐计划

创建日期：2026-10-09；更新日期：2026-10-10。权限修复、后端授权联动、设置工具关闭、全工具盘点，以及阶段二能力范围、运行诊断和安全重试已完成本地实现与定向回归。本机 Web 已验证真实登录、分配角色来源、实时目录、运行恢复说明及窄屏布局；完整模型编排对话与飞书真实客户端尚未验收。继续按平台基础、既有业务深化、新模块接入、运营与发布的顺序推进。

本计划补充 [企业级 Agent 平台化方案](dazah-enterprise-agent-gateway-tool-registry-implementation-plan-2026-07-30.md)。业务能力和权限以当前模块注册表、页面权限、工具元数据及实际运行结果为准，不沿用历史任务账本中的过时实现描述。

## 当前基础

已有统一 Tool Registry、模块 Provider 自动发现、可信主体、页面权限与助手访问范围版本、写操作确认、人工责任操作拒绝、工具调用审计。Web 浮动入口、飞书 Gateway、自动化、交互表单、附件、记忆治理及运行概览均已有实现，应先验收，再补缺口。

正式业务 Provider 已声明质量、采购、仓储、能源、生产、人事和注册；能源配置工具及缺少页面绑定的业务工具已关闭，当前可用业务工具来自质量、采购、仓储、生产、人事和注册。其余 8 个业务模块尚未在模块注册表声明 Livzon Provider；独立 MCP 工具不能直接算作 Livzon 接入。模块可进入菜单，不代表助手具有查询或执行能力。

系统设置及其全部管理功能不接入助手；设置、组织身份管理、配置诊断及平台运维仅保留人工管理入口。后续业务扩展不得恢复这些助手工具。

飞书原生文档、云盘等资源仍按飞书 Scope 和资源授权管理；Dazah 业务操作按本地用户权限管理。两种权限不能相互替代。

## 本次修复与验收

| 项目 | 本地实现 | 回归证据 | 尚需验收 |
| --- | --- | --- | --- |
| 页面授权事件同步 | 同步扫描兼容页面授权事件与旧模块授权事件，保留批量、行锁、重试机制 | 扫描查询同时包含两类事件；成功处理与失败记录测试 | 专用测试库已验证角色变更事件、真实扫描与消费、授权版本一致；部署调度健康、外部缓存通知与故障恢复待验收 |
| 供应商统计权限 | 保留 analytics.aggregate 操作与输入，绑定采购供应商页面查询权限；查询逻辑位于采购模块，经公开 API 调用 | HTTP 成功、无查询权限、撤权、旧快照、无效范围；Hermes 成功与 403 转发 | 专用测试库已验证真实聚合、角色多来源、用户覆盖、Web/飞书主体与确认 HTTP 链路；真实客户端操作待验收 |

供应商是无部门归属的主数据，目前页面只支持 all 范围。统计必须有供应商页面查询授权；非管理员的其他范围配置直接拒绝。未来新增统计数据集必须由所有者声明页面与范围适配，不得将通用统计工具扩展为任意模块查询入口。

本地定向检查不等于线上已部署；本次没有数据库结构、HTTP Schema 或环境变量变化，新增离线工具盘点文件。

## 分阶段任务

### 阶段一 权限与执行基础

由身份平台与 Agent 后端负责人承接，先于业务扩展。

| 任务 | 实现与交付 | 完成标准 |
| --- | --- | --- |
| B1 授权联动验收 | 串联角色授权、用户角色、部门角色、用户覆盖、权限 Outbox、助手快照与缓存 | 增权可用；撤权后旧会话、待确认操作和自动化不能继续越权；同步失败有状态与重试记录 |
| B2 角色语义一致 | 业务统一按平台有效页面授权判定；移除旧静态角色字段对业务的额外阻挡 | 自定义角色获得业务权限后行为一致；系统设置与运维工具始终不接入，缺少页面绑定的业务工具不可用 |
| B3 工具边界检查 | 对所有业务数据读取工具检查 module、page_keys、敏感动作、数据范围与所有者公开 API | 平台工具不得隐式读取业务数据；未绑定业务工具默认不可用；缺失适配有明确拒绝与测试 |
| B4 风险确认闭环 | 验收写操作预览、确认所有权、到期、重复点击、权限变化与执行幂等 | 未确认不写入；重复确认不重复执行；批准、驳回、处分等人工责任判断不能代理决定 |
| B5 身份跨入口验收 | 核对 Web 与飞书本地身份、租户、群准入、解绑、停用和每次入站解析 | 模型不能覆盖主体；跨用户、跨租户及停用身份失败关闭；两入口业务授权一致 |

阶段一门禁：在专用测试库完成授权联动矩阵及真实路由测试；确认后台同步任务注册、调度健康、事件延迟和积压均可观测。

### 阶段二 运行与治理基础

依赖阶段一，由 Agent 后端、Hermes 和前端负责人协作。

| 任务 | 实现与交付 | 完成标准 |
| --- | --- | --- |
| G1 能力范围视图 | 用户可查看当前可用模块、工具、权限来源与同步状态；管理员可诊断不可用原因 | 区分无授权、工具未接入、工具停用、同步失败；显示内容来自后端实时目录 |
| G2 任务运行解释 | 串联 trace、run、工具调用、确认、交互表单和推送记录 | Web 与飞书能解释执行进度、失败步骤和恢复方式；敏感输入与审计内容脱敏 |
| G3 自动化治理 | 验收草稿、预览、版本、确认、启停、模拟、失败重试与权限撤销 | 权限在运行时复核；重试不重复产生业务写入；人工决策工具不可进入自动化 |
| G4 配置与恢复 | 验收模型配置、Gateway 配置版本、健康状态、断线恢复、单消费者和回滚 | 配置失败有明确状态；控制面可诊断；日志、前端和模型上下文不暴露密钥 |
| G5 附件与记忆 | 验收 MIME、大小、数量、来源、归属、保留和删除策略，以及租户记忆偏好 | 附件与记忆不跨用户或租户泄露；删除和禁用生效；历史上下文不能成为新的越权读取入口 |

阶段二门禁：Web 和飞书完成相同业务场景，含断线、超时、重试、重复投递和权限变化；所有状态可定位，错误不能伪装成功。

### 阶段三 深化已接入模块

依赖阶段一，分别由业务模块 Owners 确认实际需求与责任边界。

| 模块 | 补齐重点 | 验收重点 |
| --- | --- | --- |
| 质量 | 按页面核对台账查询、详情、统计、起草、编辑、提交及同步覆盖 | 部门与产品范围准确；偏差、CAPA、变更等状态约束一致；放行与审批由责任人完成 |
| 采购 | 供应商统计、采购申请、订单、合同能力与页面授权完整对应 | 明细与统计口径一致；跨采购类别拒绝；审批不由助手代决策 |
| 仓储 | 从库存只读能力扩展到经业务确认的出入库草稿和异常协助 | 库存约束、物料身份、部门范围、并发和重复请求均由仓储 Service 保证 |
| 能源 | 补齐业务页面、范围与分析解释；完成验收后开放业务工具 | 业务分析遵循平台角色授权；配置、密钥和全局管理能力不接入助手 |

每个模块交付能力清单，至少列明 operation、所有者、关联页面、查询或写入、数据范围、敏感动作、确认策略、自动化适用性和验收用例。只补有实际业务需求的工具，不批量把所有 HTTP API 暴露给模型。

### 阶段四 新模块接入

依赖阶段一和二。建议先生产、设备，再安全、环保；其后人事、行政；研发、注册、法规追踪、资料撰写与产品按现有 Service 和需求成熟度接入。

| 批次 | 最小交付 | 业务限制 |
| --- | --- | --- |
| 生产与设备 | 批次或工序查询、设备台账、维修保养状态、异常任务草稿 | 生产数据修改和设备处置遵循现有状态机及责任确认 |
| 安全与环保 | 风险或隐患查询、监测台账、整改记录草稿和授权提醒 | 作业许可、合规责任和重大风险判断由责任人完成 |
| 人事与行政 | 授权范围内人员或培训查询、行政事项和流程草稿 | 员工敏感字段按授权裁剪；薪酬、处分和人事责任决定不得代理 |
| 研发与注册相关模块 | 项目进度、法规或资料检索、来源引用与资料草稿 | 项目隔离、文件权限、版本与人工复核；未经校验的生成内容不写入关键业务字段 |
| 产品 | 产品档案、规格查询与授权同步 | 产品主数据和批次、库存数据归属分开，不跨模块直接修改 |

每个新模块先查询后写入，在 module_registry 声明 Provider，由后端自动发现。Hermes 继续使用单一 dazah_tool，不新增业务白名单；已有 MCP 工具需要逐个复核 Service、权限、风险与审计后才能接入。

### 阶段五 跨模块运营与发布

依赖已验收的模块能力。

- 先选择一条跨模块只读场景，例如采购到货与仓储库存对账，再扩展异常提醒和任务草稿。数据所有者提供最小公开 API 或领域事件，明确每一步权限、幂等和失败补偿。
- 后端承接长期调度；模型编译计划，平台校验与执行。新增事件联动时核对版本、重复消息和租户范围。
- 建立自然语言评测场景，覆盖模糊请求、缺失参数、无权限、错误工具选择、超时和人工责任操作。CI 中使用可控模型与外部依赖 fake，不连接真实模型。
- 按授权执行专用测试库集成、契约、前端与 Hermes 验证；最新 PR head 的 CI 通过后再进入发布流程。线上灰度验收权限、审计、确认和恢复，保留模块或工具停用回滚路径。

阶段五完成标准：用户只操作被授权能力；普通查询和写入有来源、范围与执行结果；管理员能解释失败并恢复；业务责任判断保留人工闭环。

## 执行记录

后续任务从阶段一开始逐项记录状态、改动范围、验证命令和结果。新增字段或端点时执行根目录契约生成；数据库变化时补迁移并使用专用测试库。提交、推送、PR、发布和数据库联调分别遵守当前授权与仓库规范。


## 本次验证记录

- 两项回归测试在修复前失败：统计工具缺少采购 module 绑定，事件查询缺少页面授权事件。
- 后端定向测试 36 项通过，1 项依赖数据库的用例未执行。运行覆盖工具注册、事件扫描与处理、真实 HTTP 路由、授权与撤权、范围拒绝、聚合查询构造和工具执行器。
- Hermes 渐进工具契约测试 15 项通过，包含统计工具成功与 403 拒绝结果的转发。
- 修改范围的 Ruff 通过；四个生产文件的 Mypy 通过（follow-imports=silent）；页面权限生命周期检查通过，267 个 active 页面。
- check-test-impact.py --base main --head HEAD 通过，仅验证已提交历史。本次未提交改动另使用相同 evaluate 策略按本次生产文件和测试文件集合核对。
- 定向单测使用无真实凭据的隔离配置及 fake 数据库，不加载根 .env.local，不连接数据库、真实模型或外部服务。通过 confcutdir 排除根数据库夹具，不将其计作数据库集成验收。
- 权限修复时未连接数据库。后续授权联动验收已在专用测试库验证真实聚合与 Outbox 扫描消费；部署调度健康及线上 Web/飞书客户端验收仍留在阶段一。


## 授权联动集成验收记录

验收日期：2026-10-09。目标为本机根配置中的专用 dazah_test 数据库，与开发数据库隔离。数据库 current 与代码唯一 head 均为 a3f8c2d91e47，无待应用迁移；本轮未执行迁移或重启服务。

新增 tests/modules/agent/test_role_permission_acceptance.py，以真实授权 HTTP 路由、SQLAlchemy Repository、Tool Catalog、Tool Executor、业务聚合查询、Permission Outbox 和同步生成器串联验收。测试使用 savepoint 与外层回滚隔离数据，仅替换身份登录和外部缓存通知边界，不 mock 权限计算、工具执行或数据库查询。

| 场景 | 结果 |
| --- | --- |
| 角色已有授权但未分配给用户 | 助手目录不暴露该业务能力 |
| 分配自定义只读角色给普通用户 | 供应商统计可用，账号仍为 user；采购写操作被拒绝 |
| 手动角色与部门映射角色叠加 | 按角色并集合并查询与操作权限，授权来源可核对 |
| 授权接口产生页面权限事件 | 同步任务真实扫描并处理事件，快照版本等于用户授权版本 |
| 真实供应商统计 | 只统计测试品类且排除软删除记录，返回 count=1 |
| 用户单独拒绝与恢复继承 | 拒绝覆盖角色基线；恢复 inherit 后重新按角色基线授权 |
| 写入确认 | 未确认不产生采购申请；撤销角色权限后旧确认 HTTP 请求返回 403，不产生业务记录 |
| Web 与飞书确认路径 | Web execute 与飞书 resolve 均在撤权后拒绝执行 |
| 已确认自动化撤权 | 再启用被拒绝，状态转为 suspended_policy |
| 同步尚未完成时直接调用旧能力 | 旧快照立即失败关闭，不等待后台同步后才拒绝 |
| 删除用户手动角色 | 同步后目录与执行均拒绝原角色能力，事件全部 processed |

权限口径为平台最终生效页面授权：已分配手动角色与部门角色的并集，再应用现有用户单独覆盖。工具目录和执行共用该口径；助手不提供另一套独立的业务授权。工具尚未接入、确认要求和人工责任决策限制仍独立生效，不能以角色授权绕过。

定向命令为 pytest tests/modules/agent/test_role_permission_acceptance.py tests/modules/agent/test_page_scope_execution.py tests/modules/agent/test_analytics_tool.py tests/platform/identity/test_page_permission_write_api.py tests/modules/agent/test_phase_one_automation.py tests/modules/agent/test_supplier_analytics_permissions.py tests/modules/procurement/test_supplier_analytics_scope.py -q --tb=short --disable-warnings。执行入口从根 .env.local 仅取 TEST_DATABASE_URL，校验专用测试名称与开发隔离，在子进程内同时设置 DATABASE_URL 和 TEST_DATABASE_URL 指向测试库，其他配置使用无真实凭据的测试值；没有使用 confcutdir 跳过根数据库夹具。

结果：38 项通过；39 条既有依赖或 Schema 弃用警告未作为本轮修改范围。新增用例 Ruff 和格式检查通过，git diff --check 通过。本轮仅新增测试与更新本计划，无生产代码、migration、HTTP Schema、环境变量或生成文件变化；没有提交、推送或部署。

阶段一 B1 的后端授权联动部分已验收。下一步仍需核对部署中调度任务注册与健康、真实缓存通知、失败重试和 Web/飞书实际客户端，再推进 B2 角色语义与 B3 全工具边界盘点。当前证据覆盖采购和质量代表链路，不将其表述为所有未接入模块或飞书原生资源均已验收。

## 2026-10-09 设置接入关闭与全目录复核

当前验收边界：系统设置、组织身份管理、配置诊断及平台运维能力不接入 Livzon。保留助手本人附件、任务、确认、交互和统一消息投递。平台管理界面及其人工 API 保留，关闭的是助手工具入口。

新增 tool_policy.py，在 ToolRegistry 注册入口同时按页面归属、API 路径及管理能力识别拒绝；已退役工具不进入目录、权限快照和工作流能力投影。Catalog 同步将旧记录 status=disabled、admin_enabled=false，重新启用退役记录返回 409。直接调用和旧确认均因 operation 未注册被拒绝；旧自动化编译报告 unknown_operation，无法将设置工具继续编入执行计划。

全部声明共 150 项：实际注册 117 项，关闭 33 项。保留质量 69、采购 15（含 analytics.aggregate）、仓储 3、平台个人及基础能力 30；关闭的 33 项中 24 项为设置、配置或运维，另 9 项能源业务工具缺少页面授权绑定，暂时关闭。能源完整接入须在后续补齐所有者 Service、有效页面与数据范围后重新验收；不得恢复配置工具。保留的业务工具均有页面绑定，保留工具不存在 required_roles 静态角色门槛。

业务目录、权限快照与执行不再使用工具里的旧 required_roles 字段额外限制业务用户，而统一依赖平台有效页面授权。角色并集、用户覆盖、查询／操作／敏感动作及范围仍按平台规则计算；平台原有管理员语义保留。授权不绕过工具停用、写入确认或人工责任限制。

盘点同时修复 Catalog 将 write 直接等同 confirmation_required 的元数据错误，改为投影工具的真实确认声明。三个草案创建能力不立即确认，只生成未启用草案；后续启用仍需独立确认。业务写入的确认要求保留，回归覆盖草案、业务写入和查询三类投影。

完整目录（含所有关联页面、输入输出 Schema、风险、确认、工作流及数据范围元数据）见 [livzon-tool-inventory-2026-10-09.json](livzon-tool-inventory-2026-10-09.json)。通过 scripts/export-livzon-tool-inventory.py --output docs/livzon-tool-inventory-2026-10-09.json 更新，必须使用后端 Python 运行时及隔离配置；生成过程不连接数据库或模型。以下表列主关联页面，多页绑定以 JSON 为准。

| operation | 归属 | 页面／资源 | 读写 | 工具确认元数据 | 责任限制 |
| --- | --- | --- | --- | --- | --- |
| agent.archive_automation | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| agent.complete_manual_task | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| agent.confirm_automation | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| agent.create_automation | 平台个人能力 | 本人资源／助手基础能力 | 写 | 否 | 按授权与确认执行 |
| agent.create_automation_draft | 平台个人能力 | 本人资源／助手基础能力 | 写 | 否 | 按授权与确认执行 |
| agent.create_scheduled_task | 平台个人能力 | 本人资源／助手基础能力 | 写 | 否 | 按授权与确认执行 |
| agent.delete_attachment | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| agent.get_automation | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.get_automation_run | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.get_current_time | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.get_interaction_request | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.get_my_access_scope | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.get_push_delivery | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.list_attachments | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.list_automation_audit | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.list_automation_runs | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.list_automations | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.list_domain_events | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.list_interaction_requests | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.list_push_deliveries | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.list_scheduled_triggers | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.mutate_tabular_attachment | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| agent.preview_automation | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.read_attachment | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.retry_automation_run | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| agent.run_automation | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| agent.set_automation_enabled | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| agent.simulate_automation | 平台个人能力 | 本人资源／助手基础能力 | 读 | 否 | 按授权与确认执行 |
| agent.update_automation | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| analytics.aggregate | procurement | purchasing:supplier | 读 | 否 | 按授权与确认执行 |
| identity.deliver_feishu_message | 平台个人能力 | 本人资源／助手基础能力 | 写 | 是 | 按授权与确认执行 |
| procurement.approve_purchase_request | procurement | purchasing:approval:approval-hardware:approval-hardware-hardware-warehouse（共 43 页） | 写 | 是 | 人工责任，禁止代理 |
| procurement.create_purchase_request | procurement | purchasing:request:request-hardware（共 12 页） | 写 | 是 | 按授权与确认执行 |
| procurement.export_purchase_orders | procurement | purchasing:order | 读 | 否 | 按授权与确认执行 |
| procurement.generate_contract | procurement | purchasing:contract-generation:contract-generation-fixed-assets（共 4 页） | 写 | 是 | 按授权与确认执行 |
| procurement.get_contract_template | procurement | purchasing:contract-generation:contract-generation-fixed-assets（共 4 页） | 读 | 否 | 按授权与确认执行 |
| procurement.get_purchase_request | procurement | purchasing:request:request-hardware（共 12 页） | 读 | 否 | 按授权与确认执行 |
| procurement.list_contract_templates | procurement | purchasing:contract-generation:contract-generation-fixed-assets（共 4 页） | 读 | 否 | 按授权与确认执行 |
| procurement.list_invoice_records | procurement | purchasing:invoice-recognition | 读 | 否 | 按授权与确认执行 |
| procurement.list_purchase_orders | procurement | purchasing:order | 读 | 否 | 按授权与确认执行 |
| procurement.list_purchase_requests | procurement | purchasing:request:request-hardware（共 12 页） | 读 | 否 | 按授权与确认执行 |
| procurement.list_suppliers | procurement | purchasing:supplier | 读 | 否 | 按授权与确认执行 |
| procurement.reject_purchase_request | procurement | purchasing:approval:approval-hardware:approval-hardware-hardware-warehouse（共 43 页） | 写 | 是 | 人工责任，禁止代理 |
| procurement.submit_purchase_request | procurement | purchasing:request:request-hardware（共 12 页） | 写 | 是 | 按授权与确认执行 |
| procurement.update_purchase_request | procurement | purchasing:request:request-hardware（共 12 页） | 写 | 是 | 按授权与确认执行 |
| quality.add_capa_execution_track | quality | quality:capas:capa-ledger | 写 | 是 | 按授权与确认执行 |
| quality.auto_fill_capa_from_deviation | quality | quality:capas:capa-ledger | 读 | 否 | 按授权与确认执行 |
| quality.complete_capa_part | quality | quality:capas:capa-ledger | 写 | 是 | 按授权与确认执行 |
| quality.create_capa | quality | quality:capas:capa-ledger | 写 | 是 | 按授权与确认执行 |
| quality.create_change | quality | quality:change:change-ledger（共 2 页） | 写 | 是 | 按授权与确认执行 |
| quality.create_change_action_plan | quality | quality:change:change-action-plans | 写 | 是 | 按授权与确认执行 |
| quality.create_cpv_parameter | quality | quality:product-quality:product-quality-mfn（共 7 页） | 写 | 是 | 按授权与确认执行 |
| quality.create_cpv_product | quality | quality:product-quality:product-quality-mfn（共 7 页） | 写 | 是 | 按授权与确认执行 |
| quality.create_deviation | quality | quality:deviations:deviation-ledger | 写 | 是 | 按授权与确认执行 |
| quality.create_validation | quality | quality:validation:validation-plans（共 5 页） | 写 | 是 | 按授权与确认执行 |
| quality.get_capa | quality | quality:capas:capa-ledger | 读 | 否 | 按授权与确认执行 |
| quality.get_capa_statistics | quality | quality:capas:capa-ledger | 读 | 否 | 按授权与确认执行 |
| quality.get_change | quality | quality:change:change-ledger（共 2 页） | 读 | 否 | 按授权与确认执行 |
| quality.get_change_statistics | quality | quality:change:change-ledger（共 2 页） | 读 | 否 | 按授权与确认执行 |
| quality.get_cpv_product | quality | quality:product-quality:product-quality-mfn（共 7 页） | 读 | 否 | 按授权与确认执行 |
| quality.get_cpv_statistics | quality | quality:product-quality:product-quality-mfn（共 7 页） | 读 | 否 | 按授权与确认执行 |
| quality.get_cpv_trend | quality | quality:product-quality:product-quality-mfn（共 7 页） | 读 | 否 | 按授权与确认执行 |
| quality.get_deviation | quality | quality:deviations:deviation-ledger | 读 | 否 | 按授权与确认执行 |
| quality.get_deviation_statistics | quality | quality:deviations:deviation-ledger | 读 | 否 | 按授权与确认执行 |
| quality.get_feishu_capa_plan_track | quality | quality:capas:capa-plans | 读 | 否 | 按授权与确认执行 |
| quality.get_feishu_validation | quality | quality:validation:validation-plans | 读 | 否 | 按授权与确认执行 |
| quality.get_inspection_record | quality | quality:inspection:inspection-finished:inspection-finished-mpa（共 10 页） | 读 | 否 | 按授权与确认执行 |
| quality.get_next_change_code | quality | quality:change:change-ledger（共 2 页） | 读 | 否 | 按授权与确认执行 |
| quality.get_oos_oot_record | quality | quality:oos-oot:oos-ledger | 读 | 否 | 按授权与确认执行 |
| quality.get_related_capas | quality | quality:deviations:deviation-ledger | 读 | 否 | 按授权与确认执行 |
| quality.get_validation | quality | quality:validation:validation-plans（共 5 页） | 读 | 否 | 按授权与确认执行 |
| quality.get_validation_statistics | quality | quality:validation:validation-plans | 读 | 否 | 按授权与确认执行 |
| quality.link_capa_deviation | quality | quality:capas:capa-ledger | 写 | 是 | 按授权与确认执行 |
| quality.list_capa_departments | quality | quality:capas:capa-ledger | 读 | 否 | 按授权与确认执行 |
| quality.list_capas | quality | quality:capas:capa-ledger（共 2 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_change_action_plans | quality | quality:change:change-action-plans | 读 | 否 | 按授权与确认执行 |
| quality.list_change_action_plans_by_change | quality | quality:change:change-action-plans | 读 | 否 | 按授权与确认执行 |
| quality.list_changes | quality | quality:change:change-ledger（共 2 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_complaints | quality | quality:complaints:complaint-ledger | 读 | 否 | 按授权与确认执行 |
| quality.list_cpv_batches | quality | quality:product-quality:product-quality-mfn（共 7 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_cpv_cpp_batches | quality | quality:product-quality:product-quality-mfn（共 7 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_cpv_cqa_batches | quality | quality:product-quality:product-quality-mfn（共 7 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_cpv_parameters | quality | quality:product-quality:product-quality-mfn（共 7 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_cpv_products | quality | quality:product-quality:product-quality-mfn（共 7 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_deviation_report_records | quality | quality:deviations:deviation-ledger | 读 | 否 | 按授权与确认执行 |
| quality.list_deviations | quality | quality:deviations:deviation-ledger | 读 | 否 | 按授权与确认执行 |
| quality.list_feishu_capa_plan_tracks | quality | quality:capas:capa-plans | 读 | 否 | 按授权与确认执行 |
| quality.list_feishu_validations | quality | quality:validation:validation-plans（共 5 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_inspection_records | quality | quality:inspection:inspection-finished:inspection-finished-mpa（共 10 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_oos_oot_records | quality | quality:oos-oot:oos-ledger | 读 | 否 | 按授权与确认执行 |
| quality.list_product_quality_records | quality | quality:product-quality:product-quality-mfn（共 7 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_return_recalls | quality | quality:return-recalls:return-application（共 2 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_suppliers | quality | quality:suppliers:supplier-qualification | 读 | 否 | 按授权与确认执行 |
| quality.list_validation_executions | quality | quality:validation:equipment-qualification（共 4 页） | 读 | 否 | 按授权与确认执行 |
| quality.list_validations | quality | quality:validation:validation-plans（共 5 页） | 读 | 否 | 按授权与确认执行 |
| quality.pull_feishu_validations | quality | quality:validation:validation-plans | 写 | 是 | 按授权与确认执行 |
| quality.resubmit_capa | quality | quality:capas:capa-ledger | 写 | 是 | 按授权与确认执行 |
| quality.resubmit_deviation | quality | quality:deviations:deviation-ledger | 写 | 是 | 按授权与确认执行 |
| quality.run_change_action_plan_reminders | quality | quality:change:change-action-plans | 写 | 是 | 按授权与确认执行 |
| quality.send_change_action_plan_reminder | quality | quality:change:change-action-plans | 写 | 是 | 按授权与确认执行 |
| quality.submit_capa | quality | quality:capas:capa-ledger | 写 | 是 | 按授权与确认执行 |
| quality.submit_deviation | quality | quality:deviations:deviation-ledger | 写 | 是 | 按授权与确认执行 |
| quality.submit_deviation_investigation | quality | quality:deviations:deviation-ledger | 写 | 是 | 按授权与确认执行 |
| quality.sync_capa_plan_track_to_feishu | quality | quality:capas:capa-plans | 写 | 是 | 按授权与确认执行 |
| quality.sync_change_action_plan | quality | quality:change:change-action-plans | 写 | 是 | 按授权与确认执行 |
| quality.sync_change_action_plans_from_feishu | quality | quality:change:change-action-plans | 写 | 是 | 按授权与确认执行 |
| quality.update_capa | quality | quality:capas:capa-ledger | 写 | 是 | 按授权与确认执行 |
| quality.update_change | quality | quality:change:change-ledger（共 2 页） | 写 | 是 | 按授权与确认执行 |
| quality.update_change_action_plan | quality | quality:change:change-action-plans | 写 | 是 | 按授权与确认执行 |
| quality.update_cpv_parameter | quality | quality:product-quality:product-quality-mfn（共 7 页） | 写 | 是 | 按授权与确认执行 |
| quality.update_cpv_product | quality | quality:product-quality:product-quality-mfn（共 7 页） | 写 | 是 | 按授权与确认执行 |
| quality.update_deviation | quality | quality:deviations:deviation-ledger | 写 | 是 | 按授权与确认执行 |
| quality.update_validation | quality | quality:validation:validation-plans（共 5 页） | 写 | 是 | 按授权与确认执行 |
| quality.update_validation_execution | quality | quality:validation:equipment-qualification（共 4 页） | 写 | 是 | 按授权与确认执行 |
| warehouse.list_packaging_materials | warehouse | warehouse:materials:packaging-summary | 读 | 否 | 按授权与确认执行 |
| warehouse.list_products | warehouse | warehouse:product-inventory:product-summary | 读 | 否 | 按授权与确认执行 |
| warehouse.list_raw_materials | warehouse | warehouse:materials:raw-summary | 读 | 否 | 按授权与确认执行 |

关闭清单：

| operation | 关闭原因 |
| --- | --- |
| agent.get_automation_health | 平台运维与资源配置不接入 Livzon |
| agent.get_automation_trends | 平台运维与资源配置不接入 Livzon |
| agent.get_operations_report | 平台运维与资源配置不接入 Livzon |
| agent.list_automation_capability_impacts | 平台运维与资源配置不接入 Livzon |
| agent.list_automation_suggestions | 平台运维与资源配置不接入 Livzon |
| agent.list_automation_templates | 平台运维与资源配置不接入 Livzon |
| agent.list_feishu_resource_templates | 平台运维与资源配置不接入 Livzon |
| agent.validate_feishu_resource_template | 平台运维与资源配置不接入 Livzon |
| energy.create_feishu_source_root | 平台运维与资源配置不接入 Livzon |
| energy.delete_feishu_source_root | 平台运维与资源配置不接入 Livzon |
| energy.delete_source_sheets | 业务工具缺少页面授权绑定，暂不开放 |
| energy.get_feishu_config | 配置管理不接入 Livzon |
| energy.get_overview | 业务工具缺少页面授权绑定，暂不开放 |
| energy.get_sheet_mapping | 业务工具缺少页面授权绑定，暂不开放 |
| energy.list_feishu_source_roots | 平台运维与资源配置不接入 Livzon |
| energy.list_sheet_snapshots | 业务工具缺少页面授权绑定，暂不开放 |
| energy.list_snapshot_rows | 业务工具缺少页面授权绑定，暂不开放 |
| energy.list_source_documents | 业务工具缺少页面授权绑定，暂不开放 |
| energy.list_source_sheets | 业务工具缺少页面授权绑定，暂不开放 |
| energy.list_sync_runs | 业务工具缺少页面授权绑定，暂不开放 |
| energy.test_feishu_connectivity | 配置管理不接入 Livzon |
| energy.trigger_sync | 业务工具缺少页面授权绑定，暂不开放 |
| energy.update_feishu_source_root | 平台运维与资源配置不接入 Livzon |
| identity.check_feishu_permissions | 配置管理不接入 Livzon |
| identity.get_department_tree | 身份与组织管理不接入 Livzon |
| identity.search_personnel | 身份与组织管理不接入 Livzon |
| quality.list_quality_sync_conflicts | 配置管理页面不接入 Livzon |
| quality.pull_quality_records_from_feishu | 配置管理页面不接入 Livzon |
| warehouse.get_feishu_table_records | 配置管理页面不接入 Livzon |
| warehouse.get_feishu_ws_status | 配置管理页面不接入 Livzon |
| warehouse.list_feishu_tables | 配置管理页面不接入 Livzon |
| warehouse.restart_feishu_ws | 配置管理页面不接入 Livzon |
| warehouse.sync_feishu_table | 配置管理页面不接入 Livzon |

## 本机后台与 Web 权限验收补充

- 独立测试库与本机开发库均核对 current 等于唯一 head a3f8c2d91e47，无待应用迁移。本机使用 Dockerfile.dev 的开发栈及 localhost:3000；没有连接共享或生产环境。
- 将权限同步单独注册到一个 SchedulerEngine，避免原串行调度中的耗时业务同步延迟权限事件。单测验证业务调度阻塞时权限同步仍推进，并验证停止后任务退出；独立 PostgreSQL 验证真实循环提交、授权与撤权。
- 经用户授权创建专用本地普通账户及供应商只读角色。真实浏览器完成本地登录、供应商页面查询、无导入权限提示、打开助手及仅显示供应商推荐。用户仍为 role=user，授予的是角色页面权限。
- 本机后台实际消费三次权限事件：初始授权 version=1；撤销角色后约 3.54 秒 processed、快照 version=2、analytics.aggregate 消失；恢复角色后约 2.54 秒 processed、version=3、能力恢复。时间是该次观测，不作为稳定 SLA。
- Redis 实际权限缓存失效已验证。撤权后真实 Web access-scope HTTP 200，返回 version=2 且不含供应商统计能力；刷新原供应商页面显示“页面访问受限”。恢复角色后原页面查询可用。此次未增加前端即时权限推送机制，页面刷新及后端每次请求判定均使用新权限。
- 本机开发库已执行 ToolCatalogService.synchronize 并提交助手目录关闭状态，核对已持久化的退役记录全部 status=disabled、admin_enabled=false。开发容器健康，/health 返回 HTTP 200；页面生命周期检查通过，267 个 active 页面。
- 普通测试账户访问平台控制面工具执行接口返回 403，平台控制面权限仍生效。未将控制面请求拒绝记为成功执行助手业务工具。
- 测试结束已停用并软删除专用账户、角色及绑定，清除测试密码并撤销会话；保留验收审计及三条 processed 事件。未写入、覆盖或删除业务数据。
- 后端定向 76 项通过，质量 Provider 回归另 6 项通过；Hermes 目录转发契约 16 项通过；前端组件 11 项通过，定向 ESLint 与 TypeScript 检查通过。生产改动 Ruff、五个权限与调度文件 Mypy（follow-imports=silent）、main 编译和 git diff --check 通过。按未提交任务文件集合 evaluate 的测试影响策略没有违规项；main..HEAD 检查仅覆盖历史。
- 既有身份权限测试曾因无 ORDER BY 查询却固定断言第一条审计日志而随机失败，已改为严格核对两次授权操作的审计原因集合；未修改审计生产实现或删除断言。
- 后端测试文件：test_permission_sync_scheduler_acceptance.py、test_role_permission_acceptance.py、test_settings_tool_exclusion.py、test_supplier_analytics_permissions.py、test_page_scope_execution.py、test_analytics_tool.py、test_phase_one_automation.py、test_energy_agent_tools.py、test_page_contract_projection.py、test_tool_registry_executor.py、test_agent_v2_contracts.py、procurement/test_supplier_analytics_scope.py、identity/test_page_permission_write_api.py、unit/test_permission_sync_runtime.py；另运行 quality/test_agent_tools.py。
- 本轮没有 migration、HTTP Schema、环境变量或 OpenAPI／前端生成类型变化；新增离线工具清单由项目导出脚本生成。未提交、推送或发布。
- 用户将客户端范围限定为 Web；飞书真实私聊和卡片操作暂缓，已有 Feishu 来源及确认 HTTP 回归仍保留。按仓库测试规范未连接真实模型；自然语言对话到模型编排、业务工具选择与确认的完整浏览器端到端流程尚未验收，后续应使用可控模型和外部依赖 fake 完成。

阶段二已补齐用户能力范围视图、撤权确认持久化及重试安全检查，结果见下节。完整可控模型编排下的 Web 对话与写入确认端到端仍需后续补验；飞书真实客户端验收待用户恢复范围后执行。业务模块深化按阶段三另行推进，系统设置、组织管理、密钥配置和平台运维保持不接入助手。

## 阶段二实施与验收记录

日期：2026-10-10。用户限定真实客户端为本机 Web，允许创建临时本地测试账户。阶段二本地实现与当前 Web 范围验收完成；原计划双端完整门禁尚未关闭。

| 项目 | 本轮结果 | 验证边界 |
| --- | --- | --- |
| G1 能力范围视图 | 新增实时能力接口和助手“能力与运行”抽屉，展示授权版本、同步状态、模块工具及角色／用户覆盖来源；区分无授权、未接入、停用、同步失败 | HTTP 验证成功、停用、同步失败及账户禁用；管理员诊断仅限同租户，普通账户拒绝、跨租户 404；本机浏览器验证普通用户的分配角色来源 |
| G2 任务运行解释 | 新增运行诊断接口，并供已有 get_automation_run 工具调用；关联 trace、步骤、工具调用、确认、交互及投递，只展示状态摘要和恢复建议 | 所有者可读、其他用户拒绝；运行、步骤、事件及诊断隐藏原始异常；Web 真实打开失败运行和非幂等写入核对提示 |
| G3 自动化治理 | 失败重试恢复原 run 和当前步骤，保留已完成结果；拒绝重复重试、旧版本、未启用任务和失败的非幂等写入；执行时继续复核当前授权 | 专用测试库验证一次已完成写入、失败查询重试成功后写入仍为一次；停用账户拒绝；Web／Feishu HTTP 撤权确认返回 403 并持久化取消，跨租户 Feishu 主体拒绝且不消耗确认 |
| G4 配置与恢复 | 保留管理控制面，设置与配置能力不进入助手工具；回归既有 LLM 代理、治理路由、Gateway 配置刷新、断线处理及投递幂等契约 | 外部模型与飞书使用 fake；真实飞书断线、配置回滚和双端联调尚未执行 |
| G5 附件与记忆 | Web／Feishu 历史消息记录可信授权版本，旧版本和来源未知历史不再送入模型；拒绝无所有者会话；个人记忆只投影偏好、个人事实及交互模式，业务结果记忆不再作为新模型上下文 | 回归附件与持久化附件、记忆策略及租户／用户隔离；验证旧授权历史过滤、业务记忆排除、偏好保留和清除生效 |

主要实现：后端 `capability_view.py`、`run_explanation.py`、`automation_runner.py`、`automation_service.py`、`service.py` 和 `api.py`；前端 `AgentGovernancePanel.tsx`、`AgentFloatingAssistant.tsx` 和 API 客户端；Hermes `memory_service.py` 与 `dazah_agent_service.py`。Web 抽屉独立提供 React Query 上下文，并随窗口宽度调整尺寸。

### 验证结果

- 后端通过隔离运行器加载根 `.env.local` 的 `TEST_DATABASE_URL`，仅连接专用本机 `dazah_test`，与开发库隔离；确认数据库 current 等于代码唯一 head `a3f8c2d91e47`。定向 Pytest 共 **119 passed**，覆盖阶段二治理、重试、确认锁、V2 路由、自动化各阶段、附件、记忆、LLM 代理和治理路由。测试库使用事务隔离，外部服务 fake，不调用真实模型。
- 后端 `uv run ruff check <本轮 Agent 代码及测试>` 通过；`uv run mypy --follow-imports=silent app/modules/agent/capability_view.py app/modules/agent/run_explanation.py app/modules/agent/automation_runner.py app/modules/agent/access_scope.py` 通过，4 个文件无问题。
- Hermes `.venv/Scripts/python.exe -m pytest -q tests/test_business_memory_projection.py tests/test_user_memory.py tests/test_feishu_runtime.py tests/test_dazah_feishu_gateway.py tests/test_dazah_backend_contract.py --disable-warnings`：**216 passed**；触达服务 `compileall` 通过。
- 前端 `pnpm exec vitest run src/components/agent/AgentGovernancePanel.test.tsx src/components/agent/AgentFloatingAssistant.test.tsx src/lib/api/agent.test.ts`：**21 passed**；触达文件 ESLint 和 `pnpm typecheck` 通过。
- 本机 `http://localhost:3000` 使用临时普通账户真实登录，真实后端返回角色来源与能力目录，浏览器展示运行诊断；375×667 窄屏抽屉完整位于视口内。测试结束软删除账户、角色、绑定、授权快照及模拟任务，清除测试密码、停用账户并撤销会话；未写入业务记录。
- 从根目录执行 `scripts/generate-api.ps1` 成功，更新后端 OpenAPI、前端快照与生成类型；契约变化仅对应能力和运行诊断接口及 Schema。工具清单通过 `scripts/export-livzon-tool-inventory.py` 重新生成，仍为 **117 注册、33 关闭**；既有运行工具能力版本更新为 1.1。
- `python scripts/check-test-impact.py --base main --head HEAD` 通过；另用同一策略核对未提交及新文件，缺少测试组和未分类生产文件均为 0。`git diff --check` 通过。

本轮无 migration、数据库结构或环境变量变更，无提交、推送、部署。未运行全量测试和生产镜像构建：变更范围由定向接口、执行链、前端和 Hermes 测试覆盖。已有 Pydantic／依赖弃用警告及 pnpm 配置提示不计为失败。

### 后续验收与阶段三入口

阶段二完整门禁仍需可控模型下的 Web 自然语言到工具、确认、业务写入全链路，以及用户恢复范围后的真实飞书同场景验证（断线、超时、重复投递、权限变化及恢复）。当前浏览器结果证明真实登录和治理界面，不能等同于完整模型编排端到端。

阶段三可按模块逐项补齐现有业务能力与数据范围，优先盘点能源页面授权和业务 Service 的缺口，再审查质量、采购、仓储的查询与起草覆盖。未获业务授权或缺少有效页面绑定的工具保持关闭；审批、放行等责任判断保留人工处理。

### 用户入口调整

2026-10-10 按用户要求移除助手中的“Livzon 能力与运行”入口和抽屉，同时删除面板组件、对应测试与专用前端 API 封装。前述面板浏览器验收为移除前的历史记录，不代表当前仍有该入口。

后台实时能力诊断、运行解释及工具调用能力保留；权限跟随角色、撤权确认取消、安全重试、附件与记忆隔离继续生效。此次仅调整用户入口，未修改后端端点或生成契约，无 migration 或环境变量变化。

移除后 `pnpm exec vitest run src/components/agent/AgentFloatingAssistant.test.tsx src/lib/api/agent.test.ts` 共 18 项通过，包含入口不再出现、历史会话继续可用的断言；触达文件 ESLint、`pnpm typecheck` 和 `git diff --check` 通过。

## 系统管理模块能力接入面板

2026-10-10 按用户要求将接入盘点放在“系统管理 → Livzon Agent管理 → 运行与接入 → 模块能力接入”。助手浮动窗口不恢复“能力与运行”入口。

管理员可以查看全部业务模块的注册／启用／未开放工具、页面覆盖率和未覆盖页面，展开模块查看页面路径、绑定数量、工具状态与未开放原因。工具明细区分查询、确认后写入和需人工处理；不展示逐页面重复的管理员权限来源。筛选支持模块接入状态和仅看未覆盖页面，刷新读取实时后台目录。

统计口径：以平台有效业务页面为分母，至少绑定一个已注册业务工具的页面为分子，同一页面多个工具只计一次。设置和配置页面排除在分母外；工具停用不改变注册覆盖率，当前启用工具及页面另列。无有效页面时显示“不适用”，不伪造百分比。覆盖率不代表该页面全部业务功能均已实现，也不代表任何用户已获得操作授权。

本机真实后台快照：15 个业务模块中 3 个已注册工具；117 项工具已注册且启用，其中个人基础工具 30 项；33 项未开放。257 个有效业务页面中 98 个已绑定工具，覆盖率 38.1%。这些是验收时的实时统计，后续注册、页面或启停变化会更新。能源模块的 15 项未开放包含既有业务和配置声明，不能全部解释为业务工具。

随后按用户要求从接入面板移除法规追踪、产品管理和环保管理，面板模块数量调整为 12，已接入为 3/12。这三个模块当前均无有效业务页面和已注册工具，因此页面覆盖仍为 98/257、38.1%，工具总量不变。此调整仅限接入盘点列表，不删除平台业务模块或改变角色权限。

再次按用户要求移除“资料撰写”接入盘点行，当前面板为 11 个模块、3/11 已接入。该模块当前无有效页面统计及注册工具，整体页面覆盖与工具数量保持不变；接口回归、Ruff 与定向 Mypy 通过。

主要文件：后端 `app/modules/agent/module_coverage.py`、`api.py`、`schemas.py` 和 `tests/modules/agent/test_module_coverage.py`；前端 `AgentModuleCoverageClient.tsx`、`FeishuSettingsClient.tsx` 与 `actions/settings.ts`。新增只读接口 `GET /api/v1/agent/control/module-coverage`，仅活动管理员可访问，普通及禁用账户返回 403；没有新增可调用的助手工具。

验证：

- 专用 `dazah_test` 确认 current 等于唯一 head 后，定向后端模块覆盖及阶段二治理测试 **7 passed**；验证真实 HTTP、注册数量、页面去重、未接入及未开放状态、人工责任标识、全部停用时启用页面归零、注册覆盖率保留、普通及禁用账户拒绝。
- 前端面板、管理导航、Settings Actions 和系统管理页面定向 Vitest **26 passed**；覆盖统计与明细、失败重试、认证读取路径和新菜单入口。触达文件 ESLint、`pnpm typecheck`、后端 Ruff 与定向 Mypy 通过。
- 通过 `http://localhost:3000` 的真实本地登录和管理菜单验证 HTTP 200、目录统计、页面／工具明细、人工处理标识、无重复权限来源及 375×667 窄屏。临时本地管理员账户已软删除、停用、清除测试密码并撤销会话；未写入业务记录。
- 根目录 `scripts/generate-api.ps1` 更新 OpenAPI、前端快照和生成类型；核对现有端点与 Schema 无额外变化。本轮新增仅为覆盖统计端点及其 Schema。
- 历史测试影响门禁与未提交工作区策略检查通过，`git diff --check` 通过。无 migration、环境变量或助手工具注册变化，无提交、推送或部署；全量测试和构建未运行，本次验证覆盖管理面板及其接口调用链。

## 业务工具、任务与动态知识上下文完善（2026-10-10）

本轮沿现有单一 `dazah_tool` 接入完善通用链路，保留工作区已有实现。知识来源由模型根据问题动态发现，可组合多个已授权模块的业务事实、统计与参考资料，不固定为质量文件或注册知识库。尚未声明 Provider、未获授权或已停用的能力仍不可访问，不以模型通用知识代替平台实时事实。

- 基础工具：增加 `result_kind` 与实时 `output_hint`，区分记录、平台统计、资料索引与正文；修正聚合工具的 JSON Schema，保留原有用例说明。质量统计声明统计结果类型，质量文件目录声明不含 SOP 正文。搜索和描述接口增加类型化响应契约，复用 Registry、Executor 与权限审计链路。
- 业务任务：增加跨模块知识检索任务；读取成功与分析成功分别记录。辅助分析仅使用本轮已执行的只读证据，校验输出 Schema、证据 ID 和 JSON Pointer，并保留原始事实、查询条件、来源、时间与局限。引用校验不能证明模型解释本身正确，因此结果明确标注辅助分析与人工复核。失败或缺失资料不生成成功报告。
- 报告与后续操作：审核草稿由事实及分析证据组成，保留引用、范围与未写入状态；分析完成后的原请求依赖任务最多续行一轮，仍需实时描述、权限和写入确认。待确认、已完成与结果未知的写入不能重复。只读修复阶段结束时释放其临时限制，保留不确定写入保护。
- 页面上下文：Web 每次提问传递当前路径与受支持的 URL 筛选提示，移除固定模块 scope。后端按唯一注册路由和实时查询授权解析页面名称及模块，丢弃未知、管理页面与伪造身份信息。提示独立于可信主体传至 Hermes 的普通和流式 V2 链路，不能作为权限或写入参数。当前未自动接入各页面的选中行或未提交表单值。
- 资料正文扩展：增加 `registration.read_knowledge_article` 作为一个可动态发现的正文 Provider，读取已发布文章、适用范围、来源与更新时间，支持有界分段续读，不修改浏览量或提交事务。这是新增资料能力，不是所有业务知识的统一来源；其他模块继续通过其各自 Service 和 Provider 提供事实。资料索引不能独立完成正文知识回答。

验证记录：

- 后端：隔离配置下运行 `pytest --noconftest -q` 的 `test_business_assistant_context.py`、`test_agent_knowledge_read.py`、`test_registration_agent_tools.py`、`test_business_module_registration.py`、`test_agent_completion_tools.py`，**104 passed**。使用 fake 数据库和可控 HTTP transport；含真实 ASGI 工具描述路由、撤权拒绝、普通/流式页面契约、知识正文续读及 Provider 范围检查，不能计作数据库集成验收。
- Hermes：`pytest -q` 运行 `test_business_context.py`、`test_grounded_analysis.py`、`test_agent_task_contract.py`、`test_dazah_backend_contract.py`、`test_dazah_response_repair.py`、`test_dazah_capability_answer.py`，**164 passed**；受影响服务与工具 `compileall` 通过。跨模块场景使用人事与仓储的可控 Provider，未连接真实模型或业务服务。
- 前端：`pnpm exec vitest run src/components/agent/pageContext.test.ts src/components/agent/AgentFloatingAssistant.test.tsx`，**12 passed**；触达文件 ESLint 和生成契约后的 `pnpm typecheck` 通过。
- 受影响后端代码与测试 Ruff 通过；`mypy --follow-imports=silent` 检查页面上下文、目录、执行器、注册 Provider 和知识 Service，5 个文件通过。
- 根目录 `scripts/generate-api.ps1` 已执行；后端 OpenAPI 与前端快照一致。本轮相对生成前快照仅新增工具目录条目及两种响应 envelope，并更新搜索/描述响应引用，无无关契约变化。
- `python scripts/check-test-impact.py --base main --head HEAD` 与 `git diff --check` 通过；另按同一策略检查本轮未提交生产文件和对应测试，缺少测试组与未分类生产文件均为 0。修正既有测试对随机证据 ID 中 `999` 的误判，继续断言虚构的“共999条记录”不会出现在结果中。

无 migration、环境变量或新依赖变更；涉及工具元数据、一个业务正文工具、V2 内部可选页面上下文和生成契约。未提交、推送、部署、重启服务或运行全量构建；专用数据库集成、真实模型任务质量及 Web/飞书真实客户端验收尚未执行。模型选源和分析质量仍需真实业务问题评测，页面选中记录上下文需要各页面显式接入后再验收。

### 真实模型、专用数据库与 Web 验收补充（2026-10-10）

本节更新上段尚未执行的验收状态。用户授权运行真实模型、数据库集成及客户端验收；沿用已限定的本机 Web 范围。使用现有 `compose.dev.yml` / `Dockerfile.dev` 开发容器及已有 Web 登录会话，未新增用户或修改其权限。开发库与专用测试库均确认 `current ==` 唯一代码 head `a3f8c2d91e47`，无需迁移；后端与 Hermes `/health` 均返回 200，开发容器健康。

- PostgreSQL：根 `.env.local` 的 `TEST_DATABASE_URL` 仅由隔离运行器消费，校验本机测试库名称及其与开发库隔离；不输出连接凭据，不回退数据库。运行 `pytest -q` 的 `test_business_context_db_acceptance.py`、`test_role_permission_acceptance.py`、`test_stage_two_governance.py`、`test_supplier_analytics_permissions.py`，**16 passed**。其中新增用例在真实 PostgreSQL 事务中验证已发布知识正文续读、未发布正文拒绝、浏览量和更新时间不变、读取不提交事务，以及管理员/普通用户的实时页面查询授权和私密筛选键丢弃；既有角色权限验收覆盖真实 HTTP、授权/撤权、工具执行及确认链路。模型和外部通知在 Pytest 中仍使用 fake，真实模型另行验收。
- 真实模型：通过既有 Agent LLM 代理调用，没有替换模型响应或启用旁路供应商。合成证据、实际数据库查询证据及有界保留证据分别复放，引用校验通过；只输出引用存在性等诊断信息，不记录完整 prompt、原始模型输出或认证配置。
- Web 全链路：在生产概览页面提交跨采购与仓储的只读统计、分析及审核草稿请求。明确口径为“当前已授权范围内全量记录，不按日期、状态或仓库筛选”后，模型自主发现并调用 `warehouse.list_raw_materials`、`analytics.aggregate`、`procurement.list_suppliers`、`warehouse.get_inventory_summary`。实际供应商查询计数为 0，原辅料计数为 122；分析引用实际证据字段，并说明两类统计对象不同、分页/展示范围及数据完整性限制。两项查询、分析和审核草稿均完成，草稿明确未写入业务系统。
- 持久化与审计：成功会话 `eeeb87d6-de30-4aa8-aaea-c489d6db0694` 的四次工具调用均为 `succeeded`、`write=false`。最终助手消息 `19a0675f-e621-4d2e-8e37-eb8e3247eb8f` 已完整持久化，长度 12564，包含分析及审核草稿完成状态。服务端保存的页面上下文为 `production:overview`，与浏览器 `/production` 一致，不影响模型自主选择其他授权模块。
- 发现并修复：前两轮跨模块辅助分析被严格引用校验拒绝，未伪造完成报告。补充证据 ID 与 data 根指针的明确规则、由实际保留数据生成的有界非空引用路径清单，并增加不含敏感值的失败阶段诊断；继续拒绝未知证据、未知路径和 null 引用。修正成功查询仍显示旧失败恢复说明的问题。新增回归先复现缺失路径清单和旧失败提示，再修复；Hermes 六个受影响测试文件 **167 passed**，触达服务 `compileall`、新增后端测试 Ruff、`git diff --check` 和历史测试影响检查通过。
- 规划修复：真实业务知识场景中，模型曾把前置知识检索能提供的类别字段列入 `missing_inputs`，使已成功检索后的查询/核验停住。先增加回归复现缺少规划规则，再明确“可选筛选未提供不是缺失输入，前置任务可提供的信息只记为依赖”；写入必填业务值仍不允许猜测。修复后六个 Hermes 文件仍为 **167 passed**。
- 动态业务知识复测：再次提出“自行选择业务知识来源，解释仓储总项数类别并验证加总”后，真实模型从授权目录发现 `warehouse.get_inventory_summary`，用其说明原辅料、包材及产品类别，正确给出 `122 + 77 + 36 = 235`；没有固定检索质量文件或注册知识库。回复明确采用库存快照、缺少逐条明细和快照更新时间、不推断其他类别或源数据新鲜度。最终助手消息 `7d647189-8d79-47cf-80a6-c52836c73735` 已持久化。此证据证明实际选源及知识回答，不将自然语言回答等同于所有结构化依赖分支均已验证。

Web 截图：跨模块分析完成画面见 `livzon-web-live-acceptance-2026-10-10.jpg`，动态业务知识回答见 `livzon-web-knowledge-acceptance-2026-10-10.jpg`。浏览器使用默认窄视口，助手内容可滚动、输入区及发送控件保持可见；未替代专门的全尺寸响应式测试。

本轮边界与遗留项：

- 一轮运行在开发服务热更新时中断，客户端明确提示服务不可用，不计为通过；稳定服务下复测完成。没有执行重启、交付镜像构建、提交或推送。
- 未指定筛选条件的“总数”请求曾被模型过度判定为缺失日期/状态，明确全量口径后完成；默认口径理解仍需更多真实问题评测，不能据此声称任意自然语言均已验收。
- 本机跨业务页面导航未完成：客户端保持 `/production`，直接 `/warehouse` 请求返回 307，登录页面请求超时。当前页面提示与助手流式链路已验收，跨页面切换及新登录流程尚未通过。生产概览本身显示汇总加载失败，未将其计作助手修复范围。
- 实际 Web 使用已有管理员身份；普通用户、撤权与知识正文权限在独立数据库/HTTP测试中验证，本轮未另做普通账户真实浏览器重登。真实飞书客户端、实际业务写入确认/执行、所有模块知识来源覆盖、选中行/未保存表单上下文仍未验收。
- 实时查询的是本机开发库及其镜像数据；样例库存同步/更新时间为历史日期，不证明上游源即时一致。查询时间不能替代资料版本或业务同步时间。报告目前展示较长 JSON，后续需要改善阅读体验；辅助解释仍需人工复核。

本轮只增加验收回归、辅助分析提示/引用清单及回复状态修复，无新增 migration、OpenAPI、环境变量、依赖或生成文件变化。

## 跨页面、重新登录与实际业务写入续验收（2026-10-10）

本节更新上一轮导航、重新登录和业务写入的未验收状态。使用本机 `compose.dev.yml` 开发栈；开发库和独立测试库均确认 Alembic current 等于唯一 head `a3f8c2d91e47`，未执行迁移或连接生产库。

- 跨页面：真实点击完成生产 → 仓储 → 采购 → 五金材料申请。先前点击后立即读取到旧页面属于加载中间态，不能记作导航失败；未认证请求的 307 也是正常登录跳转。实际草稿及取消请求保存的页面上下文均为 `purchasing:request:request-hardware`、`/purchasing/request/hardware`、`procurement`，没有沿用生产页面提示。
- 实际写入：模型动态发现并描述 `procurement.create_purchase_request`，生成确认项；确认前数据库中验收部门记录为 0，点击确认后恰有 1 张草稿。记录 `241b95da-f8c3-419b-b643-fcca1900ad40`，部门 `LIVZON验收20261010-NAV-WRITE`，数量 2、单价 3.50、合计 7.00；客户端列表和详情与数据库一致，暂无审批记录。确认 `e13c893e-31d1-4751-bba3-cbf270de0016` 状态为 `executed`，`audit.logs` 存在 `agent_tool_confirm/succeeded/200`。验收草稿保留供复核，没有提交审批或采购。
- 取消写入：修复后按原始“禁止审批、不要提交审批”措辞，且不额外填写可选商品名称，真实模型成功生成确认卡片；客户端点击取消，确认 `9f8432b4-b5b5-4d99-b4fd-eadddd0dfd76` 为 `cancelled`，`LIVZON验收20261010-CANCEL` 的业务记录仍为 0。
- 登录异常：在 `127.0.0.1:3000` 使用无业务授权的临时普通用户，隔离 `localhost` 管理员会话。错误密码返回明确提示；正确登录及退出后重新登录均落地 `/no-access`，明确显示未分配页面，不进入受保护模块。通过平台会话撤销服务制造失效会话后，登录完成页显示失效提示，重新验证保留错误状态，返回登录成功。临时用户已停用、软删除、清除测试密码并撤销会话，临时凭据文件已移除。

本轮发现并修复的确定性问题：

- 后端 `app/modules/agent/service.py` 的关键词预检把否定审批限制误识别为代理审批。仅移除明确否定的责任动作，保留同一句中其他正向审批、批准、驳回和重启请求的拦截；工具执行器的人工责任规则未改变。
- 同一文件采购明细归一化把未填写的可选商品名称变成 null，并丢失合法的零数量/单价。现按所属业务 Schema 保留空字符串和零值；没有补造缺失的必填业务值。
- 前端 `AgentFloatingAssistant.tsx` 在等待旧会话归档时仍接受旧会话请求，归档后清空新消息。现立即切换会话，旧会话归档完成不再修改新会话；真实客户端也确认点击后立即显示新对话。
- 前端 `AuthCompletion.tsx` 的身份检查缺少超时。增加 10 秒后可恢复的错误状态、终止请求及取消清理，并把失效提示改成适用于本地和飞书登录的文案。
- Hermes `agent_task_contract.py` 在参数修正后已生成确认卡片，仍显示旧参数错误。现隐藏已修正的参数提示，继续保留不确定写入回执警告。`dazah_agent_service.py` 明确否定审批不是审批意图，工具 Schema 检查不是独立知识检索前置任务。

回归均先复现失败再修复。实际验证：

- 后端专用测试库：`test_service_policy.py`、`test_service_normalization.py` **89 passed**；`test_business_context_db_acceptance.py`、`test_role_permission_acceptance.py`、`test_stage_two_governance.py`、`test_supplier_analytics_permissions.py` **16 passed**。通过隔离 runner 使用根 `.env.local` 的专用 TEST_DATABASE_URL，先校验库名/主机/隔离性与迁移版本，不输出凭据。
- Hermes：`.venv/Scripts/python.exe -m pytest -q tests/test_agent_task_contract.py tests/test_dazah_policy_prompt.py tests/test_dazah_response_repair.py tests/test_dazah_backend_contract.py --tb=short --disable-warnings`，**105 passed**；触达服务 `compileall` 通过。
- 前端：`pnpm exec vitest run` 定向执行 `AuthCompletion`、`LoginPanel`、local-login/logout 路由、proxy、`AgentFloatingAssistant`、`pageContext` 七个文件，**46 passed**；触达文件 ESLint、`pnpm typecheck`、后端 Ruff、`git diff --check` 通过。一次误触全量 test:unit 已中止，未计作通过。
- `python scripts/check-test-impact.py --base main --head HEAD` 通过；这是已提交历史检查，未替代工作区改动与新增回归的复核。未提交、推送或部署。

截图保存在当前任务的 `.codex/visualizations` 目录：`livzon-write-detail.png`、`livzon-write-cancel.png`、`livzon-login-no-access.png`、`livzon-login-expired.png`，未加入代码仓库。

限制：开发热重载曾使代理连接中断，前端重新启动后复验完成，中断轮次不计作通过。少数措辞仍会使真实模型过度推测缺失字段或把确认卡片拆成额外任务；这些轮次如实显示未完成，未伪造写入。最终草稿确认、执行和取消已实测，但不声称所有自然语言规划均可靠。未执行生产构建、全量自动化 E2E、真实飞书认证、任意模块写入或所有页面遍历；本轮未变更路由、依赖、migration、OpenAPI、环境变量及生成文件，验证集中于本次交互和执行链路。

## 2026-10-12 推送前验证

本次范围经用户确认，包含 Livzon 能力完善和维护发布/CD 修复。已从原 main 保护工作到 feature 分支，并合入最新 origin/main；同步没有冲突。以下记录是本次实际验证，不覆盖前文各日期的历史验收结果。

- 后端：在根 `.env.local` 的专用 `TEST_DATABASE_URL` 上运行变更测试及 Agent V2、Tool Registry、User Tool API 契约集，`uv run pytest -q` **445 passed**。测试进程的主数据库入口也指向专用测试库，Redis 使用独立测试库；未连接真实模型。
- 后端静态检查：变更 Python 文件 `uv run ruff check` 通过；新增能力检索、能力视图、模块覆盖、页面上下文、运行解释和工具策略六个模块 `uv run mypy --follow-imports=silent` 通过。
- Hermes：受影响的 14 个测试文件 `python -m pytest -q` **314 passed**；变更路径 Ruff 和 `python -m compileall -q services tools` 通过。
- 前端：7 个受影响测试文件 `pnpm exec vitest run` **52 passed**；`pnpm typecheck` 和变更路径 ESLint 通过。
- CD：`python -m pytest -q scripts/tests/test_cd_controller.py scripts/tests/test_cd_stage_site.py scripts/tests/test_maintenance_browser.py` 首次 **111 passed, 2 skipped**。随后设置 `RUN_CD_CONTAINER_TESTS=1` 单独执行真实 Nginx 隔离用例 **1 passed**，在无网络的 Linux 开发镜像内单独执行候选文件安全用例 **1 passed**；两个跳过项都已补跑，合计 **113 项通过**。Nginx 使用独立内部网络及测试 stub，不连接业务数据库或生产入口。
- 契约与策略：根 `scripts/generate-api.ps1` 重新生成后无新增契约漂移；桥接文件、页面权限生命周期、Agent V2 残留扫描和 `check-test-impact.py --base origin/main --head HEAD` 均通过。
- 工具盘点：通过 `scripts/export-livzon-tool-inventory.py` 更新生成文件，当前开放 178 项、排除 33 项。相较最初盘点新增 61 项，无原有开放工具删除。主线新增的自动排产页面暂未接入 Agent，生产模块覆盖为 21/22；测试明确断言该缺口。
- 本地开发栈：用户明确授权两个本地库的主线破坏性迁移后，专用测试库及开发库都从 `a3f8c2d91e47` 升级至唯一 head `a3d8f2c6e1b9`。开发库使用 `docker compose --env-file .env.local -f compose.dev.yml run --rm migrate`，再次确认 current 等于 head；以 `Dockerfile.dev` 重建后端后，容器健康且 `/health` 返回 `{"status":"ok"}`。Chromium 初次下载因 TLS 重置失败，后续只对构建 HTTPS 下载使用本机已配置代理，重试成功；仓库配置未修改。

本次 PR 不新增 migration 或环境变量；新增 Agent HTTP Schema、OpenAPI、前端生成类型和工具清单随变更同步。上述数据库升级来自已合并主线，包含删表和删字段，不以代码回滚恢复已删除数据。全量测试、覆盖率、E2E 和交付镜像门禁交由最新 PR head 的 CI；本地定向通过不代表线上部署完成。
