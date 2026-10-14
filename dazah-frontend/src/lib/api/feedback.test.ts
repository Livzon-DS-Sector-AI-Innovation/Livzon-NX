import { afterEach, expect, it, vi } from 'vitest'
import { fetchFeedback } from './feedback'
afterEach(() => vi.unstubAllGlobals())

it('separates the personal feedback endpoint from the paged administrator inbox', async () => {
  const fetcher = vi.fn().mockImplementation(async () => Response.json({ items: [], total: 0, pending_count: 0, page: 2, page_size: 10 }))
  vi.stubGlobal('fetch', fetcher)
  await fetchFeedback(false)
  await fetchFeedback(true, 2, 'processing')
  expect(fetcher.mock.calls[0][0]).toBe('/api/v1/identity/me/feedback?page=1&page_size=10')
  expect(fetcher.mock.calls[1][0]).toBe('/api/v1/identity/admin/feedback?page=2&page_size=10&status=processing')
})

it('distinguishes an administrator permission failure from an empty inbox', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 403 })))
  await expect(fetchFeedback(true)).rejects.toThrow('无权查看管理员反馈')
})
