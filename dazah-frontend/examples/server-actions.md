# Server Action 请求转发片段

有副作用的操作从 `src/actions/` 或已有服务端入口调用后端，Client Component
只触发该入口。以生产批次创建接口为例，请求类型使用生成契约，写入成功后再
刷新受影响路径或 React Query 查询；实际业务错误按模块约定显示。

下例只演示已完成输入校验与当前用户认证后的请求转发、契约引用和刷新步骤，
不是可直接复制的完整公开 Action。实际入口必须复用所属模块的运行时校验和
认证流程；`getAuthHeaders()` 只转发认证上下文，不保证当前用户已登录或有权限。
后端仍须核验资源权限与业务状态，不把 TypeScript 参数类型当成运行时校验。

```ts
// 放在服务端模块内，由已校验输入和认证的 Action 调用；仅演示转发部分。
'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import { serverApiUrl } from '@/lib/server-api'
import type { components, operations } from '@/types/generated/schema'

type BatchCreate = components['schemas']['BatchCreate']
type BatchCreateResponse =
  operations['create_batch_api_v1_production_batches_post']['responses'][200]['content']['application/json']

async function forwardValidatedBatch(data: BatchCreate) {
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
