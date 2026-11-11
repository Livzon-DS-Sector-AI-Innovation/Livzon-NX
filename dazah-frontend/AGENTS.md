# dazah-frontend AI 开发规范

`dazah-frontend` 是原料药工厂管理后台，采用 Next.js App Router、React、TypeScript 和 Ant Design。开发目标是让表格、表单、审批、查询和批量操作准确高效，而不是追求营销展示效果。

所有界面修改还必须遵守 `DESIGN.md`。涉及版本敏感的 Next.js、React、Ant Design 或 React Query API 时，以项目当前版本和官方文档为准。

## 技术与事实来源

- 运行时、包管理器和依赖声明：`package.json`；解析版本：`pnpm-lock.yaml`
- 检查入口和门禁：`package.json` 的 scripts、`vitest.config.ts`、
  `eslint-warning-baseline.json`、根目录 `.github/workflows/ci.yml` 及其门禁脚本
- Ant Design 主题：`src/lib/antd-theme.ts`
- API 契约：`src/types/generated/`
- 环境变量示例：工作区根目录 `.env.example`（生产）和 `.env.local.example`（开发）

规范不得重复维护这些文件中的版本号、完整 token 或生成类型。

Next.js 优先核对安装包内 `node_modules/next/dist/docs/` 的对应章节；在线补充参考
[客户端边界](https://nextjs.org/docs/app/api-reference/directives/use-client) 和
[写入口安全](https://nextjs.org/docs/app/guides/data-security)，不直接套用在线最新
版本与当前锁定版本不同的行为。

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
- 使用 React 客户端 hooks、事件处理器、浏览器 API、Zustand 或 Ant Design
  客户端 hook 的组件必须处于客户端边界内；仅在从服务端进入客户端的模块入口
  添加 `'use client'`，不要求所有后代文件重复声明。第三方组件未声明必要边界时
  使用最小包装组件；Server Component 可以直接组装已声明边界的客户端组件。
- 交互复杂的部分拆到模块组件中，不要让整页无必要地变成 Client Component。
- 页面 `params`、`searchParams` 及 `cookies()`、`headers()` 按当前 Next.js 的
  异步 API 使用；服务端先 `await`，客户端需要时按对应 API 使用 React `use()`
  或路由 hooks，不照搬旧版同步属性访问。
- 页面缓存和动态渲染必须按数据时效、认证和现有缓存策略决定；不得为了规避构建问题机械添加 `force-dynamic`。
  不假定旧版 `fetch` 缓存默认值；含身份和权限范围的数据不得跨用户共享缓存。
  修改缓存行为前核对当前配置与随包文档，不为单页擅自启用全局缓存机制。

示例见 `examples/server-component-pattern.md`。

## 数据读取与写操作

- 浏览器端调用相对路径 `/api/v1/...`，通过项目代理访问后端。
- 服务端调用使用 `API_BASE_URL`，不得硬编码主机、端口或使用 `NEXT_PUBLIC_API_BASE_URL` 暴露后端地址。
- 客户端查询优先使用现有 React Query Provider 和 query key 约定。
- POST、PUT、PATCH、DELETE、上传和其他有副作用操作必须经过 Server Action 或项目既有服务端入口，禁止在普通 Client Component 中直接写后端。
- Server Action 和服务端写入口必须校验输入、取得当前认证上下文并向后端传递；
  后端仍执行资源权限和业务状态校验。`'use server'`、页面鉴权、按钮隐藏或前端
  传入的用户 ID 都不能代替写入口认证授权。既有入口的复用仅限当前模块和操作，
  不得以通用代理可转发为由新增无校验的写通道。
- 写操作后按影响范围失效缓存或刷新查询，不得依赖整页刷新掩盖状态问题。

Server Action 示例见 `examples/server-actions.md`。

## API 类型与契约

- API 请求、响应和参数类型必须从 `@/types/generated/schema` 或其公开导出导入，禁止重新手写同名契约。
- 生成契约中的 `unknown`/宽泛 `data` 不代表已有业务类型保证；在模块边界按
  已有 Schema 或明确业务校验收窄。视图模型可从契约派生，不用类型断言伪造
  结构确定性，也不为局部需求重写整个生成器或无关接口。
- `src/lib/api/` 只做请求、认证、错误标准化和类型封装。
- 后端端点、参数或请求/响应契约变化时，从项目根目录执行 `scripts/generate-api.ps1`，禁止手动编辑 OpenAPI 快照或生成类型。
- 如果生成结果出现大量与需求无关的变化，停止并检查后端 OpenAPI 来源。

## 管理后台交互要求

- 顶部、侧边栏和模块首页的名称、目标路径及入口语义保持一致；导航加载反馈、
  当前页、键盘焦点和窄屏操作按 `DESIGN.md` 的导航约定实现。修改导航时验证
  展开、跳转、键盘操作及受影响模块首页。
- 页面使用清晰的中文业务名称；标题、关键状态与操作、台账或表单按业务任务
  排列，不为统一外观牺牲信息密度。
- 表格考虑查询、筛选、分页、溢出、固定列和批量操作。独立列表页的已提交
  查询状态和详情返回路径按 `examples/list-url-state.md` 实现；嵌入式表格或
  多表页面先确定各自状态范围，不机械套用单列表 URL 参数。
- 表单必须有必填提示、校验反馈、提交中状态和失败后的数据保留。
- 页面和局部区域必须覆盖加载、空数据、失败、无权限和部分成功状态。
- 用户未主动明确提出编写或新增“提示框”时，禁止自主添加提示框、提示条或说明
  横幅（如页面规则、操作说明、自动计算说明等）；不得以补充说明或优化体验为由
  自行增加。
- 以下提示框规范仅约束样式、组件和交互，不构成新增提示框的要求或授权；页面
  结构、状态覆盖、权限告知和风险说明要求也不得作为自主新增提示框的依据。
  用户主动明确要求新增的提示框，以及本次任务涉及修改的既有提示框，统一使用
  `src/components/shared/PlatformNotice.tsx`，呈现左侧语义图标、简明正文及右侧
  按 `DESIGN.md` 条件显示的“了解访问规则”入口；完整说明传入 `description`，
  已有恢复操作传入 `action`。
  禁止在业务页面直接导入 Ant Design `Alert` 或手写另一套提示条。
  文案、操作入口、语义色与窄屏布局遵守
  `DESIGN.md` 的“统一提示框与提示条”。提示弹窗复用 `Modal`，不得另造主题。
- 删除、覆盖、审批、驳回、同步和批量变更等高风险操作必须说明影响并二次确认。
- 权限不足应呈现明确状态，不得伪装成空数据或普通网络失败。
- 移动端至少支持必要查看和轻量操作；复杂台账以桌面效率为主。

## 深色与浅色外观适配

- 平台支持深色与浅色两种外观模式；所有新建或修改的页面、组件和样式必须同时适配两种模式，外观适配属于开发与验收要求。
- 优先使用 Ant Design 的 `theme.useToken()` 和 `src/app/globals.css` 中已有的语义 CSS 变量；背景、文字、边框、阴影和交互状态不得硬编码为仅适用于单一模式的颜色。业务状态色在两种模式下均须清晰可辨，不能只靠颜色传达状态。
- 复用 `src/lib/antd-theme.ts`、`src/lib/appearance.ts` 和 `src/lib/useAppearance.ts` 的统一主题与外观机制；需要按外观分支时使用解析后的 `resolved`，兼容“跟随系统”，不得另建局部主题状态或自行读写外观存储。
- 适配范围包括表格、表单、弹窗、抽屉、提示条、下拉浮层、图表及自定义样式。ECharts 优先复用 `src/components/shared/ThemedEChart.tsx`；图表文字、坐标轴、图例、网格线和 tooltip 必须随外观切换保持可读。
- 界面改动交付前，在深色与浅色模式下分别验证受影响界面、主要交互和本次涉及
  的状态；不要求为删除说明、纯文案等局部改动遍历所有未受影响状态。修改外观
  判断、主题映射或图表适配逻辑时，补充两种模式及切换行为的定向测试，并验证
  切换后即时更新。交付记录区分组件测试与浏览器视觉检查，注明实际验证范围。

## 编码约束

- 组件和类型使用 PascalCase；普通函数和非组件文件使用 camelCase。
- Server Action 和业务操作函数以动词开头；查询函数使用明确的 `fetch/list/get` 语义。
- 优先复用项目现有组件、query key、错误处理和权限入口。
- 不新增与现有技术栈重复的状态、表单或请求库。
- TypeScript 必须保持可推导且边界类型明确，遵守下述类型安全要求；禁止使用
  `@ts-ignore` 或关闭 strict 检查掩盖契约问题。
- React hooks 的依赖、组件 key、受控状态和异步副作用必须正确；不得通过禁用 ESLint 规则绕过真实问题。
- 确需局部禁用规则时，只允许最小行级范围，并用注释说明框架限制或业务原因；禁止文件级关闭规则。
- 不提交本地运行日志、临时截图、调试输出或硬编码测试数据。

### TypeScript 类型安全

- 优先通过准确的类型设计和控制流收窄解决类型问题，避免滥用 `any`、`as T`、
  非空断言 `!` 或双重断言 `as unknown as T`；禁止仅为消除编译错误而绕过类型检查。
- 能可靠推导时保留类型推导；函数、组件和数据边界使用明确类型。复用生成契约与
  类型别名，通过 `Pick`、`Omit`、索引访问类型等派生所需结构，不重复手写契约，
  不把 `Record<string, any>` 当作业务模型。
- 输入与输出或字段之间存在类型关联时，使用有实际约束的泛型，例如
  `K extends keyof T`；不要为单个具体场景制造无必要的泛型，也不能用调用方任意
  指定的泛型参数把未校验的接口结果直接认定为业务类型。
- 对外部输入、JSON、存储数据和捕获的异常使用 `unknown`，通过运行时 Schema、
  `typeof`、`instanceof`、`in` 或自定义类型守卫校验后访问。类型守卫须检查其
  声明类型所需的结构与字段，不能用恒真判断或内部断言伪装校验。
- 有限的业务状态、可选结果和不同数据分支使用联合类型，优先通过可辨识字段
  区分分支并收窄；按需要做穷尽检查，不用宽泛对象、相互矛盾的可选字段或断言
  掩盖状态差异。类型别名和泛型本身不提供运行时数据校验。
- 对配置和字面量可使用 `satisfies` 校验结构，或用 `as const` 保留字面量与只读
  信息；这些用法不能替代外部数据校验，也不得用于强行改变对象的实际结构。
- 仅在第三方声明缺陷等确实无法通过类型设计或校验表达的边界，允许最小范围的
  类型断言或 `any`，须注释说明具体原因、可靠依据及适用范围；优先封装在适配层，
  不向业务调用链传播，不放宽 lint 或类型检查规则。只治理本次触达的相关代码，
  不以本节要求为由批量改写无关历史模块。

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
pnpm test:build
pnpm test:coverage
pnpm build
pnpm test:e2e:critical
# 仅 CI 或明确授权的隔离交付验证使用此交付镜像命令
docker build --file ../Dockerfile --target frontend --tag dazah-frontend:ci ..
```

- `pnpm lint` 对应 CI `Frontend Quality` 中的 ESLint。新增和修改代码必须零 error，且不得增加 warning；历史 warning 渐进清理，不得通过放宽规则或批量忽略消除。
- `eslint-warning-baseline.json` 按规则记录历史 warning 上限；任一规则计数或总数增加都会使 `pnpm lint` 失败。完成清理后只允许同步下调对应计数和总数，禁止提高基线。
- 禁止 `console.log` 和 `debugger`；确有运行故障需要记录时只使用受规则允许的 `console.warn`/`console.error`，不得输出敏感信息。
- warning 按 `react-hooks/exhaustive-deps`、`@typescript-eslint/no-explicit-any` 和其他规则分批清理；修复 hooks 必须验证依赖稳定性，清理 `any` 必须替换为真实契约类型或经过收窄的 `unknown`。
- `pnpm typecheck` 对应 `Frontend Quality` 中的类型检查，不得依赖 Next.js Build 间接发现类型错误。
- 定向单测使用 `pnpm exec vitest run <测试文件或目录>`；`pnpm test:unit` 自带
  `src` 过滤条件，会运行整个 `src` 测试集，不用追加文件参数冒充定向验证。
  CI 的 `Frontend Unit` 通过 `pnpm test:coverage` 分三片执行同一套测试。
  新增业务逻辑或缺陷修复必须有相关测试。
- `pnpm test:coverage` 按 `vitest.config.ts` 的 include/exclude 和全应用基线检查，
  CI 的 `Frontend Coverage` 合并三片报告后检查全应用基线，再用根目录脚本检查变更行覆盖率。
  两种指标不得混用，禁止降低现有门禁。
- `pnpm test:build` 验证构建脚本的失败边界与类型覆盖保护；构建脚本或相关守卫
  变化时运行，对应当前 `Frontend Quality` 的独立检查步骤。
- `pnpm test:e2e:critical` 对应 `Stable Frontend E2E`，CI 分四片覆盖不依赖真实外部系统的
  关键用户流程。
- `pnpm build` 对应 `Frontend Build`，用于验证 Next.js 生产构建、Server/Client 边界和静态生成。
- Docker 交付镜像构建对应 `Frontend Image Verify`，与 `Frontend Build` 的
  `pnpm build` 分开。变化影响镜像构建或容器运行时，执行相应开发镜像构建或容器验证，
  本地使用 `docker build --file ../Dockerfile.dev --target frontend --tag dazah-frontend:dev ..`；
  standalone 等交付镜像特有变化由 CI 或明确授权的隔离交付验证覆盖。
- `Stable Frontend E2E` 和隔离测试复用同次 CI 的 `Frontend Build` 产物。
  生产 Docker 镜像独立构建并缓存构建层。
- 统一 `CI Gate` 按根目录 `.github/scripts/ci_gate.py` 的变更范围要求相应任务
  成功；前端范围包括静态检查、生产构建、全量单测及覆盖率、镜像验证和稳定 E2E。
  只有门禁确认不适用的任务可跳过，隔离测试不阻断合并。

命令在 `dazah-frontend/` 执行，包管理器遵守 `packageManager` 声明。遇到工具
自动要求重装、清空 `node_modules` 或修改锁文件时，先核对工具版本和环境；
不得为局部验证自动升级依赖或重建用户环境。依赖已齐备时可直接通过 `node`
调用本地 Vitest/ESLint CLI，注明实际命令；缺少依赖则报告受阻范围。

交付时记录实际运行的命令、结果及其覆盖的变更表面；未运行完整门禁不等于未验证，但必须说明为何现有证据已经充分。页面和交互只需验证本次变化可能影响的主要操作及相关加载、空数据、失败、无权限、危险确认或窄屏状态。无法取得所需证据时必须说明原因、未验证范围和风险。

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
