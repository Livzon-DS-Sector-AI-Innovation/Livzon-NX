# dazah-backend AI 开发规范

`dazah-backend` 是原料药工厂数字化平台的模块化单体后端。目标是在统一的身份、审计、配置和集成能力下，让生产、质量、设备、安全、环保、能源、仓储、采购等业务模块独立演进。

不要把项目拆成微服务，不要为单个需求引入与当前规模不匹配的架构或大型抽象。

## 技术与事实来源

- 实际依赖、Python 版本和检查配置：`pyproject.toml`
- 模块清单与 schema 注册：`app/shared/module_registry.py`
- API 契约：`openapi.json`
- 数据库历史：`alembic/versions/` 和 Alembic 当前 head
- 环境变量结构：`.env.example`

规范不得重复维护容易过期的版本号、当前 revision ID 或完整第三方 API 教程。涉及版本敏感用法时，以项目当前版本和官方文档为准。

## 架构和目录边界

- `app/core/`：配置、数据库、Redis、异常、统一响应、事件总线、LLM 等技术基础设施
- `app/shared/`：ORM 基类、模块注册表和跨模块轻量契约
- `app/platform/`：身份、审计和外部系统接入等平台能力
- `app/modules/<module>/`：业务模块自己的 API、Schema、Service、Repository、Model 和工具适配
- `app/api/router.py`：全局路由装配入口
- `alembic/`：数据库迁移

新业务代码必须放在所属模块，禁止放回 `app/models/`、`app/schemas/`、`app/integrations/` 等旧式横向目录。

跨模块调用优先通过目标模块 `public_api.py`、模块注册表或既有扩展点。禁止直接复用其他模块的 repository、内部 service、handler、配置表或私有模型实现。

修改 `app/core/`、`app/shared/`、`app/platform/`、`app/api/router.py` 或 `alembic/` 前，必须确认当前需求确实需要，并检查全部调用方和影响范围。

业务模块的推荐结构见 `examples/module-structure.md`。

## 分层职责

- API 层：认证授权、依赖注入、请求/响应转换，不承载核心业务规则
- Schema：使用 Pydantic v2 描述输入、输出和明确校验
- Service：业务规则、状态流转、事务边界和跨 repository 编排
- Repository：本模块数据查询和持久化，不处理 HTTP 语义
- Model：SQLAlchemy 模型和数据库约束
- `public_api.py`：稳定、最小的跨模块公开能力

函数保持聚焦，不引入与当前需求无关的通用框架。中文业务名可用于 API 文档和说明，代码标识符使用英文。

## 编码与静态检查

- 新增和修改 Python 代码必须通过 Ruff，不得新增 lint error；历史问题按触达范围渐进修复，禁止通过扩大 ignore、`noqa` 或降低规则来绕过。
- `# noqa` 只允许最小行级范围，必须对应明确且不可消除的框架或兼容性原因；禁止文件级批量忽略。
- 新增公共函数、Service、Repository 和复杂数据结构必须有明确类型；禁止用无理由的 `Any`、宽泛 dict 或类型忽略掩盖契约问题。
- 保持异步调用链一致，不在 async 路径中加入阻塞 I/O；协程必须 await，后台任务必须有生命周期、失败记录和关闭策略。
- 不保留调试输出、临时日志、死代码、硬编码业务数据或测试凭证。

## API 规范

- 路由统一挂载在 `/api/v1` 下，并按业务模块和资源组织。
- 入参和出参使用所属模块 Schema，禁止直接返回 ORM 对象或松散 dict 作为稳定契约。
- 优先使用 `app/core/response.py` 和 `app/core/exceptions.py` 的统一能力。
- 列表接口明确分页、筛选和排序边界；不得默认返回无上限数据。
- 写操作必须做权限、业务状态和并发条件校验。
- 删除业务数据默认软删除；物理删除、批量覆盖或数据清理必须由需求明确授权。
- 不在错误信息和日志中暴露内部堆栈、数据库结构或敏感配置。

浏览器通过前端代理访问后端；前端服务端通过 `API_BASE_URL` 访问。后端不得要求前端硬编码容器地址或暴露内部端口。

## 接口 500 错误防范

HTTP 500 只用于未预期的服务端故障，不得把可预期的业务分支、输入错误或外部依赖失败统一包装成 500，也不得通过吞掉异常或返回 200 来掩盖故障。

- 新增或修改接口前，必须检查从路由、Schema、Service、Repository 到响应序列化的完整调用链，尤其确认请求字段、查询结果、数据库模型和 `response_model` 一致。
- 参数非法、资源不存在、权限不足、状态冲突、重复数据等可预期结果，必须使用 Pydantic 校验或 `app/core/exceptions.py` 中的统一异常映射为明确的 4xx 状态码。
- 数据库唯一约束、外键约束和并发冲突等可预期持久化异常，必须在事务边界内回滚并转换为明确的业务异常；禁止将原始 SQLAlchemy 异常直接暴露给接口。
- 异步 ORM 查询必须显式加载响应所需字段和关系。不得让响应序列化触发懒加载，也不得在会话关闭后访问未加载或已过期的 ORM 属性。
- 外部 HTTP、飞书、Redis、LLM 等依赖调用必须设置超时，并处理连接失败、超时、非成功状态码、空响应和响应结构变化；根据语义转换为明确的业务错误或 502/503/504，不得无条件转换成 500。
- 禁止使用宽泛的 `except Exception` 静默降级、伪造成功响应或丢失异常上下文。确需在边界捕获未知异常时，必须保留异常链并记录可定位的上下文，同时对敏感信息脱敏。
- 新增或修改接口必须使用项目的 `AsyncClient` 测试真实调用路由，至少覆盖成功路径和本次变更最可能出现的失败路径，并断言状态码与响应 Schema；仅测试 Service 或直接调用路由函数不足以证明接口不会返回 500。
- 修复已出现的 500 时，必须先根据日志或可复现请求定位根因，补充能够复现该问题的回归测试，再修复根因并保留测试。不得只增加兜底异常捕获。
- 交付前必须实际执行受影响接口测试，确认所有可预期分支均不会返回 500。无法运行测试时必须说明原因、未验证范围和风险，不得声称接口已验证。

## 数据库与异步 ORM

- 使用 SQLAlchemy 2.0 typed ORM：`Mapped[...]` 和 `mapped_column(...)`。
- 异步数据库访问使用 `AsyncSession`，避免在响应序列化阶段触发懒加载。
- 业务模型继承 `app/shared/base_model.py` 的 `BaseModel`，明确 `__tablename__` 和模块 schema。
- 字段使用英文 `snake_case`；唯一约束、常用索引和必要的数据完整性约束显式声明。
- 模块内部关系按数据完整性需要使用外键；跨模块默认不建立数据库外键，通过稳定标识和公开接口协作。偏离时必须说明理由。
- 禁止直接赋值未加载的 relationship。写操作后按返回数据需要使用显式 `select` 和 `selectinload`，不要依赖隐式刷新或懒加载。
- INSERT 在 `flush()` 后只返回已可靠回填的字段；UPDATE、DELETE 或需要关系数据时显式重新查询。

## Migration

- 模型或数据库结构变化必须伴随新的、经过审查的 Alembic migration。
- 不修改已经执行或作为基线使用的历史 migration。
- 可以使用 autogenerate 辅助生成，但必须逐行审查 `upgrade()` 和 `downgrade()`，只保留当前需求。
- 新增 PostgreSQL schema 时，同步模块注册，并确保 migration 在建表前创建 schema。
- 软删除数据需要“仅未删除记录唯一”时，必须使用 `WHERE is_deleted = false` 的部分唯一索引；禁止把 `is_deleted` 直接加入 `UniqueConstraint`，否则同一业务键第二次软删除会产生唯一键冲突。
- 可预期的数据库完整性冲突必须在事务边界回滚并转换为 4xx 业务错误；不得让 `IntegrityError` 直接成为接口 500。
- 迁移中出现未预期 DROP、其他模块变化、大量 drift 或多个 head 时立即停止并报告，不得自动合并或尝试一次性修复。
- 禁止手工执行 SQL 改库来代替 migration；禁止未经确认的数据清理和破坏性 DDL。
- 不得在规范流程中自动执行 `git pull`、merge、commit 等 Git 写操作。

常用 Alembic 命令见 `examples/commands.md`；最终判断以 migration 文件和当前 Alembic 状态为准。

## 外部集成与平台能力

- 平台集成层只提供跨模块可复用、无业务归属的客户端、协议解析和接入能力。
- 业务配置、凭证来源、同步规则和状态处理必须留在所属模块。
- 平台层不得反向依赖 `app.modules.*`，业务模块不得直接复用另一个模块的集成实现。
- 凭证由所属模块读取、解密和校验后显式传给平台 helper；平台 helper 不决定配置来源。

飞书开发还必须遵守 `app/platform/integrations/feishu/AGENTS.md`。

## Agent 与 LLM

- Livzon Agent 只能通过已注册工具和统一执行器访问业务能力，不能直接操作数据库或自由调用内部 API。
- 工具 handler 只做参数接收、Service 调用和结果序列化；业务规则留在所属模块。
- 写操作、人工责任判断、权限、确认和审计必须使用平台统一链路。
- 业务模块调用 LLM 必须使用 `app.core.llm` 的统一客户端，不得自行读取密钥或创建旁路客户端。

相关修改还必须遵守：

- `app/modules/agent/AGENTS.md`
- `app/core/llm/AGENTS.md`

## OpenAPI 与前端同步

新增、修改或删除端点、参数、请求 Schema 或响应 Schema 时，从项目根目录运行 `scripts/generate-api.ps1`，统一更新后端 OpenAPI、前端快照和生成类型。

禁止手动编辑 `openapi.json` 或前端生成类型。生成结果包含大量无关变化时停止并检查原因。

## 环境变量与敏感信息

- 新增或修改环境变量时同步 `.env.example`，并按根规范同步本地 `.env` 中的变量名。
- 不读取、输出、记录或提交真实 secret、token、password、key、Cookie 或数据库凭据。
- 日志、审计记录、异常和 API 响应必须对敏感字段脱敏。
- 不在代码、测试、migration 或示例中硬编码真实业务凭证。

## 测试策略

后端测试包括静态检查、单元测试、接口集成测试、数据库迁移测试和构建测试：

- Service、Repository、权限、状态流转、事务、序列化和纯函数使用单元测试覆盖成功、失败及边界。
- API 必须使用项目 `AsyncClient` 真实调用路由，覆盖认证授权、请求校验、成功响应、业务 4xx 和外部依赖失败；不能只直接调用 endpoint。
- Repository 和 migration 测试使用独立 PostgreSQL 测试库，不得连接开发、共享或生产数据库；测试数据必须隔离且可清理。
- 修复缺陷时先添加能复现问题的回归测试，再修复根因。
- 测试必须断言业务结果、状态码、响应 Schema、事务提交/回滚或外部调用参数。禁止为了覆盖率无断言调用、吞掉任意异常、遍历执行接口或过度 mock 关键业务链路。
- 外部 HTTP、飞书、Redis、MinIO、LLM 等默认使用可控 fake/mock，接口集成边界再验证超时、错误映射和降级；测试不得访问真实外部服务。
- 新代码必须覆盖本次引入的关键分支。全应用覆盖率不得低于 CI 门禁 60%，不得用排除生产代码、空洞测试或降低阈值换取通过。

## 本地验证与 CI 门禁

开发中先执行受影响文件和定向测试：

```powershell
uv run ruff check <相关路径>
uv run pytest <相关测试>
uv run mypy <相关路径>
```

提交前根据风险扩大验证范围。CI 对应关系如下：

- `Lint`：对变更 Python 文件执行 Ruff；所有触达文件必须零 error。
- `Backend Test`：启动 PostgreSQL 测试容器，安装锁定依赖，确认 Alembic 只有一个 head，执行 `upgrade head`，然后运行全量 Pytest 和 coverage。
- `Backend Docker Build`：构建后端生产镜像。

需要复现完整后端门禁时，在独立 PostgreSQL 测试库配置好 `TEST_DATABASE_URL` 后执行：

```powershell
uv sync --frozen --group dev
uv run ruff check <本次变更的 Python 路径>
uv run alembic heads
uv run alembic upgrade head
uv run pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=60
docker build --tag dazah-backend:ci .
```

- `alembic heads` 必须且只能有一个 head；结构变更还要验证空库升级、`upgrade()`、`downgrade()` 和模块 schema 创建。
- API、共享基础设施、数据库、依赖、测试配置或跨模块变更必须运行全量测试；局部纯实现可先定向验证，但交付时必须说明未执行的完整门禁。
- Dockerfile、依赖锁、系统依赖、启动命令或运行时配置变化必须执行 Docker Build。
- API 变化还要执行根目录契约生成脚本并验证前端生成类型。
- 无法执行检查时必须说明原因、未验证范围和风险，不得声称 CI 可通过。
