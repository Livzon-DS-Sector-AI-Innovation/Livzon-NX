# 生产管理模块迁移实施账本

> 对应计划：`docs/production-module-migration-plan-2026-07-14.md`
>
> 创建时间：2026-07-14
>
> 执行规则：每次开始、完成或阻塞一个工作单元，先回读本账本和实施计划；随后在本文件记录状态、代码变更与验证证据。
>
> 当前阶段：Phase 0–5 已完成（外部真实数据及既有全局门禁例外已明确记录）。用户于 2026-07-15 明确暂时跳过外部交接单；真实源数据导入待交接物到位后按运行手册恢复。

## 状态说明

- `未开始`：尚未进入实施。
- `进行中`：正在实现或验证，尚未满足验收。
- `已完成`：代码、迁移、测试、OpenAPI/生成类型和阶段验收均已通过。
- `受阻`：存在外部依赖，必须说明证据、负责人和恢复条件。

## 阶段总览

| 阶段 | 状态 | 目标 | 阶段验收 |
| --- | --- | --- | --- |
| Phase 0 | 已完成（外部输入延期） | 文档、基线、数据与编码契约冻结 | 内部盘点、迁移边界和交接模板已完成；外部数据输入经用户确认延期，不阻塞功能迁移。 |
| Phase 1 | 已完成 | 计划/销售执行与受控飞书同步 | 针对性迁移、CRUD、脱敏配置、绑定预览、试运行、幂等同步和专项测试均已完成。 |
| Phase 2 | 已完成 | 批次与 203 车间工艺闭环 | 13 工序、进度聚合、批次全貌和 203 工作台已通过迁移与专项验证。 |
| Phase 3 | 已完成 | 发酵与生产日志 | 五类业务、状态操作、双工作台和专项数据库验证已完成。 |
| Phase 4 | 已完成（真实数据延期） | 历史数据迁移与灰度 | 导入/对账/回滚框架、审计表和空数据演练已完成；真实灰度等待交接物。 |
| Phase 5 | 已完成（既有全局门禁例外） | 全量验证与交付 | 专项测试和运行态通过；全局 Alembic/Mypy 历史漂移已留档。 |

## Phase 0：文档、范围与基线

状态：已完成（外部交接输入延期）

- [x] 读取项目总规范、前端规范、设计规范、后端规范及来源压差子目录规范。
- [x] 盘点外部目录：97 个生产后端 Python 文件、38 个路由页、25 个 action；未发现迁移或数据导出。
- [x] 标记不迁移项：269 个独立压差工程文件、98 个 Python 字节码、一个备份页面与锁文件。
- [x] 对比平台：批次、计划、工艺规程、记录、物料平衡、标签复核、压差统计和生产飞书配置已存在基础实现。
- [x] 建立完整实施计划和本任务账本。
- [x] 确认 Alembic 静态 head 为 `15e3b08711ec`，并以此生成后续迁移 revision。
- [ ] 记录源数据库导出、附件清单、飞书表范围和业务负责人确认的产品—车间—生产线映射。
- [x] 核对生产模块迁移链与本次新增表的真实数据库结构；全局模型漂移已记录为既有跨模块问题。
- [x] 建立可填写的源数据、产品—生产线和销售执行飞书字段映射确认单：`docs/tasks/production-module-migration-inputs-2026-07-14.md`。
- [x] 用户确认暂时跳过交接单填写；交接物转为 Phase 4 真实数据导入的恢复条件，不再阻塞功能代码迁移。

## Phase 1：计划、销售执行与飞书同步

状态：已完成

- [x] 决定并实现计划执行明细与销售执行模型；不覆盖既有 `ProductionPlan` / `PlanTask`。
- [x] 实现 `SalesPlanDetail`：保留外部 14 项销售执行指标，补充来源与来源记录标识；不改既有计划表。
- [x] 创建并审查针对性迁移 `d9aaa2fe5cee_add_production_sales_plan_details.py`；仅新增 `production.sales_plan_details`，不使用外键或破坏性 DDL。
- [x] 实现销售执行明细的 Repository、Service、Schema、列表/详情/新增/更新/软删除 API。
- [x] 将 API 响应改为类型化 `ProductionApiResponse`，并已导出 OpenAPI、生成前端类型。
- [x] 在 `/production/plan` 新增“产销计划（销售执行）”页签，覆盖产品筛选与 14 项指标的新增、编辑、删除。
- [x] 为新增表执行并审查真实 upgrade；Docker 数据库已处于 `d9aaa2fe5cee (head)`，表、21 个业务/审计字段与 3 个预期索引均已核验。受控环境不执行 downgrade，以免删除已验证的业务表。
- [x] 扩展生产模块飞书配置为“凭据 + 同步绑定”；凭据沿用加密保存和脱敏页面，绑定不存储密钥。
- [x] 实现同步绑定的 Model、Repository、Schema、Service、CRUD API 和软删除；`config_id` 采用 Service 校验的逻辑关联，不新增外键。
- [x] 创建并在真实数据库应用针对性迁移 `a571e00e39c4_add_production_feishu_sync_bindings.py`；表、18 个字段和 4 个预期索引/唯一约束已核验。
- [x] 实现绑定级飞书预览、字段映射、试运行、幂等同步和脱敏失败摘要；模块内读取加密凭据后调用平台 helper。
- [x] 扩展 `/production/feishu-config`；新增同步绑定面板，使用 Server Actions 与生成的 OpenAPI 类型；保存/启用绑定不会自动读写飞书。
- [x] 新增销售执行同步映射与凭据脱敏专项测试；在独立 `dazah_production_test` 数据库执行通过，并完成前端全量 typecheck 和目标 ESLint。

## Phase 2：批次与 203 工艺闭环

状态：已完成

- [x] 采用 `workshop_code` 兼容来源车间编码，既有 `/production/batches?production_line=` 入口保持不变。
- [x] 迁入 203 车间概览、批次进度及接收至包装共 13 道工序业务规则。
- [x] 以统一工序执行模型实现 13 工序的 Schema、Repository、Service、API 与可扩展来源幂等键。
- [x] 新增 203 工作台 UI、工序录入、状态完成、批次进度矩阵及批次全貌 API；未恢复重复 workshop URL。
- [x] 覆盖状态流转、软删除、来源幂等约束、瓶颈识别与包装月产量计算；接口沿用平台当前用户依赖。

## Phase 3：发酵与生产日志

状态：已完成

- [x] 迁入发酵与种子培养；发酵液接收及预处理已纳入 Phase 2 的统一 13 工序模型。
- [x] 迁入非保密事件、班次运行摘要、班组交接确认，支持事件关闭与接班确认。
- [x] 新增发酵及日志导航/页面，补齐审计字段、列表筛选、软删除和当前用户依赖；批量导出由 Phase 4 导入/对账工具统一承接。

## Phase 4：历史数据导入与灰度

状态：已完成（真实数据执行等待交接物）

- [ ] 获取源 PostgreSQL 只读导出、附件清单、飞书历史表范围与数据保留要求（按用户指示延期）。
- [x] 在隔离测试库完成空数据 dry-run、指纹幂等、重复输入拒绝、对账及合成记录回滚演练。
- [x] 工具可输出字段校验、记录级错误、重复来源 ID、目标缺失和逐实体计数；真实异常清单等待源数据。
- [x] 已形成只读验证、单车间写入灰度、全模块切换及源端回查窗口步骤；真实切换等待交接物。
- [x] 完成按运行批次的新增软删除、更新前值恢复和回滚审计自动化演练。

## Phase 5：全量验证与交付

状态：已完成（既有全局门禁例外）

- [x] `alembic heads` 单 head、业务库/测试库 `alembic upgrade head` 通过，均为 `f31f6eac4007`。
- [ ] 全局 `alembic check` 仍受既有跨模块模型/迁移漂移影响；本次 6 个针对性 migration 已逐个审查并在真实数据库应用，禁止生成全局修复迁移。
- [x] 后端生产模块 13 项专项测试、目标 Ruff 和 compileall 通过。
- [ ] 全局 Mypy 递归检查仍报告 99 个既有文件 1243 项类型债务；即使限定新增文件也会递归既有模型，结果已作为平台基线问题记录，不在本次迁移中改写其他模块。
- [x] OpenAPI 导出、`pnpm generate:api`、`pnpm typecheck` 和新增前端目标 ESLint 通过。
- [x] 权限路由未登录返回 401，前端新增路由未登录返回 307；审计、密钥脱敏、同步幂等、导入对账及回滚均有专项验证。
- [x] 更新完整计划、任务账本、输入确认单和历史数据迁移运行手册；真实业务交接记录按用户指示延期。

## 已知风险与决策记录

| 日期 | 事项 | 结论/影响 |
| --- | --- | --- |
| 2026-07-14 | 外部模块没有迁移与数据文件 | 不能进行历史数据导入；Phase 4 等待源库与附件交付。 |
| 2026-07-14 | 外部计划模型与平台计划模型冲突 | 采用增量明细模型，不覆盖平台既有 `ProductionPlan` / `PlanTask`。 |
| 2026-07-14 | 外部 `SyncSettingsButton` 将 App Secret 写入 localStorage | 禁止迁移该实现；保留平台加密凭据与脱敏页面。 |
| 2026-07-14 | 外部压差工程为独立 Nest/Vite 项目 | 不迁移、不覆盖平台既有 FastAPI/Next 压差能力。 |
| 2026-07-14 | `alembic check` 全局失败 | 发现既有跨模块模型/迁移漂移（包括产品、质量、能耗、仓储等）以及 BaseModel 审计外键的历史建模差异；本次新增表已按后端规范不建外键。禁止用自动生成或修改历史迁移“修复”该全局问题，留待专项治理。 |
| 2026-07-14 | Phase 0 外部交接缺失 | 外部目录未提供源库、附件、飞书历史范围或业务确认的生产线映射；已创建交接确认单，收到后可恢复 Phase 0 并进入 Phase 4 导入演练。 |

## 执行记录

### 2026-07-14：建立迁移基线

- 完成外部模块结构、交接文档、业务功能、代码差异和平台约束审查。
- 发现外部后端存在大量 `db.refresh()` 写法，部分标签复核代码直接读取 AI 环境变量；后续仅迁移业务规则，按平台异步 ORM 和 `llm_client` 规范重写。
- 当前工作区已有与本任务无关的修改；本任务不回退或覆盖这些改动。
- 下一工作单元：核对 P0 的模型、迁移链和接口基线，然后开始计划/销售执行/飞书同步基础实现。

### 2026-07-14：销售执行明细首条纵向实现

- 新增 `production.sales_plan_details` 的模型、Pydantic Schema、Repository、Service 和 `/api/v1/production/sales-plan-details` CRUD API；保留现有 `ProductionPlan` 与 `PlanTask`，未覆盖历史契约。
- 使用 Alembic 自动生成 revision `d9aaa2fe5cee`，并手工审查/限定 DDL：仅创建生产 schema 下的销售执行表与产品索引，无外键、无 DROP 操作。
- 前端已在计划页增加“产销计划（销售执行）”页签；请求与响应使用 `src/types/generated/schema.ts` 的 OpenAPI 类型。
- 验证通过：`uv run alembic heads`（`15e3b08711ec`）、新增 migration 的 `ruff check`、销售执行 Schema 的实例化断言、生产模块 `compileall`、`scripts/export_openapi.py`、`pnpm generate:api`、`git diff --check`。
- 未验证：Docker Desktop 未运行，无法执行 `alembic current/upgrade` 或数据库集成测试；`pnpm typecheck` 与目标 ESLint 均在 64 秒内未返回而被执行环境超时终止。后端全量 Ruff 同时报告生产模块已有 220 项历史告警，新增 migration 的单文件 Ruff 已通过。
- 离线迁移 SQL 演练：设置 `PYTHONIOENCODING=utf-8` 后已越过历史 Emoji 注释的 GBK 编码问题，但在既有 revision `8f2d4c6a9b10` 的 JSONB `bulk_insert` SQL 渲染失败，尚未执行到本次 revision；该问题不修改历史 migration，待可用数据库上执行真实 upgrade 验证。
- 下一工作单元：为销售执行明细补独立测试和数据库验证；随后实施飞书同步绑定，禁止使用外部快照的 localStorage 密钥实现。

### 2026-07-14：Docker 数据库验证

- Docker Compose 服务正常：PostgreSQL 17 健康，应用服务已自动将数据库升级至 `d9aaa2fe5cee (head)`；`alembic current` 与 `alembic heads` 一致。
- 已在实际数据库核验 `production.sales_plan_details`：表存在，字段包含 14 项销售指标、来源字段和通用审计字段；索引为主键、产品索引与 `(source, source_record_id)` 唯一约束。
- `alembic check` 未通过，但差异为既有的全局跨模块模型漂移，并非本次针对性迁移遗漏；不修改历史迁移、不执行全局自动生成。该检查保留为 Phase 5 的专项治理项。
- 下一工作单元：实现仅保存加密配置引用、目标表、字段映射和运行状态的飞书同步绑定；实际写入同步须等待业务确认目标表和字段映射后再启用。

### 2026-07-14：受控飞书同步绑定基础

- 新增 `production.feishu_sync_bindings`：逻辑关联的飞书配置、业务目标、适用产品/车间、飞书 `table_id`、字段映射、启用状态、最近运行状态与错误摘要。迁移 `a571e00e39c4` 已在 Docker PostgreSQL 实际应用，数据库 revision 与 head 一致。
- 新增 `/api/v1/production/feishu-sync-bindings` 的列表、新增、更新、软删除 API。创建/变更会校验生产飞书配置存在，但不会读取或写入飞书；不记录 App Secret、App Token 或任何解密后的凭据。
- `/production/feishu-config` 已增加“同步绑定”管理面板。前端以生成的 `ProductionFeishuSyncBinding*` OpenAPI 类型调用 Server Actions，字段映射采用 JSON 对象录入，并明确提示“保存/启用不自动同步”。
- 验证通过：迁移单文件 Ruff、生产模块 `compileall`、`alembic heads`（`a571e00e39c4`）、真实数据库字段/索引查询、绑定 Schema 实例断言、OpenAPI 导出、`pnpm generate:api`、后端与根工作区的 `git diff --check`。
- 未验证：`pnpm typecheck` 和三个目标文件的 ESLint 均在 64 秒执行上限内未返回，因此未标记通过；尚无可用于写入演练的业务确认 `sync_target`、飞书表和字段映射，故未实现实际同步运行/幂等写入或同步运行记录。
- 下一工作单元：业务负责人确认目标表、字段映射、冲突规则和同步频率后，实现同步运行记录、预览确认、幂等 upsert、失败摘要和集成测试；并在更长的 CI/本地终端完成前端 typecheck。

### 2026-07-14：Phase 1 收口与专项验证

- 新增 `production.feishu_sync_runs` 和迁移 `266f913b410c_add_production_feishu_sync_runs.py`，记录预览/执行模式、幂等键、开始/结束时间、创建/更新/跳过/失败计数和脱敏错误摘要；已在 Docker PostgreSQL 实际应用并核验字段。
- 销售执行同步仅接受 `sales_plan_detail` 绑定：先按绑定读取飞书预览，试运行不写业务表；执行模式用飞书 `record_id` 作为 `source_record_id` 幂等 upsert，仅更新既有 `source=feishu` 记录，手工记录不会被覆盖。
- 飞书配置页已增加预览、试运行和二次确认后的执行操作；未启用绑定不能执行。运行状态回写绑定，失败信息会移除 App ID 与 App Token。
- 验证通过：生产模块 `compileall`、三个针对性 migration Ruff、OpenAPI 导出、`pnpm generate:api`、`pnpm typecheck`、目标 ESLint、`git diff --check`；独立 `dazah_production_test` 数据库已全量迁移至 `266f913b410c`，专项 pytest 结果为 `3 passed`。
- Phase 1 验收完成。Phase 0 的外部依赖不以猜测替代，详见 `docs/tasks/production-module-migration-inputs-2026-07-14.md`；在收到交接物前保持受阻。

### 2026-07-15：恢复 Phase 2–5 功能迁移

- 用户明确暂时跳过交接单填写，授权继续剩余阶段的业务功能迁移。
- 执行边界：产品—生产线映射先采用来源系统已有车间编码作为兼容值；历史数据、附件和真实飞书表数据不虚构，Phase 4 先交付可重复执行的导入/对账/回滚框架与空数据演练。
- 当前工作单元：盘点 203 工序链、来源模型/接口与平台现有批次能力，形成最小可用的批次—工序—进度纵向闭环。

### 2026-07-15：Phase 2 批次与 203 工艺闭环

- 新增统一 `production.process_execution_records`，用 `process_code` 和 `step_sequence` 承载接收、预处理、陶瓷膜、两次脱色/过滤/浓缩/离心、重结晶、烘干与包装共 13 工序；工序专属字段保存在 JSONB，避免复制 13 套重复 CRUD。
- 新增工序记录 CRUD/完成操作、批次进度矩阵、瓶颈识别、包装月产量和批次全貌 API；来源记录唯一约束可供后续导入与飞书同步幂等使用。
- 新增 `/production/workshop-203` 工作台，覆盖筛选、录入、编辑、完成、删除和进度查看；前端使用 Server Actions 与生成的 OpenAPI 类型。
- 迁移 `5d2fa1558170` 已在业务库和独立测试库应用，目标表 18 个字段完整；专项测试 `2 passed`，新增后端 Ruff/compileall、前端 typecheck/目标 ESLint、OpenAPI 导出与类型生成均通过。
- 下一工作单元：按来源字段迁入发酵、种子培养、非保密事件、班次日志与交接确认，并补齐操作台和专项测试。

### 2026-07-15：Phase 3 发酵与生产日志

- 新增发酵、种子培养、非保密事件、班次日志与班组交接五类平台模型；种子培养的来源字段按物料、质量、操作三组 JSONB 完整承载，避免丢失摇瓶制备明细。
- 新增完整列表/新增/更新/软删除 API，并实现发酵日期校验、事件影响时长自动计算、事件关闭和幂等接班确认。
- 新增 `/production/fermentation` 与 `/production/shift-log` 两个业务工作台和菜单入口，覆盖现场登记、台账查看、事件闭环及交接确认。
- 针对性迁移 `d550f4fa1c41` 已在业务库和独立测试库应用，保持单 head、无新增数据库外键；OpenAPI 与生成类型已更新。
- 验证通过：专项 Ruff/compileall、数据库集成测试 `4 passed`、前端 typecheck 和目标 ESLint。
- 下一工作单元：实现历史导入运行批次、来源记录映射、内容指纹幂等、对账报告和可审计回滚框架；无真实交接物时仅执行空数据安全演练。

### 2026-07-15：Phase 4 历史导入与灰度框架

- 新增 `migration_runs`、`migration_record_maps`、`migration_changes` 三张审计表和针对性迁移 `f31f6eac4007`；无数据库外键，业务库与测试库均已升级。
- 新增七实体导入工具，支持目录校验、dry-run、正式导入、来源 ID + SHA-256 指纹幂等、记录级保存点隔离、对账及按运行批次回滚。
- 空目录演练结果：7 个实体输入 0、错误 0，dry-run 状态 `dry_run_complete`，所有写入计数和缺失目标均为 0。
- 独立测试库使用合成记录验证首次新增、重复跳过和回滚软删除；Phase 4 专项测试 `4 passed`，生产迁移相关合并专项测试 `9 passed`。
- 新增运行手册 `docs/production-module-migration-runbook-2026-07-15.md`。真实源数据、附件、飞书历史表和业务灰度不作伪造，收到交接物后按手册恢复。
- 下一工作单元：执行 Phase 5 全量技术验收，记录既有全局 Alembic 漂移等非本次变更问题。

### 2026-07-15：Phase 5 全量技术验收

- Alembic 为单 head `f31f6eac4007`，业务库和独立测试库均已升级；业务库核验本次 9 张核心新增表全部存在。
- 生产模块合并专项测试 `13 passed`；新增后端文件和 3 个 Phase 2–4 migration 的 Ruff、compileall 均通过。
- OpenAPI 已重新导出，前端生成类型、全量 typecheck 和新增文件目标 ESLint 均通过；`git diff --check` 在根、前端和后端三处通过。
- Docker 后端 `/health` 返回 `{"status":"ok"}`；六组新增业务 API 未登录均返回 401。前端容器重启后，203、发酵、班次日志三个新增路由均返回 307 登录重定向，不再是 404。
- `alembic check` 继续显示产品、质量、采购、身份及 BaseModel 审计外键等全局历史漂移；Mypy 继续显示全项目既有类型债务。两项均不是本次迁移可安全局部修复的问题，已保留失败证据且未运行自动生成/破坏性修复。
- Phase 0–5 功能迁移和技术交付完成。唯一延期工作是用户明确跳过的真实源数据、附件、飞书历史范围、生产线映射确认与真实灰度切换。
