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
  getPressureDashboard,
  getPointMappings,
  createPointMapping,
  updatePointMapping,
  deletePointMapping,
  getPressureRecords,
  getMergedPressureRecords,
  createManualRecord,
  submitOcrRecords,
  auditPressureRecord,
  batchAuditPressureRecords,
  deletePressureRecord,
  batchDeletePressureRecords,
} from './pressure'

const API_BASE = 'http://localhost:8000'
const REVALIDATE = '/production/pressure'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('pressure actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('gets the pressure dashboard', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: {} }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getPressureDashboard()).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/dashboard`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('lists point mappings with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getPointMappings({ area: '洁净区', page_size: 20 })).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/point-mappings?area=%E6%B4%81%E5%87%80%E5%8C%BA&page_size=20`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates a point mapping and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'pm-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    const payload = { point_id: 'P1', area: '洁净区', standard_pressure: 0.5 }
    await expect(createPointMapping(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/point-mappings`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('updates and deletes a point mapping', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'pm-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(updatePointMapping('pm-1', { standard_pressure: 0.6 })).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/point-mappings/pm-1`,
      expect.objectContaining({ method: 'PUT' }),
    )

    fetchMock.mockResolvedValueOnce(jsonResponse({ code: 200, message: 'success', data: null }))
    await expect(deletePointMapping('pm-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenLastCalledWith(
      `${API_BASE}/api/v1/production/pressure/point-mappings/pm-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledTimes(2)
  })

  it('lists pressure records and merged records', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getPressureRecords({ area: 'A' })).resolves.toMatchObject({ code: 200 })
    await expect(getMergedPressureRecords({ area: 'A' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/records?area=A`,
      expect.anything(),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/records/merged?area=A`,
      expect.anything(),
    )
  })

  it('creates OCR and manual records and audits them', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: {} }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(createManualRecord({ record_time: '2026-07-01T08:00', point_id: 'P1', pressure_value: 0.5 })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/records/manual`,
      expect.objectContaining({ method: 'POST' }),
    )

    await expect(submitOcrRecords({} as any)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenLastCalledWith(
      `${API_BASE}/api/v1/production/pressure/records/ocr`,
      expect.objectContaining({ method: 'POST' }),
    )

    await expect(auditPressureRecord('p-1', { status: 'approved' })).resolves.toMatchObject({ code: 200 })
    await expect(batchAuditPressureRecords({ ids: ['p-1'], status: 'approved' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/records/p-1/audit`,
      expect.objectContaining({ method: 'PATCH' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/records/batch-audit`,
      expect.objectContaining({ method: 'PATCH' }),
    )
  })

  it('deletes pressure records singly and in batch', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: {} }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(deletePressureRecord('p-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/pressure/records/p-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )

    await expect(batchDeletePressureRecords(['p-1', 'p-2'])).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenLastCalledWith(
      `${API_BASE}/api/v1/production/pressure/records/batch-delete`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ ids: ['p-1', 'p-2'] }) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })
})