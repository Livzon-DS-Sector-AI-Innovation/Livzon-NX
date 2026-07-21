# 质量管理新增交接包合并任务账本

> 对应 Spec：`docs/quality-module-handoff-integration-spec-2026-07-13.md`  
> 任务状态：阶段 5 已完成  
> 更新时间：2026-07-13

## 执行规则

1. 每次开始工作前先读取本账本、对应 Spec、根目录 `AGENTS.md`、前端 `AGENTS.md`、`DESIGN.md` 和后端 `AGENTS.md`。
2. 平台当前代码为主基线。禁止覆盖 `quality` 同路径文件，必须用语义差异合并。
3. 每个阶段开始时更新状态为“进行中”；完成代码、测试和回读后更新为“已完成”。
4. 每次更新必须记录：改动文件、关键决策、验证命令与结果、遗留风险和下一阶段入口。
5. 未经确认不得运行交接包旧 Alembic migration、写入真实飞书凭据或迁移不可恢复的生产历史数据。
6. API 改动必须同步 OpenAPI 和前端生成类型；前端写操作必须走 Server Action。

## 阶段总览

| 阶段 | 目标 | 状态 | 开始时间 | 完成时间 |
| --- | --- | --- | --- | --- |
| 0 | 交接审计与文档初始化 | 已完成 | 2026-07-13 | 2026-07-13 |
| 1 | 检验基础：模型、迁移、API 与测试 | 已完成 | 2026-07-13 | 2026-07-13 |
| 2 | 检验飞书、趋势与前端 | 已完成 | 2026-07-13 | 2026-07-13 |
| 3 | OOS/OOT 与 OOT 限度全链路 | 已完成 | 2026-07-13 | 2026-07-13 |
| 4 | 供应商、投诉、召回、产品质量全链路 | 已完成 | 2026-07-13 | 2026-07-13 |
| 5 | Agent、OpenAPI、全量回归与发布准备 | 待开始 | - | - |

## 当前完成度

| 维度 | 完成度 | 说明 |
| --- | ---: | --- |
| 基线与范围确认 | 100% | 已审计交接包、当前质量模块、迁移链和工作区状态。 |
| 合并规格 | 100% | 已建立平台优先的功能、数据、飞书、前端、测试与发布规范。 |
| 后端实施 | 100% | 阶段 1-4 的质量功能切片均已实现；阶段 4 包含供应商、投诉、退货召回与产品质量。 |
| 前端实施 | 100% | 已交付检验、OOS/OOT 与四个外部质量菜单入口及其受控工作台。 |
| 数据迁移 | 100% | 阶段 4 已新增并在 `dazah_test` 升级 `b272bca6fada` 针对性迁移。 |
| 自动化验证 | 100% | 阶段 4 定向 API 回归、Ruff、OpenAPI/生成类型、前端 typecheck 和 `dazah_test` 全量质量回归均已通过。 |

## 阶段执行记录

### 阶段 5：Agent 扩展、契约治理与发布准备

状态：已完成

已完成：

- 为检验、OOS/OOT、供应商、投诉、退货召回和产品质量增加八个只读 Agent 查询工具，保持人工质量决策边界。
- 同步 Hermes 静态工具白名单及 Agent 注册、工作流元数据和服务委派测试。
- 修复 CAPA 执行记录新增/删除、执行确认、效果评价和分段完成的前后端路由、方法、请求体及字段映射。
- 清除 `src/actions/quality.ts`、`src/lib/api/quality.ts` 中的显式 `any`，补充分页响应解析和空响应保护。
- 修正标签复核 Server Action 的模块路径误配。

验证结果：

- `uv run python scripts/run_quality_tests.py --skip-migrate`：`137 passed, 41 warnings`。
- `pytest tests/modules/agent/test_quality_agent_tools.py -q`：`6 passed, 39 warnings`，仅使用 `dazah_test`。
- 目标 Ruff、Python `compileall`、前端 `pnpm typecheck` 和目标 ESLint：通过。
- `uv run alembic heads`：单一 head `45c37377e9a2`。

发布边界：

- 未新增或开放审批、驳回、关闭责任判断等写入型 Agent 工具。
- 真实生产飞书凭据和业务角色的上线走查仍属于部署环境验收，不以测试凭据代替。

### 阶段 0：交接审计与文档初始化

状态：已完成

已完成：

- 读取项目总规范、前端规范、设计规范和后端规范。
- 审计交接包：后端质量模块 67 个文件、前端源码 117 个文件、质量测试 7 个文件、旧迁移 13 个文件。
- 对交接包与当前平台逐文件哈希比对：后端 45 个仅交接包文件、前端 85 个仅交接包文件；同路径文件分别有 14 个和 23 个存在差异。
- 确认当前数据库迁移 head 为 `6c9b3dc4b141`，且只有一个 head。
- 识别交接包旧迁移链包含包外 revision 引用和 `DROP TABLE`，决定不复用。
- 建立本 Spec 与本任务账本。

关键决策：

- 平台代码、数据、OpenAPI、生成类型与质量飞书配置为唯一主基线。
- 以功能切片重建交接能力；不批量复制、不过度重构、不跨模块放置业务代码。
- 默认不迁移未知历史数据；历史数据迁移必须另有源数据与核对规则。

验证结果：

- `uv run alembic heads`：`6c9b3dc4b141 (head)`。
- 已回读并确认 Spec、任务账本与既有质量迁移记录不冲突。
- 本阶段未修改任何业务代码、数据库迁移或运行配置。

已知风险：

- 当前工作区存在用户已有的根目录、身份模块、Livzon、前端设置和生成类型改动；质量交接实施不得覆盖或重置这些改动。
- 交接包不含历史业务数据和飞书 record ID 导出，无法在未提供额外输入时完成历史数据回迁。

下一阶段入口：

1. 核查目标数据库中检验相关表是否已存在，以及字段、索引和数据兼容性。
2. 仅在当前 Alembic head 基础上建立检验基础模型和针对性迁移。
3. 实现 service/repository/API，补测试，导出 OpenAPI 并更新本账本。

### 阶段 1：检验基础兼容审计

状态：已完成

已开始：

- 已完成现有质量模型、迁移历史、目标数据库表和交接包检验模型的字段及索引差异核查。
- 已完成检验基础后端实施：质量 schema 模型、repository、service、API、针对性迁移和模块测试均已交付。

当前审计结果：

- 当前质量模块未定义检验基础相关模型；交接包的七类检验模型可作为新质量子域候选。
- 平台已有的同名 `inspection_records` 位于 `equipment` schema，仅服务于设备模块；按 schema 隔离后，新增 `quality.inspection_records` 不发生表冲突。
- 审计开始时，`uv run alembic current` 确认当前连接数据库位于 `6c9b3dc4b141 (head)`；本阶段迁移后当前 head 为 `07d131578c71`。
- 已通过 `information_schema.tables` 对七张检验基础目标表进行只读查询，`quality` schema 中均不存在同名表；无需为遗留表编写 ALTER、清理或回填迁移。
- 交接包模型字段、唯一约束和迁移内容已按平台规范完成审查；本阶段迁移已创建并升级，后续不再运行交接包历史迁移。

已完成实施：

- 新增 `app/modules/quality/models/inspection.py`，包含实验室物品、仪器、通用检验、成品/固体/液体检验六类模型；新增质量检验抽象基类覆盖审计列，不在新表创建数据库外键。
- 新增 `schemas/inspection.py`、`repository/inspection.py`、`service/inspection.py` 和 `api/inspection.py`，并在质量模型、Schema 和 API 注册入口完成挂载。
- 新增 `07d131578c71_add_quality_inspection_foundation.py`；开发库已从 `6c9b3dc4b141` 成功升级至 `07d131578c71`。
- 新增 `tests/modules/quality/test_inspection_api.py`，覆盖建表、零外键、主检验记录 CRUD/筛选/重复编号/软删除，以及其他五类资源的创建与列表。
- 在 `tests/modules/quality/conftest.py` 统一注入测试管理员身份，使既有质量 API 测试经过平台的质量模块访问控制，而不是绕过路由级权限。
- 新增 `scripts/run_quality_tests.py`，从本地开发连接仅派生数据库名为 `dazah_test` 的 URL，并仅向迁移、pytest 子进程注入 `DATABASE_URL` 与 `TEST_DATABASE_URL`；数据库名不含 `test`、`testing` 或 `pytest` 时拒绝运行。
- 已重新导出 `dazah-backend/openapi.json`，并执行前端 `pnpm generate:api`、`pnpm typecheck`。

验证结果：

- `uv run ruff check <阶段 1 文件>`：通过。
- `uv run python -m compileall <阶段 1 文件>`：通过。
- `uv run alembic upgrade head`、`uv run alembic heads`、`uv run alembic current`：通过，当前唯一 head 为 `07d131578c71`。
- 数据库只读核验：6 张目标表、23 个索引、0 个外键。
- 完整业务模型加载后的针对性迁移元数据比较：`inspection_foundation_drift_count=0`。
- 后端 OpenAPI 导出、`pnpm generate:api`、`pnpm typecheck`：通过；导出时保留了既有 research 模块重复 Operation ID 警告，新增质量检验路径已进入后端规范与前端生成快照。
- 独立数据库 `dazah_test`：已确认可用并升级到 `07d131578c71 (head)`；测试过程未向开发库注入测试连接。
- `uv run pytest tests/modules/quality/test_inspection_api.py -q`（仅注入 `dazah_test`）：`7 passed`。
- `uv run python scripts/run_quality_tests.py --skip-migrate`：`126 passed, 41 warnings`；警告来自既有 Pydantic v2 兼容代码、第三方飞书 SDK 和 Alembic 配置弃用提示，不影响本阶段结果。
- `uv run ruff check scripts/run_quality_tests.py tests/modules/quality/conftest.py tests/modules/quality/test_inspection_api.py`、`uv run python -m compileall -q scripts/run_quality_tests.py tests/modules/quality/conftest.py tests/modules/quality/test_inspection_api.py`：通过。
- `uv run ruff check app/modules/quality tests/modules/quality scripts/run_quality_tests.py`：发现既有质量模块 1,008 项格式/规则问题（主要在既有 `agent_tools.py`、质量 API/服务和历史测试），未修改本阶段文件；本阶段新增/改动文件的定向 Ruff 检查通过。
- `uv run alembic check`：仍因产品、身份、采购、仓储和既有质量模块的历史 drift 失败；该检查不是由本阶段六张表产生，针对性元数据对比为零 drift。

遗留风险：

- 全项目 `alembic check` 的跨模块历史 drift 尚未纳入本交接切片，后续不得为消除此失败混入无关迁移。
- 质量模块存量 Ruff 规则问题尚未纳入本交接切片；后续应以独立代码质量任务修复，避免和业务迁移混合提交。

下一阶段入口：

1. 使用 `uv run python scripts/run_quality_tests.py` 在独立 `dazah_test` 库升级并运行质量回归；需要仅回归时使用 `--skip-migrate`。
2. 开始阶段 2：在既有质量飞书设置内补充检验实体映射、趋势预警与前端页面。

### 阶段 2：检验飞书、趋势与前端

状态：已完成

已完成实施：

- 在既有质量飞书设置中新增通用检验、实验室物品、实验室仪器、成品、固体物料和液体物料六个实体，字段对齐配置直接复用现有质量模块设置页、加密凭据和平台多维表格客户端。
- 检验实体默认“仅推送”；飞书回拉默认关闭，避免第三方 Base 覆盖平台质量台账。用户在“质量管理 → 飞书设置”完成实体表绑定后，可从检验看板明确触发单条推送。
- 新增本地检验概览与趋势 API：按资源、产品/物料、检验项目汇总；解析带单位的数值结果和常用标准表达式，计算均值、标准差、统计控制限，并标识超标准/超控制限记录。
- 新增 `/quality/inspection` 页面、质量菜单入口、React Query 局部 Provider、趋势预警表和 Server Action；前端 API 类型全部来自重新生成的 OpenAPI schema。
- 本阶段不新增数据表或迁移：飞书配置继续使用 `quality_feishu_entity_settings`，趋势预警在平台本地记录上即时计算。没有确认收件人、升级路径前，不创建通知记录或自动发送飞书消息。

改动文件：

- 后端：`app/modules/quality/api/inspection.py`、`schemas/inspection_dashboard.py`、`service/inspection_dashboard.py`、`service/inspection_feishu.py`、`service/quality_feishu_settings.py`、`service/quality_feishu_sync.py`。
- 测试：`tests/modules/quality/test_inspection_stage2_api.py`。
- 前端：`src/app/(dashboard)/quality/inspection/page.tsx`、`src/components/quality/InspectionDashboardPage.tsx`、`InspectionQueryProvider.tsx`、`src/lib/api/quality-inspection.ts`、`src/actions/quality.ts`、`src/lib/menu-config.ts` 和 OpenAPI 生成快照。

验证结果：

- `uv run pytest tests/modules/quality/test_inspection_stage2_api.py -q`（仅注入 `dazah_test`）：`4 passed`。
- `uv run python scripts/run_quality_tests.py --skip-migrate`：`130 passed, 41 warnings`；仅使用独立 `dazah_test` 数据库。
- 新增/改动阶段 2 后端文件与测试的 Ruff、`compileall`：通过。
- OpenAPI 已导出，`pnpm generate:api`、`pnpm typecheck`：通过。

遗留风险：

- 趋势预警当前为即时分析与页面提醒；若业务需要飞书通知、收件人路由、提醒去重或升级时限，必须先确认质量责任人与审批策略，再作为独立后续切片实现。
- 既有全量质量 Ruff 规则问题和跨模块 Alembic drift 仍按阶段 1 记录处理，不由本阶段引入。

下一阶段入口：

1. 开始阶段 3：OOS/OOT 台账、产品限度及其审批/飞书映射全链路。
2. 延续 `dazah_test` 专用测试库和 `scripts/run_quality_tests.py` 作为所有质量阶段回归入口。

### 阶段 3：OOS/OOT 与 OOT 限度全链路

状态：已完成

关键决策：

- 未复制交接包中直接访问 ORM、`db.refresh()`、无鉴权路由、数据库外键和硬编码飞书配置的实现。平台质量模块新增独立 ORM、repository、service、Schema 与 API 切片。
- 新增 OOS/OOT 状态机：`open → investigating → closed`。关闭只允许在“调查中”执行，且必须填写调查结论；已关闭记录不能编辑或重新启动调查。
- OOT 限度项目只保存无外键的 `product_id` UUID，由 service 在创建、查询和删除时校验产品存在；同一产品的显示顺序由唯一约束和业务校验共同保护。删除产品时同步软删除其限度项目。
- OOS 台账、OOT 台账、OOT 限度产品、OOT 限度项目各自注册为质量飞书实体，全部默认“仅推送、不开回拉”；只开放用户明确触发的单条推送，不写入或调用交接包的飞书凭据。

已完成实施：

- 新增 `quality.oos_oot_records`、`quality.oot_limit_products`、`quality.oot_limit_items` 模型与随机 Alembic revision `7a69407edc70_add_quality_oos_oot_foundation.py`。
- 新增台账、状态流转、OOT 产品/项目 CRUD、单条飞书推送 API，并用具名响应模型将输入、输出和分页元数据同步到 OpenAPI。
- 新增 `/quality/oos-oot` 前端工作台、质量菜单入口、局部 React Query Provider 和 Server Actions。页面提供 OOS/OOT 筛选、建单、启动调查、关闭、单条飞书推送，以及 OOT 产品和限度项目维护。
- 前端业务接口类型仅引用 `src/types/generated/schema.ts`；没有手写 API 输入或输出类型。

验证结果：

- 独立库 `dazah_test` 已在容器网络中升级至唯一 head `7a69407edc70`；只读检查确认三张新表存在，且数据库外键数为 `0`。本阶段未连接、迁移或写入开发库 `dazah`。
- `tests/modules/quality/test_oos_oot_api.py`：`3 passed, 39 warnings`，覆盖受控关闭、OOT 限度应用层关联/顺序冲突、飞书默认推送策略和单条推送。
- `tests/modules/quality`：`133 passed, 41 warnings`，在 `dazah_test` 执行。警告来自既有 Pydantic v2 兼容代码、第三方飞书 SDK 和 Alembic 配置弃用提示。
- 阶段 3 后端模型、Schema、repository、service、API、迁移和测试的 Ruff、`compileall`：通过；`pnpm generate:api`、`pnpm typecheck`：通过。
- `uv run alembic heads`：唯一 head 为 `7a69407edc70`。`alembic check` 仍报告产品、身份、采购、仓储等跨模块历史 drift；检查中未报告本阶段三张质量表的新增/删除差异，未为掩盖历史 drift 创建无关迁移。

运行环境说明：

- 宿主机到 PostgreSQL 端口被拒绝（`WinError 1225`），但 Docker 中 `dazah-backend-db-1` 健康，故迁移与 pytest 显式在应用容器内以 `DATABASE_URL`、`TEST_DATABASE_URL` 指向 `dazah_test` 运行。临时测试副本位于容器 `/tmp`，不修改工作区源文件或开发数据库。

下一阶段入口：

1. 阶段 4 按同一平台优先模式实施供应商、投诉、退货召回和产品质量标准；每个子域单独迁移、飞书映射、页面和测试。
2. 继续仅使用 `dazah_test`；若宿主机端口仍不可达，沿用容器网络测试方式，禁止回退到开发库。

### 阶段 4：供应商、投诉、召回与产品质量全链路

状态：已完成

关键决策：

- 交接包中供应商、投诉、退货召回和产品质量源码只作为字段与业务流语义参考；没有复制其同步 ORM 写入、`db.refresh()`、无鉴权路由、数据库外键或直连飞书的实现。
- 供应商领域保留质量模块独立台账，不与采购模块供应商实体混用；所有跨记录关系均以 UUID 应用层关联和 service 校验实现。
- 平台 PostgreSQL 是唯一事实来源。新增的六个质量飞书实体全部默认仅推送、禁止自动回拉，只允许用户明确触发单条推送。

已完成实施：

- 新增 `quality.suppliers`、`quality.supplier_qualifications`、`quality.complaint_records`、`quality.return_recall_records`、`quality.product_quality_records` 和 `quality.product_quality_standard_items`，以及随机 revision `b272bca6fada_add_quality_external_foundation.py`。
- 新增外部质量模型、Pydantic 契约、repository、service、API、飞书手动推送服务和专项 API 测试；写路径经 service/repository 更新回读，不使用 `db.refresh()`。
- 实现受控状态流：投诉 `pending → investigating → responded → closed`；退货/召回 `pending → assessing → processing → completed`；产品质量 `draft → completed → approved`。各转移均在 service 侧校验前置条件。
- 在既有质量飞书设置中注册供应商、供应商资质、投诉、退货召回、产品质量记录和产品质量标准明细，映射仅使用平台已有的设置、字段映射与凭据体系。
- 新增 `/quality/suppliers`、`/quality/complaints`、`/quality/return-recalls`、`/quality/product-quality` 四个 Server Component 入口；共用外部质量 React Query Provider 和 Ant Design 工作台，覆盖台账分页、空态/加载/失败反馈、创建、状态流转、标准明细和单条飞书推送。所有浏览器写操作均由 `src/actions/quality.ts` 的 Server Action 承载。
- 重新导出 OpenAPI、生成前端 schema。由于采购与质量都有 `SupplierListResponse` / `SupplierResponse`，生成器自动输出命名空间消歧键；采购类型别名和新质量 API 读取层均改为引用生成键，未手写 API 契约。

改动文件：

- 后端：`app/modules/quality/models/external_quality.py`、`schemas/external_quality.py`、`repository/external_quality.py`、`service/external_quality.py`、`service/external_quality_feishu.py`、`api/external_quality.py`、`service/quality_feishu_settings.py`、相关模块 `__init__.py`、`alembic/versions/b272bca6fada_add_quality_external_foundation.py`。
- 测试与契约：`tests/modules/quality/test_external_quality_api.py`、`openapi.json`、`dazah-frontend/src/types/generated/schema.ts`。
- 前端：`src/actions/quality.ts`、`src/lib/api/quality-external.ts`、`src/components/quality/ExternalQualityManagementPage.tsx`、`ExternalQualityQueryProvider.tsx`、质量组件出口、四个页面入口、`src/lib/menu-config.ts`；为生成器消歧同步调整 `src/types/purchasing.ts`。

验证结果：

- `dazah_test` 仅升级至阶段 4 revision `b272bca6fada`；只读核验确认上述六张目标表存在，且这六张表的数据库外键数量为 `0`。开发库 `dazah` 未参与迁移或测试。
- `tests/modules/quality/test_external_quality_api.py -q`（显式 `DATABASE_URL`、`TEST_DATABASE_URL` 均为 `dazah_test`）：`4 passed, 39 warnings`。
- 阶段 4 后端模型、Schema、repository、service、API、迁移与测试的定向 `ruff check`：通过。
- 后端 OpenAPI 已重新导出；`pnpm generate:api` 已同步生成 schema，`pnpm typecheck`：通过。
- `git diff --check`：通过（仅提示工作区既有 `.gitignore` 的 LF/CRLF 转换警告）。
- Docker 恢复后，容器网络中的 `tests/modules/quality -q` 显式以 `DATABASE_URL`、`TEST_DATABASE_URL` 均指向 `dazah_test` 重跑：`137 passed, 41 warnings in 17.46s`。
- 验收复核：`dazah_test` 六张目标表数量为 `6`、目标表数据库外键数量为 `0`；阶段 4 定向 Ruff 与前端 `pnpm typecheck` 均再次通过。源码迁移链保持单一 head `deaa413e8c30`，该工作区既有能源迁移以阶段 4 revision 为父节点。

已知风险：

- Docker Desktop 曾在首次验收读取容器结果时返回 HTTP 500，现已恢复；全量质量回归已在恢复后的容器网络中完成。宿主机 PostgreSQL 端口仍不作为测试入口，后续继续优先使用容器网络。
- 当前源码迁移链的唯一 head 为工作区既有能源迁移 `deaa413e8c30`，其父 revision 是本阶段 `b272bca6fada`。阶段 4 测试库仅验证到质量 revision，未迁移或验证无关能源表。
- 全局 `alembic check` 的跨模块历史 drift 仍按阶段 1-3 已知风险处理；本阶段不创建无关修复迁移。

下一阶段入口：

1. 阶段 5 已完成；后续仅处理生产环境业务角色、飞书凭据和真实 Base 表绑定的上线验收。
2. 后续回归继续仅使用 `dazah_test`，禁止使用开发库 `dazah`。

## 实时更新模板

每次后续更新在本节上方新增一条记录，使用以下结构：

```markdown
### 阶段 N：<名称>

状态：进行中 | 已完成 | 阻塞

已完成：

- ...

改动文件：

- `相对路径`

验证结果：

- `<命令>`：<结果>

风险 / 阻塞：

- ...

下一阶段入口：

- ...
```
