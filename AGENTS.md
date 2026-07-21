# Dazah 项目 AI 开发总规范

Dazah 是面向原料药工厂的综合管理平台：

- `dazah-frontend/`：Next.js 工厂管理后台
- `dazah-backend/`：FastAPI 模块化单体后端
- `Hermes-Lite/`：Livzon Agent 编排层
- `docs/`：跨项目需求、设计和实施文档
- `scripts/`：开发、联调和契约同步脚本

开发优先保证业务准确、权限清晰、操作可追踪、风险可控制和前后端契约一致。不要把管理平台改造成营销网站，不要把模块化单体随意拆成微服务。

## 规范层级

修改前必须完整阅读所有适用规范：

- 前端：`dazah-frontend/AGENTS.md` 和 `dazah-frontend/DESIGN.md`
- 后端：`dazah-backend/AGENTS.md`
- Hermes-Lite：`Hermes-Lite/AGENTS.md`
- 目标目录存在更近的 `AGENTS.md` 时，必须叠加遵守

本文件只规定跨项目协作、安全和交付要求；框架用法、专项集成和完整示例应放在子项目规范、目录级规范或 README/examples 中。

冲突优先级：用户当前明确要求 → 距目标文件最近的 `AGENTS.md` → 子项目规范 → 本文件。无法安全判断时停止并说明冲突。

## 通用开发边界

- 修改前检查工作区状态、现有实现、调用关系和适用规范。
- 只修改完成当前任务必需的文件，保留用户已有修改。
- 不顺手重构、移动目录、调整无关公共抽象或清理无关文件。
- 跨模块优先使用公开接口、注册表和既有扩展点。
- 自动生成文件必须通过项目脚本更新，禁止手动编辑。
- 不保留临时调试代码、无用日志、测试密钥或硬编码业务数据。
- 能从代码、配置、测试和文档确认的信息应先自行调查；只有影响实现方向的关键歧义才询问用户。

## Git 安全

执行前先确认当前仓库和工作区状态。允许使用 `git status`、`git diff`、`git log`、`git show` 等只读命令。

未经用户明确要求，禁止：

- `git pull`、`git push`、`git fetch`
- `git add`、`git commit`
- 创建、删除或切换分支
- merge、rebase、cherry-pick
- reset、restore、checkout、clean
- 修改远程仓库、tag 或 submodule

用户要求提交或发布时，必须先确认修改范围，不得混入无关文件。禁止用破坏性命令覆盖用户修改。

## 跨项目契约同步

后端 API 的端点、参数、请求或响应 Schema 变化时，从根目录运行：

```powershell
.\scripts\generate-api.ps1
```

必须检查：

- 后端 `openapi.json`
- 前端 OpenAPI 快照和生成的 TypeScript 类型
- 是否出现与当前需求无关的大量变化

Agent 工具发生变化时，还必须同步检查后端工具注册、权限、风险和确认策略，以及 Hermes-Lite operation 白名单或工具 schema、相关测试和文档。

## 环境变量与敏感信息

- 新增或修改环境变量时，同步对应项目的 `.env.example`。
- 后端 `.env.example` 变化时，将变量名同步到 `dazah-backend/.env`，保留所有已有本地配置。
- 非敏感变量可使用安全的本地默认值；敏感变量只能保留已有值或使用安全占位符。
- 不得读取、输出、写入或提交真实密码、Token、Cookie、API Key、数据库凭据、飞书密钥或 LLM 密钥。
- 检查环境配置时只确认变量名和结构。

## 数据库变更

修改 SQLAlchemy 模型或数据库结构时：

- 必须创建并审查对应 Alembic migration。
- 不修改已执行或作为基线使用的历史 migration。
- migration 只包含当前需求的数据库变化。
- 检查 `upgrade()`、`downgrade()`、Alembic head 和空库 schema 创建。
- 不执行未经确认的删表、删字段或数据清理。
- 出现多个 head、未预期 DROP 或大量无关 drift 时停止并报告。
- 不用手工执行 SQL 代替 migration。

## 验证与交付

验证范围必须与修改风险匹配，并遵守受影响子项目的具体命令。跨项目修改分别验证所有受影响项目；无法执行的检查必须说明原因，不得伪造结果。

完成后说明：

- 实现内容和关键文件
- 已执行验证及结果
- 未执行验证及原因
- 是否涉及 migration、OpenAPI、环境变量或生成文件
- 遗留风险和需要用户处理的事项
