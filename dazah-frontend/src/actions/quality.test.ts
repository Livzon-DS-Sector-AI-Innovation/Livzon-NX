import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({ Authorization: 'Bearer test-token' }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import { approveCapa, createCapa, createDeviation, deleteDeviation, submitCapa } from './quality'

const API_BASE = 'http://localhost:8000'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('quality actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('creates a deviation', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'dv-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { title: '含量偏差', severity: 'major' }
    await createDeviation(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/deviations`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
  })

  it('deletes a deviation', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteDeviation('dv-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/deviations/dv-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('creates a capa and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'capa-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { title: '设备校准', capa_content: '更换传感器' }
    await createCapa(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/capas`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalled()
  })

  it('submits a capa', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await submitCapa('capa-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/quality/capas/capa-1/submit`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('approves a capa with payload', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { approved: true, comment: '同意' }
    await approveCapa('capa-1', payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/quality/capas/capa-1/'),
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
