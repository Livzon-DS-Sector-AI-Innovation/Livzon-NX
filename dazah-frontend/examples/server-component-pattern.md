# Server Component 模式示例

## Server Component（获取数据）

```tsx
// app/(dashboard)/production/page.tsx（Server Component）
export default async function Page() {
  const data = await fetch(`${process.env.API_BASE_URL}/production/batches`, {
    headers: { Authorization: `Bearer ${await getServerToken()}` },
    next: { revalidate: 60 }
  }).then(r => r.json())

  return <BatchTable initialData={data} />  // BatchTable 是 Client 组件
}
```

## Client 组件条件

只有以下情况才加 `'use client'`：
- 用了 useState / useEffect / 事件处理器
- 用了浏览器 API
- 用了 Zustand store

Client 组件放在 `components/<模块>/` 里，`page.tsx` 只负责拿数据然后传给 Client 组件。
