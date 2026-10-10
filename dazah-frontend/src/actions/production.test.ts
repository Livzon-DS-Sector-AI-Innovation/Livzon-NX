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
  uploadScheduleExcel,
  getScheduleExcelArchives,
  getScheduleExcelArchive,
  deleteScheduleExcelArchive,
  getFermentationBoard,
  markTankMaintenance,
  removeTankMaintenance,
  getScheduleValidation,
  getScheduleConstraints,
  saveScheduleConstraints,
  generateScheduleDraft,
  exportScheduleDraft,
  getScheduleDraftRecords,
  getScheduleDraftRecord,
  deleteScheduleDraftRecord,
  downloadScheduleDraftRecordFile,
  getFermentationBatchActuals,
  upsertFermentationBatchActual,
  deleteFermentationBatchActual,
  setFermentationMonthCapacity,
  getPlanMonthlySummary,
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
    await expect(updateBatchMaterial('m-1', { material_name: '葡萄糖' })).resolves.toMatchObject({ code: 200 })
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
    await expect(updateProductionRecord('r-1', { remarks: '完成' })).resolves.toMatchObject({ code: 200 })
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

  it('uploads a schedule excel archive with multipart body and no JSON content type', async () => {
    const fetchMock = vi.fn(
      (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse({ code: 200, data: { id: 'arc-1' } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const formData = new FormData()
    formData.append('file', new Blob(['excel'], { type: 'application/vnd.ms-excel' }), 'plan.xlsx')

    await expect(uploadScheduleExcel(formData)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-excel?product=FA`,
      expect.objectContaining({ method: 'POST', body: formData }),
    )
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer test-token')
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('lists schedule excel archives with pagination params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getScheduleExcelArchives(2, 20)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-excel?page=2&page_size=20&product=FA`,
      expect.anything(),
    )

    await expect(getScheduleExcelArchives()).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenLastCalledWith(
      `${API_BASE}/api/v1/production/schedule-excel?page=1&page_size=50&product=FA`,
      expect.anything(),
    )
  })

  it('fetches a schedule excel archive by id', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'arc-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getScheduleExcelArchive('arc-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-excel/arc-1`,
      expect.anything(),
    )
  })

  it('deletes a schedule excel archive', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteScheduleExcelArchive('arc-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-excel/arc-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('gets the schedule validation report for an archive', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { issues: [] } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getScheduleValidation('arc-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-excel/arc-1/validation`,
      expect.anything(),
    )
  })

  it('gets the schedule constraints by product', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: { product_code: 'FA' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getScheduleConstraints('FA')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-constraints?product=FA`,
      expect.anything(),
    )
  })

  it('saves schedule constraints with a JSON body', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: { product_code: 'FA' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      saveScheduleConstraints(
        {
          product_code: 'FA',
          standard_cycle_hours: 61,
          cycle_tolerance_hours: 4,
          max_cycle_hours: 72,
          turnaround_hours: 8,
          monthly_dump_target: 26,
        },
        'FA',
      ),
    ).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-constraints?product=FA`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          standard_cycle_hours: 61,
          cycle_tolerance_hours: 4,
          max_cycle_hours: 72,
          turnaround_hours: 8,
          monthly_dump_target: 26,
        }),
      }),
    )
  })

  it('generates a schedule draft with instruction params', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: { days: [], summary: {}, validation: {} } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      generateScheduleDraft({
        period_start: '2026-11-27',
        period_end: '2026-12-26',
        skip_dates: ['2026-12-05'],
        tank_blocks: [
          { tank_no: '302A', from_date: '2026-12-01', to_date: '2026-12-05' },
        ],
      }),
    ).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-drafts/generate`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          period_start: '2026-11-27',
          period_end: '2026-12-26',
          batch_start_no: null,
          skip_dates: ['2026-12-05'],
          tank_blocks: [
            { tank_no: '302A', from_date: '2026-12-01', to_date: '2026-12-05' },
          ],
        }),
      }),
    )
  })

  it('exports the schedule draft excel as bytes with filename', async () => {
    const fetchMock = vi.fn(
      () =>
        new Response(new Uint8Array([1, 2, 3]), {
          status: 200,
          headers: {
            'content-type':
              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'content-disposition':
              "attachment; filename*=utf-8''FA%E6%8E%92%E4%BA%A7%E8%8D%89%E7%A8%BF.xlsx",
          },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const file = await exportScheduleDraft({})
    expect(file.filename).toBe('FA排产草稿.xlsx')
    expect(file.bytes.byteLength).toBe(3)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-drafts/export`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('falls back to the default filename without a starred disposition', async () => {
    const fetchMock = vi.fn(
      () => new Response(new Uint8Array([9]), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const file = await exportScheduleDraft({})
    expect(file.filename).toBe('FA排产草稿.xlsx')
    expect(file.bytes.byteLength).toBe(1)
  })

  it('throws the backend message when the draft export fails', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ message: '排产约束缺失' }, 500),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(exportScheduleDraft({})).rejects.toThrow('排产约束缺失')
  })

  it('keeps the default export hint for non-JSON failures', async () => {
    const fetchMock = vi.fn(
      () => new Response('Internal Server Error', { status: 502 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(exportScheduleDraft({})).rejects.toThrow('导出失败')
  })

  it('lists and fetches schedule draft records', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getScheduleDraftRecords(2, 5)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-drafts/records?page=2&page_size=5`,
      expect.anything(),
    )
    await expect(getScheduleDraftRecord('rec-9')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-drafts/records/rec-9`,
      expect.anything(),
    )
  })

  it('deletes a schedule draft record via DELETE', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteScheduleDraftRecord('rec-9')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/schedule-drafts/records/rec-9`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('returns null when the record file was never exported', async () => {
    const fetchMock = vi.fn(() => new Response(null, { status: 404 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(downloadScheduleDraftRecordFile('rec-9')).resolves.toBeNull()
  })

  it('throws for a failed record file download', async () => {
    const fetchMock = vi.fn(() => new Response(null, { status: 500 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(downloadScheduleDraftRecordFile('rec-9')).rejects.toThrow(
      '下载草稿文件失败',
    )
  })

  it('downloads a record file parsing the starred filename', async () => {
    const fetchMock = vi.fn(
      () =>
        new Response(new Uint8Array([4, 5]), {
          status: 200,
          headers: {
            'content-disposition':
              "attachment; filename*=utf-8''FA%E6%8E%92%E4%BA%A7%E8%8D%89%E7%A8%BF.xlsx",
          },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const file = await downloadScheduleDraftRecordFile('rec-9')
    expect(file?.filename).toBe('FA排产草稿.xlsx')
    expect(file?.bytes.byteLength).toBe(2)
  })

  it('marks tank maintenance with an optional recovery date', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(markTankMaintenance('302A', '染菌检查', '2026-10-13')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/tank-maintenance`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          tank_no: '302A',
          reason: '染菌检查',
          expected_recovery_date: '2026-10-13',
        }),
      }),
    )
  })

  it('fetches the fermentation board without caching', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { tanks: [] } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getFermentationBoard()).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation-board?product=FA`,
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('marks and removes tank maintenance', async () => {
    const fetchMock = vi.fn(
      (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse({ code: 200, data: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(markTankMaintenance('F-1', '搅拌桨检修')).resolves.toMatchObject({ code: 200 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE}/api/v1/production/tank-maintenance`)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual({ tank_no: 'F-1', reason: '搅拌桨检修', expected_recovery_date: null })
    expect(((init?.headers ?? {}) as Record<string, string>)['Content-Type']).toBe('application/json')

    await expect(removeTankMaintenance('m-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenLastCalledWith(
      `${API_BASE}/api/v1/production/tank-maintenance/m-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('lists fermentation batch actuals with auth header', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [{ id: 'a-1', batch_no: 'FA26231' }] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const res = await getFermentationBatchActuals()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation-batch-actuals?product=FA`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
    expect(res.data?.[0]?.batch_no).toBe('FA26231')
  })

  it('upserts a fermentation batch actual with normalized payload', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'a-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const res = await upsertFermentationBatchActual({
      batch_no: 'FA26230',
      dump_date: '2026-09-07',
      yield_kg: 30500,
      remark: null,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation-batch-actuals?product=FA`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          batch_no: 'FA26230',
          dump_date: '2026-09-07',
          yield_kg: 30500,
          remark: null,
        }),
      }),
    )
    expect(res.code).toBe(200)
  })

  it('deletes a fermentation batch actual by id', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteFermentationBatchActual('a-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation-batch-actuals/a-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('sets the fermentation month planned capacity', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(setFermentationMonthCapacity(930000)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/fermentation-month-capacity?product=FA`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ planned_capacity_kg: 930000 }),
      }),
    )
  })

  it('fetches the plan monthly summary for a month', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getPlanMonthlySummary('2026-09')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/plans/monthly-summary?month=2026-09`,
      expect.anything(),
    )
  })
})