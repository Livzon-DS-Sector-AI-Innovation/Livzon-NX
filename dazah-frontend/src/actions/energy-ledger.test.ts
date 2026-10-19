import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: async () => ({ 'Content-Type': 'application/json' }) }))
vi.mock('@/lib/api/energy-ledger', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/api/energy-ledger')>(),
  ledgerRequest: vi.fn(),
}))

import { revalidatePath } from 'next/cache'
import { EnergyLedgerRequestError, ledgerRequest, type MeterWrite, type RuleWrite, type PlanWrite } from '@/lib/api/energy-ledger'
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
    expect(ledgerRequest).toHaveBeenCalledWith('/imports/preview?year=2026&start_date=2026-06-27&end_date=2026-07-19', { method: 'POST', body: data }, {})
    expect(data.get('file')).toBeInstanceOf(Blob)
    expect(data.has('start_date')).toBe(false)
  })
  it('returns a structured failure without losing the selected date boundaries', async () => {
    vi.mocked(ledgerRequest).mockRejectedValue(new Error('offline'))
    const data = new FormData(); data.set('year', '2026'); data.set('end_date', '2026-07-19')
    expect((await previewLedgerImport(data)).ok).toBe(false)
    expect(ledgerRequest).toHaveBeenCalledWith('/imports/preview?year=2026&end_date=2026-07-19', expect.anything(), {})
  })
})

describe('energy mutation contracts', () => {
  const meter: MeterWrite = { definition: { code: 'water', name: '水表', category: 'drinking_water', area: '101', department: '101车间', unit: 'm3', active_from: '2026-07-01', enabled: false, frequency: 'daily', multiplier: '1', notes: '', precision: 3, quantity_kind: 'volume', reading_type: 'counter', report_scope: 'source', source_sheet: '', temperature: '', workshop: '' }, version: 3, reason: '校准' }
  const rule: RuleWrite = { definition: { code: 'total', name: '用水合计', category: 'drinking_water', unit: 'm3', department: '101车间', terms: [{ metric_key: 'point:water', coefficient: '1' }], active_from: '2026-07-01', enabled: false, frequency: 'daily', notes: '', operation: 'sum', quantity_kind: 'volume', report_scope: 'detail', source_sheet: '', temperature: '', workshop: '' }, reason: '', version: 0 }
  const plan: PlanWrite = { definition: { name: '水表组', point_ids: ['water'], owner_ids: ['owner'], deadline_time: '10:00', enabled: true, group_chat_id: '', publish_time: '08:00', reminder_time: '10:30' }, reason: '', version: 0 }
  const cases: { name: string; invoke: () => Promise<unknown>; path: string; method: string; payload: unknown }[] = [
    { name: 'new meter', invoke: () => actions.saveLedgerMeter(null, meter), path: '/meter-points', method: 'POST', payload: meter },
    { name: 'versioned meter update', invoke: () => actions.saveLedgerMeter('water/1', meter), path: '/meter-points/water%2F1', method: 'PUT', payload: meter },
    { name: 'new rule', invoke: () => actions.saveLedgerRule(null, rule), path: '/calculation-rules', method: 'POST', payload: rule },
    { name: 'rule update', invoke: () => actions.saveLedgerRule('rule/1', rule), path: '/calculation-rules/rule%2F1', method: 'PUT', payload: rule },
    { name: 'new plan', invoke: () => actions.saveLedgerPlan(null, plan), path: '/entry-plans', method: 'POST', payload: plan },
    { name: 'plan update', invoke: () => actions.saveLedgerPlan('plan/1', plan), path: '/entry-plans/plan%2F1', method: 'PUT', payload: plan },
    { name: 'draft submission', invoke: () => actions.submitLedgerTask('task/1', { values: [], draft: true, reason: '', source: 'platform' }), path: '/entry-tasks/task%2F1/submit', method: 'POST', payload: { values: [], draft: true, reason: '', source: 'platform' } },
    { name: 'task generation', invoke: () => actions.generateLedgerTasks('2026-07-02'), path: '/entry-tasks/generate', method: 'POST', payload: { task_date: '2026-07-02' } },
    { name: 'period locking', invoke: () => actions.saveLedgerLock('2026-07', { locked: true, reason: '月末核对', version: 2 }), path: '/period-locks/2026-07', method: 'PUT', payload: { locked: true, reason: '月末核对', version: 2 } },
    { name: 'bot configuration', invoke: () => actions.saveLedgerBot({ definition: { enabled: false, app_id: '', base_url: '' }, version: 2 }), path: '/bot-config', method: 'PUT', payload: { definition: { enabled: false, app_id: '', base_url: '' }, version: 2 } },
    { name: 'notification retry', invoke: () => actions.retryLedgerNotification('notice/1'), path: '/notification-runs/notice%2F1/retry', method: 'POST', payload: {} },
    { name: 'import confirmation', invoke: () => actions.confirmLedgerImport('batch/1', { mappings: [{ sheet: '电量', column: 2, point_id: 'meter-1' }], reason: '核对映射' }), path: '/imports/batch%2F1/confirm', method: 'POST', payload: { mappings: [{ sheet: '电量', column: 2, point_id: 'meter-1' }], reason: '核对映射' } },
    { name: 'template draft', invoke: () => actions.createLedgerTemplateDraft('batch/1'), path: '/imports/batch%2F1/draft-config', method: 'POST', payload: {} },
    { name: 'snapshot preview', invoke: () => actions.previewLedgerSnapshots({ snapshot_ids: ['s1'], year: 2026 }), path: '/imports/from-snapshot', method: 'POST', payload: { snapshot_ids: ['s1'], year: 2026 } },
    { name: 'audited adjustment', invoke: () => actions.adjustLedgerUsage({ metric_key: 'point:water', usage_date: '2026-07-01', mode: 'delta', value: '0.1', reason: '核对修正' }), path: '/adjustments', method: 'POST', payload: { metric_key: 'point:water', usage_date: '2026-07-01', mode: 'delta', value: '0.1', reason: '核对修正' } },
    { name: 'report rebuild', invoke: () => actions.rebuildLedgerReports('2026-07-01', '2026-07-31'), path: '/reporting/rebuild', method: 'POST', payload: { start_date: '2026-07-01', end_date: '2026-07-31' } },
    { name: 'nonpersisting trial', invoke: () => actions.trialLedgerRules('2026-07-01'), path: '/calculation-rules/trial', method: 'POST', payload: { usage_date: '2026-07-01' } },
  ]
  it.each(cases)('$name preserves its payload, authentication and invalidates the energy layout', async ({ invoke, path, method, payload }) => {
    vi.mocked(ledgerRequest).mockResolvedValue({ id: 'saved' })
    expect(await invoke()).toEqual({ ok: true, data: { id: 'saved' } })
    expect(ledgerRequest).toHaveBeenCalledWith(path, { method, body: JSON.stringify(payload) }, { 'Content-Type': 'application/json' })
    expect(revalidatePath).toHaveBeenCalledWith('/energy', 'layout')
  })
  it.each([new EnergyLedgerRequestError('版本已变化，请刷新'), new Error('internal connection detail')])('keeps public failures and hides internal failures without invalidating data', async error => {
    vi.mocked(ledgerRequest).mockRejectedValue(error)
    const result = await actions.saveLedgerMeter('m1', meter)
    expect(result).toEqual({ ok: false, message: error instanceof EnergyLedgerRequestError ? error.message : '请求未完成，请稍后重试；本次输入已保留' })
    expect(revalidatePath).not.toHaveBeenCalled()
  })
})
