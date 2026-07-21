# 能源 Wiki 管理模块实施账本

> 来源：`docs/energy-wiki-management-spec-2026-07-13.md`
> 创建时间：2026-07-13
> 执行规则：每次开始、完成或阻塞一个阶段时，先回读本账本和 Spec，并在同一工作单元中更新状态、实现摘要及验证证据。
> 当前阶段：Phase 0–5 与能源运营总览/动态导航已完成（真实飞书资源授权仍待外部前置条件）

## 状态说明

- `未开始`：尚未进入阶段。
- `进行中`：正在实现，尚未达到阶段验收。
- `已完成`：代码、迁移、测试、OpenAPI、前端类型及阶段验收均已通过。
- `受阻`：存在外部依赖；必须写明证据和恢复条件。

## 阶段总览

| 阶段 | 状态 | 目标 | 阶段验收 |
| --- | --- | --- | --- |
| Phase 0 | 已完成 | 文档、基线和范围冻结 | 文档落盘、现状与迁移基线已记录 |
| Phase 1 | 已完成 | 飞书来源配置和持久化模型 | 数据库迁移、配置权限与凭据脱敏测试已通过 |
| Phase 2 | 已完成 | Wiki 发现、快照与可靠调度 | 快照去重、映射继承、重试与调度幂等测试已通过 |
| Phase 3 | 已完成 | 字段映射、事实数据与分析 API | 分页、事实计算、总览去重与 API 测试已通过 |
| Phase 4 | 已完成 | 能源前端重建 | 四类页面、状态反馈、生成类型和 typecheck 已通过 |
| Phase 5 | 已完成 | 全量验证与交付 | 能源范围验证、OpenAPI 与前端类型已通过；外部联调另列前置条件 |

## Phase 0：文档与基线

状态：已完成

- [x] 建立实施 Spec。
- [x] 建立阶段任务账本和实时更新规则。
- [x] 记录当前能源模块、路由、调度、迁移与测试基线。
- [x] 确认工作树中的既有修改不属于本任务。
- [x] 标记外部前置条件和来源边界。

## Phase 1：飞书来源与持久化

状态：已完成（真实飞书连通性另待外部前置条件）

- [x] 新增能源独立飞书配置及加密凭据处理。
- [x] 新增 Wiki 文档、工作表、同步运行、快照、快照行、映射和事实模型；新增表均无数据库外键。
- [x] 创建并审查仅包含能源表的 Alembic migration（`deaa413e8c30`，父 revision 为 `b272bca6fada`）。
- [x] 实现 repository/service 与配置、连通性 API。
- [x] 在 `dazah_test` 执行真实 downgrade/upgrade、管理员配置 API 与凭据脱敏集成测试。

## Phase 2：发现、归档与可靠同步

状态：已完成（真实历史回补待飞书前置条件）

- [x] 实现模块内 Wiki/Sheets 只读客户端、月度识别和递归发现。
- [x] 实现工作表快照、内容哈希、行归档、映射继承和三次指数退避重试。
- [x] 通过统一调度引擎实现每日同步、补偿、锁和手动触发。
- [x] 停止旧第三方能源采集循环和旧入口，保留历史表。
- [x] 执行快照去重、失败重试、数据库锁与补偿集成测试；真实回补另需 Wiki 根目录与凭据。

## Phase 3：映射与分析 API

状态：已完成（真实来源数据验证待飞书前置条件）

- [x] 实现映射预览、保存、版本化事实重建和数据质量反馈。
- [x] 实现直接值、累计表底、负差值和单位隔离聚合。
- [x] 实现来源、快照行、运行日志和总览 API。
- [x] 导出 OpenAPI；纯逻辑测试覆盖递归发现、月份继承、累计计算与负差值。
- [x] 执行快照分页、映射继承、配置 API 和总览去重的数据库集成测试。

## Phase 4：前端能源管理

状态：已完成

- [x] 重建总览，支持日期、类别、单位和维度筛选。
- [x] 新增来源与映射、原始数据、同步运行页面。
- [x] 删除旧设备、预警、采集日志路由及模块入口。
- [x] 使用生成类型、Server Actions、加载/空态/错误态并通过类型检查。

## Phase 5：验证与交付

状态：已完成（真实飞书联调仍待外部前置条件）

- [x] 审查针对性迁移并生成 `b272bca6fada:deaa413e8c30` 的离线 upgrade/downgrade SQL。
- [x] 执行数据库 upgrade/downgrade，并确认能源 schema drift 为 `0`。
- [x] 执行能源纯逻辑测试与 Ruff。
- [x] 执行 Mypy 并隔离能源新增代码影响；项目全局既有跨模块类型错误已记录。
- [x] 导出 OpenAPI，生成前端类型并执行 typecheck。
- [x] 记录已通过、既有失败和外部依赖。

## 外部前置条件

- [ ] 提供包含月度表格的 Wiki 父根目录 URL。当前链接仅为月度叶子表。
- [ ] 为能源模块独立飞书自建应用配置 Wiki 与电子表格读取权限，并授予目标知识库和文档访问权。

## 追加工作单元：配置鉴权与多 Sheet 关联（2026-07-13）

状态：已完成

- [x] 修复 Server Action 到后端的 `Authorization` 透传，保持后端管理员权限校验不变。
- [x] 增加工作表来源角色：全厂日总量、能源分表、车间明细；总览默认只统计明细来源。
- [x] 支持以工作表标题作为固定 `车间` 维度，适配各车间字段不一致的 Sheet。
- [x] 在映射界面清晰显示角色、默认统计规则和固定维度提示。
- [x] 新增覆盖角色继承、固定车间维度和总览排重的测试；重新导出 OpenAPI、生成前端类型并执行类型检查。

## 追加工作单元：Server Action 运行时鉴权兜底（2026-07-13）

状态：已完成

- [x] 转发原始 `auth_token` Cookie，并在无原始 Cookie 时回退 Bearer Token，避免 Server Action 上下文无法可靠解析认证状态。
- [x] 重启开发前端并以容器日志验证保存配置、连通性测试和手动同步写请求均返回 200；日志未记录 token。

## 追加工作单元：Wiki 节点错误诊断与 Sheet 发现（2026-07-13）

状态：受阻（等待飞书知识库资源授权）

- [x] 保留飞书 HTTP 400 响应中的安全错误码、错误描述和请求日志标识，避免只显示泛化的 HTTP 异常。
- [x] 按官方 Wiki 节点接口复核请求参数，并将“节点不存在/无权限/服务错误”的可操作指引显示在连通性结果中。
- [x] 修正多 Sheet 枚举为官方 `GET /sheets/v3/spreadsheets/:spreadsheet_token/sheets/query` 接口。
- [x] 核对开发数据库的 Alembic revision，并补齐已部署能源映射角色字段迁移（`deaa413e8c30 → 15e3b08711ec`）。
- [ ] 用已保存的能源配置重新验证节点读取与工作表发现：当前实测为飞书 `131006 permission denied`，需先将应用加入目标知识库成员/管理员或节点协作者，并开通 Wiki 节点读取权限；授权后可直接点击“测试连通性”恢复验证。

## 追加工作单元：能源运营总览与动态导航（2026-07-13）

状态：已完成

- [x] 扩展总览查询，严格隔离日总量、能源分表与车间明细口径，并支持车间/来源工作表筛选。
- [x] 返回数据最近日期和最新 KPI，保证百分比指标不参与期间求和。
- [x] 在侧边栏由已映射 Sheet 动态生成“按能源”和“按车间”菜单。
- [x] 重建总览为 KPI、趋势、排名和明细的图表驾驶舱，并处理加载、空态、失败和窄屏。
- [x] 更新 OpenAPI、生成类型并完成后端、前端验证。

## 实施日志

### 2026-07-13

- 已创建能源 Wiki 管理模块 Spec 与实施账本；尚未修改业务代码、数据库迁移或前端路由。
- 基线确认：后端当前 Alembic 唯一 head 为 `b272bca6fada`；能源模块公开设备、采集、预警 API，且 `app/main.py` 启动旧 `energy_collection_loop`。
- 后端工作树存在质量模块及平台飞书相关的既有未提交改动；本任务仅修改能源模块、必要的调度注册、对应迁移、前端能源目录及本账本，不触碰上述改动。
- 外部来源边界已冻结：用户提供的 URL 是月度叶子表，生产配置必须填写 Wiki 父根目录；未提供根目录和飞书凭据前，可完成代码与模拟验证，不能做真实联调。
- Phase 0 已完成，进入 Phase 1：新增能源独立飞书配置和持久化模型。
- 已完成 Phase 1–3 的代码实现：新增 8 个无外键的能源 Wiki 表模型、独立飞书只读客户端、快照/映射/事实服务、统一调度器注册和 11 个能源 API 路径（13 项操作）；迁移为 `deaa413e8c30`。旧第三方采集 loop、旧 API 和前端旧路由已移除，历史表不动。
- 已完成 Phase 4：交付能源总览、来源与映射、原始数据与快照、同步运行记录四类页面；写操作均通过 Server Actions，页面使用 OpenAPI 生成类型。
- 验证通过：`pytest tests/modules/energy/test_models.py tests/modules/energy/test_wiki_ingestion.py -q` 为 **9 passed**（39 条既有弃用/第三方告警）；针对性 `ruff check` 通过；`alembic upgrade b272bca6fada:deaa413e8c30 --sql` 与 `alembic downgrade deaa413e8c30:b272bca6fada --sql` 通过；OpenAPI 已导出；`pnpm generate:api` 与 `pnpm typecheck` 通过。
- 验证受阻：安全测试库 `dazah_test` 的 PostgreSQL `localhost:5432` 拒绝连接，Docker Desktop daemon 未运行；因此未执行迁移实际 upgrade/downgrade、持久化 repository/service/API 测试、快照锁和分页集成测试。
- 既有基线问题：全量 `alembic upgrade head --sql` 在早期 Agent JSONB `bulk_insert` 迁移失败；全量 `mypy` 报 1,024 个既有跨模块错误（85 个文件）。这两项不由能源改动引入，能源 migration 的定向离线 SQL 已通过。
- 真实联调仍受阻：尚未提供含月份节点的 Wiki 父根目录 URL 和已授权的能源飞书应用凭据；当前月度叶子链接不能发现后续月份。
- 已恢复验证：`localhost:5432` 已可连接且 Docker Server 可用；开始在隔离测试数据库执行实际迁移、集成测试及 migration drift 检查。
- 已在 `dazah_test` 完成真实 `deaa413e8c30 → b272bca6fada → deaa413e8c30`，并确认 revision 回到 `deaa413e8c30 (head)`；能源 metadata 定向 drift 检查结果为 **0**。
- 扩展能源测试至 **17 passed**（39 条项目既有弃用/第三方告警）：覆盖快照只在变化时新建、同结构映射继承、重试退避、调度幂等/补偿、分页、看板仅取最新快照、累计负差值、凭据脱敏、配置管理员权限和旧接口下线。
- 已补强写接口权限：配置读取/保存、连通性测试、手动同步及映射预览/保存均要求管理员；凭据字段不出现在响应中。
- 验证通过：能源相关 Ruff；新增 `wiki_repository.py` 严格单文件 Mypy；OpenAPI 重新导出、`pnpm generate:api`、`pnpm typecheck` 均通过。
- 项目级基线仍未通过：`alembic check` 报产品、核心 Agent、身份、质量、采购与仓储的既有迁移 drift；Mypy 依赖图报 1,011 条既有跨模块类型错误（83 个文件）。定向能源 schema drift 为 0，Mypy 输出不含新增 Wiki 代码错误，未对无关模块做修改。
- Phase 1、2、3、5 的代码、迁移、测试、OpenAPI 和前端类型验收均已完成。唯一尚待执行的是外部真实飞书联调和历史回补，需要用户提供 Wiki 父根目录及已授权的独立飞书应用凭据。
- 已回读 Spec 与账本并开始追加工作单元：保存配置经由 Server Action 访问后端时漏传 `auth_token`，因此后端正确返回 `401 Login required`。将通过既有 `getAuthHeaders()` 显式透传令牌修复，绝不取消管理员保护。已根据截图把同一工作簿明确为“日总量 → 能源分表 → 车间明细”三层；总览默认只取车间明细，其他两层保留归档和核对，防止重复统计。
- 已完成追加工作单元：`src/actions/energy.ts` 通过 `getAuthHeaders()` 将 `auth_token` 转发给保存配置、连通性、同步和映射写接口，后端仍使用管理员依赖校验。新增 `15e3b08711ec` 迁移，为 `energy.sheet_mappings` 增加来源角色；角色随相同表头映射继承，`$sheet_title` 可作为固定车间维度。总览 repository 只取 `workshop_detail` / `shared_detail`，因此 `日总量` 和能源分表不会与明细重复相加。
- 验证通过：在 `dazah_test` 执行真实 `15e3b08711ec → deaa413e8c30 → 15e3b08711ec`；能源 metadata drift 为 **0**；`pytest tests/modules/energy -q` 为 **19 passed**（39 条既有告警）；能源 Ruff 与严格单文件 Mypy 均通过；已导出 OpenAPI、执行 `pnpm generate:api` 和 `pnpm typecheck`。
- 运行时复核发现前端开发容器已加载修复版 Server Action，但保存配置仍返回 401；同一容器的 `/identity/me` 为 200。判断为 Server Action 请求上下文未可靠提供解析后的 `auth_token`，开始补充原始 Cookie 透传兜底，不在日志中输出任何凭据。
- 已完成 Server Action 鉴权兜底：重启前端开发容器后，保存配置、连通性测试和手动同步均由后端返回 HTTP 200，`Login required` 已消除；未输出任何认证凭据。最新真实连通性仍在 Wiki `get_node` 返回 HTTP 400 时停止，因此不会产生任何工作表；开始保留飞书响应体错误码并针对节点授权做诊断。
- 已完成 Wiki 节点诊断与 Sheet 发现代码修复：官方确认 `get_node?token=` 调用参数正确；运行时实际收到 `131006 permission denied`，说明 App ID/Secret 已成功换取租户令牌，但应用未获该 Wiki 节点资源权限。已在连通性结果中转为中文授权指引并保留请求日志 ID；另已修正工作表发现为官方 `/sheets/query` 路径。开发库已从 `deaa413e8c30` 升级到 `15e3b08711ec (head)`，消除运行时 `sheet_mappings.source_role` 缺列错误。验证通过：能源全量 pytest **21 passed**（39 条既有告警）、Ruff、`feishu_client.py` 与 `wiki_service.py` 严格 Mypy；新增测试覆盖响应体错误码脱敏和多 Sheet 查询路径。真实 Sheet 发现受外部飞书资源授权阻塞。
- 已回读字段清单、实施 Spec 与账本并开始运营总览工作单元：采用“日总量为全厂 KPI、车间明细为拆解、能源分表为独立来源查看”的三层口径。侧边菜单将复用现有仓储模块的动态菜单模式，但只从已映射来源生成；总览 API 将补充来源角色、车间、工作表标题和最新指标语义，避免把外供蒸汽占比等百分比相加。
- 已完成运营总览工作单元：总览新增 `source_scope`（`detail`、`daily_summary`、`energy_summary`）、`workshop` 与 `source_sheet_title`，查询层按当前映射角色隔离来源，不能把三层表混加。响应补充 `metric_key`、`last_observed_at` 与 `latest_metrics`；百分比/占比仅保留最新日状态，不进入累计、趋势或排行。侧边栏只读取已映射 Sheet，自动生成“按能源”（分表）和“按车间”（车间明细）菜单，并保留范围/类别 URL 状态。`/energy` 已重构为 KPI、ECharts 趋势、排行和明细驾驶舱，含骨架、失败和无映射空态。
- 最终验证通过：`pytest tests/modules/energy -q` 为 **21 passed**（39 条既有弃用/第三方告警）；能源 Ruff 通过；`mypy --follow-imports=skip app/modules/energy/wiki_repository.py app/modules/energy/wiki_service.py` 通过；OpenAPI 已重新导出、`pnpm generate:api` 和 `pnpm typecheck` 均通过。`scripts/export_openapi.py` 的控制台勾选字符已改为 ASCII 输出，解决 Windows GBK 环境中“文件已经导出但命令失败”的误报。
- 已回读账本并处理侧边栏可见性反馈：开发数据库查询确认 `energy.workbook_sheets` 当前为 **0 行**，因此动态菜单按设计无法出现，不是前端样式未加载。侧边栏现增加“数据导航”状态提示：加载中、来源请求失败和“同步并完成字段映射后自动显示”均可见，并提供“前往来源与映射”入口；出现已映射来源后提示自动隐藏，仍只显示实际的按能源/按车间菜单。`pnpm typecheck` 已通过。
- 已检查并恢复前端开发容器热更新链路：`dazah-frontend-frontend-1` 以 `pnpm dev:webpack` 运行，工作区通过读写 bind mount 挂载至 `/app`；本机与容器内 `Sidebar.tsx` 的 SHA-256 完全一致，容器已重启并重新编译 `/energy`，最终以 HTTP **200** 响应。首次 Webpack 编译耗时约 61 秒，编译期间浏览器可能仍显示旧页面或等待响应；之后请对 `http://localhost:3000/energy` 执行一次硬刷新。
