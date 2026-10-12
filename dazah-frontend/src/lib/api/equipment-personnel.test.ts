import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchCandidates, fetchPersonnelList } from './equipment-personnel'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function lastUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  return String(fetchMock.mock.calls.at(-1)?.[0] ?? '')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('equipment-personnel workshop scoping', () => {
  it('fetches personnel list with workshop filter and maps pagination meta', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({
        code: 200,
        data: [{ id: 'p1', name: '张三', workshop_code: '101-2' }],
        meta: { total: 1, page: 1, page_size: 20 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchPersonnelList({ workshop: '101-2', keyword: '张' })
    const url = lastUrl(fetchMock)
    expect(url.startsWith('/api/v1/equipment/personnel?')).toBe(true)
    expect(url).toContain('workshop=101-2')
    expect(url).toContain('keyword=')
    expect(result).toMatchObject({ total: 1 })
  })

  it('omits workshop when not provided (跨车间查询)', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [], meta: { total: 0, page: 1, page_size: 20 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchPersonnelList({ page: 1 })
    expect(lastUrl(fetchMock)).not.toContain('workshop')
  })

  it('fetches candidates with workshop filter', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [{ personnel_id: 'p1', name: '李四', roles: [] }] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const candidates = await fetchCandidates(
      ['maintenance_tech'],
      undefined,
      '201-1',
    )
    const url = lastUrl(fetchMock)
    expect(url.startsWith('/api/v1/equipment/personnel/candidates?')).toBe(true)
    expect(url).toContain('role_codes=maintenance_tech')
    expect(url).toContain('workshop=201-1')
    expect(candidates).toHaveLength(1)
  })

  it('surfaces a readable error when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Response('Internal Server Error', { status: 500 })),
    )
    await expect(fetchPersonnelList({ workshop: '101-2' })).rejects.toThrow(
      '请求失败: 500',
    )
  })
})
