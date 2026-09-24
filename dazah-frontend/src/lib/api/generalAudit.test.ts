import { afterEach, expect, it, vi } from 'vitest'

import { fetchGeneralAuditLogs } from './generalAudit'

afterEach(() => vi.unstubAllGlobals())

it('sends the operation category and module filter to the paged audit API', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ data: { items: [], page: 2, page_size: 20, total: 0 } }),
  })
  vi.stubGlobal('fetch', fetchMock)

  const result = await fetchGeneralAuditLogs({
    category: 'operations', page: 2, pageSize: 20, module: 'quality', keyword: '查看',
  })
  const url = new URL(fetchMock.mock.calls[0][0], 'http://test')
  expect(url.pathname).toBe('/api/v1/audit/logs')
  expect(url.searchParams.get('category')).toBe('operations')
  expect(url.searchParams.get('module')).toBe('quality')
  expect(url.searchParams.get('keyword')).toBe('查看')
  expect(result.page).toBe(2)
})
