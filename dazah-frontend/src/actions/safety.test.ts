import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({ Authorization: 'Bearer test-token' }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import { createCheck, fetchHazardStats, getChecks, getHazard, submitCheck } from './safety'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('safety actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists safety checks with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [], total: 0 } }))
    vi.stubGlobal('fetch', fetchMock)

    await getChecks({ page: 1, page_size: 20, status: 'pending' })
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/safety/checks?'),
      expect.anything(),
    )
  })

  it('creates a safety check', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'ck-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { check_type: '日常巡检', location: '102车间' }
    await createCheck(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/checks`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('submits a check', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await submitCheck('ck-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/checks/ck-1/submit`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('fetches hazard stats', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { total: 5 } }))
    vi.stubGlobal('fetch', fetchMock)

    const res = await fetchHazardStats()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/safety/hazards/stats'),
      expect.anything(),
    )
    expect(res).toMatchObject({ code: 200 })
  })

  it('fetches a single hazard', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'hz-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await getHazard('hz-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/safety/hazards/hz-1`,
      expect.anything(),
    )
  })
})
