import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({
    'Content-Type': 'application/json',
    Authorization: 'Bearer test-token',
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  createNCE,
  deleteNCE,
  getNCEs,
  updateNCE,
} from './nce'

const API_BASE = 'http://localhost:8000'
const REVALIDATE = '/production/shift-log/deviation'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('nce actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists non-conforming events with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      getNCEs({ workshop: 'WS-1', event_type: '偏差', date_from: '2026-07-01' }),
    ).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/non-conforming-events?workshop=WS-1&event_type=%E5%81%8F%E5%B7%AE&date_from=2026-07-01`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates an event and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'nce-new' } }),)
    vi.stubGlobal('fetch', fetchMock)

    const payload = { event_type: '偏差', description: '温度偏高', event_time: '2026-07-01T08:00', workshop: '201-2' }
    await expect(createNCE(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/non-conforming-events`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('updates an event and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'nce-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateNCE('nce-1', { remarks: '已处理' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/non-conforming-events/nce-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('deletes an event and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: null }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteNCE('nce-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/non-conforming-events/nce-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })
})