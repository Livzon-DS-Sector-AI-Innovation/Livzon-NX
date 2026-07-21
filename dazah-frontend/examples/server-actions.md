# Server Actions 示例

所有 POST/PUT/DELETE 操作写在 `actions/` 目录，不要在 Client 组件里直接 fetch 写接口。

```ts
// actions/production.ts
'use server'
export async function createBatch(data: CreateBatchInput) {
  const token = await getServerToken()
  const res = await fetch(`${process.env.API_BASE_URL}/production/batches`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  if (!res.ok) throw new Error('创建批次失败')
  revalidatePath('/production')
}
```
