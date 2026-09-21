import { describe, expect, it, vi } from 'vitest'

// 物品管理文档目录页（SSR）兜底契约：部门数据拉取失败时降级空数据，
// 保证页面照常打开而非整页报错。

vi.mock('@/lib/api/server/quality', () => ({
  fetchDocumentDepartmentsServer: vi.fn(async () => {
    throw new Error('offline')
  }),
}))

describe('quality documents page SSR fallback', () => {
  it('renders with empty departments when the backend fails', async () => {
    const page = await import('./documents/page')
    await expect(page.default()).resolves.toBeDefined()
  })
})
