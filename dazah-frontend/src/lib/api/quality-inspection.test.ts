import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchInspectionTrend } from './quality-inspection'

describe('quality inspection API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('serializes inspection trend filters without dropping the resource code', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ points: [], alerts: [], summary: {} }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchInspectionTrend({ resource_code: 'MVT', subject: '成品', limit: 10 })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/inspection-trends?resource_code=MVT&subject=%E6%88%90%E5%93%81&limit=10',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })
})
