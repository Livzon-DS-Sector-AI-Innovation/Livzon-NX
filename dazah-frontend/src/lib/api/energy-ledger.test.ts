import { afterEach, describe, expect, it, vi } from 'vitest'
import { estimateUsage, formatAmount, ledgerRequest, reportQuery, resolveLedgerAction, taskChanges, type Task } from './energy-ledger'

afterEach(() => vi.unstubAllGlobals())

const task: Task = {
  id: 'task-1', task_date: '2026-07-02', name: '水表组', owner_ids: [], deadline_time: '10:00', total_count: 2, completed_count: 0,
  items: [
    { id: 'reading-1', point_id: 'point-1', name: '水表', category: 'drinking_water', unit: 'm3', precision: 3, multiplier: '1', reading_type: 'counter', frequency: 'daily', reading_date: '2026-07-02', value: null, draft_value: '0', previous_value: '0', previous_date: '2026-07-01', version: 1, submitted_at: null },
    { id: 'reading-2', point_id: 'point-2', name: '电表', category: 'electricity', unit: 'kWh', precision: 3, multiplier: '1', reading_type: 'direct', frequency: 'daily', reading_date: '2026-07-01', value: null, draft_value: null, previous_value: '100', previous_date: '2026-06-30', version: 0, submitted_at: null },
  ],
}

describe('energy entry precision and draft submissions', () => {
  it('shows structured Server Action errors in production without relying on thrown server errors', async () => {
    await expect(resolveLedgerAction(Promise.resolve({ ok: false, message: '数据已被其他人修改，请刷新' }))).rejects.toThrow('数据已被其他人修改')
    expect(await resolveLedgerAction(Promise.resolve({ ok: true, data: 0 }))).toBe(0)
  })
  it('submits an existing zero draft and does not auto-copy previous values', () => {
    expect(taskChanges(task, {})).toEqual([{ reading_id: 'reading-1', version: 1, value: '0' }])
    expect(taskChanges(task, { 'reading-1': '', 'reading-2': '12.5' })).toEqual([{ reading_id: 'reading-2', version: 0, value: '12.5' }])
  })
  it('estimates counter differences exactly and preserves large values', () => {
    expect(estimateUsage('0.3', '0.1', '10', false)).toBe('2')
    expect(estimateUsage('9007199254740993.1', '9007199254740993', '1', false)).toBe('0.1')
    expect(estimateUsage('0', '0E-8', '1', false)).toBe('0')
    expect(estimateUsage('9', '10', '1', false)).toBeUndefined()
    expect(estimateUsage('12.5', null, '2', true)).toBe('25')
  })
  it('distinguishes missing from zero and keeps significant digits', () => {
    expect(formatAmount(null)).toBe('—')
    expect(formatAmount('0E-8')).toBe('0')
    expect(formatAmount('10.1000')).toBe('10.1')
    expect(formatAmount('100')).toBe('100')
  })
  it('serializes filters without dropping numeric zero', () => {
    expect(reportQuery({ start_date: '2026-07-01', workshop: '101车间', page: 0, category: undefined })).toBe('start_date=2026-07-01&workshop=101%E8%BD%A6%E9%97%B4&page=0')
  })
  it('returns useful authorization errors without swallowing them', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: '当前任务未分配给您' }), { status: 403 })))
    await expect(ledgerRequest('/entry-tasks/id')).rejects.toThrow('当前任务未分配给您')
  })
})
