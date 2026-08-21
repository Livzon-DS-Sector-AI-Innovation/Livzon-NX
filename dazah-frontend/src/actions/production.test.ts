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

import { BatchStatus, OperationType, ProcessSpecStatus } from '@/types/production'
import {
  getBatches,
  getBatch,
  createBatch,
  updateBatch,
  updateBatchStatus,
  deleteBatch,
  getBatchMaterials,
  addBatchMaterial,
  updateBatchMaterial,
  deleteBatchMaterial,
  getPlans,
  getPlan,
  createPlan,
  updatePlan,
  deletePlan,
  getProcessSpecs,
  getProcessSpec,
  createProcessSpec,
  updateProcessSpec,
  deleteProcessSpec,
  getProcessSteps,
  createProcessStep,
  updateProcessStep,
  deleteProcessStep,
  getProcessParameters,
  createProcessParameter,
  updateProcessParameter,
  deleteProcessParameter,
  getProductionRecords,
  createProductionRecord,
  updateProductionRecord,
  deleteProductionRecord,
  getMaterialBalance,
  calculateMaterialBalance,
  getFermentationRecords,
  getFermentationRecord,
  createFermentationRecord,
  updateFermentationRecord,
  updateFermentationStatus,
  deleteFermentationRecord,
} from './production'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

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

    await expect(getBatches({ page: 1, page_size: 20, status: BatchStatus.IN_PROGRESS })).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/batches?page=1&page_size=20&status=in_progress`,
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

    await expect(updateBatch('b-1', { notes: '完成' })).resolves.toMatchObject({ code: 200 })
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

    await expect(getProcessSpecs({ status: ProcessSpecStatus.EFFECTIVE })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/process-specs?status=effective`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates a process spec with revalidation', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'ps-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { spec_code: 'S-001', product_code: 'FA', spec_name: '无菌工艺', version: 'v1' }
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

    const payload = { spec_id: 'ps-1', step_no: 1, step_name: '消毒' }
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

    await expect(createProcessParameter({ step_id: 'st-1', param_name: '温度' })).resolves.toMatchObject({ code: 200 })
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

    await expect(createProductionRecord({ batch_id: 'b-1', record_no: 'R-001', operation_type: 'material_add' as OperationType })).resolves.toMatchObject({ code: 200 })
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

    const payload = { batch_no: 'B001', fermenter: 'F-1', entry_date: '2026-07-01' }
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

    await expect(updateFermentationRecord('fr-1', { status: 'running' })).resolves.toMatchObject({ code: 200 })
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

  // ── coverage: 补充尚未被断言的分支 ──
  it('fetches a single fermentation record', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'fr-1' } }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getFermentationRecord('fr-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation/fr-1`,
      expect.anything(),
    )
  })

  it('updates and deletes a batch material', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(updateBatchMaterial('m-1', { qty: 2 })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/materials/m-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    await expect(deleteBatchMaterial('m-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/materials/m-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('gets a single plan and updates/deletes it', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'p-1' } }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getPlan('p-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/api/v1/production/plans/p-1`, expect.anything())

    await expect(updatePlan('p-1', { product_name: '洛伐他汀' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/plans/p-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    await expect(deletePlan('p-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/plans/p-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/plan')
  })

  it('gets a single process spec and updates/deletes it', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'ps-1' } }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getProcessSpec('ps-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/api/v1/production/process-specs/ps-1`, expect.anything())

    await expect(updateProcessSpec('ps-1', { version: 'v2' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/process-specs/ps-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    await expect(deleteProcessSpec('ps-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/process-specs/ps-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/production/process')
  })

  it('fetches process steps and updates/deletes a step', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getProcessSteps('ps-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/api/v1/production/process-specs/ps-1/steps`, expect.anything())

    await expect(updateProcessStep('st-1', { step_name: '消毒' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/steps/st-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    await expect(deleteProcessStep('st-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/steps/st-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('fetches process parameters and updates/deletes a parameter', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getProcessParameters('st-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/api/v1/production/steps/st-1/parameters`, expect.anything())

    await expect(updateProcessParameter('prm-1', { param_name: '温度' })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/parameters/prm-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    await expect(deleteProcessParameter('prm-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/parameters/prm-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('updates and deletes a production record', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(updateProductionRecord('r-1', { actual_qty: 5 })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/records/r-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    await expect(deleteProductionRecord('r-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/records/r-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})