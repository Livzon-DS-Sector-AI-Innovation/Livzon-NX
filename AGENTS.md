# Dazah 项目 AI 开发总规范

Dazah 是面向原料药工厂的综合管理平台：

- `dazah-frontend/`：Next.js 工厂管理后台
- `dazah-backend/`：FastAPI 模块化单体后端
- `Hermes-Lite/`：Livzon Agent 编排层
- `docs/`：跨项目需求、设计和实施文档
- `scripts/`：开发、联调和契约同步脚本

优先保证业务准确、权限清晰、操作可追踪、风险可控制和前后端契约一致。

## LLM 调用边界

- 前端和后端业务模块需要 AI 分析时，统一走“前端业务 API → 后端所属模块
  Service → `app.core.llm.llm_client`”。前端不得直接调用模型供应商，不得接触
  LLM API Key；业务页面只能调用所属模块的 `/api/v1/...` 接口。
- 后端业务代码统一使用 `from app.core.llm import llm_client`，不得直接实例化
  OpenAI 兼容客户端、拼接供应商 `/chat/completions` 请求、读取 `LLM_*`
  环境变量或创建旁路 provider。
- 普通业务 AI 不得调用 `/api/v1/agent/llm/*`，不得读取或复用
  `HERMES_*`、`AGENT_LLM_PROXY_TOKEN`、`DAZAH_LLM_*` 等 Agent/Hermes 配置。
- 普通文本调用使用
  `await llm_client.chat(messages, response_format=None)`；当前 `chat()` 默认要求
  JSON object，因此自然语言或 Markdown 输出必须显式传 `response_format=None`。
- 结构化分析优先使用
  `await llm_client.chat_json(messages, expected_keys=[...])`，随后还必须通过
  Pydantic Schema 或明确业务校验检查字段类型、枚举、长度和数值范围。
- 图片结构化分析使用
  `await llm_client.chat_vision_json(prompt, image_urls, expected_keys=[...])`；
  图片上传和传递前必须校验 MIME、大小、数量、来源及当前用户权限。
- 流式文本使用 `async for chunk in llm_client.stream_chat(messages=messages)`，
  并由所属业务模块 API 向前端提供流；前端不得直接连接供应商流式接口。
- 调用方必须区分并处理 `LLMConfigError`、`LLMRateLimitError`、
  `LLMOutputError` 和 `LLMProviderError`，转换为所属模块的统一业务错误；不得把
  API Key、Authorization、完整敏感 prompt 或模型 `raw_response` 返回前端。
- 数据库中的激活配置优先于本地环境回退。模型配置和密钥由系统管理入口统一
  维护，业务模块只传业务输入和必要调用参数，不处理密钥解密、供应商认证或
  底层连接生命周期。
- LLM 输出只能作为辅助分析，不得替代权限判断、数据库约束、人工确认、审批、
  驳回或处分等责任判断；结构化结果未经校验不得直接写入关键业务字段。
- 测试必须 mock 业务模块实际导入的 `llm_client`，覆盖正常输出、无配置、无效
  输出、限流、超时和供应商失败，不得连接真实模型或使用真实密钥。

## 规范入口

修改前必须完整阅读目标项目规范；目标目录有更近的 `AGENTS.md` 时叠加遵守：

- 前端：`dazah-frontend/AGENTS.md`、界面改动再读 `dazah-frontend/DESIGN.md`
- 后端：`dazah-backend/AGENTS.md`
- Hermes-Lite：`Hermes-Lite/AGENTS.md`

框架、编码和测试细节以下级规范为准。本文件只保留跨项目边界。冲突优先级为：用户当前要求 → 最近的 `AGENTS.md` → 子项目规范 → 本文件。

## 跨项目边界

- 修改前检查工作区状态、现有实现、调用关系和适用规范。
- `AGENTS.md` 是跨 AI 工具共享规范的唯一事实源；每个 `AGENTS.md` 同目录必须
  存在仅负责导入 `@AGENTS.md` 的 `CLAUDE.md`。禁止在 `CLAUDE.md` 中复制规范，
  新增、移动或删除规范时必须同步维护桥接文件并通过仓库检查脚本。
- 只修改当前任务必需的文件，保留用户已有修改；不顺手重构或清理无关内容。
- 生产代码变化必须按 `.ci/test-impact-policy.toml` 在同一变更中补充对应模块
  测试；不得用无关测试、扩大排除或降低阈值绕过门禁。
- 提交前运行 `python scripts/check-test-impact.py --base <目标分支> --head HEAD`；
  新增代码根目录、模块布局或测试框架时同步更新策略并由 Owners 审查。
- 自动生成文件必须通过项目脚本更新，禁止手工编辑。
- 后端端点或请求/响应 Schema 变化时，从根目录运行 `.\scripts\generate-api.ps1`，核对后端 OpenAPI、前端快照和生成类型，出现无关大范围变化时停止检查。
- Agent 工具变化时同步检查后端工具注册、权限、风险与确认策略，以及 Hermes-Lite 白名单、Schema、测试和文档。
- 新增或修改环境变量时同步根目录 `.env.example`（生产）和
  `.env.local.example`（开发）；禁止在前后端或 Hermes-Lite 子目录新增环境变量文件。
- 开发和本地联调期间，Docker 构建、启动和验证必须使用开发环境镜像与容器，禁止使用生产环境镜像或容器。
- 发现后端存在尚未应用的数据库更新时，必须先执行数据库迁移并确认成功，再启动或验证后端接口，避免因数据库结构不一致导致接口不可用。
- 不读取、输出或提交真实密码、Token、Cookie、API Key、数据库凭据、飞书或 LLM 密钥。

## Git 安全

允许使用 `git status`、`git diff`、`git log`、`git show` 等只读命令。未经用户明确要求，禁止 pull、fetch、push、add、commit、分支切换或创建、merge、rebase、cherry-pick、reset、restore、checkout、clean，以及修改远程仓库、tag 或 submodule。

用户要求提交或发布时，先确认范围，不得混入无关修改或覆盖用户工作。

### 提交、推送与 PR 合并流程

本流程约束后续提交与发布操作，不代表现在执行，也不构成对所有 Git 写操作的
永久授权。用户仅要求本地提交时，只执行本地提交相关步骤；用户明确要求执行
完整推送合并流程时，才执行同步、建分支、提交、推送、创建 PR、跟踪 CI、相关
失败修复与压缩合并。授权或改动范围不清楚时，先询问，不自行扩展。

以下流程默认 GitHub 远端名为 `origin`、目标分支为 `main`。如仓库实际使用的
远端名或目标分支不同，必须先确认并在整个流程中一致替换，不得混用本地分支、
旧的远端跟踪引用或未确认的远端。这里的“同步”分为两种状态：开发分支同步是
指最新 `origin/main` 已包含在当前 feature 分支的提交历史中，即
`origin/main` 是 `HEAD` 的祖先；合并后同步是指本地 `main` 与最新
`origin/main` 指向同一提交。feature 分支在开发期间不要求、也通常不可能与
`origin/main` 哈希完全相等。

GitHub 仓库必须为 `main` 配置保护规则或规则集：合并必须通过 Pull Request，
启用必需的 CI 状态检查，并在状态检查设置中勾选“Require branches to be up to
date before merging”。除非已经确认的紧急流程明确授权，不允许绕过这些规则或
直接向 `main` 推送；多人并行开发频繁时可进一步启用 merge queue。规则配置完成
后应使用一个故意落后于 `main` 的测试 PR 验证确实会被阻止，不能只以页面上存在
规则名称作为配置成功的依据。

1. **检查并确认范围**：先检查当前分支、工作区、暂存区、未推送提交和目标远端，
   阅读适用规范；列明拟提交文件与已有提交，确认均属于本次任务。不得把工作区
   全部改动默认为提交范围，不得盲目使用 `git add .` 或 `git add -A`；只暂存已
   确认的文件或改动块，并复核暂存差异。不得读取或输出真实凭据，也不得将密钥、
   本地配置或无关生成物加入提交。
2. **保护工作并准备分支**：工作区干净且没有待保护的本次提交时，可先切换到
   `main`，先执行 `git fetch origin main --prune`，再执行
   `git merge --ff-only origin/main`，确认本地 `main` 已更新到当前远端主线后，
   再创建并切换到描述本次改动的 `feature/<简述>` 分支。已有本次未提交改动或
   未推送提交时，优先从当前状态创建 feature 分支保留工作，仅提交确认范围内的
   改动；已有专用分支时先检查是否可复用，避免重复分支或 PR。存在无关未提交改动、
   无关历史或无法安全切换时暂停确认隔离方案，不强制切换，不自动 stash、清理或
   覆盖文件。
3. **同步开发分支基线**：保护工作后，在工作区安全的前提下再次执行
   `git fetch origin main --prune`，将最新 `origin/main` 纳入 feature 分支；
   默认使用 merge 保留历史，不擅自 rebase 已推送提交。同步完成后必须确认
   `origin/main` 是当前 `HEAD` 的祖先；可用
   `git merge-base --is-ancestor origin/main HEAD` 验证。快进失败、历史分叉或
   出现冲突时先检查并报告，方案不明确则暂停；不得强推、重置或绕过保护。确认
   PR 相对最新 `main` 的实际差异仅含本次范围，不能仅因分支名称正确就推送。
4. **提交前同步与本地验证**：准备提交前必须重新执行
   `git fetch origin main --prune`。如果 `origin/main` 自上次同步后前进，必须
   先将其纳入 feature 分支并重新运行受影响项目规定的测试；工作区不安全且无法
   在不覆盖用户改动的前提下同步时，暂停并请求隔离方案。随后执行适用的 migration、
   OpenAPI、环境变量、生成文件一致性检查；规范文件变化运行
   `python scripts/check-agent-instruction-bridges.py`。按测试影响策略补齐测试，
   并执行 `python scripts/check-test-impact.py --base <目标分支> --head HEAD`；
   该命令检查已提交历史，不能代替对暂存或未提交改动的审查。检查失败不得当作
   通过；无法执行时说明原因与风险，未经确认不继续提交或推送。
5. **提交后、推送前复核**：提交后、推送 feature 分支前，必须再次执行
   `git fetch origin main --prune`，并验证 `git merge-base --is-ancestor
   origin/main HEAD`。验证失败说明远端主线在提交或验证期间发生了漂移；必须先
   将最新主线纳入 feature 分支，重新执行受影响验证和
   `python scripts/check-test-impact.py --base <目标分支> --head HEAD`，再推送。
   本地检查只对 fetch 成功时的远端状态负责，不能替代 GitHub 的服务端保护规则。
   若为保护工作提前提交，仍须在推送前完成全部验证。提交后核对提交内容，不夹带
   无关改动。
6. **推送并创建 PR**：将 feature 分支推送到 `origin` 并设置上游，
   不直接推送 `main`。向 `main` 创建 PR；已有对应 PR 时更新而非重复创建。
   标题使用 `[类型] 功能简述`，类型根据实际改动选择，如 `[feat]`、`[fix]`、
   `[docs]`、`[refactor]`、`[test]` 或 `[chore]`。描述包含背景、变更范围、验证
   命令与结果、未执行项、migration/OpenAPI/环境变量/生成文件影响，以及风险
   和回滚注意事项；不得虚构验证结果。没有实际差异时不创建空 PR。
7. **跟踪 CI 并处理失败**：持续跟踪该 PR 最新 head SHA 对应的 GitHub Actions
   与必需状态检查，及时报告状态变化。若 GitHub 报告 feature 分支落后于 `main`，
   必须更新 feature 分支并重新运行受影响验证；不能以本地此前通过的检查代替更新
   后的检查。失败时读取相关运行和 job 的日志，输出前脱敏；仅修复本次改动导致的
   问题，补充测试、本地验证、提交并推送后重新跟踪最新 SHA，直至通过或遇到需用户
   处理的阻碍。禁止关闭检查、降低阈值、扩大排除范围、删除有效测试或修改无关代码
   来换取绿色。遇到权限、密钥、审批、部署、无关基础设施故障或需扩大范围的修复
   时暂停并请求处理；无法继续监控时明确说明，不声称仍在后台跟踪。
8. **仅在门禁满足后压缩合并**：合并前重新核对 PR 最新 head SHA、`origin/main`、
   CI 结果、审批、冲突和分支保护要求。必须确认 PR 已基于 GitHub 当前 `main`，
   所有适用 CI 与必需检查均已完成且成功；未触发、排队、运行中、失败、取消或结果
   未知均不得视为通过。被跳过或中性结果的检查不得直接当作绿色，须核实其确实不
   适用且符合仓库规则；必需检查缺失或未成功时不得合并。新提交或主线更新使验证
   失效时重新验证，不沿用旧结果。满足全部条件且已获完整流程或合并授权后，执行
   `Squash and Merge`，使用平台支持的 head SHA 校验防止合入未经检查的新提交，
   不使用管理员绕过。
9. **合并后收口同步**：确认 PR 已合并及目标提交后，执行
   `git fetch origin main --prune`，在工作区安全时切换到本地 `main`，再执行
   `git merge --ff-only origin/main`，并确认本地 `main` 与 `origin/main` 指向同一
   提交。若快进失败、存在本地未发布提交或工作区不安全，暂停并报告，不使用 reset、
   restore、checkout、强推或自动删除分支来掩盖漂移。合并后的 feature 分支可能因
   `Squash and Merge` 保留历史差异，不要求它与 `main` 哈希相等，也不得未经确认
   擅自重写或删除该分支。

## 验证与交付

验证范围必须与修改风险匹配，并执行受影响子项目 `AGENTS.md` 规定的检查。跨项目修改分别验证各项目；无法执行的检查必须说明原因和风险，不得伪造结果。

完成后说明：实现和关键文件、验证命令与结果、未执行项及原因、是否涉及 migration/OpenAPI/环境变量/生成文件、遗留风险及需要用户处理的事项。
