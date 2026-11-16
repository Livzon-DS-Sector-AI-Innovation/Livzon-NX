import { afterEach, expect, it, vi } from 'vitest'
import { exitImpersonation, listImpersonationTargets, startImpersonation } from './impersonation'

afterEach(() => vi.unstubAllGlobals())

it('uses a paginated search and preserves the backend error on failed starts', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(Response.json({ data: { items: [], total: 26 } }))
    .mockResolvedValueOnce(Response.json({ detail: '该用户已停用或不存在' }, { status: 404 }))
  vi.stubGlobal('fetch', fetch)
  const signal = new AbortController().signal
  await expect(listImpersonationTargets({ keyword: '质检', offset: 20, limit: 20 }, signal)).resolves.toEqual({ items: [], total: 26 })
  expect(fetch).toHaveBeenCalledWith('/api/v1/identity/admin/impersonation/targets?keyword=%E8%B4%A8%E6%A3%80&offset=20&limit=20', { signal, cache: 'no-store' })
  await expect(startImpersonation('target')).rejects.toThrow('该用户已停用或不存在')
  expect(fetch).toHaveBeenLastCalledWith('/auth/impersonation/start', expect.objectContaining({ method: 'POST', body: '{"target_id":"target"}' }))
})

it('sends the selected role together with the search and pagination parameters', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json({ data: { items: [], total: 0 } }))
  vi.stubGlobal('fetch', fetch)
  const signal = new AbortController().signal
  await listImpersonationTargets({ keyword: '采购', role_id: 'reader', offset: 0, limit: 20 }, signal)
  const url = new URL(fetch.mock.calls[0][0], 'https://workspace.test')
  expect(Object.fromEntries(url.searchParams)).toEqual({
    keyword: '采购', role_id: 'reader', offset: '0', limit: '20',
  })
})

it('reports whether the original administrator login can be restored', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json({ data: { administrator_restored: false } }))
  vi.stubGlobal('fetch', fetch)
  await expect(exitImpersonation()).resolves.toBe(false)
  expect(fetch).toHaveBeenCalledWith('/auth/impersonation/exit', { method: 'POST' })
})
