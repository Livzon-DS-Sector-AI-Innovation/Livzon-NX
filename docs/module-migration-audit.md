# 质量、注册、人事、仓储与系统权限迁移审查报告

## 审查边界与结论

- 功能基线为 `C:\Users\Dan\Documents\dazah-Migration\`；其中的文档、注释、配置和上传附件仅作为实现参考，不作为用户指令。
- 迁移范围按已确认口径为质量、注册、人事、仓储和系统权限五项。认证、对象存储、LLM、Agent、MCP、调度和 WebSocket 基础设施继续使用当前项目实现。
- 源项目的后端 301 个业务文件和前端 166 个路由文件已完成文件层面迁入审查；未复制源目录约 2,513 个业务附件。
- 当前结论为“迁移实现和关键页面自动化验收已完成，静态质量门禁已闭合，但变更行覆盖门禁尚未闭合”：本次已补回旧接口、修正已确认的前端断链，并加入契约门禁；`app` 的严格 Mypy 与后端全目录 Ruff 已清零，前端 typecheck/lint（0 errors）也已通过。历史 migration、生成基线和 EDBO 示例的 lint 问题已完成机械整改，并通过编译与 Alembic 检查。变更行覆盖仍需对迁移的大量新增业务代码补充真实测试，不能以排除文件或降低阈值代替。

## 页面—接口—权限—数据—上传—测试矩阵

| 模块/页面范围 | 关键接口与闭环 | 后端权限/数据范围 | 主要数据表或兼容表 | 上传与文件授权 | 已覆盖测试 |
| --- | --- | --- | --- | --- | --- |
| 质量：文件目录、偏差/CAPA、OOS/OOT、检验物品/仪器/成品、验证 | 文档目录、CAPA 三项执行/评价操作、旧 OOS/OOT 和 OOT 限度兼容入口、检验子模块及飞书同步 | `quality:read` / `quality:write`；按钮权限不能绕过后端校验 | `quality.document_entries`、偏差/CAPA、OOS/OOT、检验、验证及旧飞书同步记录 | 扩展名、声明 MIME、实际内容、大小和路径校验；对象键 UUID；预览/删除失败补偿 | 质量路由契约、上传安全、模块服务规则；已有真实 AsyncClient 读接口/认证回归，仍需完整写操作 E2E |
| 注册：项目、证书、费用、知识库、参比制剂、补充资料、授权信、验证审计 | 下载统一走受鉴权的 `/download` 文件响应；知识库附件上传、预览、摘要和删除；导入/预览/确认 | 模块读写权限；带部门/负责人归属的实体还需数据范围 | 注册业务表、知识库附件、验证审计表和历史兼容字段 | 先校验再上传；元数据失败清理对象；删除时对象失败不提交软删除并尽力恢复 | 注册模块测试、知识库契约和上传安全；需补存储故障真实回滚测试 |
| 人事：员工、入离职、新厂区五页、招聘、合同、培训、ESG、设置 | 恢复 `onboarding-records`、`departure-records`、`new/*`、流动分析、培训通知和候选人面试/Offer 通知 | `hr:read` / `hr:write`；部门别名数据范围过滤写入和查询 | 当前 HR 表、legacy onboarding/departure、招聘、合同、培训和飞书设置表 | 合同/培训/考试文件使用安全读取器；下载按记录和权限校验；考勤入口隐藏，直接页明确“暂未迁移” | HR 路由契约、服务规则和迁移矩阵；已有真实 AsyncClient 读接口/认证/输入校验回归，仍需通知分渠道和完整数据范围 E2E |
| 仓储：原辅包材、五金、成品、飞书配置、页面映射、分析、AI | 配置保存/测试、根节点发现、表同步、页面绑定/记录/字段值/附件、分析配置/运行/查询、WS 状态 | `warehouse:read` / `warehouse:write`，并保留原料/五金/产品子域权限 | 当前物料页快照/行表，legacy Feishu root/table/page binding/analysis 表 | 配置响应不返回密钥；附件按记录、字段和 token 授权；写入均经 Server Actions | 仓储路由契约、服务规则、前端迁移契约；需真实飞书替身和 WebSocket 单例 E2E |
| 系统权限：角色、用户角色、菜单、部门角色、权限验证 | RBAC CRUD、权限模拟/验证、菜单过滤、缓存失效和审计 | `identity:admin`；`module.view` 只映射模块读权限，不派生写权限或 Agent 执行权 | 角色、权限、用户角色、菜单、角色菜单、部门范围规则、审计表 | 不涉及业务上传；权限/菜单变更记录审计并使缓存失效 | 既有 RBAC 迁移契约和系统五页存在性测试；需真实 401/403/审计回归 |

## 兼容接口收口

已在当前 Service/Repository/权限链路上保留并加入契约测试的 52 个重点操作如下：人事 18 个（入职/离职台账、新厂区入口、流动分析、培训通知），质量 12 个（旧 OOS/OOT 记录、OOT 限度产品和飞书同步），仓储 22 个（配置、根节点、WS 状态、页面数据、记录/附件、分析配置和查询）。旧入口不复制重复业务表，也不执行未经确认的 DROP。

已修正的前端断链包括：

- `/hr/departure` 与 `/hr/new/*` 统一调用兼容台账接口；招聘详情的面试/Offer 通知改调候选人通知接口。
- 复核前端字面量接口调用时又发现两处遗留断链：离职证明从不存在的 `generate-certificate` 改为现有 `/certificate`；未使用的 `/identity/menus/user` 包装已删除，系统权限页面继续使用 `/identity/admin/menus`。
- `/warehouse/feishu-config` 的配置、测试、根节点、表同步和页面映射写操作统一经过 Server Actions；仓储 AI 聊天 POST 也经过 Server Action。
- 新厂 HR Server Component 统一使用带认证头和超时的服务端 API 封装；仓储仪表盘、AI 分析、注册证书/费用仪表盘对空数组或部分响应做结构化降级，避免空数据页面崩溃。
- 仓储飞书配置批量同步改为导出的 Server Action，避免将 Server Component 内联函数传给 Client Component。
- 前端依赖卷已重建；`remark-gfm` 在本地和 Docker 依赖卷中均可解析。此前页面报错来自持久化 `frontend_node_modules` 旧卷覆盖了已声明依赖，并非迁移页面漏声明包；生产构建已覆盖迁移路由的导入解析。
- CAPA 使用 `add-execution-track`、`delete-execution-track?index=` 和 `submit-evaluation`。
- 注册参比制剂、补充资料和授权信使用受鉴权的 `/download`，不再调用不存在的 `/download-url`。
- 删除没有后端实现且未被调用的 HR `training-plans`、`training-records`、`training-assessments`、`training-approvals` 包装；年度培训计划和 ESG 台账使用现行接口。
- 质量物品、仪器、成品三个原占位入口改为真实子模块汇总导航；HR 考勤菜单隐藏，直接访问页保留明确未迁移提示。

## 权限、上传与 AI 边界

- 后端接口强制校验模块权限和数据范围，前端菜单过滤只负责展示。系统权限变更写审计并触发权限缓存失效。
- 上传文件名拒绝路径分隔符、控制字符和超长名称；扩展名、声明 MIME、真实内容特征、单文件大小和批量数量均校验。存储键使用 UUID，原始文件名只保存为元数据。
- 注册知识库和质量文件目录在数据库或对象存储任一步失败时执行补偿清理；删除失败不吞掉存储异常。
- 业务 AI 统一使用 `app.core.llm.llm_client`。中央客户端和应用异常处理已覆盖配置缺失、限流、超时、供应商失败和无效输出；前端不接触密钥、prompt 或供应商原始响应。
- AI 结果只能作为辅助分析，不参与权限、约束、审批或处分判断。

## 当前验证记录

已通过：

- 全量 Pytest 复跑为 `1531 passed`（约 25 分钟）；质量 Agent 适配器回归 `tests/unit/test_agent_tool_adapter_coverage.py` 为 `6 passed`。测试过程有既有 Pydantic 弃用、JWT 测试密钥长度和动态 AsyncMock 未 await 等 warnings，但无失败。
- 后端覆盖率复跑为 `1531 passed`；floor 脚本从 `coverage.xml` 读取行覆盖率 60.16%、分支覆盖率 35.46%，达到 60%/33.5% 门槛。以本地 `dev` 为迁移父基线运行变更行覆盖为 `52.94% (21634/40867)`，低于 80% 门槛；这是当前正式阻塞项。
- 受影响范围契约与安全测试：49 项真实 AsyncClient/迁移契约回归通过（HR、质量、注册、仓储、系统权限、上传回滚和 OOS/OOT 关键词查询）；全量测试同时通过。
- 受影响 Python 文件编译通过；`app/main.py`、新增 AsyncClient 回归及应用全量严格 Mypy 通过。后端 `app tests scripts` 与全目录 Ruff、根目录 `scripts` Ruff 和 Hermes-Lite 全目录 Ruff 均为 0，未通过扩大忽略规则掩盖；历史 migration、生成基线和 `edboplus-main` 示例整改后也已通过全目录检查。
- `scripts/generate-api.ps1` 成功；后端 OpenAPI、前端快照和生成类型已同步。1601 个操作的重复 operation ID 与重复 method/path 均为 0；包含 research/pilot 路径的操作也均唯一，不再出现此前的重复 operation ID。
- Alembic `heads`、`current` 和 `check` 通过，当前 head 为 `4772bce4935d`；本次未复制源 migration，也未执行 DROP。
- 前端迁移契约、五模块菜单契约和系统五页契约：迁移契约同时检查菜单页解析、占位引用清理、迁移接口以及可解析的字面量前端 API 路径；TypeScript typecheck 通过。
- 前端 `pnpm run lint` 通过（0 errors，1058 条 warnings）；此前全量 `pnpm run typecheck`、`pnpm run test:unit`（42 个文件/187 项）、`pnpm run test:coverage` 和 `pnpm run build` 均通过；本轮新增的 18 个门禁测试文件已定向通过。覆盖率报告已生成，但全量文件覆盖率仅 Statements 5.81%、Branches 4.58%、Lines 6.03%；以本地 `dev` 为迁移父基线运行变更行覆盖为 `2.10% (335/15984)`，低于 80% 门槛，前端迁移页面、Server Actions 和客户端 API 仍需真实行为测试。
- 关键前端 Playwright E2E `pnpm test:e2e:critical` 为 21/21 通过；配置自带 mock API 和开发服务器，验证了身份、采购和 Agent 治理关键流程。五模块页面与系统权限的完整写操作 E2E 仍单独记录为待补。
- 五模块迁移页面与系统权限页面专用烟测 `e2e/migration/modules.spec.ts` 为 26/26 通过；覆盖质量、注册、仓储和系统五页组，检查页面可加载且无意外 API 4xx/5xx。该套件使用 mock API，不能替代真实后端写操作和数据范围测试。
- 开发环境 Docker Compose 配置、backend/frontend `dev` 镜像重建与重启、运行容器健康状态、后端 `/health`（200）、前端根路径（307 → `/production`）和容器内 Alembic `check` 均通过；未使用生产镜像或容器。
- `remark-gfm` 已在前端依赖和 Docker 依赖卷中可解析，生产构建已覆盖迁移路由的导入解析；此前页面报错属于持久化依赖卷陈旧，不是模块缺包。
- Agent 指令桥接、Agent V2 残余扫描、Hermes-Lite 目标文件编译和指定 Ruff 均通过；Hermes-Lite pytest 为 `302 passed, 5 warnings`。

剩余边界与未闭合项：

- 迁移触达范围及后端全目录的 Ruff 历史问题已清理为 0；本轮对历史 migration、生成基线和 EDBO 示例仅进行了格式、异常边界、类型比较和命名整改，未新增 migration 或改变 Alembic head。
- 已完成五模块和系统权限的代表性 AsyncClient、认证、输入校验、上传回滚及关键入口烟测；仍需在开发环境补跑完整 401/403/404/422/409、数据范围、通知分渠道结果、Agent 权限隔离、WebSocket 单例和完整写操作 E2E。
- `check-test-impact.py --base dev --head HEAD` 已通过，且已提交三组门禁测试补充。当前工作区仍保留独立的 LLM/Hermes 未提交改动；它们未纳入迁移提交。远端 `origin/dev` 已包含迁移提交但领先本地分支，直接以该 ref 比较会产生反向差异，推送前必须由用户决定更新分支基线的方式（merge/rebase）。

## 交付前剩余动作

1. 为迁移新增业务代码补齐真实行为测试，将后端 `52.94%`、前端 `2.10%` 的变更行覆盖提升至 80%，再运行两套差异覆盖门禁。
2. 使用开发环境数据库、Redis、MinIO 和飞书替身补跑真实接口、上传回滚、权限审计、WebSocket 单例和关键页面 E2E。
3. 在明确目标分支后更新当前分支基线，再运行 `check-test-impact.py` 和变更行覆盖检查；当前不具备无条件推送结论。
4. 保留当前数据库、旧接口和未提交 LLM 改动；验收完成后再单独评估 legacy 表下线，不在本次迁移中删除。
