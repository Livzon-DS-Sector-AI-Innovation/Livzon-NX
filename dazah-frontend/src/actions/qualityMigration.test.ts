import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({ Authorization: 'Bearer quality-action-token' }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  addExecutionTrack,
  analyzeCapaAi,
  analyzeChangeAi,
  analyzeDeviationAi,
  approveCapa,
  closeOosOotRecord,
  confirmCapaImport,
  createCapa,
  createChange,
  createOosOotRecord,
  createOotLimitItem,
  createOotLimitProduct,
  deleteExecutionTrack,
  deleteOotLimitItem,
  deleteOotLimitProduct,
  pullOosLedgerRecords,
  pullOosOotReportRecords,
  pullOotLedgerRecords,
  regenerateDeviationAiSession,
  startOosOotInvestigation,
  submitCapa,
  submitEvaluation,
  syncOosOotRecordToFeishu,
  updateCapa,
  updateChange,
} from './quality'

function response(data: unknown = { ok: true }): Response {
  return new Response(JSON.stringify({ code: 200, message: 'ok', data }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('quality migration server-action contracts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('keeps CAPA, OOS/OOT, import and Feishu compatibility actions on one request path', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)

    await createCapa({ title: 'CAPA' } as never)
    await updateCapa('capa-1', { title: 'CAPA-2' } as never)
    await submitCapa('capa-1')
    await approveCapa('capa-1', { approved: true } as never)
    await addExecutionTrack('capa-1', { description: '执行' } as never)
    await deleteExecutionTrack('capa-1', 0)
    await submitEvaluation('capa-1', { result: 'effective' } as never)

    await createOosOotRecord({ title: 'OOS' } as never)
    await startOosOotInvestigation('oos-1')
    await closeOosOotRecord('oos-1', { conclusion: 'closed' } as never)
    await syncOosOotRecordToFeishu('oos-1')
    await createOotLimitProduct({ product_name: '产品A' } as never)
    await createOotLimitItem({ product_id: 'product-1', item_name: '含量' } as never)
    await deleteOotLimitItem('item-1')
    await deleteOotLimitProduct('product-1')
    await pullOosOotReportRecords()
    await pullOosLedgerRecords()
    await pullOotLedgerRecords()

    await confirmCapaImport(new FormData(), { skipDuplicates: true, updateExisting: false })
    await createChange({ title: '变更' } as never)
    await updateChange('change-1', { title: '变更2' } as never)

    await analyzeDeviationAi('deviation-1')
    await regenerateDeviationAiSession('deviation-1')
    await analyzeCapaAi('capa-1')
    await analyzeChangeAi('change-1')

    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/quality/capas/capa-1/add-execution-track'))).toBe(true)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/quality/capas/capa-1/delete-execution-track'))).toBe(true)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/quality/oos-oot'))).toBe(true)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/quality/changes'))).toBe(true)
    expect(fetchMock.mock.calls.every(([, init]) => {
      const headers = init?.headers as Record<string, string> | undefined
      return headers?.Authorization === 'Bearer quality-action-token'
    })).toBe(true)
  })
})
