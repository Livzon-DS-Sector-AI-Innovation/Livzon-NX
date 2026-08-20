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
  createFermentationRecord,
  deleteFermentationRecord,
  getFermentationRecord,
  getFermentationRecords,
  updateFermentationRecord,
  updateFermentationStatus,
} from './fermentation'

const API_BASE = 'http://localhost:8000'
const REVALIDATE = '/production/batches/workshop/103'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('fermentation actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists fermentation records with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      getFermentationRecords({ product_name: 'FA', batch_no: 'FA-001', status: 'running' }),
    ).resolves.toMatchObject({ code: 200 })

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation?product_name=FA&batch_no=FA-001&status=running`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('fetches a single fermentation record', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'rec-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getFermentationRecord('rec-1')).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation/rec-1`,
      expect.anything(),
    )
  })

  it('creates a fermentation record and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'rec-new' } }),)
    vi.stubGlobal('fetch', fetchMock)

    const payload = { batch_no: 'FA-002', product_name: 'FA', entry_date: '2026-07-01' }
    await expect(createFermentationRecord(payload)).resolves.toMatchObject({ code: 200 })

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('updates a fermentation record and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'rec-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateFermentationRecord('rec-1', { status: 'done' })).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation/rec-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('updates a fermentation status and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'rec-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateFermentationStatus('rec-1', 'done')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation/rec-1/status`,
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ status: 'done' }) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('deletes a fermentation record and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: null }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteFermentationRecord('rec-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation/rec-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })
})