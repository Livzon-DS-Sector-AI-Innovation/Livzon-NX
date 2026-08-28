# dazah-frontend AI 开发规范

`dazah-frontend` 是原料药工厂管理后台，采用 Next.js App Router、React、TypeScript 和 Ant Design。开发目标是让表格、表单、审批、查询和批量操作准确高效，而不是追求营销展示效果。

所有界面修改还必须遵守 `DESIGN.md`。涉及版本敏感的 Next.js、React、Ant Design 或 React Query API 时，以项目当前版本和官方文档为准。

## 技术与事实来源

- 实际依赖和脚本：`package.json`
- Ant Design 主题：`src/lib/antd-theme.ts`
- API 契约：`src/types/generated/`
- 环境变量示例：工作区根目录 `.env.example`（生产）和 `.env.local.example`（开发）

规范不得重复维护这些文件中的版本号、完整 token 或生成类型。

## 目录和模块边界

- `src/app/(dashboard)/<module>/`：路由入口、数据获取和页面组装
- `src/components/<module>/`：模块 UI 和交互组件
- `src/components/shared/`：跨模块公共组件，修改前确认所有调用方
- `src/actions/`：Server Actions 和服务端写操作入口
- `src/lib/api/`：API 薄封装，不承载业务状态
- `src/stores/`：确有跨组件共享需要的客户端状态
- `src/types/generated/`：自动生成 API 类型，禁止手动编辑
- `src/lib/`、`src/app/layout.tsx`、代理和权限基础设施：仅在当前需求不可避免时最小修改

模块间不得导入对方内部文件；需要复用时通过模块 `index.ts` 或既有公共入口。不要为了单个页面把业务组件提升为全局公共组件。

## Server 与 Client Component

- `page.tsx` 默认保持 Server Component，负责读取服务端数据和组装页面。
- 只有使用 React 客户端 hooks、事件处理器、浏览器 API、Zustand 或 Ant Design 客户端 hook 时才添加 `'use client'`。
- 交互复杂的部分拆到模块组件中，不要让整页无必要地变成 Client Component。
- 页面缓存和动态渲染必须按数据时效、认证和现有缓存策略决定；不得为了规避构建问题机械添加 `force-dynamic`。

示例见 `examples/server-component-pattern.md`。

## 数据读取与写操作

- 浏览器端调用相对路径 `/api/v1/...`，通过项目代理访问后端。
- 服务端调用使用 `API_BASE_URL`，不得硬编码主机、端口或使用 `NEXT_PUBLIC_API_BASE_URL` 暴露后端地址。
- 客户端查询优先使用现有 React Query Provider 和 query key 约定。
- POST、PUT、PATCH、DELETE、上传和其他有副作用操作必须经过 Server Action 或项目既有服务端入口，禁止在普通 Client Component 中直接写后端。
- 写操作后按影响范围失效缓存或刷新查询，不得依赖整页刷新掩盖状态问题。

Server Action 示例见 `examples/server-actions.md`。

## API 类型与契约

- API 请求、响应和参数类型必须从 `@/types/generated/schema` 或其公开导出导入，禁止重新手写同名契约。
- `src/lib/api/` 只做请求、认证、错误标准化和类型封装。
- 后端 API 变化时，从项目根目录执行 `scripts/generate-api.ps1`，禁止手动编辑 OpenAPI 快照或生成类型。
- 如果生成结果出现大量与需求无关的变化，停止并检查后端 OpenAPI 来源。

## 管理后台交互要求

- 页面优先使用清晰的中文业务名称和合理的信息密度。
- 表格必须考虑查询、筛选、分页、溢出、固定列和批量操作。
- 表单必须有必填提示、校验反馈、提交中状态和失败后的数据保留。
- 页面和局部区域必须覆盖加载、空数据、失败、无权限和部分成功状态。
- 删除、覆盖、审批、驳回、同步和批量变更等高风险操作必须说明影响并二次确认。
- 权限不足应呈现明确状态，不得伪装成空数据或普通网络失败。
- 移动端至少支持必要查看和轻量操作；复杂台账以桌面效率为主。

## 编码约束

- 组件和类型使用 PascalCase；普通函数和非组件文件使用 camelCase。
- Server Action 和业务操作函数以动词开头；查询函数使用明确的 `fetch/list/get` 语义。
- 优先复用项目现有组件、query key、错误处理和权限入口。
- 不新增与现有技术栈重复的状态、表单或请求库。
- TypeScript 必须保持可推导且边界类型明确；禁止用无理由的 `any`、类型断言、`@ts-ignore` 或关闭 strict 检查掩盖契约问题。
- React hooks 的依赖、组件 key、受控状态和异步副作用必须正确；不得通过禁用 ESLint 规则绕过真实问题。
- 确需局部禁用规则时，只允许最小行级范围，并用注释说明框架限制或业务原因；禁止文件级关闭规则。
- 不提交本地运行日志、临时截图、调试输出或硬编码测试数据。

## 测试策略

- 修改纯函数、格式转换、金额/精度、权限判断、query key 或 API 路径时，补充 Vitest 单元测试。
- 修改页面数据流、表单、筛选、分页、缓存刷新或错误处理时，至少覆盖成功、失败和关键边界；修复缺陷必须先保留可复现的回归测试。
- 测试应断言用户可见结果、请求参数或状态变化，不以无断言 smoke test、过度 mock 或快照替代业务行为验证。
- 测试文件与被测代码就近放置并使用 `*.test.ts` 或 `*.test.tsx`；复用现有测试工具，不新增重复测试框架。

## 验证策略与 CI 门禁

验证必须根据本次变更表面选择最小可信证据：先列出实际触达的文件、调用方和用户路径，再选择能够直接证明这些变化正确的检查。默认不为局部修改运行全量测试、全量覆盖率、完整 E2E、生产构建或 Docker Build；不得用与改动无关的宽泛检查代替受影响行为验证。

- 仅修改文档、注释或不参与运行时的规范文件时，检查 diff、引用路径和格式即可；没有代码或配置影响时无需运行 lint、typecheck、测试或构建。
- 修改纯函数、格式转换、query key、API 路径或局部组件逻辑时，运行对应测试文件，并对触达文件执行可用的定向 lint；类型边界变化再运行 `pnpm typecheck`。
- 修改页面数据流、表单、缓存、权限或错误处理时，运行覆盖该页面或组件的定向测试，并实际验证本次变化涉及的成功、失败和关键边界状态；不要求重复验证未受影响的页面状态。
- 修改路由、Server/Client 边界、Next.js 配置或静态生成行为时，增加 `pnpm build`；修改关键跨页用户流程时，增加对应的定向 E2E。
- 修改依赖、锁文件、Dockerfile、standalone 输出或运行时配置时，运行安装/构建/Docker 中与变化直接相关的检查。
- 只有影响范围无法可靠收敛，或触及共享基础设施、全局入口、测试基础设施、构建链路并可能波及大部分应用时，才扩大到相关测试集或完整前端门禁。完整门禁不是每次修改的默认交付要求。

以下命令是完整前端 CI 门禁的参考集合，按上述变更表面选择执行；CI 中仍按流水线配置执行完整门禁：

```powershell
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test:unit
pnpm test:coverage
pnpm test:e2e:critical
pnpm build
docker build --tag dazah-frontend:ci .
```

- `pnpm lint` 对应 CI `Lint` 中的 ESLint。新增和修改代码必须零 error，且不得增加 warning；历史 warning 渐进清理，不得通过放宽规则或批量忽略消除。
- `eslint-warning-baseline.json` 按规则记录历史 warning 上限；任一规则计数或总数增加都会使 `pnpm lint` 失败。完成清理后只允许同步下调对应计数和总数，禁止提高基线。
- 禁止 `console.log` 和 `debugger`；确有运行故障需要记录时只使用受规则允许的 `console.warn`/`console.error`，不得输出敏感信息。
- warning 按 `react-hooks/exhaustive-deps`、`@typescript-eslint/no-explicit-any` 和其他规则分批清理；修复 hooks 必须验证依赖稳定性，清理 `any` 必须替换为真实契约类型或经过收窄的 `unknown`。
- `pnpm typecheck` 对应 `Type Check`，不得依赖 Next.js Build 间接发现类型错误。
- `pnpm test:unit` 对应 `Unit Tests`；新增业务逻辑或缺陷修复必须有相关测试。
- `pnpm test:coverage` 对整个 `src` 建立不可回退基线，PR 变更可执行行覆盖率
  不得低于 80%。
- `pnpm test:e2e:critical` 对应 `Frontend E2E`，覆盖不依赖真实外部系统的关键
  用户流程。
- `pnpm build` 对应 `Frontend Build`，用于验证 Next.js 生产构建、Server/Client 边界和静态生成。
- Docker 命令对应 `Docker Build`，涉及依赖、构建配置、运行时配置、standalone 输出或 Dockerfile 时必须本地执行。
- 聚合任务 `Frontend Test` 只有在 `Lint`、`Type Check`、`Unit Tests`、`Frontend Build` 和 `Docker Build` 全部成功时才通过。

交付时记录实际运行的命令、结果及其覆盖的变更表面；未运行完整门禁不等于未验证，但必须说明为何现有证据已经充分。页面和交互只需验证本次变化可能影响的主要操作及相关加载、空数据、失败、无权限、危险确认或窄屏状态。无法取得所需证据时必须说明原因、未验证范围和风险。
