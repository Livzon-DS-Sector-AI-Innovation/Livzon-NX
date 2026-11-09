# Server Component 读取示例

`page.tsx` 默认作为 Server Component 按需读取数据并组装页面；既有客户端
React Query 已负责读取时，不要求为满足示例额外发起相同请求。以下以生产批次接口说明路径、
认证和缓存边界；实际响应类型从 `src/types/generated/schema.ts` 的对应 operation
导入，并检查后端统一响应中的业务状态。复杂交互放到模块 Client Component。

```tsx
// src/app/(dashboard)/production/batches/page.tsx 中的数据读取片段
import { getAuthHeaders } from '@/lib/auth'
import { serverApiUrl } from '@/lib/server-api'
import type { operations } from '@/types/generated/schema'

type BatchListResponse =
  operations['get_batches_api_v1_production_batches_get']['responses'][200]['content']['application/json']

const response = await fetch(serverApiUrl('/production/batches?page=1&page_size=20'), {
  headers: await getAuthHeaders(),
  cache: 'no-store', // 当前用户的业务数据；缓存策略须按认证与时效单独决定
})
if (!response.ok) throw new Error(`批次列表请求失败 (${response.status})`)
const payload: BatchListResponse = await response.json()
if (payload.code !== 200) throw new Error(payload.message)
// payload.data 仍是 unknown；按模块 Schema 校验/标准化后传给组件。
```

`serverApiUrl()` 会加 `/api/v1` 前缀；不要手拼主机、端口，也不要漏掉 API
前缀。需要 React 客户端 hooks、事件处理器、浏览器 API 或客户端状态的部分
放在客户端边界内，只在边界入口声明 `'use client'`，已在该边界内的后代不必
重复添加。不要因为表格组件需要交互就把整页改为 Client Component。带动态
参数的页面按当前 Next.js 异步 `params`/`searchParams` API 读取；该片段未演示
这些入参，不应据此照搬旧版同步访问。
