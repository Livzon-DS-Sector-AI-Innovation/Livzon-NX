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
  createExtractionRecord,
  createRefinementRecord,
  createBlendingRecord,
  getExtractionRecords,
  updateExtractionRecord,
  getRefinementRecords,
  getBlendingRecords,
} from './stages'

const API = process.env.API_BASE_URL || 'http://localhost:8000'
const BASE = '/api/v1/production/mc'
const REVALIDATE = '/production/batches/workshop/201-2'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('mc stages actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists mc extraction records with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getExtractionRecords({ batch_no: 'MC-1' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-records?batch_no=MC-1`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates an extraction record and revalidates the 201-2 workshop path', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'er-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    const payload = { batch_no: 'MC-2', stage: 'extraction' }
    await expect(createExtractionRecord(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-records`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('creates a refinement record and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'rr-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    const payload = { batch_no: 'MC-1', stage: 'refinement' }
    await expect(createRefinementRecord(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/refinement-records`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('creates a blending record and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'bl-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    const payload = { batch_no: 'MC-1', stage: 'blending' }
    await expect(createBlendingRecord(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/blending-records`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('lists refinement and blending records with singletons', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getRefinementRecords({})).resolves.toMatchObject({ code: 200 })
    await expect(getBlendingRecords({})).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/refinement-records`, expect.anything())
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/blending-records`, expect.anything())
  })

  it('updates and deletes extraction records', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'er-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateExtractionRecord('er-1', { amount: 7 })).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-records/er-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
  })
})