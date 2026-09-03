/* @vitest-environment happy-dom */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildAuthHeaders,
  fetchFeishuValidationDashboardStatsServer,
} from './quality'

describe('buildAuthHeaders（serverFetch 鉴权头）', () => {
  it('wraps token as Bearer header', () => {
    expect(buildAuthHeaders('token-abc')).toEqual({
      Authorization: 'Bearer token-abc',
    })
  })

  it('returns undefined without token so requests stay anonymous', () => {
    expect(buildAuthHeaders(undefined)).toBeUndefined()
    expect(buildAuthHeaders(null)).toBeUndefined()
    expect(buildAuthHeaders('')).toBeUndefined()
  })
})

describe('quality serverFetch behaviour', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('unwraps the API envelope data for the dashboard stats', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 200,
          message: 'success',
          data: {
            total: 258,
            typeDistribution: [],
            statusDistribution: [],
            executionDistribution: [],
            revalidationUpcoming: 0,
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const stats = await fetchFeishuValidationDashboardStatsServer()
    expect(stats.total).toBe(258)
    // 请求结构：鉴权头由 getAuthHeadersForServer → buildAuthHeaders 提供
    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers['Content-Type']).toBe('application/json')
  })

  it('throws on 401 so pages surface the failure instead of empty data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('denied', { status: 401 })),
    )
    await expect(fetchFeishuValidationDashboardStatsServer()).rejects.toThrow(
      '请求失败: 401',
    )
  })
})
