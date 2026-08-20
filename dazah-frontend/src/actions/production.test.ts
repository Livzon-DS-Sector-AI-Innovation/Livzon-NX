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
  getBatches,
  getBatch,
  createBatch,
  updateBatch,
  updateBatchStatus,
  deleteBatch,
  getBatchMaterials,
  addBatchMaterial,
  getPlans,
  createPlan,
  getProcessSpecs,
  createProcessSpec,
  createProcessStep,
  createProcessParameter,
  getProductionRecords,
  createProductionRecord,
  getMaterialBalance,
  calculateMaterialBalance,
  getFermentationRecords,
  createFermentationRecord,
  updateFermentationRecord,
  updateFermentationStatus,
  deleteFermentationRecord,
} from './production'

const API_BASE = 'http://localhost:8000'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('production actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists batches with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(getBatches({ page: 1, page_size: 20, status: 'running' })).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches?page=1&page_size=20&status=running`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('fetches a single batch by id', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'b-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getBatch('b-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches/b-1`,
      expect.anything(),
    )
  })

  it('creates a batch and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'b-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { batch_no: 'B001', product_code: 'FA' }
    await expect(createBatch(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/batches')
  })

  it('updates a batch and its status', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'b-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateBatch('b-1', { status: 'completed' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches/b-1`,
      expect.objectContaining({ method: 'PUT' }),
    )

    await expect(updateBatchStatus('b-1', 'completed')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches/b-1/status`,
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ status: 'completed' }) }),
    )
  })

  it('deletes a batch', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteBatch('b-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches/b-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/batches')
  })

  it('lists batch materials and adds one', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getBatchMaterials('b-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches/b-1/materials`,
      expect.anything(),
    )

    const payload = { material_code: 'M01', batch_no: 'B001' }
    await expect(addBatchMaterial('b-1', payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches/b-1/materials`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/batches/b-1')
  })

  it('lists plans with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getPlans({ page: 1 })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/plans?page=1`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates a plan with revalidation', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'p-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { product_name: '洛伐他汀', workshop: 'WS-1' }
    await expect(createPlan(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/plans`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/plan')
  })

  it('lists process specs with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getProcessSpecs({ status: 'active' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/process-specs?status=active`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates a process spec with revalidation', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'ps-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { spec_name: '无菌工艺', version: 'v1' }
    await expect(createProcessSpec(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/process-specs`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/process')
  })

  it('creates a process step and revalidates its spec', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'st-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { spec_id: 'ps-1', step_name: '消毒' }
    await expect(createProcessStep(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/steps`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/process/ps-1')
  })

  it('creates a process parameter and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'prm-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(createProcessParameter({ step_id: 'st-1', param_key: 'temp' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/parameters`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/process')
  })

  it('lists production records for a batch', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getProductionRecords('b-1', 1, 50)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches/b-1/records?page=1&page_size=50`,
      expect.anything(),
    )
  })

  it('creates a production record and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'r-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(createProductionRecord({ batch_id: 'b-1', stage: 'seed' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/records`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/records')
  })

  it('gets material balance and calculates it', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: {} }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getMaterialBalance('b-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches/b-1/balance`,
      expect.anything(),
    )

    await expect(calculateMaterialBalance('b-1', 96.0)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches/b-1/balance/calculate?min_balance_rate=96`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/balance')
  })

  it('lists fermentation records with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getFermentationRecords({ fermenter: 'F-1' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation?fermenter=F-1`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates a fermentation record and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'fr-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { batch_no: 'B001', fermenter: 'F-1', temp: 30 }
    await expect(createFermentationRecord(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/fermentation')
  })

  it('updates a fermentation record and its status', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'fr-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateFermentationRecord('fr-1', { temp: 32 })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation/fr-1`,
      expect.objectContaining({ method: 'PUT' }),
    )

    await expect(updateFermentationStatus('fr-1', 'running')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation/fr-1/status`,
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ status: 'running' }) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/fermentation')
  })

  it('deletes a fermentation record', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteFermentationRecord('fr-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation/fr-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/fermentation')
  })
})