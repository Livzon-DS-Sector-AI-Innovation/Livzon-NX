import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'server-token' }),
  }),
  headers: vi.fn(async () => new Headers({ 'X-Dazah-Page-Path': '/admin/tobacco-gift' })),
}))

import { fetchTobaccoGiftDashboardStats } from './administration'

const stats = {
  item_categories: 35,
  item_total_value: 152547,
  item_total_count: 515,
  requisitioned_total: 16,
  inventory_by_item: [],
  requisition_by_item: [],
  value_by_item: [],
  requisition_by_employee: [],
  inventory_synced_at: null,
  requisition_synced_at: null,
}

describe('fetchTobaccoGiftDashboardStats', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns stats with the dashboard page context header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 200, message: 'success', data: stats }), {
        status: 200,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchTobaccoGiftDashboardStats('admin:tobacco-gift:dashboard')

    expect(result.item_categories).toBe(35)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/administration\/tobacco-gift\/dashboard-stats$/)
    expect(init.headers['X-Dazah-Page-Key']).toBe('admin:tobacco-gift:dashboard')
    expect(init.headers.Authorization).toBe('Bearer server-token')
    expect(init.cache).toBe('no-store')
  })

  it('throws backend message on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: 403, message: '当前页面不能调用此业务接口' }), {
          status: 403,
        }),
      ),
    )
    await expect(fetchTobaccoGiftDashboardStats('admin:tobacco-gift:dashboard')).rejects.toThrow(
      '当前页面不能调用此业务接口',
    )
  })

  it('falls back to status text when body is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 500 })))
    await expect(fetchTobaccoGiftDashboardStats('admin:tobacco-gift:dashboard')).rejects.toThrow(
      '读取烟酒礼品统计失败（500）',
    )
  })
})
