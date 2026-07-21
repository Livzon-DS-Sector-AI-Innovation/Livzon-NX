# dazah-frontend AI 开发规范

`dazah-frontend` 是原料药工厂管理后台，采用 Next.js App Router、React、TypeScript 和 Ant Design。开发目标是让表格、表单、审批、查询和批量操作准确高效，而不是追求营销展示效果。

所有界面修改还必须遵守 `DESIGN.md`。涉及版本敏感的 Next.js、React、Ant Design 或 React Query API 时，以项目当前版本和官方文档为准。

## 技术与事实来源

- 实际依赖和脚本：`package.json`
- Ant Design 主题：`src/lib/antd-theme.ts`
- API 契约：`src/types/generated/`
- 环境变量示例：项目 `.env.example`

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
- 不提交本地运行日志、临时截图、调试输出或硬编码测试数据。

## 验证

按修改范围至少运行相关检查：

```powershell
pnpm typecheck
pnpm lint
pnpm build
```

涉及页面和交互时，还要验证主要操作以及加载、空数据、失败、无权限、危险确认和窄屏表现。无法运行完整构建时，说明原因并至少完成与改动直接相关的检查。
