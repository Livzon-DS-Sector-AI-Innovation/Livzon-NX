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
  deleteExtractionRecord,
  createExtractionInput,
  updateExtractionInput,
  deleteExtractionInput,
  getExtractionRecords,
  getExtractionInputs,
  createRefinementRecord,
  updateRefinementRecord,
  deleteRefinementRecord,
  getRefinementRecords,
  getRefinementInputs,
  createRefinementInput,
  updateRefinementInput,
  deleteRefinementInput,
  createBlendingRecord,
  updateBlendingRecord,
  deleteBlendingRecord,
  getBlendingRecords,
  getBlendingInputs,
  createBlendingInput,
  deleteBlendingInput,
  calculateBlendImpurities,
  getQcInspections,
  createQcInspection,
  updateQcInspection,
  getQcInspectionItems,
  createQcInspectionItem,
  updateExtractionRecord,
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

function expectAuth() {
  return expect.objectContaining({
    headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
  })
}

describe('mc stages actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    mocks.revalidatePath.mockClear()
  })

  it('lists mc extraction records with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getExtractionRecords({ batch_no: 'MC-1' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-records?batch_no=MC-1`,
      expectAuth(),
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

  it('updates and deletes extraction records', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'er-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateExtractionRecord('er-1', { amount: 7 })).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-records/er-1`,
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ amount: 7 }) }),
    )

    await expect(deleteExtractionRecord('er-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-records/er-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('manages extraction inputs', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getExtractionInputs('MC-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-records/MC-1/inputs`,
      expectAuth(),
    )

    await expect(createExtractionInput({ batch_no: 'MC-1' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-inputs`,
      expect.objectContaining({ method: 'POST' }),
    )

    await expect(updateExtractionInput('ei-1', { amount: 3 })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-inputs/ei-1`,
      expect.objectContaining({ method: 'PUT' }),
    )

    await expect(deleteExtractionInput('ei-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/extraction-inputs/ei-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
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

  it('updates and deletes refinement records and manages inputs', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'rr-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateRefinementRecord('rr-1', { amount: 2 })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/refinement-records/rr-1`,
      expect.objectContaining({ method: 'PUT' }),
    )

    await expect(deleteRefinementRecord('rr-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/refinement-records/rr-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )

    await expect(getRefinementInputs('MC-1')).resolves.toMatchObject({ code: 200 })
    await expect(createRefinementInput({ batch_no: 'MC-1' })).resolves.toMatchObject({ code: 200 })
    await expect(updateRefinementInput('ri-1', { amount: 1 })).resolves.toMatchObject({ code: 200 })
    await expect(deleteRefinementInput('ri-1')).resolves.toMatchObject({ code: 200 })

    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/refinement-records/MC-1/inputs`,
      expectAuth(),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/refinement-inputs`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/refinement-inputs/ri-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/refinement-inputs/ri-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('lists refinement and blending records with singletons', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getRefinementRecords({})).resolves.toMatchObject({ code: 200 })
    await expect(getBlendingRecords({})).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/refinement-records`, expect.anything())
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/blending-records`, expect.anything())
  })

  it('creates, updates, deletes blending records and manages inputs/impurities', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'bl-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(createBlendingRecord({ batch_no: 'MC-1' })).resolves.toMatchObject({ code: 200 })
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)

    await expect(updateBlendingRecord('bl-1', { amount: 4 })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/blending-records/bl-1`,
      expect.objectContaining({ method: 'PUT' }),
    )

    await expect(deleteBlendingRecord('bl-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/blending-records/bl-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )

    await expect(getBlendingInputs('MC-1')).resolves.toMatchObject({ code: 200 })
    await expect(createBlendingInput({ batch_no: 'MC-1' })).resolves.toMatchObject({ code: 200 })
    await expect(deleteBlendingInput('bi-1')).resolves.toMatchObject({ code: 200 })

    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/blending-records/MC-1/inputs`, expectAuth())
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/blending-inputs`, expect.objectContaining({ method: 'POST' }))
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/blending-inputs/bi-1`, expect.objectContaining({ method: 'DELETE' }))

    await expect(calculateBlendImpurities('MC-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/blending-records/MC-1/calculate`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('manages qc inspections and items', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'qc-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getQcInspections({ batch_no: 'MC-1' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/qc-inspections?batch_no=MC-1`, expectAuth())

    await expect(createQcInspection({ batch_no: 'MC-1' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/qc-inspections`, expect.objectContaining({ method: 'POST' }))

    await expect(updateQcInspection('qc-1', { status: 'passed' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/qc-inspections/qc-1`, expect.objectContaining({ method: 'PUT' }))

    await expect(getQcInspectionItems('qc-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API}${BASE}/qc-inspections/qc-1/items`, expectAuth())

    await expect(createQcInspectionItem({ qc_id: 'qc-1' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}${BASE}/qc-inspection-items`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ qc_id: 'qc-1' }) }),
    )
  })
})