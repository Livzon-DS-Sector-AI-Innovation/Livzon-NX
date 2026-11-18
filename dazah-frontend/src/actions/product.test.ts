import { afterEach, expect, it, vi } from 'vitest'
import { revalidatePath } from 'next/cache'
import { createProduct, deleteProduct, updateProduct } from './product'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: async () => ({
  Authorization: 'Bearer fixture', 'Content-Type': 'application/json',
}) }))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it.each([
  ['POST', '/products', () => createProduct({ name: '测试产品' }), { name: '测试产品' }, 201],
  ['PUT', '/products/item', () => updateProduct('item', { name: '测试产品' }), { name: '测试产品' }, 200],
  ['DELETE', '/products/item', () => deleteProduct('item'), undefined, 200],
] as const)('keeps the authenticated %s request and refreshes on success', async (method, path, call, body, status) => {
  const data = { code: status, data: method === 'DELETE' ? null : { name: '测试产品' } }
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status }))
  vi.stubGlobal('fetch', fetcher)
  await expect(call()).resolves.toEqual({ ok: true, data })
  expect(fetcher).toHaveBeenCalledWith(expect.stringContaining(`/api/v1/product${path}`), expect.objectContaining({
    method, headers: expect.objectContaining({ Authorization: 'Bearer fixture' }),
  }))
  expect(fetcher.mock.calls[0][1].body).toBe(body && JSON.stringify(body))
  expect(revalidatePath).toHaveBeenCalledWith('/production/products')
})

it.each([
  [401, '登录已失效，请重新登录'],
  [403, '没有执行此操作的权限，请联系管理员'],
  [404, '请求的内容不存在或已被删除，请刷新后重试'],
  [409, '数据已发生变化，请刷新后重试'],
  [422, '填写内容有误，请检查后重试'],
])('maps HTTP %i instead of the backend message', async (status, message) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    message: '后端内部详情',
  }), { status })))
  await expect(updateProduct('item', { name: '测试产品' })).resolves.toEqual({ ok: false, message })
  expect(revalidatePath).not.toHaveBeenCalled()
})
