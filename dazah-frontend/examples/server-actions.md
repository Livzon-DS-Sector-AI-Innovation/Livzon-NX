# Server Action 写操作示例

有副作用的操作从 `src/actions/` 或已有服务端入口调用后端，Client Component
只触发该入口。以生产批次创建接口为例，请求类型使用生成契约，写入成功后再
刷新受影响路径或 React Query 查询；实际业务错误按模块约定显示。

```ts
// src/actions/production.ts 中的写操作片段
'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import { serverApiUrl } from '@/lib/server-api'
import type { components, operations } from '@/types/generated/schema'

type BatchCreate = components['schemas']['BatchCreate']
type BatchCreateResponse =
  operations['create_batch_api_v1_production_batches_post']['responses'][200]['content']['application/json']

export async function createBatch(data: BatchCreate) {
  const response = await fetch(serverApiUrl('/production/batches'), {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`创建批次失败 (${response.status})`)
  const payload: BatchCreateResponse = await response.json()
  if (payload.code !== 200) throw new Error(payload.message)
  revalidatePath('/production/batches')
  return payload
}
```

`serverApiUrl('/production/batches')` 对应 `/api/v1/production/batches`。
上传、流式返回或需要特定错误映射的操作，按所属模块现有服务端入口实现，
不要把普通写请求直接放在 Client Component 中。
