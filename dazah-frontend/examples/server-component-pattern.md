# Server Component 读取示例

`page.tsx` 默认在服务端读取数据并组装页面。以下以当前生产批次接口说明路径、
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
前缀。只有用到 React 客户端 hooks、事件处理器、浏览器 API 或客户端状态时
才为对应组件加 `'use client'`，不因为表格组件需要交互就把整页改为 Client
Component。
