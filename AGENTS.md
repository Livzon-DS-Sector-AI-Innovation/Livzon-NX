# Dazah 项目 AI 开发总规范

Dazah 是面向原料药工厂的综合管理平台：

- `dazah-frontend/`：Next.js 工厂管理后台
- `dazah-backend/`：FastAPI 模块化单体后端
- `Hermes-Lite/`：Livzon Agent 编排层
- `docs/`：跨项目需求、设计和实施文档
- `scripts/`：开发、联调和契约同步脚本

优先保证业务准确、权限清晰、操作可追踪、风险可控制和前后端契约一致。

## 规范入口

修改前必须完整阅读目标项目规范；目标目录有更近的 `AGENTS.md` 时叠加遵守：

- 前端：`dazah-frontend/AGENTS.md`、界面改动再读 `dazah-frontend/DESIGN.md`
- 后端：`dazah-backend/AGENTS.md`
- Hermes-Lite：`Hermes-Lite/AGENTS.md`

框架、编码和测试细节以下级规范为准。本文件只保留跨项目边界。冲突优先级为：用户当前要求 → 最近的 `AGENTS.md` → 子项目规范 → 本文件。

## 跨项目边界

- 修改前检查工作区状态、现有实现、调用关系和适用规范。
- 只修改当前任务必需的文件，保留用户已有修改；不顺手重构或清理无关内容。
- 生产代码变化必须按 `.ci/test-impact-policy.toml` 在同一变更中补充对应模块
  测试；不得用无关测试、扩大排除或降低阈值绕过门禁。
- 提交前运行 `python scripts/check-test-impact.py --base <目标分支> --head HEAD`；
  新增代码根目录、模块布局或测试框架时同步更新策略并由 Owners 审查。
- 自动生成文件必须通过项目脚本更新，禁止手工编辑。
- 后端端点或请求/响应 Schema 变化时，从根目录运行 `.\scripts\generate-api.ps1`，核对后端 OpenAPI、前端快照和生成类型，出现无关大范围变化时停止检查。
- Agent 工具变化时同步检查后端工具注册、权限、风险与确认策略，以及 Hermes-Lite 白名单、Schema、测试和文档。
- 新增或修改环境变量时同步对应 `.env.example`；后端还需向本地 `.env` 补变量名并保留已有值。
- 开发和本地联调期间，Docker 构建、启动和验证必须使用开发环境镜像与容器，禁止使用生产环境镜像或容器。
- 发现后端存在尚未应用的数据库更新时，必须先执行数据库迁移并确认成功，再启动或验证后端接口，避免因数据库结构不一致导致接口不可用。
- 不读取、输出或提交真实密码、Token、Cookie、API Key、数据库凭据、飞书或 LLM 密钥。

## Git 安全

允许使用 `git status`、`git diff`、`git log`、`git show` 等只读命令。未经用户明确要求，禁止 pull、fetch、push、add、commit、分支切换或创建、merge、rebase、cherry-pick、reset、restore、checkout、clean，以及修改远程仓库、tag 或 submodule。

用户要求提交或发布时，先确认范围，不得混入无关修改或覆盖用户工作。

## 验证与交付

验证范围必须与修改风险匹配，并执行受影响子项目 `AGENTS.md` 规定的检查。跨项目修改分别验证各项目；无法执行的检查必须说明原因和风险，不得伪造结果。

完成后说明：实现和关键文件、验证命令与结果、未执行项及原因、是否涉及 migration/OpenAPI/环境变量/生成文件、遗留风险及需要用户处理的事项。
