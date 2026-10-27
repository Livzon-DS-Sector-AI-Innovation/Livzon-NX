import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: async () => ({ 'Content-Type': 'application/json' }) }))
vi.mock('@/lib/api/energy-ledger', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/api/energy-ledger')>(),
  ledgerRequest: vi.fn(),
}))

import { revalidatePath } from 'next/cache'
import { EnergyLedgerRequestError, ledgerRequest } from '@/lib/api/energy-ledger'
import * as actions from './energy-ledger'
const { previewLedgerImport } = actions

afterEach(() => vi.clearAllMocks())

describe('energy import server action', () => {
  it('sends the selected date boundaries as query parameters and preserves the file', async () => {
    vi.mocked(ledgerRequest).mockResolvedValue({ id: 'batch', status: 'preview', payload: {} })
    const data = new FormData()
    data.set('year', '2026'); data.set('start_date', '2026-06-27'); data.set('end_date', '2026-07-19')
    data.set('file', new Blob(['workbook']), 'energy.xlsx')
    expect((await previewLedgerImport(data)).ok).toBe(true)
    expect(ledgerRequest).toHaveBeenCalledWith('/imports/preview?year=2026&start_date=2026-06-27&end_date=2026-07-19', { method: 'POST', body: data }, { 'X-Dazah-Page-Path': '/energy/settings' })
    expect(data.get('file')).toBeInstanceOf(Blob)
    expect(data.has('start_date')).toBe(false)
  })
  it('returns a structured failure without losing the selected date boundaries', async () => {
    vi.mocked(ledgerRequest).mockRejectedValue(new Error('offline'))
    const data = new FormData(); data.set('year', '2026'); data.set('end_date', '2026-07-19')
    expect((await previewLedgerImport(data)).ok).toBe(false)
    expect(ledgerRequest).toHaveBeenCalledWith('/imports/preview?year=2026&end_date=2026-07-19', expect.anything(), { 'X-Dazah-Page-Path': '/energy/settings' })
  })
})

describe('energy mutation contracts', () => {
  const cases: { name: string; invoke: () => Promise<unknown>; path: string; method: string; payload: unknown }[] = [
    { name: 'bot configuration', invoke: () => actions.saveLedgerBot({ definition: { enabled: false, app_id: '', base_url: '' }, version: 2 }), path: '/bot-config', method: 'PUT', payload: { definition: { enabled: false, app_id: '', base_url: '' }, version: 2 } },
    { name: 'notification retry', invoke: () => actions.retryLedgerNotification('notice/1'), path: '/notification-runs/notice%2F1/retry', method: 'POST', payload: {} },
    { name: 'import confirmation', invoke: () => actions.confirmLedgerImport('batch/1', { mappings: [{ sheet: '电量', column: 2, point_id: 'meter-1' }], reason: '核对映射' }), path: '/imports/batch%2F1/confirm', method: 'POST', payload: { mappings: [{ sheet: '电量', column: 2, point_id: 'meter-1' }], reason: '核对映射' } },
    { name: 'template draft', invoke: () => actions.prepareLedgerImport('batch/1'), path: '/imports/batch%2F1/prepare', method: 'POST', payload: {} },
    { name: 'usage review', invoke: () => actions.saveUsageReviews({ reviews: [{ dataset: '冰水量', column: 14, periods: [] }], reason: '复核' }), path: '/usage-reviews', method: 'PUT', payload: { reviews: [{ dataset: '冰水量', column: 14, periods: [] }], reason: '复核' } },
  ]
  it.each(cases)('$name preserves its payload, authentication and invalidates the energy layout', async ({ invoke, path, method, payload }) => {
    vi.mocked(ledgerRequest).mockResolvedValue({ id: 'saved' })
    expect(await invoke()).toEqual({ ok: true, data: { id: 'saved' } })
    expect(ledgerRequest).toHaveBeenCalledWith(path, { method, body: JSON.stringify(payload) }, { 'Content-Type': 'application/json', ...(path.startsWith('/imports/') || path.startsWith('/usage-reviews') ? { 'X-Dazah-Page-Path': '/energy/settings' } : {}) })
    expect(revalidatePath).toHaveBeenCalledWith('/energy', 'layout')
  })
  it.each([new EnergyLedgerRequestError('版本已变化，请刷新'), new Error('internal connection detail')])('keeps public failures and hides internal failures without invalidating data', async error => {
    vi.mocked(ledgerRequest).mockRejectedValue(error)
    const result = await actions.saveDirectReadings({ dataset: '电量', reading_date: '2026-10-20', draft: false, reason: '', values: [{ point_id: 'p1', value: '0', version: 0 }] })
    expect(result).toEqual({ ok: false, message: error instanceof EnergyLedgerRequestError ? error.message : '请求未完成，请稍后重试；本次输入已保留' })
    expect(revalidatePath).not.toHaveBeenCalled()
  })
})
