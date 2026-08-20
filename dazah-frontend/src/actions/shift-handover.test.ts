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
  confirmShiftHandover,
  createShiftHandover,
  deleteShiftHandover,
  getDistinctPositions,
  getShiftHandovers,
  updateShiftHandover,
} from './shift-handover'

const API_BASE = 'http://localhost:8000'
const REVALIDATE = '/production/shift-log/handover'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('shift-handover actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists shift handovers with query params', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, message: 'success', data: [] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getShiftHandovers({ position: '洁净区', workshop: 'WS-1' })).resolves.toMatchObject(
      { code: 200 },
    )
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/shift-handovers?position=%E6%B4%81%E5%87%80%E5%8C%BA&workshop=WS-1`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates a shift handover and revalidates', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, message: 'success', data: { id: 'sh-new' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const payload = { position: '洁净区', workshop: 'WS-1', shift: '早班', handover_time: '2026-07-01T08:00', handover_from: '张三', handover_to: '李四' }
    await expect(createShiftHandover(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/shift-handovers`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('updates a shift handover and revalidates', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, message: 'success', data: { id: 'sh-1' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateShiftHandover('sh-1', { remarks: 'ok' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/shift-handovers/sh-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('confirms a shift handover and revalidates', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, message: 'success', data: { id: 'sh-1' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(confirmShiftHandover('sh-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/shift-handovers/sh-1/confirm`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('fetches distinct positions', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, message: 'success', data: ['洁净区', '生产区'] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getDistinctPositions()).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/shift-handovers/positions`,
      expect.anything(),
    )
  })

  it('deletes a shift handover and revalidates', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, message: 'success', data: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteShiftHandover('sh-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/shift-handovers/sh-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })
})